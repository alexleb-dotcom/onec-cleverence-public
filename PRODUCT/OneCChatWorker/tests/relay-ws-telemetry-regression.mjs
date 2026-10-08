import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here=path.dirname(fileURLToPath(import.meta.url));
const code=fs.readFileSync(path.join(here,'../relay/src/index.js'),'utf8');
const begin=code.indexOf('function traceWs(');
const end=code.indexOf('\nasync function sha256HexValue(',begin);
assert(begin>=0&&end>begin,'trace helper must remain distinct and reviewable');
const outputs=[];
const traceWs=new Function('console','Date',code.slice(begin,end)+'\nreturn traceWs;')(
  {log:(label,line)=>outputs.push({label,doc:JSON.parse(line),line})},Date
);
let passed=0;
function ok(name,fn){fn();passed++;console.log('PASS '+name);}
const opaque='mcp-'+'a'.repeat(52)+'f'.repeat(12);

ok('OPAQUE_CORRELATION_RETAINS_ONLY_12_HEX',()=>{
  traceWs('rpc_dispatch',{request_id:opaque,generation:2,op:'context',age_ms:13.7,pending_count:1,socket_state:1});
  const item=outputs.at(-1);
  assert.equal(item.label,'RELAY_WS_TRACE');
  assert.equal(item.doc.request_key,'f'.repeat(12));
  assert.equal(item.doc.generation,2);
  assert.equal(item.doc.op,'context');
  assert.equal(item.doc.age_ms,14);
  assert.equal(item.doc.socket_state,1);
  assert(!item.line.includes(opaque));
});

ok('DIAGNOSTIC_ALLOWLIST_NEVER_LOGS_SOURCE_OR_SECRETS',()=>{
  const sourceMarker='SECRET_OR_SOURCE_CONTENT_MUST_NOT_LEAK';
  traceWs('result_frame',{
    request_id:opaque,matched:true,op:'read',pending_count:1,
    token:sourceMarker,helper_secret:sourceMarker,source_path:sourceMarker,
    url:'wss://example.invalid/?token='+sourceMarker,
    payload:{content:sourceMarker},args:{query:sourceMarker}
  });
  assert(!outputs.at(-1).line.includes(sourceMarker));
  assert.deepEqual(Object.keys(outputs.at(-1).doc).sort(),[
    'age_ms','at_ms','event','generation','matched','op','pending_count','request_key','socket_state'
  ].sort());
  assert.equal(outputs.at(-1).doc.matched,true);
});

ok('BAD_CORRELATION_OR_UNRECOGNIZED_OP_FAILS_CLOSED',()=>{
  traceWs('rpc_dispatch',{request_id:'mcp-bad-secret',op:'unknown',generation:'bad',age_ms:-20,pending_count:'bad'});
  const doc=outputs.at(-1).doc;
  assert.equal(doc.request_key,null);
  assert.equal(doc.op,null);
  assert.equal(doc.generation,null);
  assert.equal(doc.age_ms,0);
  assert.equal(doc.pending_count,null);
});

ok('DIAGNOSTIC_EVENTS_COVER_EXACT_TRANSPORT_BOUNDARIES',()=>{
  for(const event of [
    'socket_accepted','socket_replaced','socket_closed','socket_error',
    's4_hello_ack','rpc_received','rpc_dispatch','result_frame','rpc_deadline',
    'message_handler_rejected'
  ])assert(code.includes("traceWs('"+event+"'"),event);
});

ok('PENDING_REQUEST_CORRELATION_PRESERVED',()=>{
  assert(code.includes("this.pending.set(request_id,{startedAt,generation,resolve:"));
  assert(code.includes("const p=this.pending.get(msg.request_id);"));
  assert(code.includes("if(p){this.pending.delete(msg.request_id);this.busy=false;p.resolve(msg);}"));
  assert(code.includes("},15000);"),'existing S4 timeout must not silently change');
});

ok('NO_S4_POLICY_OR_PUBLIC_MCP_SCHEMA_EDITS_REQUIRED',()=>{
  assert(code.includes("chargeAmbiguousRequest(record,{requestId:clientId,fingerprint,reason:'HELPER_TIMEOUT'})"));
  assert(code.includes("await sealOneActivity(record,clientId,{status:'ERROR',error_class:'HELPER_TIMEOUT'})"));
  for(const name of ['source_context','source_search','source_read','proposal_write','proposal_read','task_checkpoint_write'])
    assert(code.includes("name:'"+name+"'"));
});

console.log('RELAY_WS_TELEMETRY_REGRESSION_PASS checks='+passed);
