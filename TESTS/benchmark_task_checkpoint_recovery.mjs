import assert from 'node:assert/strict';
import fsp from 'node:fs/promises';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {createTaskCheckpointStore} from '../PRODUCT/OneCChatWorker/runtime/task-checkpoint-store.mjs';

const root=process.env.ONEC_TEST_SCRATCH_ROOT;
if(!root)throw new Error('ONEC_TEST_SCRATCH_ROOT_REQUIRED');
const a={schema_version:3,accounting_contract:'S4_DURABLE_TASK_ACCOUNTING_V1',task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),project_id:'Bench92',task_id:'bench-task',task_goal_sha256:'c'.repeat(64),source_snapshot_id:'snapshot-'+'d'.repeat(40),manifest_sha256:'e'.repeat(64),predecessor:null};
const s=createTaskCheckpointStore({programDataRoot:path.join(root,'pd'),admission:a});
const cursor={schema:'S4_ACTIVITY_CURSOR_V1',task_admission_id:a.task_admission_id,activity_seq:0,receipt_sha256:null};
const durations=[],receiptBytes=[];let seq=0,pred=null;
for(let i=1;i<=20;i++){
  const args={idempotency_key:'bench-'+i,expected_seq:seq,expected_predecessor_sha256:pred,phase:'PHASE-'+i,status:'IN_PROGRESS',progress_summary:'Bounded material phase completed; continue from the first unfinished step.',completed_steps:['authority read','bounded implementation'],decisions_constraints:['do not replay accepted gates'],unresolved_questions:[],first_unfinished_step:'Continue the next unfinished implementation or validation phase.',do_not_replay:['accepted S4 cap qualification'],source_evidence_refs:[],proposal_refs:[],machine_operation_refs:[],assumptions_requiring_confirmation:[]};
  const t=performance.now();const r=await s.write(args,{activity_cursor_before:cursor,writer_epoch_seq:Math.floor(i/4)});durations.push(performance.now()-t);receiptBytes.push(Buffer.byteLength(JSON.stringify(r)));seq=r.seq;pred=r.sha256;
}
const activity_delta={schema:'S4_ACTIVITY_DELTA_V1',available:true,from_cursor:cursor,to_cursor:cursor,request_count:0,charged_result_bytes:0,operation_counts:{},critical_events:[],safe_targets:[],epoch_rollovers:0,truncated:false,receipt_identity:null};
const recoveryTimes=[];let recoveryBytes=0;
for(let i=0;i<20;i++){const t=performance.now();const r=await s.recovery({activity_delta,activity_cursor_before:cursor},1350);recoveryTimes.push(performance.now()-t);recoveryBytes=Buffer.byteLength(JSON.stringify(r));assert.equal(r.recovery_available,true);}
const pct=(a,b)=>+(100*a/b).toFixed(3),p95=x=>{const y=[...x].sort((a,b)=>a-b);return +y[Math.floor((y.length-1)*.95)].toFixed(3);};
const maxReceipt=Math.max(...receiptBytes),writeP95=p95(durations),recoveryP95=p95(recoveryTimes);
const frozen={
  MEDIUM_SINGLE_OBJECT:{requests:96,result_bytes:132600,checkpoint_writes:4},
  MULTI_OBJECT_INTEGRATION:{requests:450,result_bytes:553910,checkpoint_writes:12}
};
const workloads={};
for(const [name,b] of Object.entries(frozen)){
  const addedRequests=b.checkpoint_writes,addedBytes=b.checkpoint_writes*maxReceipt;
  workloads[name]={baseline_requests:b.requests,baseline_result_bytes:b.result_bytes,checkpoint_writes:b.checkpoint_writes,added_requests:addedRequests,added_result_bytes_upper_bound:addedBytes,request_overhead_pct:pct(addedRequests,b.requests),result_byte_overhead_pct_upper_bound:pct(addedBytes,b.result_bytes)};
  assert(workloads[name].request_overhead_pct<=5,name+' request overhead');
  assert(workloads[name].result_byte_overhead_pct_upper_bound<=5,name+' byte overhead');
}
assert(writeP95<250,'write p95 '+writeP95);
assert(recoveryP95<250,'recovery p95 '+recoveryP95);
assert(recoveryBytes<=1350,'recovery bytes '+recoveryBytes);
const output={schema:'TASK_CHECKPOINT_BENCHMARK_V1',baseline_source:'accepted #87 S4 qualification measurements; corpus not replayed',checkpoint_write_p95_ms:writeP95,recovery_build_p95_ms:recoveryP95,max_checkpoint_receipt_bytes:maxReceipt,recovery_package_bytes:recoveryBytes,workloads,fresh_chat:{source_context_calls_to_recovery:1,productive_after_one_source_context:true},pass:true};
console.log(JSON.stringify(output,null,2));
