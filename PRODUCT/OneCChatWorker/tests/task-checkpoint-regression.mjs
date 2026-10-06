import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {createTaskCheckpointStore,RECOVERY_PACKAGE_SCHEMA} from '../runtime/task-checkpoint-store.mjs';
import {createTaskRecord,reserveRequest,commitRequest,activityReceiptHashInput,sealActivityReceipt,activityCursor,activityDelta,rotateEpoch,S4_ACTIVITY_CURSOR_SCHEMA} from '../relay/src/s4-accounting.js';

const root=process.env.ONEC_TEST_SCRATCH_ROOT;
if(!root)throw new Error('ONEC_TEST_SCRATCH_ROOT_REQUIRED');
const programData=path.join(root,'pd');
const sourceProbe=path.join(root,'source-probe.bsl');
await fsp.mkdir(programData,{recursive:true});
await fsp.writeFile(sourceProbe,'Процедура Тест()\nКонецПроцедуры\n','utf8');
const sourceBefore=crypto.createHash('sha256').update(await fsp.readFile(sourceProbe)).digest('hex');
const stable=v=>Array.isArray(v)?v.map(stable):(v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v);
const hash=v=>crypto.createHash('sha256').update(JSON.stringify(stable(v))).digest('hex');
const aid=n=>n.toString(16).padStart(32,'0');
const sid=n=>(n+1000).toString(16).padStart(32,'0');
const goalA='a'.repeat(64),goalB='b'.repeat(64),manifestA='c'.repeat(64),manifestB='d'.repeat(64),snapA='snapshot-'+'e'.repeat(40),snapB='snapshot-'+'f'.repeat(40);
const admission=(n=1,over={})=>({schema_version:3,accounting_contract:'S4_DURABLE_TASK_ACCOUNTING_V1',task_admission_id:aid(n),session_id:sid(n),project_id:'P92',task_id:'task-92',task_goal_sha256:goalA,source_snapshot_id:snapA,manifest_sha256:manifestA,predecessor:null,...over});
const hello=a=>({admission_schema_version:3,task_admission_id:a.task_admission_id,session_id:a.session_id,project_id:a.project_id,task_id:a.task_id,task_goal_sha256:a.task_goal_sha256,manifest_sha256:a.manifest_sha256,snapshot_id:a.source_snapshot_id,output_task_root:'Output/'+a.task_id,task_created_utc:'2026-10-06T10:00:00.000Z',task_expires_utc:'2026-10-07T10:00:00.000Z',predecessor:a.predecessor??null,caps:{task_request_limit:1000,task_result_byte_limit:3000000,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:96000,max_result_bytes:3000}});
const zeroCursor=a=>({schema:S4_ACTIVITY_CURSOR_SCHEMA,task_admission_id:a.task_admission_id,activity_seq:0,receipt_sha256:null});
let checks=0;
async function ok(name,fn){await fn();checks++;console.log('PASS',name);}
const semantic=(over={})=>({idempotency_key:'cp-default',expected_seq:0,expected_predecessor_sha256:null,phase:'IMPLEMENT',status:'IN_PROGRESS',progress_summary:'Implemented bounded semantic checkpoint state.',completed_steps:['Read authority','Implemented owner'],decisions_constraints:['No second activity journal'],unresolved_questions:[],first_unfinished_step:'Run exact regressions.',do_not_replay:['Do not replay accepted benchmark'],source_evidence_refs:[{path:'Participants/ut/Target/Main/Module.bsl',sha256:'1'.repeat(64),start:1,end:5}],proposal_refs:[],machine_operation_refs:[],assumptions_requiring_confirmation:[],...over});
const store=(a,sub='')=>createTaskCheckpointStore({programDataRoot:path.join(programData,sub),admission:a});
async function rmSub(sub){await fsp.rm(path.join(programData,sub),{recursive:true,force:true});}
function activityRecord(a){let i=0;return createTaskRecord(hello(a),{nowMs:Date.parse('2026-10-06T11:00:00Z'),epochIdFactory:()=>('epoch-'+(++i))});}
function seal(record,id,op,safeRequest,safeResult,nbytes=100){
  const fp='fp-'+id,q=reserveRequest(record,{requestId:id,fingerprint:fp,op,safeRequest,nowMs:Date.parse('2026-10-06T11:00:00Z'),epochIdFactory:()=>('epoch-r-'+id)});
  assert.equal(q.action,'EXECUTE');
  commitRequest(record,{requestId:id,fingerprint:fp,payloadBytes:nbytes,nowMs:Date.parse('2026-10-06T11:00:01Z')});
  sealActivityReceipt(record,{requestId:id,safeResult,activitySha256:hash(activityReceiptHashInput(record,id,safeResult))});
  return q.reservation;
}
const commitCheckpoint=(s,args,cursor,epoch=0,opts={})=>s.write(args,{activity_cursor_before:cursor,writer_epoch_seq:epoch},opts);

await ok('FIRST_WRITE_AND_READBACK',async()=>{
  await rmSub('first');const a=admission(),s=store(a,'first'),r=await commitCheckpoint(s,semantic(),zeroCursor(a));
  assert.equal(r.status,'COMMITTED');assert.equal(r.seq,1);assert.equal(r.current_head,true);
  const h=await s.readHeadVerified();assert.equal(h.checkpoint.checkpoint_sha256,r.sha256);assert.equal(h.checkpoint.schema,'TASK_CHECKPOINT_V1');assert((await fsp.readFile(h.path)).length<=4096);
});
await ok('CAS_CONCURRENT_WRITERS_NO_LAST_WRITER_WINS',async()=>{
  await rmSub('cas');const a=admission(),s1=store(a,'cas'),s2=store(a,'cas'),c=zeroCursor(a);
  const [x,y]=await Promise.all([commitCheckpoint(s1,semantic({idempotency_key:'cas-a'}),c),commitCheckpoint(s2,semantic({idempotency_key:'cas-b'}),c)]);
  assert.equal([x,y].filter(z=>z.status==='COMMITTED').length,1);assert.equal([x,y].filter(z=>z.status==='STALE_CHECKPOINT_HEAD').length,1);
});
await ok('IDEMPOTENT_RETRY_AND_KEY_REUSE_REJECTED',async()=>{
  await rmSub('idem');const a=admission(),s=store(a,'idem'),c=zeroCursor(a),args=semantic({idempotency_key:'idem-one'});
  const one=await commitCheckpoint(s,args,c),two=await commitCheckpoint(s,args,c);assert.equal(two.sha256,one.sha256);assert.equal(two.replayed,true);
  await assert.rejects(()=>commitCheckpoint(s,{...args,progress_summary:'different'},c),/IDEMPOTENCY_KEY_REUSE/);
});
await ok('AMBIGUOUS_AFTER_FILE_COMMIT_RECOVERS_HEAD',async()=>{
  await rmSub('amb-file');const a=admission(),s=store(a,'amb-file'),c=zeroCursor(a),args=semantic({idempotency_key:'amb-file'});
  await assert.rejects(()=>commitCheckpoint(s,args,c,0,{fault:'AFTER_FILE_COMMIT'}),/INJECTED_AFTER_FILE_COMMIT/);
  const r=await commitCheckpoint(s,args,c);assert.equal(r.status,'COMMITTED');assert.equal(r.replayed,true);assert.equal((await s.readHeadVerified()).head.head_seq,1);
});
await ok('AMBIGUOUS_AFTER_HEAD_COMMIT_RETURNS_ORIGINAL_RECEIPT',async()=>{
  await rmSub('amb-head');const a=admission(),s=store(a,'amb-head'),c=zeroCursor(a),args=semantic({idempotency_key:'amb-head'});
  await assert.rejects(()=>commitCheckpoint(s,args,c,0,{fault:'AFTER_HEAD_COMMIT'}),/INJECTED_AFTER_HEAD_COMMIT/);
  const r=await commitCheckpoint(s,args,c);assert.equal(r.status,'COMMITTED');assert.equal(r.replayed,true);assert.equal(r.seq,1);
});
await ok('SUPERSEDED_REPLAY_NEVER_MOVES_HEAD_BACK',async()=>{
  await rmSub('sup');const a=admission(),s=store(a,'sup'),c=zeroCursor(a),a1=semantic({idempotency_key:'sup-1'});
  const r1=await commitCheckpoint(s,a1,c),r2=await commitCheckpoint(s,semantic({idempotency_key:'sup-2',expected_seq:1,expected_predecessor_sha256:r1.sha256,phase:'TEST'}),c);
  const replay=await commitCheckpoint(s,a1,c);assert.equal(replay.superseded,true);assert.equal((await s.readHeadVerified()).head.head_checkpoint_sha256,r2.sha256);
});
await ok('RETENTION_MAX_16_AND_P95',async()=>{
  await rmSub('retain');const a=admission(),s=store(a,'retain'),c=zeroCursor(a);let seq=0,pred=null;const durations=[];
  for(let i=1;i<=24;i++){const t=performance.now();const r=await commitCheckpoint(s,semantic({idempotency_key:'ret-'+i,expected_seq:seq,expected_predecessor_sha256:pred,phase:'P'+i,progress_summary:'checkpoint '+i}),c);durations.push(performance.now()-t);seq=r.seq;pred=r.sha256;}
  const files=(await fsp.readdir(s.checkpoints)).filter(x=>x.endsWith('.json'));assert(files.length<=16);assert.equal((await s.readHeadVerified()).head.head_seq,24);
  let retainedBytes=(await fsp.stat(s.headPath)).size;for(const name of files)retainedBytes+=(await fsp.stat(path.join(s.checkpoints,name))).size;assert(retainedBytes<=65536,'retained bytes '+retainedBytes);console.log('RETAINED_TASK_STATE_BYTES',retainedBytes);
  durations.sort((a,b)=>a-b);const p95=durations[Math.floor((durations.length-1)*.95)];assert(p95<250,'p95 '+p95);console.log('WRITE_P95_MS',p95.toFixed(3));
});
await ok('CORRUPT_HEAD_FAILS_CLOSED',async()=>{
  await rmSub('corrupt-head');const a=admission(),s=store(a,'corrupt-head');await commitCheckpoint(s,semantic(),zeroCursor(a));await fsp.writeFile(s.headPath,'{"schema":"broken"}');
  const r=await s.recovery({});assert.equal(r.compatibility,'CORRUPT');assert.equal(r.recovery_complete,false);
});
await ok('CORRUPT_CHECKPOINT_FAILS_CLOSED',async()=>{
  await rmSub('corrupt-cp');const a=admission(),s=store(a,'corrupt-cp');await commitCheckpoint(s,semantic(),zeroCursor(a));const h=await s.readHeadVerified();await fsp.appendFile(h.path,' ');
  const r=await s.recovery({});assert.equal(r.compatibility,'CORRUPT');assert.equal(r.recovery_complete,false);
});
await ok('FRESH_CHAT_ONE_CONTEXT_RECOVERY',async()=>{
  await rmSub('fresh');const a=admission(),record=activityRecord(a),s=store(a,'fresh'),cpCursor=activityCursor(record),cp=await commitCheckpoint(s,semantic({idempotency_key:'fresh-cp'}),cpCursor);
  const cpRes=seal(record,'cp-write','task_checkpoint_write',{phase:'IMPLEMENT'},{status:'OK',checkpoint_receipt:{status:'COMMITTED',checkpoint_id:cp.checkpoint_id,seq:cp.seq,sha256:cp.sha256,current_head:true,activity_cursor:cp.activity_cursor}},120);
  seal(record,'read-1','read',{path:'Participants/ut/Target/Main/Module.bsl',start:1,end:5},{status:'OK',path:'Participants/ut/Target/Main/Module.bsl',sha256:'2'.repeat(64)},400);
  seal(record,'prop-1','proposal_write',{path:'fix.bsl'},{status:'OK',path:'fix.bsl',sha256:'3'.repeat(64),committed:true,read_back_verified:true},250);
  const delta=activityDelta(record,{fromCursor:cpRes.activity_cursor_before,throughSeq:record.activity_committed_seq});
  const recovery=await store(a,'fresh').recovery({activity_cursor_before:activityCursor(record),activity_delta:delta},1350);
  assert.equal(recovery.schema,RECOVERY_PACKAGE_SCHEMA);assert.equal(recovery.compatibility,'CURRENT');assert.equal(recovery.activity_delta.request_count,3);assert.equal(recovery.activity_delta.operation_counts.proposal_write,1);assert.equal(recovery.recovery_next_action,'Run exact regressions.');assert(Buffer.byteLength(JSON.stringify(recovery))<=1350);
});
await ok('HELPER_RESTART_PRESERVES_CHECKPOINT',async()=>{
  await rmSub('restart');const a=admission(),s=store(a,'restart'),cp=await commitCheckpoint(s,semantic({idempotency_key:'restart'}),zeroCursor(a));assert.equal((await store(a,'restart').readHeadVerified()).head.head_checkpoint_sha256,cp.sha256);
});
await ok('EPOCH_ROLLOVER_TRANSPARENT',async()=>{
  await rmSub('epoch');const a=admission(),record=activityRecord(a),s=store(a,'epoch'),cursor=activityCursor(record);await commitCheckpoint(s,semantic({idempotency_key:'epoch'}),cursor,0);
  rotateEpoch(record,{epochIdFactory:()=> 'epoch-rolled'});seal(record,'read-after-roll','read',{path:'Participants/ut/Target/Main/Module.bsl'},{status:'OK',path:'Participants/ut/Target/Main/Module.bsl',sha256:'4'.repeat(64)},100);
  const r=await s.recovery({activity_delta:activityDelta(record,{fromCursor:cursor}),activity_cursor_before:activityCursor(record)},1350);assert.equal(r.compatibility,'CURRENT');assert.equal(r.activity_delta.available,true);
});
await ok('EXPLICIT_CONTINUATION_CROSSES_ADMISSION',async()=>{
  await rmSub('cont');const old=admission(1),oldRecord=activityRecord(old),sOld=store(old,'cont'),cursor=activityCursor(oldRecord),cp=await commitCheckpoint(sOld,semantic({idempotency_key:'cont-old'}),cursor);
  seal(oldRecord,'old-read','read',{path:'Participants/ut/Target/Main/A.bsl'},{status:'OK',path:'Participants/ut/Target/Main/A.bsl',sha256:'5'.repeat(64)},100);
  const pred={task_admission_id:old.task_admission_id,checkpoint_sha256:cp.sha256,checkpoint_id:cp.checkpoint_id,checkpoint_seq:cp.seq,activity_cursor:cp.activity_cursor,source_snapshot_id:old.source_snapshot_id,task_goal_sha256:old.task_goal_sha256};
  const cur=admission(2,{predecessor:pred}),curRecord=activityRecord(cur);seal(curRecord,'new-read','read',{path:'Participants/ut/Target/Main/B.bsl'},{status:'OK',path:'Participants/ut/Target/Main/B.bsl',sha256:'6'.repeat(64)},100);
  const r=await store(cur,'cont').recovery({predecessor_activity_delta:activityDelta(oldRecord,{fromCursor:cursor}),activity_delta:activityDelta(curRecord,{fromCursor:zeroCursor(cur)}),activity_cursor_before:activityCursor(curRecord)},1350);
  assert.equal(r.compatibility,'CURRENT');assert.equal(r.continued_from_predecessor,true);assert.equal(r.activity_delta.crossed_task_admission,true);assert.equal(r.activity_delta.request_count,2);
});
await ok('SOURCE_STALE_GOAL_STALE_ADMISSION_STALE_SUPERSEDED',async()=>{
  await rmSub('compat');const old=admission(1),s=store(old,'compat'),cp=await commitCheckpoint(s,semantic({idempotency_key:'compat'}),zeroCursor(old));
  const pred={task_admission_id:old.task_admission_id,checkpoint_sha256:cp.sha256,checkpoint_id:cp.checkpoint_id,checkpoint_seq:cp.seq,activity_cursor:cp.activity_cursor,source_snapshot_id:old.source_snapshot_id,task_goal_sha256:old.task_goal_sha256};
  const oldDelta=activityDelta(activityRecord(old),{fromCursor:zeroCursor(old)});
  const staleSrc=admission(2,{source_snapshot_id:snapB,manifest_sha256:manifestB,predecessor:pred}),staleSrcDelta=activityDelta(activityRecord(staleSrc),{fromCursor:zeroCursor(staleSrc)});
  const sr=await store(staleSrc,'compat').recovery({predecessor_activity_delta:oldDelta,activity_delta:staleSrcDelta},1350);assert.equal(sr.compatibility,'SOURCE_SNAPSHOT_STALE');assert(sr.invalidated_sections.includes('source_evidence_refs'));assert(!('source_evidence_refs' in sr.checkpoint));
  const gm=await store(admission(3,{task_goal_sha256:goalB}),'compat').recovery({},1350);assert.equal(gm.compatibility,'TASK_GOAL_MISMATCH');
  const ta=await store(admission(4),'compat').recovery({},1350);assert.equal(ta.compatibility,'TASK_ADMISSION_STALE');
  const sup=await store(admission(5,{predecessor:{...pred,checkpoint_sha256:'9'.repeat(64)}}),'compat').recovery({},1350);assert.equal(sup.compatibility,'SUPERSEDED');
});
await ok('ACTIVITY_TRUNCATION_PRESERVES_COUNTS_DIGEST',async()=>{
  await rmSub('truncate');const a=admission(),record=activityRecord(a),s=store(a,'truncate'),cursor=activityCursor(record);await commitCheckpoint(s,semantic({idempotency_key:'truncate'}),cursor);
  for(let i=0;i<120;i++)seal(record,'r-'+i,'read',{path:'Participants/ut/Target/Main/M'+i+'.bsl'},{status:'OK',path:'Participants/ut/Target/Main/M'+i+'.bsl',sha256:hash('m'+i)},10);
  const delta=activityDelta(record,{fromCursor:cursor,limit:48});assert.equal(delta.request_count,120);assert.equal(delta.truncated,true);assert(delta.receipt_identity);
  const recovery=await s.recovery({activity_delta:delta,activity_cursor_before:activityCursor(record)},1350);assert.equal(recovery.activity_delta.request_count,120);assert.equal(recovery.recovery_complete,false);assert(Buffer.byteLength(JSON.stringify(recovery))<=1350);
});
await ok('COMPLETED_TERMINAL_RECOVERY',async()=>{
  await rmSub('done');const a=admission(),s=store(a,'done');await commitCheckpoint(s,semantic({idempotency_key:'done',status:'COMPLETED',first_unfinished_step:'',phase:'DONE'}),zeroCursor(a));
  const r=await s.recovery({activity_delta:activityDelta(activityRecord(a),{fromCursor:zeroCursor(a)})},1350);assert.equal(r.compatibility,'COMPLETED');assert.equal(r.recovery_next_action,'TASK_COMPLETE');
});
await ok('NO_SOURCE_OUTPUT_MUTATION',async()=>{
  const sourceAfter=crypto.createHash('sha256').update(await fsp.readFile(sourceProbe)).digest('hex');assert.equal(sourceAfter,sourceBefore);assert.equal(fs.existsSync(path.join(root,'Output')),false);assert.equal(fs.existsSync(path.join(root,'Participants')),false);
});
await ok('EXACT_SIX_TOOL_SURFACE',async()=>{
  const relay=await fsp.readFile(new URL('../relay/src/index.js',import.meta.url),'utf8');
  const tools=[...relay.matchAll(/\{name:'([^']+)'/g)].map(x=>x[1]).filter(x=>['source_context','source_search','source_read','proposal_write','proposal_read','task_checkpoint_write'].includes(x));
  assert.deepEqual(tools,['source_context','source_search','source_read','proposal_write','proposal_read','task_checkpoint_write']);
  assert(!relay.includes("name:'shell'"));assert(!relay.includes("name:'file_write'"));assert(!relay.includes("name:'task_checkpoint_read'"));
});
const retentionPd=path.join(root,'retention-pd');
for(const spec of [
  {task_id:'old-abandoned',date:'2026-08-01T00:00:00.000Z'},
  {task_id:'old-active',date:'2026-08-01T00:00:00.000Z'},
  {task_id:'fresh-task',date:new Date().toISOString()}
]){
  const a=admission(20+spec.task_id.length,{task_id:spec.task_id});
  const rs=createTaskCheckpointStore({programDataRoot:retentionPd,admission:a,nowFactory:()=>new Date(spec.date)});
  await rs.write(semantic({idempotency_key:'ret-'+spec.task_id}),{activity_cursor_before:zeroCursor(a),writer_epoch_seq:0});
  if(spec.task_id==='old-active'){
    await fsp.mkdir(path.join(retentionPd,'runtime'),{recursive:true});
    await fsp.writeFile(path.join(retentionPd,'runtime','active-admission.json'),JSON.stringify(a),'utf8');
  }
}
const corruptDir=path.join(retentionPd,'task-state','P92','corrupt-old');
await fsp.mkdir(corruptDir,{recursive:true});
await fsp.writeFile(path.join(corruptDir,'head.json'),'{"schema":"broken","updated_utc":"2026-08-01T00:00:00Z"}','utf8');
console.log('RETENTION_FIXTURE_READY',retentionPd);
console.log('TASK_CHECKPOINT_REGRESSION_PASS checks='+checks);
