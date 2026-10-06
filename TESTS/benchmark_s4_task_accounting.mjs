import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {createTaskRecord,reserveRequest,commitRequest,chargeAmbiguousRequest,lifecycleProjection} from '../PRODUCT/OneCChatWorker/relay/src/s4-accounting.js';

const EPOCH_REQ=32,EPOCH_BYTES=36000,MAX_RESULT=3000;
const LIVE_LOWER_BOUND={manual_sessions:15,requests:397,result_bytes:509662,completed:false,task_class:'RetailGroup multi-object integration'};
const LEGACY_FINITE_TTL_MINUTES=360;
const q32=n=>Math.ceil(n/32)*32;
const q36k=n=>Math.ceil(n/36000)*36000;
const bytes=v=>Buffer.byteLength(JSON.stringify(v),'utf8');
const exactPayload=(target,label)=>{const base={label,content:''},n=bytes(base);if(target<n)throw new Error('TARGET_TOO_SMALL');const out={label,content:'X'.repeat(target-n)};assert.equal(bytes(out),target);return out;};
const mkCalls=spec=>{const out=[];let seq=0;for(const row of spec){for(let i=0;i<row.count;i++){seq++;out.push({op:row.op,payload:exactPayload(row.bytes,row.op+'-'+seq),prepared_quality_bytes:row.prepared_quality_bytes||0,ambiguous:row.ambiguous===true&&i===0});}}return out;};
const hello=(name,caps)=>({admission_schema_version:3,task_admission_id:(name.replace(/[^a-f0-9]/gi,'a').toLowerCase()+'a'.repeat(32)).slice(0,32),session_id:('b'+name.replace(/[^a-f0-9]/gi,'b').toLowerCase()+'b'.repeat(32)).slice(0,32),project_id:'BENCH',task_id:name,task_goal_sha256:'c'.repeat(64),manifest_sha256:'d'.repeat(64),snapshot_id:'s'.repeat(64),output_task_root:'Output/'+name,task_created_utc:'2026-10-06T10:00:00.000Z',task_expires_utc:'2026-10-06T22:00:00.000Z',helper_version:'bench',caps:{task_request_limit:caps.requests,task_result_byte_limit:caps.bytes,epoch_soft_request_limit:EPOCH_REQ,epoch_soft_result_byte_limit:EPOCH_BYTES,max_result_bytes:MAX_RESULT}});
let epochSeed=0;const epochIdFactory=()=>('bench-epoch-'+(++epochSeed));
function runTrace(name,calls,caps={requests:2048,bytes:2000000}){
 const started=performance.now(),record=createTaskRecord(hello(name,caps),{nowMs:Date.parse('2026-10-06T10:01:00Z'),epochIdFactory});
 const byOp={},searchRead={source_search:0,source_read:0};let prepared_quality_bytes=0,delivered=0,ambiguous_count=0,proposal_recovery='NONE';
 for(let i=0;i<calls.length;i++){const c=calls[i],id=name+'-'+(i+1),fp='fp-'+id;const q=reserveRequest(record,{requestId:id,fingerprint:fp,op:c.op,nowMs:Date.parse('2026-10-06T10:02:00Z'),epochIdFactory});if(q.action!=='EXECUTE')throw new Error(name+': reserve '+q.action+' '+(q.error||''));if(c.ambiguous){chargeAmbiguousRequest(record,{requestId:id,fingerprint:fp,reason:'BENCH_AMBIGUOUS_DELIVERY'});ambiguous_count++;proposal_recovery='RECOVER_FIRST_READ_BACK_REQUIRED';byOp[c.op]=(byOp[c.op]||0)+MAX_RESULT;}else{const n=bytes(c.payload);commitRequest(record,{requestId:id,fingerprint:fp,payloadBytes:n,nowMs:Date.parse('2026-10-06T10:02:01Z')});delivered+=n;byOp[c.op]=(byOp[c.op]||0)+n;}if(c.op==='search')searchRead.source_search++;if(c.op==='read')searchRead.source_read++;prepared_quality_bytes+=c.prepared_quality_bytes||0;}
 const elapsed_ms=+(performance.now()-started).toFixed(3),life=lifecycleProjection(record,Date.parse('2026-10-06T10:03:00Z'));
 return {name,total_model_facing_requests:record.task_requests_used,total_result_bytes:record.task_result_bytes_used,delivered_result_bytes:delivered,bytes_by_operation:byOp,epoch_count:record.epoch_seq+1,wall_time_ms:elapsed_ms,reconnects:0,helper_restarts:0,operator_interventions:0,source_search_count:searchRead.source_search,source_read_count:searchRead.source_read,prepared_quality_bytes,correctness_completion:true,proposal_recovery_behavior:proposal_recovery,ambiguous_results_charged:ambiguous_count,final_accounting:life.accounting};
}

const specs={
 SMALL_R0:[{op:'context',count:1,bytes:800},{op:'search',count:3,bytes:1050},{op:'read',count:8,bytes:1450}],
 MEDIUM_SINGLE_OBJECT:[{op:'context',count:2,bytes:850},{op:'search',count:18,bytes:1150},{op:'read',count:76,bytes:1450}],
 MULTI_OBJECT_INTEGRATION:[{op:'context',count:5,bytes:900},{op:'search',count:85,bytes:1150},{op:'read',count:356,bytes:1260},{op:'proposal_write',count:2,bytes:700},{op:'proposal_read',count:2,bytes:850}],
 FORM_HEAVY_A:[{op:'context',count:1,bytes:900},{op:'read',count:220,bytes:1750}],
 FORM_HEAVY_B:[{op:'read',count:1,bytes:950},{op:'context',count:1,bytes:1850,prepared_quality_bytes:1100}]
};
const corpus={};for(const [name,spec] of Object.entries(specs))corpus[name]=runTrace(name,mkCalls(spec));
corpus.READ_PLUS_PROPOSAL=runTrace('READ_PLUS_PROPOSAL',[...mkCalls([{op:'context',count:2,bytes:850},{op:'search',count:4,bytes:950},{op:'read',count:10,bytes:1200}]),...mkCalls([{op:'proposal_write',count:1,bytes:800,ambiguous:true}]),...mkCalls([{op:'proposal_read',count:2,bytes:850},{op:'proposal_write',count:2,bytes:900},{op:'proposal_read',count:3,bytes:850}])]);
assert(corpus.MULTI_OBJECT_INTEGRATION.total_model_facing_requests>LIVE_LOWER_BOUND.requests);assert(corpus.MULTI_OBJECT_INTEGRATION.total_result_bytes>LIVE_LOWER_BOUND.result_bytes);assert.equal(corpus.READ_PLUS_PROPOSAL.proposal_recovery_behavior,'RECOVER_FIRST_READ_BACK_REQUIRED');
const normal=Object.values(corpus),Rmax=Math.max(...normal.map(x=>x.total_model_facing_requests)),Bmax=Math.max(...normal.map(x=>x.total_result_bytes));
const candidate={task_request_limit:q32(Rmax+2),task_result_byte_limit:q36k(Bmax+6000),task_ttl_minutes:LEGACY_FINITE_TTL_MINUTES,epoch_soft_request_limit:EPOCH_REQ,epoch_soft_result_byte_limit:EPOCH_BYTES,max_result_bytes:MAX_RESULT,request_formula:'ceil32(Rmax '+Rmax+' + 2)',byte_formula:'ceil36000(Bmax '+Bmax+' + 6000)',ttl_basis:'retain accepted finite 360-minute legacy security envelope; isolated corpus wall time is measured but not treated as human/model orchestration duration'};
assert(candidate.task_request_limit>Rmax);assert(candidate.task_result_byte_limit>=Bmax+6000);assert(candidate.task_request_limit>LIVE_LOWER_BOUND.requests);assert(candidate.task_result_byte_limit>LIVE_LOWER_BOUND.result_bytes);
const validation={};
for(const [name,row] of Object.entries(corpus)){const calls=name==='READ_PLUS_PROPOSAL'?[...mkCalls([{op:'context',count:2,bytes:850},{op:'search',count:4,bytes:950},{op:'read',count:10,bytes:1200}]),...mkCalls([{op:'proposal_write',count:1,bytes:800,ambiguous:true}]),...mkCalls([{op:'proposal_read',count:2,bytes:850},{op:'proposal_write',count:2,bytes:900},{op:'proposal_read',count:3,bytes:850}])]:mkCalls(specs[name]);const v=runTrace(name+'_CAP_VALIDATION',calls,{requests:candidate.task_request_limit,bytes:candidate.task_result_byte_limit});validation[name]={pass:v.correctness_completion,requests:v.total_model_facing_requests,result_bytes:v.total_result_bytes,epochs:v.epoch_count};}
const A=corpus.FORM_HEAVY_A,B=corpus.FORM_HEAVY_B;
const formAB={without_prepared_quality:{requests:A.total_model_facing_requests,result_bytes:A.total_result_bytes},with_prepared_quality:{requests:B.total_model_facing_requests,result_bytes:B.total_result_bytes,prepared_quality_bytes:B.prepared_quality_bytes},request_reduction_pct:+(100*(1-B.total_model_facing_requests/A.total_model_facing_requests)).toFixed(2),byte_reduction_pct:+(100*(1-B.total_result_bytes/A.total_result_bytes)).toFixed(2),basis_note:'actual JSON payload bytes charged through S4 accounting; Q0 input-size percentages are not reused as MCP-byte measurements'};
const output={schema:'S4_CAP_QUALIFICATION_V1',live_retailgroup_lower_bound:LIVE_LOWER_BOUND,historical_reference:{q1_completed_terminal_followup:{requests:2,result_bytes:489},output_proposal_gate:{requests:17,result_bytes:15356,proposal_files:2,recovery:'HELPER_TIMEOUT -> recover-first read -> commit; idempotent replay'},q0_form_input_reference_bytes:390700},corpus,candidate,validation,form_heavy_ab:formAB,qualification:{candidate_finite:true,all_corpus_completed:Object.values(corpus).every(x=>x.correctness_completion),candidate_rerun_pass:Object.values(validation).every(x=>x.pass),production_deployment_authorized:false,note:'candidate is for RP cap/TTL review; live RetailGroup evidence was incomplete and remains a lower bound'}};
console.log(JSON.stringify(output,null,2));
