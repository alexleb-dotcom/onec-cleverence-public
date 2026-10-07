export const S4_ACCOUNTING_CONTRACT='S4_DURABLE_TASK_ACCOUNTING_V1';
export const S4_ACTIVITY_CURSOR_SCHEMA='S4_ACTIVITY_CURSOR_V1';

const copy=x=>structuredClone(x);
const int=(v,min=1,max=Number.MAX_SAFE_INTEGER)=>Number.isInteger(v)&&v>=min&&v<=max;
const text=(v,max)=>typeof v==='string'&&v.length>0&&v.length<=max;
const iso=v=>typeof v==='string'&&Number.isFinite(Date.parse(v));
const fail=code=>{const e=new Error(code);e.code=code;throw e;};

function ensureActivity(record){
  if(!Number.isInteger(record.activity_seq)||record.activity_seq<0)record.activity_seq=0;
  if(!Number.isInteger(record.activity_committed_seq)||record.activity_committed_seq<0)record.activity_committed_seq=0;
  if(record.activity_committed_seq>record.activity_seq)fail('ACCOUNTING_STATE_UNAVAILABLE');
  if(record.activity_integrity_sha256!=null&&!/^[a-f0-9]{64}$/.test(String(record.activity_integrity_sha256)))fail('ACCOUNTING_STATE_UNAVAILABLE');
  record.request_receipts=record.request_receipts||{};
  return record;
}

export function activityCursor(record){
  ensureActivity(record);
  return {
    schema:S4_ACTIVITY_CURSOR_SCHEMA,
    task_admission_id:record.task_admission_id,
    activity_seq:record.activity_committed_seq,
    receipt_sha256:record.activity_integrity_sha256??null
  };
}

export function validateS4Hello(h){
  if(!h||h.admission_schema_version!==3)fail('ADMISSION_SCHEMA_UNSUPPORTED');
  for(const [k,max] of [['task_admission_id',128],['session_id',128],['project_id',64],['task_id',64],['manifest_sha256',64],['snapshot_id',128],['output_task_root',256]])if(!text(h[k],max))fail('TASK_BINDING_INVALID:'+k);
  if(h.task_goal_sha256!=null&&!text(h.task_goal_sha256,64))fail('TASK_BINDING_INVALID:task_goal_sha256');
  if(!iso(h.task_created_utc)||!iso(h.task_expires_utc)||Date.parse(h.task_expires_utc)<=Date.parse(h.task_created_utc))fail('TASK_EXPIRY_INVALID');
  if(h.predecessor!=null){
    const p=h.predecessor;
    if(!p||typeof p!=='object'||!text(p.task_admission_id,128)||!text(p.checkpoint_sha256,64)||!p.activity_cursor||p.activity_cursor.schema!==S4_ACTIVITY_CURSOR_SCHEMA||p.activity_cursor.task_admission_id!==p.task_admission_id||!Number.isInteger(p.activity_cursor.activity_seq)||p.activity_cursor.activity_seq<0)fail('TASK_PREDECESSOR_INVALID');
    if(p.activity_cursor.activity_seq===0&&p.activity_cursor.receipt_sha256!=null)fail('TASK_PREDECESSOR_INVALID');
    if(p.activity_cursor.activity_seq>0&&!text(p.activity_cursor.receipt_sha256,64))fail('TASK_PREDECESSOR_INVALID');
  }
  const c=h.caps||{};
  if(!int(c.task_request_limit,1,1000000))fail('TASK_REQUEST_LIMIT_INVALID');
  if(!int(c.task_result_byte_limit,1,1024*1024*1024))fail('TASK_BYTE_LIMIT_INVALID');
  if(!int(c.epoch_soft_request_limit,1,c.task_request_limit))fail('EPOCH_REQUEST_LIMIT_INVALID');
  if(!int(c.epoch_soft_result_byte_limit,1,c.task_result_byte_limit))fail('EPOCH_BYTE_LIMIT_INVALID');
  if(!int(c.max_result_bytes,1,c.epoch_soft_result_byte_limit))fail('MAX_RESULT_BYTES_INVALID');
  return true;
}

const bindingFields=['task_admission_id','session_id','project_id','task_id','task_goal_sha256','manifest_sha256','snapshot_id','output_task_root','task_created_utc','task_expires_utc'];

export function createTaskRecord(h,{nowMs=Date.now(),epochIdFactory=()=>crypto.randomUUID()}={}){
  validateS4Hello(h);
  if(nowMs>=Date.parse(h.task_expires_utc))fail('TASK_EXPIRED');
  return {
    schema_version:2,accounting_contract:S4_ACCOUNTING_CONTRACT,
    task_admission_id:h.task_admission_id,session_id:h.session_id,project_id:h.project_id,task_id:h.task_id,
    task_goal_sha256:h.task_goal_sha256??null,manifest_sha256:h.manifest_sha256,snapshot_id:h.snapshot_id,output_task_root:h.output_task_root,
    predecessor:h.predecessor?copy(h.predecessor):null,
    task_created_utc:h.task_created_utc,task_expires_utc:h.task_expires_utc,
    task_request_limit:h.caps.task_request_limit,task_result_byte_limit:h.caps.task_result_byte_limit,
    epoch_soft_request_limit:h.caps.epoch_soft_request_limit,epoch_soft_result_byte_limit:h.caps.epoch_soft_result_byte_limit,max_result_bytes:h.caps.max_result_bytes,
    task_requests_used:0,task_result_bytes_used:0,
    epoch_id:epochIdFactory(),epoch_seq:0,epoch_requests_used:0,epoch_result_bytes_used:0,
    activity_seq:0,activity_committed_seq:0,activity_integrity_sha256:null,
    request_receipts:{},connected:true,helper_version:h.helper_version??null,controlled_restart_done:!!h.controlled_restart_done
  };
}

export function reconcileTaskHello(record,h,{nowMs=Date.now()}={}){
  validateS4Hello(h);
  if(!record||record.accounting_contract!==S4_ACCOUNTING_CONTRACT)fail('ACCOUNTING_STATE_UNAVAILABLE');
  ensureActivity(record);
  for(const k of bindingFields){
    const a=record[k]??null,b=h[k]??null;
    if(a!==b)fail(k==='manifest_sha256'||k==='snapshot_id'?'SNAPSHOT_OR_MANIFEST_CHANGED':'TASK_ADMISSION_BINDING_MISMATCH');
  }
  if(JSON.stringify(record.predecessor??null)!==JSON.stringify(h.predecessor??null))fail('TASK_PREDECESSOR_BINDING_MISMATCH');
  if(record.task_request_limit!==h.caps.task_request_limit||record.task_result_byte_limit!==h.caps.task_result_byte_limit||
     record.epoch_soft_request_limit!==h.caps.epoch_soft_request_limit||record.epoch_soft_result_byte_limit!==h.caps.epoch_soft_result_byte_limit||
     record.max_result_bytes!==h.caps.max_result_bytes)fail('TASK_SECURITY_POLICY_MISMATCH');
  for(const receipt of Object.values(record.request_receipts||{})){
    if(receipt?.state!=='RESERVED')continue;
    const charge=Number(receipt.reserved_bytes||0);
    if(!int(charge,1,record.max_result_bytes))fail('ACCOUNTING_STATE_UNAVAILABLE');
    if(record.task_result_bytes_used+charge>record.task_result_byte_limit)fail('ACCOUNTING_STATE_UNAVAILABLE');
    record.task_result_bytes_used+=charge;
    record.epoch_result_bytes_used+=charge;
    receipt.state='AMBIGUOUS_CHARGED';
    receipt.charged_bytes=charge;
    receipt.reason='RECONNECT_WITH_UNRESOLVED_RESERVATION';
    receipt.committed_utc=new Date(nowMs).toISOString();
    receipt.safe_result={status:'ERROR',error_class:'RECONNECT_WITH_UNRESOLVED_RESERVATION'};
    delete receipt.reserved_bytes;
  }
  record.connected=true;record.helper_version=h.helper_version??record.helper_version;record.controlled_restart_done=!!h.controlled_restart_done;
  return record;
}

export function taskState(record,nowMs=Date.now()){
  if(!record||record.accounting_contract!==S4_ACCOUNTING_CONTRACT)return 'ACCOUNTING_UNAVAILABLE';
  if(record.invalid_reason==='SNAPSHOT_MISMATCH')return 'SNAPSHOT_MISMATCH';
  if(nowMs>=Date.parse(record.task_expires_utc))return 'EXPIRED';
  const rr=record.task_request_limit-record.task_requests_used;
  const rb=record.task_result_byte_limit-record.task_result_bytes_used;
  if(rr<=0||rb<record.max_result_bytes)return 'EXHAUSTED';
  if(rr<=2||rb<record.max_result_bytes*2)return 'LOW_BUDGET';
  return 'ACTIVE';
}

export function lifecycleProjection(record,nowMs=Date.now()){
  const state=taskState(record,nowMs);
  if(state==='ACCOUNTING_UNAVAILABLE')fail('ACCOUNTING_STATE_UNAVAILABLE');
  ensureActivity(record);
  return {
    accounting_contract:S4_ACCOUNTING_CONTRACT,
    task_admission_id:record.task_admission_id,
    session_id:record.session_id,
    task_state:state,
    task_created_utc:record.task_created_utc,
    task_expires_utc:record.task_expires_utc,
    epoch_id:record.epoch_id,
    epoch_seq:record.epoch_seq,
    activity_cursor:activityCursor(record),
    continuation:(state==='ACTIVE'||state==='LOW_BUDGET')?'AUTO':'OPERATOR_READMISSION_REQUIRED',
    accounting:{
      owner:'relay',
      task_requests_used:record.task_requests_used,
      task_requests_limit:record.task_request_limit,
      task_requests_remaining:Math.max(0,record.task_request_limit-record.task_requests_used),
      task_result_bytes_used:record.task_result_bytes_used,
      task_result_bytes_limit:record.task_result_byte_limit,
      task_result_bytes_remaining:Math.max(0,record.task_result_byte_limit-record.task_result_bytes_used),
      epoch_requests_used:record.epoch_requests_used,
      epoch_requests_soft_limit:record.epoch_soft_request_limit,
      epoch_result_bytes_used:record.epoch_result_bytes_used,
      epoch_result_bytes_soft_limit:record.epoch_soft_result_byte_limit,
      max_result_bytes:record.max_result_bytes
    }
  };
}

export function rotateEpoch(record,{epochIdFactory=()=>crypto.randomUUID()}={}){
  record.epoch_seq+=1;record.epoch_id=epochIdFactory();record.epoch_requests_used=0;record.epoch_result_bytes_used=0;return record;
}

function ensureEpochCapacity(record,epochIdFactory){
  if(record.epoch_requests_used+1>record.epoch_soft_request_limit||
     record.epoch_result_bytes_used+record.max_result_bytes>record.epoch_soft_result_byte_limit){
    rotateEpoch(record,{epochIdFactory});
  }
}

export function reserveRequest(record,{requestId,fingerprint,op,safeRequest={},nowMs=Date.now(),epochIdFactory=()=>crypto.randomUUID()}){
  if(!record||record.accounting_contract!==S4_ACCOUNTING_CONTRACT)fail('ACCOUNTING_STATE_UNAVAILABLE');
  ensureActivity(record);
  if(!text(String(requestId||''),256)||!text(String(fingerprint||''),256)||!text(String(op||''),64))fail('REQUEST_IDENTITY_INVALID');
  const existing=record.request_receipts?.[requestId];
  if(existing){
    if(existing.fingerprint!==fingerprint)fail('REQUEST_ID_REUSE');
    return {action:'REPLAY_BLOCKED',receipt:copy(existing),record};
  }
  const state=taskState(record,nowMs);
  if(state==='EXPIRED')return op==='context'?{action:'CONTROL_ONLY',record}:{action:'BLOCKED',error:'TASK_EXPIRED',record};
  if(state==='SNAPSHOT_MISMATCH')return op==='context'?{action:'CONTROL_ONLY',record}:{action:'BLOCKED',error:'SNAPSHOT_OR_MANIFEST_CHANGED',record};
  if(state==='EXHAUSTED')return op==='context'?{action:'CONTROL_ONLY',record}:{action:'BLOCKED',error:'TASK_SECURITY_BUDGET_EXHAUSTED',record};
  ensureEpochCapacity(record,epochIdFactory);
  if(record.task_requests_used+1>record.task_request_limit||
     record.task_result_bytes_used+record.max_result_bytes>record.task_result_byte_limit){
    return op==='context'?{action:'CONTROL_ONLY',record}:{action:'BLOCKED',error:'TASK_SECURITY_BUDGET_EXHAUSTED',record};
  }
  const cursorBefore=activityCursor(record);
  const activitySeq=record.activity_seq+1;
  record.activity_seq=activitySeq;
  const receipt={request_id:requestId,fingerprint,op,state:'RESERVED',reserved_bytes:record.max_result_bytes,charged_bytes:0,epoch_seq:record.epoch_seq,epoch_id:record.epoch_id,created_utc:new Date(nowMs).toISOString(),activity_seq:activitySeq,activity_cursor_before:cursorBefore,safe_request:copy(safeRequest||{})};
  record.task_requests_used+=1;record.epoch_requests_used+=1;
  record.request_receipts=record.request_receipts||{};record.request_receipts[requestId]=receipt;
  return {action:'EXECUTE',reservation:copy(receipt),record};
}

export function commitRequest(record,{requestId,fingerprint,payloadBytes,nowMs=Date.now()}){
  const r=record?.request_receipts?.[requestId];if(!r)fail('REQUEST_RESERVATION_MISSING');
  if(r.fingerprint!==fingerprint)fail('REQUEST_ID_REUSE');
  if(r.state!=='RESERVED')fail('REQUEST_RESERVATION_NOT_ACTIVE');
  if(!Number.isInteger(payloadBytes)||payloadBytes<0||payloadBytes>r.reserved_bytes)fail('RESULT_CAP');
  record.task_result_bytes_used+=payloadBytes;record.epoch_result_bytes_used+=payloadBytes;
  if(record.task_result_bytes_used>record.task_result_byte_limit)fail('TASK_BYTE_CAP_OVERSHOOT');
  r.state='COMMITTED';r.charged_bytes=payloadBytes;r.committed_utc=new Date(nowMs).toISOString();delete r.reserved_bytes;
  return record;
}

export function chargeAmbiguousRequest(record,{requestId,fingerprint,nowMs=Date.now(),reason='AMBIGUOUS_DELIVERY'}){
  const r=record?.request_receipts?.[requestId];if(!r)fail('REQUEST_RESERVATION_MISSING');
  if(r.fingerprint!==fingerprint)fail('REQUEST_ID_REUSE');
  if(r.state!=='RESERVED')return record;
  const charge=r.reserved_bytes;
  record.task_result_bytes_used+=charge;record.epoch_result_bytes_used+=charge;
  if(record.task_result_bytes_used>record.task_result_byte_limit)fail('TASK_BYTE_CAP_OVERSHOOT');
  r.state='AMBIGUOUS_CHARGED';r.charged_bytes=charge;r.reason=reason;r.safe_result={status:'ERROR',error_class:reason};r.committed_utc=new Date(nowMs).toISOString();delete r.reserved_bytes;
  return record;
}

export function activityReceiptHashInput(record,requestId,safeResult){
  ensureActivity(record);
  const r=record?.request_receipts?.[requestId];if(!r)fail('REQUEST_RESERVATION_MISSING');
  if(!Number.isInteger(r.activity_seq)||r.activity_seq<1)fail('ACTIVITY_SEQUENCE_INVALID');
  return {
    schema:'S4_ACTIVITY_RECEIPT_V1',
    task_admission_id:record.task_admission_id,
    activity_seq:r.activity_seq,
    predecessor_sha256:r.activity_cursor_before?.receipt_sha256??null,
    request_id:r.request_id,
    request_fingerprint:r.fingerprint,
    operation:r.op,
    state:r.state,
    charged_bytes:r.charged_bytes,
    epoch_seq:r.epoch_seq,
    safe_request:r.safe_request||{},
    safe_result:safeResult||r.safe_result||{},
    committed_utc:r.committed_utc||null
  };
}

export function canonicalizeRecoveredOrphanPredecessor(record,requestId){
  ensureActivity(record);
  const r=record?.request_receipts?.[requestId];
  if(!r)fail('REQUEST_RESERVATION_MISSING');
  // Normal terminal receipts and existing sealed history must never be rebased.
  if(r.state!=='AMBIGUOUS_CHARGED'||r.reason!=='RECONNECT_WITH_UNRESOLVED_RESERVATION'||r.activity_sha256)return record;
  if(r.activity_seq!==record.activity_committed_seq+1)fail('ACTIVITY_SEQUENCE_GAP');
  const current=activityCursor(record);
  const prior=r.activity_cursor_before;
  if(!prior||prior.task_admission_id!==record.task_admission_id||
     !Number.isInteger(prior.activity_seq)||prior.activity_seq<0||
     prior.activity_seq>=r.activity_seq||
     (prior.receipt_sha256!==null&&!/^[a-f0-9]{64}$/.test(String(prior.receipt_sha256||''))))fail('ACTIVITY_PREDECESSOR_MISMATCH');
  if(prior.activity_seq===current.activity_seq&&prior.receipt_sha256===current.receipt_sha256)return record;
  // Only the historical shared, pre-recovery committed cursor is a valid source.
  // Verify prior points to a sealed predecessor (or the genesis cursor).
  if(prior.activity_seq!==0){
    const source=Object.values(record.request_receipts||{}).find(x=>x?.activity_seq===prior.activity_seq&&x.activity_sha256===prior.receipt_sha256);
    if(!source)fail('ACTIVITY_RECOVERY_PREDECESSOR_UNVERIFIED');
  }else if(prior.receipt_sha256!==null)fail('ACTIVITY_RECOVERY_PREDECESSOR_UNVERIFIED');
  if(current.activity_seq<=prior.activity_seq)fail('ACTIVITY_RECOVERY_PREDECESSOR_INVALID');
  if(r.activity_cursor_before_original)fail('ACTIVITY_RECOVERY_ALREADY_REBASED');
  r.activity_cursor_before_original=copy(prior);
  r.activity_cursor_before=copy(current);
  r.recovery_predecessor_canonicalized=true;
  return record;
}

export function sealActivityReceipt(record,{requestId,safeResult,activitySha256}){
  ensureActivity(record);
  if(!/^[a-f0-9]{64}$/.test(String(activitySha256||'')))fail('ACTIVITY_INTEGRITY_INVALID');
  const r=record?.request_receipts?.[requestId];if(!r)fail('REQUEST_RESERVATION_MISSING');
  if(!['COMMITTED','AMBIGUOUS_CHARGED'].includes(r.state))fail('ACTIVITY_RECEIPT_NOT_TERMINAL');
  if(r.activity_sha256){
    if(r.activity_sha256!==activitySha256)fail('ACTIVITY_INTEGRITY_MISMATCH');
    return record;
  }
  if(r.activity_seq!==record.activity_committed_seq+1)fail('ACTIVITY_SEQUENCE_GAP');
  const expectedPred=record.activity_integrity_sha256??null;
  if((r.activity_cursor_before?.receipt_sha256??null)!==expectedPred)fail('ACTIVITY_PREDECESSOR_MISMATCH');
  r.safe_result=copy(safeResult||r.safe_result||{});
  r.activity_sha256=activitySha256;
  record.activity_committed_seq=r.activity_seq;
  record.activity_integrity_sha256=activitySha256;
  return record;
}

export function unsealedTerminalReceipts(record){
  ensureActivity(record);
  return Object.values(record.request_receipts||{}).filter(r=>r&&Number.isInteger(r.activity_seq)&&r.activity_seq>0&&['COMMITTED','AMBIGUOUS_CHARGED'].includes(r.state)&&!r.activity_sha256).sort((a,b)=>a.activity_seq-b.activity_seq);
}

export function activityTail(record,{throughSeq,limit=64}={}){
  ensureActivity(record);
  const end=Number.isInteger(throughSeq)?Math.min(throughSeq,record.activity_committed_seq):record.activity_committed_seq;
  const all=Object.values(record.request_receipts||{}).filter(r=>r&&r.activity_sha256&&Number.isInteger(r.activity_seq)&&r.activity_seq<=end).sort((a,b)=>a.activity_seq-b.activity_seq);
  const selected=all.slice(Math.max(0,all.length-Math.max(1,Math.min(128,limit))));
  return {
    schema:'S4_ACTIVITY_WINDOW_V1',
    task_admission_id:record.task_admission_id,
    through_cursor:activityCursor({...record,activity_committed_seq:end,activity_integrity_sha256:(selected.length&&selected[selected.length-1].activity_seq===end)?selected[selected.length-1].activity_sha256:(end===0?null:record.activity_integrity_sha256)}),
    earliest_seq:selected.length?selected[0].activity_seq:(end===0?0:null),
    retained_count:selected.length,
    truncated_before:selected.length?selected[0].activity_seq>1:false,
    receipts:selected.map(r=>({
      activity_seq:r.activity_seq,activity_sha256:r.activity_sha256,predecessor_sha256:r.activity_cursor_before?.receipt_sha256??null,
      operation:r.op,state:r.state,charged_bytes:r.charged_bytes,epoch_seq:r.epoch_seq,epoch_id:r.epoch_id,
      created_utc:r.created_utc,committed_utc:r.committed_utc||null,safe_request:copy(r.safe_request||{}),safe_result:copy(r.safe_result||{})
    }))
  };
}

export function projectCommittedRecord(record,{payloadBytes}){
  if(!Number.isInteger(payloadBytes)||payloadBytes<0||payloadBytes>record.max_result_bytes)fail('RESULT_CAP');
  const projected=copy(record);
  projected.task_result_bytes_used+=payloadBytes;projected.epoch_result_bytes_used+=payloadBytes;
  return projected;
}

export function minimalControlPayload(record,nowMs=Date.now()){
  return lifecycleProjection(record,nowMs);
}

export function latestCheckpointRequestCursor(record){
  ensureActivity(record);
  const rows=Object.values(record.request_receipts||{}).filter(r=>r&&r.op==='task_checkpoint_write'&&Number.isInteger(r.activity_seq)&&r.activity_cursor_before).sort((a,b)=>b.activity_seq-a.activity_seq);
  return rows.length?copy(rows[0].activity_cursor_before):null;
}

export function activityDelta(record,{fromCursor,throughSeq,limit=48}={}){
  ensureActivity(record);
  if(!fromCursor||fromCursor.schema!==S4_ACTIVITY_CURSOR_SCHEMA||fromCursor.task_admission_id!==record.task_admission_id||!Number.isInteger(fromCursor.activity_seq)||fromCursor.activity_seq<0)return {schema:'S4_ACTIVITY_DELTA_V1',available:false,reason:'ACTIVITY_CURSOR_INVALID',truncated:true};
  if(fromCursor.activity_seq===0){
    if(fromCursor.receipt_sha256!=null)return {schema:'S4_ACTIVITY_DELTA_V1',available:false,reason:'ACTIVITY_CURSOR_INVALID',truncated:true};
  }else{
    const base=Object.values(record.request_receipts||{}).find(r=>r?.activity_seq===fromCursor.activity_seq&&r.activity_sha256===fromCursor.receipt_sha256);
    if(!base)return {schema:'S4_ACTIVITY_DELTA_V1',available:false,reason:'PREDECESSOR_ACTIVITY_UNAVAILABLE',from_cursor:copy(fromCursor),truncated:true};
  }
  const end=Number.isInteger(throughSeq)?Math.min(throughSeq,record.activity_committed_seq):record.activity_committed_seq;
  if(end<fromCursor.activity_seq)return {schema:'S4_ACTIVITY_DELTA_V1',available:false,reason:'ACTIVITY_CURSOR_AHEAD',from_cursor:copy(fromCursor),truncated:true};
  const rows=Object.values(record.request_receipts||{}).filter(r=>r&&r.activity_sha256&&Number.isInteger(r.activity_seq)&&r.activity_seq>fromCursor.activity_seq&&r.activity_seq<=end).sort((a,b)=>a.activity_seq-b.activity_seq);
  if(rows.length&&((rows[0].activity_cursor_before?.receipt_sha256??null)!==(fromCursor.receipt_sha256??null)||rows[0].activity_seq!==fromCursor.activity_seq+1))return {schema:'S4_ACTIVITY_DELTA_V1',available:false,reason:'ACTIVITY_SEQUENCE_GAP',from_cursor:copy(fromCursor),truncated:true};
  const counts={},targets=[],critical=[];let charged=0,rollovers=0,lastEpoch=null;
  for(const r of rows){
    counts[r.op]=(counts[r.op]||0)+1;charged+=Number(r.charged_bytes||0);
    if(lastEpoch!=null&&r.epoch_seq!==lastEpoch)rollovers++;lastEpoch=r.epoch_seq;
    const q=r.safe_request||{},s=r.safe_result||{},target=s.path||q.path||null;
    if(target&&!targets.includes(target)&&targets.length<8)targets.push(target);
    if((r.op==='proposal_write'||r.state==='AMBIGUOUS_CHARGED'||s.error_class)&&critical.length<6)critical.push({seq:r.activity_seq,op:r.op,state:r.state,path:target,sha256:s.sha256||null,error_class:s.error_class||null,read_back_verified:s.read_back_verified??null});
  }
  const last=rows.length?rows[rows.length-1]:null;
  const toCursor={schema:S4_ACTIVITY_CURSOR_SCHEMA,task_admission_id:record.task_admission_id,activity_seq:end,receipt_sha256:end===0?null:(last&&last.activity_seq===end?last.activity_sha256:record.activity_integrity_sha256)};
  const max=Math.max(1,Math.min(96,limit)),events=rows.slice(Math.max(0,rows.length-max)).map(r=>({seq:r.activity_seq,op:r.op,state:r.state,charged_bytes:r.charged_bytes,epoch_seq:r.epoch_seq,created_utc:r.created_utc,committed_utc:r.committed_utc||null,safe_request:copy(r.safe_request||{}),safe_result:copy(r.safe_result||{}),activity_sha256:r.activity_sha256}));
  return {schema:'S4_ACTIVITY_DELTA_V1',available:true,from_cursor:copy(fromCursor),to_cursor:toCursor,request_count:rows.length,charged_result_bytes:charged,operation_counts:counts,safe_targets:targets,critical_events:critical,epoch_rollovers:rollovers,events,truncated:rows.length>events.length,receipt_identity:toCursor.receipt_sha256};
}
