import assert from 'node:assert/strict';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';
import * as accounting from '../relay/src/s4-accounting.js';
import {startBoundedResponseRetries} from '../relay/src/ws-response-retry.mjs';
import {createSerializedMessagePump,persistAndSendProcessed} from '../runtime/helper-state-coordinator.mjs';

// Execute the production class and helper handler without OAuth, network, a
// provider process or Source. Only Cloudflare host facilities are simulated.
const relayCode=fs.readFileSync(new URL('../relay/src/index.js',import.meta.url),'utf8');
const helperCode=fs.readFileSync(new URL('../runtime/hosted-helper.mjs',import.meta.url),'utf8');
const relayBody=relayCode.slice(relayCode.indexOf('const ORIGIN='),relayCode.indexOf('\nfunction mcpError(')).replace('export class RelaySession','class RelaySession');
// Retain coverage of the legacy WebSocket lane. S4 Pull is exercised separately
// through native workerd; this harness deliberately selects the old lane.
const helperBody=helperCode.slice(helperCode.indexOf('const advisoryPump='),helperCode.indexOf('\nlet fatalHelperError=')).replace('  if(IS_S4){','  if(false){');
const NOW=Date.parse('2026-10-08T11:00:00Z');
class ClockDate extends Date {constructor(...args){super(...(args.length?args:[NOW]));}static now(){return NOW;}}
const hello={
  type:'hello',admission_schema_version:3,task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),
  project_id:'P',task_id:'T',task_goal_sha256:'c'.repeat(64),manifest_sha256:'d'.repeat(64),
  snapshot_id:'s'.repeat(64),output_task_root:'Output/T',helper_version:'test',
  task_created_utc:'2026-10-08T10:00:00Z',task_expires_utc:'2026-10-08T22:00:00Z',
  caps:{task_request_limit:96,task_result_byte_limit:108000,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000}
};
const key='task:'+hello.task_admission_id;
const clone=v=>v===undefined?undefined:structuredClone(v);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
// Crypto digests use the native host thread pool. Bound the host phase wait by
// time, not a rapid setImmediate spin count; transport deadlines stay virtual.
async function until(test){const deadline=Date.now()+5000;while(Date.now()<deadline){if(test())return;await new Promise(r=>setTimeout(r,1));}assert.fail('deterministic phase did not arrive');}
class Socket {
  readyState=1;frames=[];closed=[];attachment=null;onSend=()=>{};
  send(raw){if(this.readyState!==1)throw Error('closed');this.frames.push(JSON.parse(raw));this.onSend(raw);}
  close(code,reason){this.closed.push([code,reason]);this.readyState=3;}
  serializeAttachment(a){this.attachment=clone(a);}
  deserializeAttachment(){return clone(this.attachment);}
  accept(){assert.fail('standard WebSocket API is forbidden');}
  addEventListener(){assert.fail('hibernation must use class callbacks');}
}
class HostResponse {
  constructor(body,init){if(init?.status===101)return {status:101,webSocket:init.webSocket};return new Response(body,init);}
  static json(...args){return Response.json(...args);}
}
function harness(){
  const h={sockets:[],jobs:[],puts:[],traces:[],reservations:0,executions:0,persists:0,errors:[],dropRequests:0,dropResults:0,dropPongs:false};
  h.data=new Map([['active_mode','s4'],['active_task_id',hello.task_admission_id],[key,accounting.createTaskRecord(hello,{nowMs:NOW,epochIdFactory:()=> 'epoch-1'})]]);
  h.storage={get:async k=>clone(h.data.get(k)),put:async(k,v)=>{if(h.beforePut)await h.beforePut(k,v);h.puts.push(k);h.data.set(k,clone(v));},delete:async k=>h.data.delete(k)};
  h.ctx={storage:h.storage,getWebSockets:tag=>{assert.equal(tag,'helper');return h.sockets;},acceptWebSocket:(s,tags)=>{assert.deepEqual(tags,['helper']);h.sockets.push(s);}};
  h.schedule=(fn,ms)=>{const j={fn,ms,cancelled:false};h.jobs.push(j);return j;};
  h.cancel=j=>{j.cancelled=true;};
  h.fire=ms=>{const j=h.jobs.find(j=>j.ms===ms&&!j.cancelled);assert(j,'missing timer '+ms);j.cancelled=true;j.fn();};
  const deps={...accounting,reserveRequest:(...a)=>{h.reservations++;return accounting.reserveRequest(...a);}};
  const Pair=function(){return {0:new Socket(),1:new Socket()};};
  h.Relay=new Function(...Object.keys(deps),'startBoundedResponseRetries','crypto','Date','setTimeout','clearTimeout','Response','WebSocketPair','console',relayBody+'\nreturn RelaySession;')(
    ...Object.values(deps),options=>startBoundedResponseRetries({...options,schedule:h.schedule,cancel:h.cancel}),webcrypto,ClockDate,h.schedule,h.cancel,HostResponse,Pair,{log:(label,line)=>h.traces.push(JSON.parse(line))}
  );
  h.relay=new h.Relay(h.ctx,{HELPER_SECRET:'test-secret-not-real'});
  h.record=()=>clone(h.data.get(key));
  h.helperState={processed:{}};h.disk={processed:{}};
  const helperDeps={state:h.helperState,caps:hello.caps,persistAndSendProcessed,createSerializedMessagePump,
    saveState:async state=>{await h.onPersist?.();h.persists++;h.disk=clone(state);},
    exec:async op=>{h.executions++;return {status:'OK',metadata:{op,elapsed_ms:1},payload:{content:'bounded fixture'}};},
    log:async entry=>{await h.onLog?.(entry);},saveUiProjection:async projection=>{await h.onProjection?.(projection);},
    TASK_ADMISSION_ID:hello.task_admission_id,STABLE_SESSION_ID:hello.session_id,IS_S4:true,
    PROJECT:hello.project_id,TASK:hello.task_id,SNAPSHOT:hello.snapshot_id,manifestHash:hello.manifest_sha256,
    TASK_CREATED_UTC:hello.task_created_utc,TASK_EXPIRES_UTC:hello.task_expires_utc,OUTPUT_TASK_ROOT:hello.output_task_root,
    VERSION:hello.helper_version,admission:hello,SECRET_PATH:'fixture',RELAY:'wss://fixture.invalid/helper',
    fsp:{readFile:async()=> 'fixture-secret-not-real'},Date:ClockDate,sleep:async()=>{},
    WebSocket:function(url){return h.makeClient(url);}
  };
  const helper=new Function(...Object.keys(helperDeps),helperBody+'\nreturn {handle:handleRelayMessage,drain:()=>advisoryPump.drain(),connectLoop};')(...Object.values(helperDeps));
  h.handle=helper.handle;
  h.connectLoop=helper.connectLoop;h.drainAdvisory=helper.drain;
  h.wire=s=>{
    const helperSocket={send:raw=>{
      const m=JSON.parse(raw);
      if(m.type==='transport_pong'&&h.dropPongs)return;
      if(m.type==='result'&&h.dropResults-->0)return;
      void h.relay.webSocketMessage(s,raw);
    }};
    const pump=createSerializedMessagePump({handle:ev=>h.handle(helperSocket,ev),onFailure:async e=>h.errors.push(e)});
    h.dispatch=ev=>pump.dispatch(ev);
    s.onSend=raw=>{
      const m=JSON.parse(raw);
      if(m.type==='request'&&h.dropRequests-->0)return;
      void pump.dispatch({data:raw});
    };
    h.drain=async()=>{await pump.drain();await helper.drain();};
  };
  h.accept=async()=>{
    const response=await h.relay.acceptHelper(new Request('https://relay.invalid/helper?token=test-secret-not-real',{headers:{Upgrade:'websocket'}}));
    assert.equal(response.status,101);
    const s=h.relay.helper;h.wire(s);return s;
  };
  h.connect=async()=>{const s=await h.accept();await h.relay.webSocketMessage(s,JSON.stringify(hello));return s;};
  h.rpc=(op='read',args={path:'fixture.bsl',start:1,end:2})=>h.relay.rpc(new Request('https://relay.invalid/rpc',{method:'POST',body:JSON.stringify({op,args})}));
  h.noTimers=()=>assert(h.jobs.every(j=>j.cancelled),'all transport timers must be cancelled');
  return h;
}
let passed=0;
async function ok(name,test){await test();passed++;console.log('PASS '+name);}

await ok('CONTEXT_THEN_READ_WHILE_ADVISORY_IO_IS_DELAYED',async()=>{
  for(const lane of ['result-log','ui-projection']){
    const h=harness(),s=await h.connect();await h.drain();
    let release,blocked=false;
    const barrier=new Promise(resolve=>{release=resolve;});
    if(lane==='result-log')h.onLog=async entry=>{if(entry.event==='RESULT'){blocked=true;await barrier;}};
    else h.onProjection=async()=>{blocked=true;await barrier;};
    try{
      assert.equal((await h.rpc('context',{})).status,200);
      await until(()=>blocked);
      const before=h.record(),next=h.rpc();
      for(let i=0;i<10;i++)await tick();
      // Advance exactly the existing probe deadline if advisory I/O blocked it.
      // The healthy socket and helper remain connected throughout the stall.
      if(h.relay.probe)h.fire(2500);
      const response=await next;
      assert.equal(response.status,200,lane+' must not prevent application readiness');
      assert.equal(h.record().task_requests_used,before.task_requests_used+1);
      assert.equal(h.reservations,2);assert.equal(h.executions,2);
      assert.equal(h.relay.helper,s);h.noTimers();
    }finally{release();await h.drain();}
  }
});
await ok('LISTENERS_PRECEDE_HELLO_AND_DELAYED_CONNECTED_LOG',async()=>{
  const h=harness(),frames=[],listeners=new Map();let release,blocked=false;
  const barrier=new Promise(resolve=>{release=resolve;});
  h.helperState.expires_utc=hello.task_expires_utc;
  h.onLog=async entry=>{if(entry.event==='CONNECTED'){blocked=true;await barrier;}};
  const emit=(name,event)=>{for(const fn of listeners.get(name)||[])fn(event);};
  h.makeClient=()=>{
    const ws={
      addEventListener:(name,fn)=>{listeners.set(name,[...(listeners.get(name)||[]),fn]);},
      send:raw=>{
        const m=JSON.parse(raw);frames.push(m);
        if(m.type==='hello')queueMicrotask(()=>{
          emit('message',{data:JSON.stringify({type:'hello_ack'})});
          emit('message',{data:JSON.stringify({type:'transport_ping',nonce:'12345678-1234-4234-8234-123456789abc'})});
          emit('message',{data:JSON.stringify({type:'request',request_id:'startup-fixture',op:'read'})});
        });
        if(m.type==='result')queueMicrotask(()=>{
          h.helperState.expires_utc='2000-01-01T00:00:00Z';emit('close',{});
        });
      },close:()=>emit('close',{})
    };
    queueMicrotask(()=>emit('open',{}));return ws;
  };
  const loop=h.connectLoop();
  try{
    await until(()=>frames.some(m=>m.type==='result'));
    await loop;await until(()=>blocked);
    assert.equal(frames.filter(m=>m.type==='transport_pong').length,1);
    assert.equal(h.executions,1);assert.equal(h.persists,1);
    assert(h.disk.processed['startup-fixture']);
  }finally{release();await h.drainAdvisory();}
});
await ok('PROBE_WAITS_FOR_AUTHORITATIVE_PERSISTENCE',async()=>{
  const h=harness(),s=await h.connect();await h.drain();let release,blocked=false;
  const barrier=new Promise(resolve=>{release=resolve;});
  h.onPersist=async()=>{blocked=true;await barrier;};
  const request=h.rpc();await until(()=>blocked);
  const probe=h.dispatch({data:JSON.stringify({type:'transport_ping',nonce:'12345678-1234-4234-8234-123456789abc'})});
  // Only the RPC preflight ping has completed. The second challenge is queued
  // behind authoritative persistence, not allowed to claim readiness early.
  for(let i=0;i<5;i++)await tick();
  assert.equal(h.persists,0);assert.equal(s.frames.filter(m=>m.type==='request').length,1);
  let settled=false;void probe.then(()=>{settled=true;});await tick();assert.equal(settled,false);
  release();assert.equal((await request).status,200);await probe;await h.drain();
  assert.equal(h.persists,1);assert.equal(h.reservations,1);h.noTimers();
});
await ok('DELAYED_PONG_BEFORE_DEADLINE_PASSES_ONCE',async()=>{
  const h=harness(),s=await h.connect();h.dropPongs=true;
  const p=h.rpc();await until(()=>h.relay.probe);
  await h.relay.webSocketMessage(s,JSON.stringify({type:'transport_pong',nonce:h.relay.probe.nonce}));
  assert.equal((await p).status,200);assert.equal(h.reservations,1);h.noTimers();
});
await ok('EXPIRED_PROBE_LATE_PONG_AND_RECONNECT_PRESERVE_CACHE',async()=>{
  const h=harness(),s=await h.connect();assert.equal((await h.rpc()).status,200);await h.drain();
  const before=h.record(),cache=clone(h.disk);h.dropPongs=true;
  const p=h.rpc();await until(()=>h.relay.probe);
  const late=JSON.stringify({type:'transport_pong',nonce:h.relay.probe.nonce});
  assert.equal((await h.relay.acceptHelper(new Request('https://relay.invalid/helper?token=test-secret-not-real',{headers:{Upgrade:'websocket'}}))).status,409);
  await h.relay.webSocketMessage(s,JSON.stringify(hello));assert.deepEqual(h.record(),before);
  h.fire(2500);assert.equal((await p).status,503);
  const expired=h.traces.find(t=>t.event==='probe_expired');assert(expired?.request_key);
  assert(h.traces.some(t=>t.event==='probe_started'&&t.request_key===expired.request_key));
  assert(!h.traces.some(t=>t.event==='rpc_dispatch'&&t.request_key===expired.request_key));
  await h.relay.webSocketMessage(s,late);assert.deepEqual(h.record(),before);
  assert.equal(s.deserializeAttachment().ready,false);assert.deepEqual(h.disk,cache);
  h.dropPongs=false;const next=await h.connect();
  await h.relay.webSocketMessage(s,late);assert.equal(h.relay.helper,next);
  assert.equal((await h.rpc()).status,200);assert.equal(h.reservations,2);
  assert.equal(h.record().task_requests_used,before.task_requests_used+1);
  for(const [id,result] of Object.entries(cache.processed))assert.deepEqual(h.disk.processed[id],result);
  h.noTimers();
});
await ok('FAILED_CLOSE_CANNOT_RESTORE_STALE_READY_ATTACHMENT',async()=>{
  const h=harness(),s=await h.connect();h.dropPongs=true;s.close=()=>{throw Error('close failed');};
  const before=h.record(),p=h.rpc();await until(()=>h.relay.probe);h.fire(2500);
  assert.equal((await p).status,503);assert.equal(s.readyState,1);assert.equal(s.deserializeAttachment().ready,false);
  h.relay=new h.Relay(h.ctx,{HELPER_SECRET:'test-secret-not-real'});
  assert.equal(h.relay.helperReady,false);assert.equal((await h.rpc()).status,503);
  assert.deepEqual(h.record(),before);assert.equal(h.reservations,0);
  h.dropPongs=false;await h.connect();assert.equal((await h.rpc()).status,200);
  assert.equal(h.reservations,1);h.noTimers();
});
await ok('ADVISORY_ORDER_SURVIVES_RECONNECT_AND_WRITE_REJECTION',async()=>{
  const h=harness();let active=0,maxActive=0,release,blocked=false;const seen=[];
  const barrier=new Promise(resolve=>{release=resolve;});
  h.onProjection=async p=>{
    active++;maxActive=Math.max(maxActive,active);seen.push(p.activity.request_count);
    try{if(seen.length===1){blocked=true;await barrier;throw Error('projection rejected');}}finally{active--;}
  };
  await h.connect();await until(()=>blocked);
  assert.equal((await h.rpc()).status,200);await h.connect();assert.equal((await h.rpc()).status,200);
  release();await h.drain();
  assert.equal(maxActive,1);assert.deepEqual(seen,[0,2]);
  assert.equal(h.errors.length,0);assert.equal(h.executions,2);assert.equal(h.reservations,2);
  h.noTimers();
});
await ok('ADVISORY_BACKLOG_IS_BOUNDED_AND_LATEST_PROJECTION_RETAINED',async()=>{
  const h=harness();await h.connect();await h.drain();let release,blocked=false,logs=0;const projections=[];
  const barrier=new Promise(resolve=>{release=resolve;});
  h.onLog=async e=>{if(e.event==='RESULT'){logs++;blocked=true;await barrier;}};
  h.onProjection=async p=>projections.push(p.activity.request_count);
  try{
    for(let i=0;i<70;i++)assert.equal((await h.rpc()).status,200);
    await until(()=>blocked);assert.equal(h.reservations,70);assert.equal(h.persists,70);
    release();await h.drain();assert.equal(logs,64);assert.deepEqual(projections,[70]);
    assert.equal(h.record().task_requests_used,70);assert.equal(h.errors.length,0);h.noTimers();
  }finally{release();await h.drain();}
});

await ok('HIBERNATION_RESTORES_TRANSPORT_WITHOUT_HELLO_OR_S4_RECONCILIATION',async()=>{
  const h=harness(),s=await h.connect();
  for(let i=0;i<4;i++){
    const before=h.record(),writes=h.puts.length;
    h.relay=new h.Relay(h.ctx,{HELPER_SECRET:'test-secret-not-real'});
    assert.equal(h.relay.helper,s);assert.equal(h.relay.helperReady,true);
    assert.equal(h.puts.length,writes);assert.deepEqual(h.record(),before);
    const r=await h.rpc();assert.equal(r.status,200);
    assert.equal(h.record().task_requests_used,i+1);
  }
  assert.equal(h.executions,4);assert.equal(h.reservations,4);
  assert.equal(h.record().activity_committed_seq,4);
  assert.equal(h.record().session_id,hello.session_id);
  assert.equal(h.record().task_expires_utc,hello.task_expires_utc);
  h.noTimers();
});
await ok('NO_HELLO_MISSING_PONG_HALF_OPEN_OR_CLOSED_ZERO_S4_USAGE',async()=>{
  for(const mode of ['no-hello','half-open','closed','missing-pong']){
    const h=harness(),s=mode==='no-hello'?await h.accept():await h.connect();
    if(mode==='closed')s.readyState=3;
    if(mode==='half-open')s.onSend=()=>{};
    if(mode==='missing-pong')h.dropPongs=true;
    const before=h.record(),writes=h.puts.length,p=h.rpc();
    if(['half-open','missing-pong'].includes(mode)){await until(()=>h.relay.probe);h.fire(2500);}
    assert.equal((await p).status,503);
    assert.deepEqual(h.record(),before);assert.equal(h.puts.length,writes);
    assert.equal(h.reservations,0);assert.equal(h.executions,0);h.noTimers();
  }
});
await ok('STALE_NONCE_GENERATION_WRONG_SOCKET_CANNOT_PASS_LIVENESS',async()=>{
  const h=harness(),s=await h.connect();h.dropPongs=true;
  const p=h.rpc();await until(()=>h.relay.probe);
  const {nonce,generation}=h.relay.probe;
  const raw=JSON.stringify({type:'transport_pong',nonce});
  await h.relay.onHelperMessage(raw,generation-1,s);
  const old=new Socket();old.serializeAttachment({generation});
  await h.relay.webSocketMessage(old,raw);
  await h.relay.webSocketMessage(s,JSON.stringify({type:'transport_pong',nonce:'old-nonce'}));
  assert.equal(h.reservations,0);assert(h.relay.probe);
  h.fire(2500);assert.equal((await p).status,503);h.noTimers();
  const next=await h.connect();h.dropPongs=true;
  const q=h.rpc();await until(()=>h.relay.probe);
  await h.relay.webSocketMessage(next,raw);assert(h.relay.probe);
  h.fire(2500);assert.equal((await q).status,503);assert.equal(h.reservations,0);h.noTimers();
});
await ok('PROBE_SEND_FAILURE_AND_CLOSE_CANCEL_TIMERS_BEFORE_RESERVE',async()=>{
  for(const error of [true,false]){
    const h=harness(),s=await h.connect();h.dropPongs=true;
    if(error)s.onSend=()=>{throw Error('injected send failure');};
    const p=h.rpc();if(!error){await until(()=>h.relay.probe);h.relay.webSocketClose(s,1000,'fixture');}
    assert.equal((await p).status,503);assert.equal(h.reservations,0);h.noTimers();
  }
});
await ok('MISSING_REQUEST_OR_RESULT_RETRIES_EXECUTE_AND_CHARGE_ONCE',async()=>{
  for(const loss of ['request','result']){
    const h=harness(),s=await h.connect();
    if(loss==='request')h.dropRequests=1;else h.dropResults=1;
    const p=h.rpc();await until(()=>s.frames.some(m=>m.type==='request'));await h.drain();
    h.fire(2500);const response=await p;assert.equal(response.status,200);
    assert.equal(h.executions,1);assert.equal(h.persists,1);assert.equal(h.reservations,1);
    const frames=s.frames.filter(m=>m.type==='request');assert.equal(frames.length,2);assert.deepEqual(frames[0],frames[1]);
    assert(h.disk.processed[frames[0].request_id]);
    assert.equal(h.record().task_requests_used,1);assert.equal(h.record().activity_committed_seq,1);h.noTimers();
  }
});
await ok('WRONG_SOCKET_GENERATION_REQUEST_ID_AND_LATE_RESULT_IGNORED',async()=>{
  const h=harness(),s=await h.connect();h.dropResults=10;
  const p=h.rpc();await until(()=>h.relay.pending.size===1);await h.drain();
  const [requestId,pending]=[...h.relay.pending][0];
  const raw=JSON.stringify(h.disk.processed[requestId]);
  const old=new Socket();old.serializeAttachment({generation:pending.generation});
  await h.relay.webSocketMessage(old,raw);
  await h.relay.onHelperMessage(raw,pending.generation-1,s);
  await h.relay.webSocketMessage(s,JSON.stringify({type:'result',request_id:'wrong',payload:{}}));
  assert.equal(h.relay.pending.size,1);h.fire(15000);
  assert.equal((await p).status,504);const charged=h.record();
  assert.equal(charged.task_requests_used,1);assert.equal(charged.task_result_bytes_used,3000);
  await h.relay.webSocketMessage(s,raw);assert.deepEqual(h.record(),charged);h.noTimers();
});
await ok('NO_REPLACEMENT_DUPLICATE_HELLO_OR_CONCURRENT_RPC_WHILE_RESERVED',async()=>{
  const h=harness(),s=await h.connect();h.dropResults=10;
  const p=h.rpc();await until(()=>h.relay.pending.size===1);
  const before=h.record();
  assert.equal((await h.rpc()).status,429);
  const reconnect=await h.relay.acceptHelper(new Request('https://relay.invalid/helper?token=test-secret-not-real',{headers:{Upgrade:'websocket'}}));
  assert.equal(reconnect.status,409);assert.equal(h.relay.helper,s);assert.equal(s.closed.length,0);
  await h.relay.webSocketMessage(s,JSON.stringify(hello));assert.deepEqual(h.record(),before);
  h.fire(15000);assert.equal((await p).status,504);assert.equal(h.reservations,1);h.noTimers();
});
await ok('LANE_REMAINS_OWNED_THROUGH_RESULT_ACCOUNTING_COMMIT',async()=>{
  const h=harness(),s=await h.connect();let release,blocked=false;
  const barrier=new Promise(resolve=>{release=resolve;});
  h.beforePut=async(k,r)=>{if(k===key&&r.activity_committed_seq===1){blocked=true;await barrier;}};
  const p=h.rpc();await until(()=>blocked);
  assert.equal(h.relay.pending.size,0);assert.equal(h.relay.busy,true);
  assert.equal((await h.rpc()).status,429);
  assert.equal((await h.relay.acceptHelper(new Request('https://relay.invalid/helper?token=test-secret-not-real',{headers:{Upgrade:'websocket'}}))).status,409);
  await h.relay.webSocketMessage(s,JSON.stringify(hello));
  assert.equal(h.record().task_result_bytes_used,0);
  release();assert.equal((await p).status,200);assert.equal(h.record().task_requests_used,1);h.noTimers();
});
await ok('POST_RESERVE_SEND_FAILURE_CLOSE_ERROR_CHARGED_ONCE_AND_CANCELLED',async()=>{
  for(const mode of ['send','close','error']){
    const h=harness(),s=await h.connect();
    if(mode==='send'){const send=s.onSend;s.onSend=raw=>{if(JSON.parse(raw).type==='request')throw Error('send');send(raw);};}
    else h.dropResults=10;
    const p=h.rpc();if(mode!=='send'){
      await until(()=>h.relay.pending.size===1);await h.drain();
      if(mode==='close')h.relay.webSocketClose(s,1000,'fixture');else h.relay.webSocketError(s);
    }
    assert.equal((await p).status,504);assert.equal(h.record().task_requests_used,1);
    assert.equal(h.record().task_result_bytes_used,3000);assert.equal(h.record().activity_committed_seq,1);
    assert.equal(h.reservations,1);assert.equal(h.relay.busy,false);h.noTimers();
    const before=h.record();await h.connect();assert.equal(h.record().task_requests_used,before.task_requests_used);
    assert.equal(h.record().task_result_bytes_used,before.task_result_bytes_used);assert.equal(h.record().activity_committed_seq,1);
  }
});
await ok('RECONNECT_AND_OLD_CLOSE_PRESERVE_ACCOUNTING_AND_PROCESSED_CACHE',async()=>{
  const h=harness(),old=await h.connect();assert.equal((await h.rpc()).status,200);
  const before=h.record(),cache=clone(h.disk);
  const s=await h.connect();assert.notEqual(s,old);
  h.relay.webSocketClose(old,1000,'old');assert.equal(h.relay.helper,s);
  assert.equal(h.record().task_requests_used,before.task_requests_used);
  assert.equal(h.record().task_expires_utc,before.task_expires_utc);
  assert.equal(h.record().session_id,before.session_id);assert.deepEqual(h.disk,cache);
  const requestId=Object.keys(cache.processed)[0];
  await h.handle({send:raw=>assert.deepEqual(JSON.parse(raw),cache.processed[requestId])},{data:JSON.stringify({type:'request',request_id:requestId,op:'read'})});
  assert.equal(h.executions,1);assert.equal(h.persists,1);h.noTimers();
});
await ok('HELPER_PROBE_DOES_NOT_EXECUTE_PERSIST_OR_RENEW_ANY_STATE',async()=>{
  const h=harness(),before=clone(h.helperState),sent=[];
  await h.handle({send:raw=>sent.push(JSON.parse(raw))},{data:JSON.stringify({type:'transport_ping',nonce:'12345678-1234-4234-8234-123456789abc'})});
  assert.deepEqual(sent,[{type:'transport_pong',nonce:'12345678-1234-4234-8234-123456789abc'}]);
  assert.equal(h.executions,0);assert.equal(h.persists,0);assert.deepEqual(h.helperState,before);
  for(const nonce of [null,1,{},'oversized'.repeat(100)])await h.handle({send:()=>assert.fail('invalid probe')},{data:JSON.stringify({type:'transport_ping',nonce})});
});
await ok('COLD_RESTART_ORPHAN_STILL_RECOVERS_FAIL_CLOSED',async()=>{
  const h=harness();let r=h.record();accounting.reserveRequest(r,{requestId:'orphan',fingerprint:'fp',op:'read',nowMs:NOW});h.data.set(key,r);
  const before=h.record();h.relay=new h.Relay(h.ctx,{HELPER_SECRET:'test-secret-not-real'});
  assert.deepEqual(h.record(),before);assert.equal((await h.rpc()).status,503);
  await h.connect();r=h.record();assert.equal(r.task_requests_used,1);assert.equal(r.task_result_bytes_used,3000);
  assert.equal(r.request_receipts.orphan.state,'AMBIGUOUS_CHARGED');assert.equal(r.activity_committed_seq,1);h.noTimers();
});
await ok('UNSETTLED_DURABLE_RESERVATION_BLOCKS_SECOND_RESERVE_AFTER_FAILURE',async()=>{
  const h=harness();await h.connect();
  h.beforePut=async(k,r)=>{if(k===key&&r.activity_committed_seq===1)throw Error('injected storage failure');};
  assert.equal((await h.rpc()).status,503);
  assert.equal(h.relay.busy,false);assert.equal(h.relay.pending.size,0);
  const before=h.record();assert(Object.values(before.request_receipts).some(r=>r.state==='RESERVED'));
  h.relay=new h.Relay(h.ctx,{HELPER_SECRET:'test-secret-not-real'});
  assert.equal((await h.rpc()).status,409);assert.deepEqual(h.record(),before);assert.equal(h.reservations,1);
  h.beforePut=null;await h.connect();assert.equal(h.record().task_requests_used,1);
  assert.equal(h.record().task_result_bytes_used,3000);assert.equal(h.record().activity_committed_seq,1);h.noTimers();
});
console.log('RELAY_HELPER_LIFECYCLE_REGRESSION_PASS checks='+passed);
