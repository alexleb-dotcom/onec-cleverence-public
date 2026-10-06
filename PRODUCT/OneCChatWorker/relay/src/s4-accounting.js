export const S4_ACCOUNTING_CONTRACT='S4_DURABLE_TASK_ACCOUNTING_V1';

const copy=x=>structuredClone(x);
const int=(v,min=1,max=Number.MAX_SAFE_INTEGER)=>Number.isInteger(v)&&v>=min&&v<=max;
const text=(v,max)=>typeof v==='string'&&v.length>0&&v.length<=max;
const iso=v=>typeof v==='string'&&Number.isFinite(Date.parse(v));
const fail=code=>{const e=new Error(code);e.code=code;throw e;};

export function validateS4Hello(h){
  if(!h||h.admission_schema_version!==3)fail('ADMISSION_SCHEMA_UNSUPPORTED');
  for(const [k,max] of [['task_admission_id',128],['session_id',128],['project_id',64],['task_id',64],['manifest_sha256',64],['snapshot_id',128],['output_task_root',256]])if(!text(h[k],max))fail('TASK_BINDING_INVALID:'+k);
  if(h.task_goal_sha256!=null&&!text(h.task_goal_sha256,64))fail('TASK_BINDING_INVALID:task_goal_sha256');
  if(!iso(h.task_created_utc)||!iso(h.task_expires_utc)||Date.parse(h.task_expires_utc)<=Date.parse(h.task_created_utc))fail('TASK_EXPIRY_INVALID');
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
    schema_version:1,accounting_contract:S4_ACCOUNTING_CONTRACT,
    task_admission_id:h.task_admission_id,session_id:h.session_id,project_id:h.project_id,task_id:h.task_id,
    task_goal_sha256:h.task_goal_sha256??null,manifest_sha256:h.manifest_sha256,snapshot_id:h.snapshot_id,output_task_root:h.output_task_root,
    task_created_utc:h.task_created_utc,task_expires_utc:h.task_expires_utc,
    task_request_limit:h.caps.task_request_limit,task_result_byte_limit:h.caps.task_result_byte_limit,
    epoch_soft_request_limit:h.caps.epoch_soft_request_limit,epoch_soft_result_byte_limit:h.caps.epoch_soft_result_byte_limit,max_result_bytes:h.caps.max_result_bytes,
    task_requests_used:0,task_result_bytes_used:0,
    epoch_id:epochIdFactory(),epoch_seq:0,epoch_requests_used:0,epoch_result_bytes_used:0,
    request_receipts:{},connected:true,helper_version:h.helper_version??null,controlled_restart_done:!!h.controlled_restart_done
  };
}

export function reconcileTaskHello(record,h,{nowMs=Date.now()}={}){
  validateS4Hello(h);
  if(!record||record.accounting_contract!==S4_ACCOUNTING_CONTRACT)fail('ACCOUNTING_STATE_UNAVAILABLE');
  for(const k of bindingFields){
    const a=record[k]??null,b=h[k]??null;
    if(a!==b)fail(k==='manifest_sha256'||k==='snapshot_id'?'SNAPSHOT_OR_MANIFEST_CHANGED':'TASK_ADMISSION_BINDING_MISMATCH');
  }
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
  return {
    accounting_contract:S4_ACCOUNTING_CONTRACT,
    task_admission_id:record.task_admission_id,
    session_id:record.session_id,
    task_state:state,
    task_created_utc:record.task_created_utc,
    task_expires_utc:record.task_expires_utc,
    epoch_id:record.epoch_id,
    epoch_seq:record.epoch_seq,
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

export function reserveRequest(record,{requestId,fingerprint,op,nowMs=Date.now(),epochIdFactory=()=>crypto.randomUUID()}){
  if(!record||record.accounting_contract!==S4_ACCOUNTING_CONTRACT)fail('ACCOUNTING_STATE_UNAVAILABLE');
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
  const receipt={request_id:requestId,fingerprint,op,state:'RESERVED',reserved_bytes:record.max_result_bytes,charged_bytes:0,epoch_seq:record.epoch_seq,epoch_id:record.epoch_id,created_utc:new Date(nowMs).toISOString()};
  record.task_requests_used+=1;record.epoch_requests_used+=1;
  record.request_receipts=record.request_receipts||{};record.request_receipts[requestId]=receipt;
  return {action:'EXECUTE',reservation:copy(receipt),record};
}

export function commitRequest(record,{requestId,fingerprint,payloadBytes,nowMs=Date.now()}){
  const r=record?.request_receipts?.[requestId];if(!r)fail('REQUEST_RESERVATION_MISSING');
  if(r.fingerprint!==fingerprint)fail('REQUEST_ID_REUSE');
  if(r.state!=='RESERVED')fail('REQUEST_RESERVATION_NOT_ACTIVE');
  if(!int(payloadBytes,0,r.reserved_bytes))fail('RESULT_CAP');
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
  r.state='AMBIGUOUS_CHARGED';r.charged_bytes=charge;r.reason=reason;r.committed_utc=new Date(nowMs).toISOString();delete r.reserved_bytes;
  return record;
}

export function projectCommittedRecord(record,{payloadBytes}){
  if(!int(payloadBytes,0,record.max_result_bytes))fail('RESULT_CAP');
  const projected=copy(record);
  projected.task_result_bytes_used+=payloadBytes;projected.epoch_result_bytes_used+=payloadBytes;
  return projected;
}

export function minimalControlPayload(record,nowMs=Date.now()){
  return lifecycleProjection(record,nowMs);
}
