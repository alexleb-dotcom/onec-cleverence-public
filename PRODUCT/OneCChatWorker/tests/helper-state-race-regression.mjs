import assert from 'node:assert/strict';
import fsp from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createSerializedMessagePump,persistAndSendProcessed,saveStateAtomic} from '../runtime/helper-state-coordinator.mjs';

const scratch=process.argv[2];
if(!scratch)throw new Error('SCRATCH_ROOT_REQUIRED');
await fsp.rm(scratch,{recursive:true,force:true});
await fsp.mkdir(scratch,{recursive:true});
const statePath=path.join(scratch,'hosted-helper-state.json');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let passed=0;
const ok=async(name,fn)=>{await fn();passed++;console.log('PASS '+name);};
const result=id=>({type:'result',request_id:id,status:'OK',metadata:{op:'read'},payload:{id}});

await ok('OVERLAPPING_REQUESTS_SERIALIZED_NO_CRASH',async()=>{
  const state={schema_version:2,processed:{},idempotency:{},quality_targets:[]};
  await saveStateAtomic(statePath,state);
  let active=0,maxActive=0;
  const sent=[];
  const delayedFs={
    writeFile:async(...a)=>{await fsp.writeFile(...a);await sleep(12);},
    rename:(...a)=>fsp.rename(...a)
  };
  const pump=createSerializedMessagePump({
    handle:async m=>{
      active++;maxActive=Math.max(maxActive,active);
      await sleep(m.pre);
      await persistAndSendProcessed({
        state,requestId:m.id,result:result(m.id),
        persist:s=>saveStateAtomic(statePath,s,{fsApi:delayedFs}),
        send:async out=>{sent.push(out.request_id);}
      });
      active--;
    },
    onFailure:async()=>{}
  });
  const calls=[
    pump.dispatch({id:'mcp-a',pre:8}),
    pump.dispatch({id:'mcp-b',pre:1}),
    pump.dispatch({id:'mcp-c',pre:4}),
    pump.dispatch({id:'mcp-d',pre:0})
  ];
  await Promise.all(calls);await pump.drain();
  assert.equal(pump.failed(),false);
  assert.equal(maxActive,1);
  assert.deepEqual(sent,['mcp-a','mcp-b','mcp-c','mcp-d']);
});

await ok('FINAL_STATE_HAS_EVERY_COMMITTED_REQUEST_ONCE',async()=>{
  const doc=JSON.parse(await fsp.readFile(statePath,'utf8'));
  assert.deepEqual(Object.keys(doc.processed),['mcp-a','mcp-b','mcp-c','mcp-d']);
  for(const id of Object.keys(doc.processed))assert.equal(doc.processed[id].request_id,id);
});

await ok('PROCESSED_REQUEST_REPLAY_STORED_RESULT',async()=>{
  const state=JSON.parse(await fsp.readFile(statePath,'utf8'));
  let persistCalls=0;const sent=[];
  const r=await persistAndSendProcessed({
    state,requestId:'mcp-b',result:{...result('mcp-b'),payload:{id:'SHOULD_NOT_REPLACE'}},
    persist:async()=>{persistCalls++;},
    send:async out=>sent.push(out)
  });
  assert.equal(r.replayed,true);assert.equal(persistCalls,0);
  assert.equal(sent.length,1);assert.equal(sent[0].payload.id,'mcp-b');
  assert.equal(Object.keys(state.processed).length,4);
});

await ok('PERSIST_FAILURE_FINAL_VALID_TMP_RECOVERABLE',async()=>{
  const state=JSON.parse(await fsp.readFile(statePath,'utf8'));
  const before=JSON.parse(JSON.stringify(state));
  const failingFs={
    writeFile:(...a)=>fsp.writeFile(...a),
    rename:async()=>{const e=new Error('injected rename failure');e.code='EPERM';throw e;}
  };
  let sent=false,error=null;
  try{
    await persistAndSendProcessed({
      state,requestId:'mcp-e',result:result('mcp-e'),
      persist:s=>saveStateAtomic(statePath,s,{fsApi:failingFs}),
      send:async()=>{sent=true;}
    });
  }catch(e){error=e;}
  assert.equal(error?.code,'HELPER_STATE_PERSIST_FAILED');
  assert.equal(error?.cause_code,'EPERM');
  assert.equal(sent,false);
  assert.equal(state.processed['mcp-e'],undefined);
  const finalDoc=JSON.parse(await fsp.readFile(statePath,'utf8'));
  const tmpDoc=JSON.parse(await fsp.readFile(statePath+'.tmp','utf8'));
  assert.deepEqual(finalDoc,before);
  assert.equal(tmpDoc.processed['mcp-e'].request_id,'mcp-e');
  assert.equal(Object.keys(tmpDoc.processed).length,Object.keys(finalDoc.processed).length+1);
});

await ok('PERSIST_FAILURE_CLASSIFIED_QUEUE_CONTAINED',async()=>{
  const seen=[],failures=[];
  const pump=createSerializedMessagePump({
    handle:async m=>{seen.push(m.id);if(m.id==='bad'){const e=new Error('persist');e.code='HELPER_STATE_PERSIST_FAILED';throw e;}},
    onFailure:async(e,m)=>failures.push({code:e.code,id:m.id})
  });
  const a=pump.dispatch({id:'bad'}),b=pump.dispatch({id:'queued-after-failure'});
  await Promise.all([a,b]);await pump.drain();
  assert.equal(pump.failed(),true);
  assert.deepEqual(seen,['bad']);
  assert.deepEqual(failures,[{code:'HELPER_STATE_PERSIST_FAILED',id:'bad'}]);
});

await ok('NEW_CONNECTION_PUMP_RECOVERS_AFTER_FAILURE',async()=>{
  const seen=[];
  const pump=createSerializedMessagePump({handle:async m=>seen.push(m.id),onFailure:async()=>{}});
  await pump.dispatch({id:'after-reconnect'});await pump.drain();
  assert.deepEqual(seen,['after-reconnect']);assert.equal(pump.failed(),false);
});

await ok('HELPER_WIRES_SERIALIZED_MESSAGE_PUMP',async()=>{
  const here=path.dirname(fileURLToPath(import.meta.url));
  const helper=await fsp.readFile(path.join(here,'../runtime/hosted-helper.mjs'),'utf8');
  for(const token of ['createSerializedMessagePump','persistAndSendProcessed','saveStateAtomic','MESSAGE_HANDLER_ERROR','HELPER_STATE_PERSISTENCE_FATAL'])assert(helper.includes(token),token);
  assert(!helper.includes("ws.addEventListener('message',async ev=>"));
});

await ok('ORDINARY_CLOSE_ERROR_RECONNECT_LOOP_PRESERVED',async()=>{
  const here=path.dirname(fileURLToPath(import.meta.url));
  const helper=await fsp.readFile(path.join(here,'../runtime/hosted-helper.mjs'),'utf8');
  assert(helper.includes("ws.addEventListener('close'"));
  assert(helper.includes("ws.addEventListener('error'"));
  assert(helper.includes('while(Date.now()<Date.parse(state.expires_utc))'));
  assert(helper.includes('await sleep(1000)'));
});

console.log('HELPER_STATE_RACE_REGRESSION_PASS checks='+passed);
