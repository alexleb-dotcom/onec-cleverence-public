import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {
  createTaskRecord,reconcileTaskHello,reserveRequest as reserveRequestRaw,commitRequest,chargeAmbiguousRequest,
  lifecycleProjection,minimalControlPayload as minimalControlPayloadRaw,rotateEpoch,taskState as taskStateRaw,S4_ACCOUNTING_CONTRACT
} from '../relay/src/s4-accounting.js';

const HERE=path.dirname(fileURLToPath(import.meta.url));
const PRODUCT=path.resolve(HERE,'..');
let passed=0;
const ok=(name,fn)=>{fn();passed++;console.log('PASS',name);};
const hello=(over={})=>({
  admission_schema_version:3,
  task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),project_id:'P',task_id:'T',task_goal_sha256:'c'.repeat(64),
  manifest_sha256:'d'.repeat(64),snapshot_id:'s'.repeat(64),output_task_root:'Output/T',
  task_created_utc:'2026-10-06T10:00:00.000Z',task_expires_utc:'2026-10-06T22:00:00.000Z',
  helper_version:'test',caps:{task_request_limit:96,task_result_byte_limit:108000,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000},
  ...over
});
const epochFactory=(()=>{let n=0;return()=>('epoch-'+(++n));})();
const TEST_NOW=Date.parse('2026-10-06T11:00:00Z');
const reserveRequest=(record,args)=>reserveRequestRaw(record,{nowMs:TEST_NOW,...args});
const taskState=(record,nowMs=TEST_NOW)=>taskStateRaw(record,nowMs);
const minimalControlPayload=(record,nowMs=TEST_NOW)=>minimalControlPayloadRaw(record,nowMs);
const make=(h=hello())=>createTaskRecord(h,{nowMs:Date.parse('2026-10-06T11:00:00Z'),epochIdFactory:epochFactory});
const commit=(r,id,bytes,op='read')=>{
  const fp='fp-'+id;
  const q=reserveRequest(r,{requestId:id,fingerprint:fp,op,nowMs:Date.parse('2026-10-06T11:00:00Z'),epochIdFactory:epochFactory});
  assert.equal(q.action,'EXECUTE');
  commitRequest(r,{requestId:id,fingerprint:fp,payloadBytes:bytes,nowMs:Date.parse('2026-10-06T11:00:01Z')});
};

ok('RECONNECT_PRESERVES_TASK_COUNTERS',()=>{
  const h=hello(),r=make(h);commit(r,'1',500);const before=lifecycleProjection(r,Date.parse('2026-10-06T11:01:00Z'));
  reconcileTaskHello(r,h,{nowMs:Date.parse('2026-10-06T11:02:00Z')});const after=lifecycleProjection(r,Date.parse('2026-10-06T11:02:00Z'));
  assert.equal(after.accounting.task_requests_used,before.accounting.task_requests_used);assert.equal(after.accounting.task_result_bytes_used,500);
});
ok('HELPER_RESTART_PRESERVES_TASK_COUNTERS',()=>{const h=hello(),r=make(h);commit(r,'1',700);r.connected=false;reconcileTaskHello(r,{...h,helper_version:'restart'});assert.equal(r.task_result_bytes_used,700);assert.equal(r.session_id,h.session_id);});
ok('EPOCH_ROTATION_PRESERVES_TASK_COUNTERS',()=>{
  const h=hello({caps:{task_request_limit:10,task_result_byte_limit:30000,epoch_soft_request_limit:2,epoch_soft_result_byte_limit:6000,max_result_bytes:3000}}),r=make(h);
  commit(r,'1',1000);commit(r,'2',1000);const prior=r.epoch_id;commit(r,'3',1000);assert.equal(r.task_requests_used,3);assert.notEqual(r.epoch_id,prior);assert.equal(r.epoch_seq,1);assert.equal(r.epoch_requests_used,1);
});
ok('NEW_EPOCH_STARTS_FROM_CURRENT_TASK_USAGE_NOT_ZERO',()=>{const r=make();commit(r,'1',100);rotateEpoch(r,{epochIdFactory:epochFactory});assert.equal(r.task_requests_used,1);assert.equal(r.task_result_bytes_used,100);assert.equal(r.epoch_requests_used,0);});
ok('MODEL_CANNOT_MINT_TASK_ADMISSION_OR_EPOCH',()=>{
  const relay=fs.readFileSync(path.join(PRODUCT,'relay/src/index.js'),'utf8');const core=fs.readFileSync(path.join(PRODUCT,'core/OneCChatWorker.Core.psm1'),'utf8');
  const tools=[...relay.matchAll(/\{name:'(source_context|source_search|source_read|proposal_write|proposal_read|task_checkpoint_write)'/g)].map(x=>x[1]);
  assert.deepEqual(tools,['source_context','source_search','source_read','proposal_write','proposal_read','task_checkpoint_write']);
  const toolBlock=relay.slice(relay.indexOf('const TOOLS=['),relay.indexOf('const McpApiHandler'));
  assert(!toolBlock.includes('task_admission_id'));assert(!toolBlock.includes('epoch_id'));
  const sig=core.slice(core.indexOf('function New-Admission {'),core.indexOf('Assert-SafeId $TaskId'));
  assert(!/task_admission_id|epoch_id/i.test(sig));assert(core.includes("[Guid]::NewGuid().ToString('N')"));
});
ok('ARBITRARY_EPOCH_ID_CANNOT_CREATE_FRESH_BUDGET',()=>{const h=hello(),r=make(h);commit(r,'1',333);const before=r.epoch_id;reconcileTaskHello(r,{...h,epoch_id:'attacker',epoch_seq:999});assert.equal(r.epoch_id,before);assert.equal(r.task_requests_used,1);});
ok('TASK_BYTE_CAP_APPLIES_ACROSS_ALL_EPOCHS',()=>{
  const h=hello({caps:{task_request_limit:10,task_result_byte_limit:7000,epoch_soft_request_limit:1,epoch_soft_result_byte_limit:3000,max_result_bytes:3000}}),r=make(h);
  commit(r,'1',3000);commit(r,'2',3000);const q=reserveRequest(r,{requestId:'3',fingerprint:'fp-3',op:'read',epochIdFactory:epochFactory});assert.equal(q.action,'BLOCKED');assert.equal(q.error,'TASK_SECURITY_BUDGET_EXHAUSTED');assert.equal(r.task_result_bytes_used,6000);
});
ok('TASK_REQUEST_CAP_APPLIES_ACROSS_ALL_EPOCHS',()=>{
  const h=hello({caps:{task_request_limit:3,task_result_byte_limit:20000,epoch_soft_request_limit:1,epoch_soft_result_byte_limit:6000,max_result_bytes:3000}}),r=make(h);
  commit(r,'1',10);commit(r,'2',10);commit(r,'3',10);const q=reserveRequest(r,{requestId:'4',fingerprint:'fp-4',op:'read',epochIdFactory:epochFactory});assert.equal(q.action,'BLOCKED');assert.equal(r.task_requests_used,3);
});
ok('TASK_EXPIRY_NOT_EXTENDED_BY_EPOCH',()=>{const r=make(),expiry=r.task_expires_utc;rotateEpoch(r,{epochIdFactory:epochFactory});assert.equal(r.task_expires_utc,expiry);assert.equal(taskState(r,Date.parse('2026-10-06T22:00:01Z')),'EXPIRED');});
ok('ACCOUNTING_STATE_LOSS_FAILS_CLOSED',()=>{assert.throws(()=>reserveRequest(null,{requestId:'x',fingerprint:'f',op:'read'}),/ACCOUNTING_STATE_UNAVAILABLE/);});
ok('OLD_REQUEST_REPLAY_DOES_NOT_REEXECUTE_OR_REFUND',()=>{const r=make();commit(r,'same',800);const before={q:r.task_requests_used,b:r.task_result_bytes_used};const q=reserveRequest(r,{requestId:'same',fingerprint:'fp-same',op:'read'});assert.equal(q.action,'REPLAY_BLOCKED');assert.deepEqual({q:r.task_requests_used,b:r.task_result_bytes_used},before);});
ok('AMBIGUOUS_PROPOSAL_WRITE_RECOVERS_BEFORE_REPLAY',()=>{
  const r=make(),q=reserveRequest(r,{requestId:'pw1',fingerprint:'proposal-fp',op:'proposal_write'});assert.equal(q.action,'EXECUTE');
  chargeAmbiguousRequest(r,{requestId:'pw1',fingerprint:'proposal-fp',reason:'HELPER_TIMEOUT'});assert.equal(r.task_result_bytes_used,3000);
  const replay=reserveRequest(r,{requestId:'pw1',fingerprint:'proposal-fp',op:'proposal_write'});assert.equal(replay.action,'REPLAY_BLOCKED');assert.equal(replay.receipt.state,'AMBIGUOUS_CHARGED');
});
ok('SNAPSHOT_OR_MANIFEST_CHANGE_INVALIDATES_TASK_ADMISSION',()=>{const h=hello(),r=make(h);assert.throws(()=>reconcileTaskHello(r,{...h,manifest_sha256:'e'.repeat(64)}),/SNAPSHOT_OR_MANIFEST_CHANGED/);assert.throws(()=>reconcileTaskHello(r,{...h,snapshot_id:'z'.repeat(64)}),/SNAPSHOT_OR_MANIFEST_CHANGED/);});
ok('TASK_EXHAUSTION_SURVIVES_RECONNECT_AND_HELPER_RESTART',()=>{
  const h=hello({caps:{task_request_limit:1,task_result_byte_limit:4000,epoch_soft_request_limit:1,epoch_soft_result_byte_limit:4000,max_result_bytes:3000}}),r=make(h);commit(r,'1',1500);assert.equal(taskState(r),'EXHAUSTED');r.connected=false;reconcileTaskHello(r,h);assert.equal(taskState(r),'EXHAUSTED');assert.equal(r.task_requests_used,1);
});
ok('PREPARED_QUALITY_BYTES_ARE_CHARGED_TO_TASK_BUDGET',()=>{const r=make();const prepared=1200,base=440;commit(r,'ctx',base+prepared,'context');assert.equal(r.task_result_bytes_used,1640);});
ok('EXHAUSTED_CONTROL_CONTEXT_LEAKS_NO_SOURCE',()=>{
  const h=hello({caps:{task_request_limit:1,task_result_byte_limit:3000,epoch_soft_request_limit:1,epoch_soft_result_byte_limit:3000,max_result_bytes:3000}}),r=make(h);commit(r,'1',100);
  const q=reserveRequest(r,{requestId:'control',fingerprint:'f-control',op:'context'});assert.equal(q.action,'CONTROL_ONLY');
  const p=minimalControlPayload(r);for(const forbidden of ['participants','target_hints','prepared_quality','canonical_project_root','content'])assert(!(forbidden in p));
});
ok('UNKNOWN_RESPONSE_SIZE_CANNOT_OVERSHOOT_TASK_CAP',()=>{
  const h=hello({caps:{task_request_limit:5,task_result_byte_limit:3500,epoch_soft_request_limit:5,epoch_soft_result_byte_limit:3500,max_result_bytes:3000}}),r=make(h);commit(r,'1',600);
  const q=reserveRequest(r,{requestId:'2',fingerprint:'fp-2',op:'read'});assert.equal(q.action,'BLOCKED');assert.equal(r.task_result_bytes_used,600);assert(r.task_result_bytes_used<=r.task_result_byte_limit);
});
ok('FAIL_CLOSED_RESET_CONTRACT',()=>{const relay=fs.readFileSync(path.join(PRODUCT,'relay/src/index.js'),'utf8');assert(relay.includes('S4_TASK_ACCOUNTING_RESET_FORBIDDEN'));});
ok('ACCOUNTING_CONTRACT_ID',()=>assert.equal(S4_ACCOUNTING_CONTRACT,'S4_DURABLE_TASK_ACCOUNTING_V1'));
ok('RECONNECT_CHARGES_ORPHAN_RESERVED_BYTES',()=>{
  const h=hello(),r=make(h);
  const q=reserveRequest(r,{requestId:'orphan',fingerprint:'fp-orphan',op:'read',epochIdFactory:epochFactory});
  assert.equal(q.action,'EXECUTE');assert.equal(r.task_result_bytes_used,0);
  reconcileTaskHello(r,h,{nowMs:Date.parse('2026-10-06T11:05:00Z')});
  assert.equal(r.task_result_bytes_used,3000);
  assert.equal(r.request_receipts.orphan.state,'AMBIGUOUS_CHARGED');
  assert.equal(r.request_receipts.orphan.reason,'RECONNECT_WITH_UNRESOLVED_RESERVATION');
  const replay=reserveRequest(r,{requestId:'orphan',fingerprint:'fp-orphan',op:'read'});
  assert.equal(replay.action,'REPLAY_BLOCKED');
});
ok('SNAPSHOT_MISMATCH_CONTEXT_IS_CONTROL_ONLY',()=>{
  const r=make();r.invalid_reason='SNAPSHOT_MISMATCH';
  const view=lifecycleProjection(r,Date.parse('2026-10-06T11:00:00Z'));
  assert.equal(view.task_state,'SNAPSHOT_MISMATCH');assert.equal(view.continuation,'OPERATOR_READMISSION_REQUIRED');
  const ctx=reserveRequest(r,{requestId:'ctx-mismatch',fingerprint:'fp-ctx-mismatch',op:'context'});
  assert.equal(ctx.action,'CONTROL_ONLY');
  const read=reserveRequest(r,{requestId:'read-mismatch',fingerprint:'fp-read-mismatch',op:'read'});
  assert.equal(read.action,'BLOCKED');assert.equal(read.error,'SNAPSHOT_OR_MANIFEST_CHANGED');
});
ok('SOURCE_CONTEXT_S4_LIFECYCLE_FIELDS_EXACT',()=>{
  const r=make(),p=lifecycleProjection(r,Date.parse('2026-10-06T11:00:00Z'));
  for(const k of ['task_admission_id','session_id','task_state','task_created_utc','task_expires_utc','epoch_id','epoch_seq','continuation','accounting_contract'])assert(k in p,k);
  for(const k of ['owner','task_requests_used','task_requests_limit','task_requests_remaining','task_result_bytes_used','task_result_bytes_limit','task_result_bytes_remaining','epoch_requests_used','epoch_requests_soft_limit','epoch_result_bytes_used','epoch_result_bytes_soft_limit','max_result_bytes'])assert(k in p.accounting,k);
  assert.equal(p.accounting.owner,'relay');assert.equal(p.continuation,'AUTO');
});
ok('LEGACY_V2_REMAINS_LEGACY_NOT_ZERO_MIGRATED',()=>{
  const relay=fs.readFileSync(path.join(PRODUCT,'relay/src/index.js'),'utf8');
  assert(relay.includes("await this.state.storage.put('active_mode','legacy')"));
  assert(relay.includes("if(mode!=='s4')return this.rpcLegacy(body)"));
  assert(!relay.includes('seed durable counters from zero'));
});

console.log('S4_ACCOUNTING_REGRESSION_PASS checks='+passed);
