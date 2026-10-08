import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {startBoundedResponseRetries,WS_RESPONSE_RETRY_DELAYS_MS} from '../relay/src/ws-response-retry.mjs';
import {createTaskRecord,reserveRequest,commitRequest} from '../relay/src/s4-accounting.js';

const here=path.dirname(fileURLToPath(import.meta.url));
const relay=fs.readFileSync(path.join(here,'../relay/src/index.js'),'utf8');
const helper=fs.readFileSync(path.join(here,'../runtime/hosted-helper.mjs'),'utf8');
let count=0;
function ok(name,fn){fn();count++;console.log('PASS '+name);}
function fakeScheduler(){
  const jobs=[];
  return {
    jobs,schedule:(fn,ms)=>{const job={fn,ms,cancelled:false};jobs.push(job);return job;},
    cancel:job=>{job.cancelled=true;},
    fire:ms=>{const job=jobs.find(x=>x.ms===ms);assert(job);if(!job.cancelled)job.fn();}
  };
}
const id='mcp-'+'a'.repeat(64);
const payload=JSON.stringify({type:'request',request_id:id,op:'read',args:{start:1,end:20}});
const socket={readyState:1};

ok('DROP_FIRST_RESULT_THEN_REPLAY_CACHED_SAME_REQUEST_ID',()=>{
  const s=fakeScheduler(),observed=[],cache=new Map();
  let executeCount=0,pending=true,delivered=false;
  const send=(_,frame)=>{
    const req=JSON.parse(frame);
    assert.equal(req.request_id,id);
    if(!cache.has(id)){executeCount++;cache.set(id,{type:'result',request_id:id,status:'OK',payload:{value:'saved'}});}
    if(executeCount===1&&!delivered){ // Simulate first result frame lost on the return path.
      if(observed.length===0){observed.push('FIRST_RESULT_DROPPED');return;}
    }
    delivered=true;pending=false;
    observed.push(cache.get(id));
  };
  const stop=startBoundedResponseRetries({
    requestId:id,frame:payload,dispatchedSocket:socket,generation:1,
    isPending:()=>pending,currentSocket:()=>socket,currentGeneration:()=>1,
    onResend:send,schedule:s.schedule,cancel:s.cancel
  });
  send(socket,payload);
  assert.equal(executeCount,1);assert.equal(delivered,false);
  s.fire(2500);
  assert.equal(delivered,true);
  assert.equal(executeCount,1);
  assert.equal(observed.at(-1).request_id,id);
  stop();
  assert(s.jobs.every(job=>job.cancelled));
});

ok('NO_RETRY_AFTER_RESPONSE_MATCHED_OR_DEADLINE',()=>{
  const s=fakeScheduler();let pending=false,attempts=0;
  const stop=startBoundedResponseRetries({
    requestId:id,frame:payload,dispatchedSocket:socket,generation:1,
    isPending:()=>pending,currentSocket:()=>socket,currentGeneration:()=>1,
    onResend:()=>attempts++,schedule:s.schedule,cancel:s.cancel
  });
  s.fire(2500);assert.equal(attempts,0);
  pending=true;stop();s.fire(6500);assert.equal(attempts,0);
});

ok('NO_RETRY_TO_REPLACED_OR_CLOSED_SOCKET',()=>{
  const s=fakeScheduler();let attempts=0,generation=2;
  startBoundedResponseRetries({
    requestId:id,frame:payload,dispatchedSocket:socket,generation:1,
    isPending:()=>true,currentSocket:()=>socket,currentGeneration:()=>generation,
    onResend:()=>attempts++,schedule:s.schedule,cancel:s.cancel
  });
  s.fire(2500);assert.equal(attempts,0);
  generation=1;socket.readyState=3;s.fire(6500);assert.equal(attempts,0);
  socket.readyState=1;
});

ok('SEND_FAILURE_CONTAINED_NO_WIDENED_BUDGET',()=>{
  const s=fakeScheduler();const phases=[];
  startBoundedResponseRetries({
    requestId:id,frame:payload,dispatchedSocket:socket,generation:1,
    isPending:()=>true,currentSocket:()=>socket,currentGeneration:()=>1,
    onResend:()=>{throw new Error('disconnect');},
    onRetry:(ms,status)=>phases.push([ms,status]),
    schedule:s.schedule,cancel:s.cancel
  });
  s.fire(2500);
  assert.deepEqual(phases,[[2500,'SEND_FAILED']]);
  assert(WS_RESPONSE_RETRY_DELAYS_MS.every(ms=>ms>0&&ms<15000));
  assert.equal(WS_RESPONSE_RETRY_DELAYS_MS.length,3);
});

ok('S4_RESERVATION_AND_CHARGE_STAY_ONE_PER_CALL',()=>{
  const h={
    admission_schema_version:3,task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),
    project_id:'P',task_id:'T',task_goal_sha256:'c'.repeat(64),
    manifest_sha256:'d'.repeat(64),snapshot_id:'s'.repeat(64),
    output_task_root:'Output/T',
    task_created_utc:'2026-10-06T10:00:00Z',task_expires_utc:'2026-10-06T22:00:00Z',
    helper_version:'test',caps:{task_request_limit:96,task_result_byte_limit:108000,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000}
  };
  const start=Date.parse('2026-10-06T11:00:00Z');
  const r=createTaskRecord(h,{nowMs:start,epochIdFactory:()=> 'epoch-1'});
  const first=reserveRequest(r,{requestId:id,fingerprint:'fp',op:'read',nowMs:start});
  assert.equal(first.action,'EXECUTE');
  // Transport retry never invokes reserveRequest again; it only repeats the
  // already-reserved opaque request_id across the SAME helper WebSocket.
  commitRequest(r,{requestId:id,fingerprint:'fp',payloadBytes:1800,nowMs:start+100});
  assert.equal(r.task_requests_used,1);
  assert.equal(r.task_result_bytes_used,1800);
});

ok('RELAY_AND_HELPER_WIRING_PRESERVES_ONE_REQUEST_ID',()=>{
  for(const token of [
    "import { startBoundedResponseRetries } from './ws-response-retry.mjs';",
    "const requestFrame=JSON.stringify({type:'request',request_id,op:body.op,args:helperArgs});",
    "cancelResends=startBoundedResponseRetries({",
    "isPending:id=>this.pending.has(id)",
    "currentSocket:()=>this.helper,currentGeneration:()=>this.socketGeneration"
  ])assert(relay.includes(token),token);
  assert(helper.includes('if(state.processed[m.request_id]){ws.send(JSON.stringify(state.processed[m.request_id]));return;}'));
  assert(relay.includes("},15000);"),'existing 15s hard timeout unchanged');
});

console.log('RELAY_WS_RESPONSE_RETRY_REGRESSION_PASS checks='+count);
