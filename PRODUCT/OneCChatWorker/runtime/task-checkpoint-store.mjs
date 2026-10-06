import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

export const TASK_CHECKPOINT_SCHEMA='TASK_CHECKPOINT_V1';
export const TASK_CHECKPOINT_HEAD_SCHEMA='TASK_CHECKPOINT_HEAD_V1';
export const RECOVERY_PACKAGE_SCHEMA='RECOVERY_PACKAGE_V1';
export const ACTIVITY_CURSOR_SCHEMA='S4_ACTIVITY_CURSOR_V1';

const CHECKPOINT_MAX_BYTES=4096;
const SEMANTIC_MAX_BYTES=2048;
const MAX_VERSIONS=16;
const TEXT_ITEM_MAX_BYTES=192;
const textEncoder=new TextEncoder();
const locks=new Map();

const bytes=v=>Buffer.isBuffer(v)||v instanceof Uint8Array?v.length:Buffer.byteLength(typeof v==='string'?v:JSON.stringify(v),'utf8');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const stable=v=>Array.isArray(v)?v.map(stable):(v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v);
const stableBytes=v=>Buffer.from(JSON.stringify(stable(v)),'utf8');
const fail=code=>{const e=new Error(code);e.code=code;throw e;};
const safeId=v=>typeof v==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(v);
const hex64=v=>typeof v==='string'&&/^[A-Fa-f0-9]{64}$/.test(v);
const utf8=(v,max,required=false)=>{
  if(v==null){if(required)fail('CHECKPOINT_FIELD_REQUIRED');return '';}
  if(typeof v!=='string')fail('CHECKPOINT_TEXT_INVALID');
  const n=v.normalize('NFC').replace(/\r\n?/g,'\n').trim();
  if(required&&!n)fail('CHECKPOINT_FIELD_REQUIRED');
  if(bytes(n)>max)fail('CHECKPOINT_TEXT_CAP');
  if(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(n))fail('CHECKPOINT_TEXT_CONTROL_CHAR');
  return n;
};
const relPath=(v,max=260)=>{
  const n=utf8(v,max,true).replaceAll('\\','/').replace(/^\/+|\/+$/g,'');
  if(!n||path.posix.isAbsolute(n)||/^[A-Za-z]:/.test(n)||n.split('/').some(x=>!x||x==='.'||x==='..'))fail('CHECKPOINT_REFERENCE_PATH_INVALID');
  return n;
};
const arrText=(value,maxItems)=>{
  if(value==null)return [];
  if(!Array.isArray(value)||value.length>maxItems)fail('CHECKPOINT_ARRAY_CAP');
  return value.map(x=>utf8(x,TEXT_ITEM_MAX_BYTES,true));
};
const canonicalWithout=(obj,key)=>{const x={...obj};delete x[key];return x;};
const objectSha=(obj,key)=>sha(stableBytes(canonicalWithout(obj,key)));

function normalizeSourceRefs(value){
  if(value==null)return [];
  if(!Array.isArray(value)||value.length>6)fail('CHECKPOINT_SOURCE_REF_CAP');
  return value.map(x=>{
    if(!x||typeof x!=='object'||Array.isArray(x))fail('CHECKPOINT_SOURCE_REF_INVALID');
    const out={path:relPath(x.path,260),sha256:String(x.sha256||'').toLowerCase()};
    if(!hex64(out.sha256))fail('CHECKPOINT_SOURCE_REF_SHA_INVALID');
    if(x.start!=null||x.end!=null){
      if(!Number.isInteger(x.start)||!Number.isInteger(x.end)||x.start<1||x.end<x.start)fail('CHECKPOINT_SOURCE_REF_RANGE_INVALID');
      out.start=x.start;out.end=x.end;
    }
    return out;
  });
}
function normalizeProposalRefs(value){
  if(value==null)return [];
  if(!Array.isArray(value)||value.length>4)fail('CHECKPOINT_PROPOSAL_REF_CAP');
  return value.map(x=>{
    if(!x||typeof x!=='object'||Array.isArray(x))fail('CHECKPOINT_PROPOSAL_REF_INVALID');
    const out={path:relPath(x.path,180),sha256:String(x.sha256||'').toLowerCase()};
    if(!hex64(out.sha256))fail('CHECKPOINT_PROPOSAL_REF_SHA_INVALID');
    return out;
  });
}
function normalizeMachineRefs(value){
  if(value==null)return [];
  if(!Array.isArray(value)||value.length>4)fail('CHECKPOINT_MACHINE_REF_CAP');
  return value.map(x=>{
    if(!x||typeof x!=='object'||Array.isArray(x))fail('CHECKPOINT_MACHINE_REF_INVALID');
    const out={operation_id:utf8(x.operation_id,128,true)};
    if(x.sha256!=null){out.sha256=String(x.sha256).toLowerCase();if(!hex64(out.sha256))fail('CHECKPOINT_MACHINE_REF_SHA_INVALID');}
    return out;
  });
}
function normalizeSemantic(args){
  if(!args||typeof args!=='object'||Array.isArray(args))fail('CHECKPOINT_REQUEST_INVALID');
  const status=String(args.status||'');
  const semantic={
    phase:utf8(args.phase,64,true),
    status,
    progress_summary:utf8(args.progress_summary,640,true),
    completed_steps:arrText(args.completed_steps,6),
    decisions_constraints:arrText(args.decisions_constraints,6),
    unresolved_questions:arrText(args.unresolved_questions,4),
    first_unfinished_step:utf8(args.first_unfinished_step,320,status!=='COMPLETED'),
    do_not_replay:arrText(args.do_not_replay,6),
    source_evidence_refs:normalizeSourceRefs(args.source_evidence_refs),
    proposal_refs:normalizeProposalRefs(args.proposal_refs),
    machine_operation_refs:normalizeMachineRefs(args.machine_operation_refs),
    assumptions_requiring_confirmation:arrText(args.assumptions_requiring_confirmation,4)
  };
  if(!['IN_PROGRESS','BLOCKED','COMPLETED'].includes(semantic.status))fail('CHECKPOINT_STATUS_INVALID');
  if(semantic.status==='COMPLETED'&&semantic.first_unfinished_step)fail('CHECKPOINT_COMPLETED_HAS_UNFINISHED_STEP');
  if(semantic.source_evidence_refs.length+semantic.proposal_refs.length+semantic.machine_operation_refs.length>12)fail('CHECKPOINT_REFERENCE_CAP');
  if(bytes(stableBytes(semantic))>SEMANTIC_MAX_BYTES)fail('CHECKPOINT_SEMANTIC_BYTE_CAP');
  return semantic;
}
function validateCursor(cursor,taskAdmissionId){
  if(!cursor||cursor.schema!==ACTIVITY_CURSOR_SCHEMA||cursor.task_admission_id!==taskAdmissionId||!Number.isInteger(cursor.activity_seq)||cursor.activity_seq<0)fail('ACTIVITY_CURSOR_UNAVAILABLE');
  if(cursor.receipt_sha256!=null&&!hex64(cursor.receipt_sha256))fail('ACTIVITY_CURSOR_INVALID');
  if(cursor.activity_seq===0&&cursor.receipt_sha256!=null)fail('ACTIVITY_CURSOR_INVALID');
  if(cursor.activity_seq>0&&cursor.receipt_sha256==null)fail('ACTIVITY_CURSOR_INVALID');
  return {schema:ACTIVITY_CURSOR_SCHEMA,task_admission_id:cursor.task_admission_id,activity_seq:cursor.activity_seq,receipt_sha256:cursor.receipt_sha256??null};
}
function cpFilename(seq,h){return String(seq).padStart(8,'0')+'-'+h+'.json';}

async function atomicJson(file,obj){
  const dir=path.dirname(file);await fsp.mkdir(dir,{recursive:true});
  const temp=path.join(dir,'.'+path.basename(file)+'.'+crypto.randomUUID()+'.tmp');
  const data=stableBytes(obj);
  const fh=await fsp.open(temp,'wx',0o600);
  try{await fh.writeFile(data);await fh.sync();}finally{await fh.close();}
  await fsp.rename(temp,file);
}
async function readJson(file){
  const data=await fsp.readFile(file);
  let obj;try{obj=JSON.parse(data.toString('utf8'));}catch{fail('CHECKPOINT_STATE_CORRUPT');}
  return {obj,data};
}
async function exists(file){try{await fsp.access(file);return true;}catch{return false;}}

function headCore(cp,file,fileSha){
  const h={
    schema:TASK_CHECKPOINT_HEAD_SCHEMA,project_id:cp.project_id,task_id:cp.task_id,
    head_seq:cp.seq,head_checkpoint_id:cp.checkpoint_id,head_checkpoint_sha256:cp.checkpoint_sha256,
    head_checkpoint_file:path.basename(file),head_checkpoint_file_sha256:fileSha,head_task_admission_id:cp.task_admission_id,
    head_task_goal_sha256:cp.task_goal_sha256,head_source_snapshot_id:cp.source_snapshot_id,
    head_manifest_sha256:cp.manifest_sha256,head_status:cp.status,updated_utc:cp.created_utc
  };
  h.head_sha256=objectSha(h,'head_sha256');return h;
}
function verifyCheckpointObject(cp,expected){
  if(!cp||cp.schema!==TASK_CHECKPOINT_SCHEMA||!safeId(cp.project_id)||!safeId(cp.task_id)||!Number.isInteger(cp.seq)||cp.seq<1||!hex64(cp.checkpoint_sha256))fail('CHECKPOINT_STATE_CORRUPT');
  if(objectSha(cp,'checkpoint_sha256')!==String(cp.checkpoint_sha256).toLowerCase())fail('CHECKPOINT_STATE_CORRUPT');
  if(expected){
    if(cp.project_id!==expected.project_id||cp.task_id!==expected.task_id)fail('CHECKPOINT_STATE_CORRUPT');
    if(expected.sha256&&cp.checkpoint_sha256!==expected.sha256)fail('CHECKPOINT_STATE_CORRUPT');
    if(expected.seq&&cp.seq!==expected.seq)fail('CHECKPOINT_STATE_CORRUPT');
  }
  return cp;
}
function verifyHeadObject(head,identity){
  if(!head||head.schema!==TASK_CHECKPOINT_HEAD_SCHEMA||head.project_id!==identity.project_id||head.task_id!==identity.task_id||!Number.isInteger(head.head_seq)||head.head_seq<1||!hex64(head.head_checkpoint_sha256)||!hex64(head.head_checkpoint_file_sha256)||!hex64(head.head_sha256))fail('CHECKPOINT_STATE_CORRUPT');
  if(objectSha(head,'head_sha256')!==String(head.head_sha256).toLowerCase())fail('CHECKPOINT_STATE_CORRUPT');
  if(path.basename(String(head.head_checkpoint_file||''))!==String(head.head_checkpoint_file||''))fail('CHECKPOINT_STATE_CORRUPT');
  return head;
}

export function createTaskCheckpointStore({programDataRoot,admission,nowFactory=()=>new Date()}){
  if(!programDataRoot||!admission||!safeId(String(admission.project_id||''))||!safeId(String(admission.task_id||'')))fail('CHECKPOINT_ACTIVE_TASK_BINDING_INVALID');
  const identity={
    project_id:String(admission.project_id),task_id:String(admission.task_id),task_goal_sha256:admission.task_goal_sha256??null,
    task_admission_id:String(admission.task_admission_id||''),session_id:String(admission.session_id||''),
    source_snapshot_id:String(admission.source_snapshot_id||''),manifest_sha256:String(admission.manifest_sha256||'')
  };
  if(!/^[A-Fa-f0-9]{32}$/.test(identity.task_admission_id)||!/^[A-Fa-f0-9]{32}$/.test(identity.session_id)||!hex64(identity.manifest_sha256)||!identity.source_snapshot_id)fail('CHECKPOINT_ACTIVE_TASK_BINDING_INVALID');
  if(identity.task_goal_sha256!=null&&!hex64(identity.task_goal_sha256))fail('CHECKPOINT_ACTIVE_TASK_BINDING_INVALID');
  const root=path.join(programDataRoot,'task-state',identity.project_id,identity.task_id);
  const checkpoints=path.join(root,'checkpoints'),headPath=path.join(root,'head.json');
  const lockKey=root.toLowerCase();

  async function readHeadVerified(){
    if(!await exists(headPath))return null;
    const {obj:head}=await readJson(headPath);verifyHeadObject(head,identity);
    const cpPath=path.join(checkpoints,head.head_checkpoint_file);
    const {obj:cp,data:cpData}=await readJson(cpPath);
    if(sha(cpData)!==head.head_checkpoint_file_sha256)fail('CHECKPOINT_STATE_CORRUPT');
    verifyCheckpointObject(cp,{project_id:identity.project_id,task_id:identity.task_id,sha256:head.head_checkpoint_sha256,seq:head.head_seq});
    return {head,checkpoint:cp,path:cpPath};
  }
  async function listCheckpointFiles(){
    if(!await exists(checkpoints))return [];
    const names=(await fsp.readdir(checkpoints)).filter(x=>/^\d{8}-[a-f0-9]{64}\.json$/.test(x)).sort();
    if(names.length>64)fail('CHECKPOINT_STATE_CORRUPT');
    return names;
  }
  async function findIdempotency(key){
    let match=null;
    for(const name of await listCheckpointFiles()){
      const file=path.join(checkpoints,name);const {obj}=await readJson(file);verifyCheckpointObject(obj,{project_id:identity.project_id,task_id:identity.task_id});
      if(obj.idempotency_key!==key)continue;
      if(match)fail('CHECKPOINT_STATE_CORRUPT');
      match={checkpoint:obj,path:file};
    }
    return match;
  }
  async function pruneVersions(headSeq){
    const rows=[];
    for(const name of await listCheckpointFiles()){
      const seq=Number(name.slice(0,8));if(Number.isInteger(seq)&&seq<=headSeq-MAX_VERSIONS)rows.push({name,seq});
    }
    for(const row of rows)await fsp.rm(path.join(checkpoints,row.name),{force:true});
  }
  function receipt(cp,currentHead,replayed=false,superseded=false){
    const out={status:'COMMITTED',checkpoint_id:cp.checkpoint_id,seq:cp.seq,sha256:cp.checkpoint_sha256,current_head:currentHead,replayed:!!replayed,superseded:!!superseded,size:stableBytes(cp).length,activity_cursor:cp.activity_cursor};
    if(bytes(out)>512)fail('CHECKPOINT_RECEIPT_CAP');
    return out;
  }
  async function writeUnlocked(args,internal={},options={}){
    const key=utf8(args.idempotency_key,64,true);if(!/^[A-Za-z0-9._-]+$/.test(key))fail('CHECKPOINT_IDEMPOTENCY_KEY_INVALID');
    if(!Number.isInteger(args.expected_seq)||args.expected_seq<0||args.expected_seq>1000000)fail('CHECKPOINT_EXPECTED_SEQ_INVALID');
    const pred=args.expected_predecessor_sha256==null?null:String(args.expected_predecessor_sha256).toLowerCase();
    if(pred!=null&&!hex64(pred))fail('CHECKPOINT_EXPECTED_PREDECESSOR_INVALID');
    if((args.expected_seq===0)!==(pred===null))fail('CHECKPOINT_EXPECTED_HEAD_INVALID');
    const semantic=normalizeSemantic(args);
    const cursor=validateCursor(internal.activity_cursor_before,identity.task_admission_id);
    if(!Number.isInteger(internal.writer_epoch_seq)||internal.writer_epoch_seq<0)fail('ACTIVITY_CURSOR_UNAVAILABLE');
    const fingerprint=sha(stableBytes({project_id:identity.project_id,task_id:identity.task_id,task_admission_id:identity.task_admission_id,idempotency_key:key,expected_seq:args.expected_seq,expected_predecessor_sha256:pred,semantic}));

    const prior=await findIdempotency(key);
    if(prior){
      if(prior.checkpoint.request_fingerprint!==fingerprint)fail('IDEMPOTENCY_KEY_REUSE');
      const hv=await readHeadVerified();
      if(hv&&hv.head.head_checkpoint_sha256===prior.checkpoint.checkpoint_sha256)return receipt(prior.checkpoint,true,true,false);
      if(hv&&hv.head.head_seq>prior.checkpoint.seq)return receipt(prior.checkpoint,false,true,true);
      const currentSeq=hv?.head.head_seq??0,currentSha=hv?.head.head_checkpoint_sha256??null;
      if(currentSeq===args.expected_seq&&currentSha===pred&&prior.checkpoint.seq===currentSeq+1&&prior.checkpoint.predecessor_sha256===currentSha){
        const priorRaw=await fsp.readFile(prior.path);const h=headCore(prior.checkpoint,prior.path,sha(priorRaw));await atomicJson(headPath,h);
        const rb=await readHeadVerified();if(!rb||rb.head.head_checkpoint_sha256!==prior.checkpoint.checkpoint_sha256)fail('CHECKPOINT_HEAD_READBACK_FAILED');
        await pruneVersions(rb.head.head_seq);return receipt(prior.checkpoint,true,true,false);
      }
      return {status:'STALE_CHECKPOINT_HEAD',current_seq:currentSeq,current_head_sha256:currentSha,replayed:true,orphan_checkpoint_sha256:prior.checkpoint.checkpoint_sha256};
    }

    const hv=await readHeadVerified();
    const currentSeq=hv?.head.head_seq??0,currentSha=hv?.head.head_checkpoint_sha256??null;
    if(currentSeq!==args.expected_seq||currentSha!==pred)return {status:'STALE_CHECKPOINT_HEAD',current_seq:currentSeq,current_head_sha256:currentSha,replayed:false};

    const cp={
      schema:TASK_CHECKPOINT_SCHEMA,project_id:identity.project_id,task_id:identity.task_id,task_goal_sha256:identity.task_goal_sha256,
      task_admission_id:identity.task_admission_id,source_snapshot_id:identity.source_snapshot_id,manifest_sha256:identity.manifest_sha256,
      checkpoint_id:crypto.randomUUID(),seq:currentSeq+1,predecessor_sha256:currentSha,created_utc:nowFactory().toISOString(),
      writer_session_id:identity.session_id,writer_epoch_seq:internal.writer_epoch_seq,activity_cursor:cursor,
      idempotency_key:key,request_fingerprint:fingerprint,...semantic
    };
    cp.checkpoint_sha256=objectSha(cp,'checkpoint_sha256');
    const encoded=stableBytes(cp);
    if(encoded.length>CHECKPOINT_MAX_BYTES)fail('CHECKPOINT_CANONICAL_BYTE_CAP');
    const file=path.join(checkpoints,cpFilename(cp.seq,cp.checkpoint_sha256));
    await fsp.mkdir(checkpoints,{recursive:true});
    const fh=await fsp.open(file,'wx',0o600);try{const body=stableBytes(cp);await fh.writeFile(body);await fh.sync();}finally{await fh.close();}
    const {obj:rb,data:rbData}=await readJson(file);verifyCheckpointObject(rb,{project_id:identity.project_id,task_id:identity.task_id,sha256:cp.checkpoint_sha256,seq:cp.seq});
    if(rbData.length>CHECKPOINT_MAX_BYTES)fail('CHECKPOINT_READBACK_BYTE_CAP');
    if(options.fault==='AFTER_FILE_COMMIT')fail('INJECTED_AFTER_FILE_COMMIT');
    const h=headCore(rb,file,sha(rbData));await atomicJson(headPath,h);
    if(options.fault==='AFTER_HEAD_COMMIT')fail('INJECTED_AFTER_HEAD_COMMIT');
    const checked=await readHeadVerified();if(!checked||checked.head.head_checkpoint_sha256!==rb.checkpoint_sha256)fail('CHECKPOINT_HEAD_READBACK_FAILED');
    await pruneVersions(checked.head.head_seq);
    return receipt(rb,true,false,false);
  }
  async function write(args,internal={},options={}){
    const prev=locks.get(lockKey)||Promise.resolve();
    let release;const gate=new Promise(r=>{release=r;});const chain=prev.then(()=>gate);locks.set(lockKey,chain);
    await prev;
    try{return await writeUnlocked(args,internal,options);}finally{release();if(locks.get(lockKey)===chain)locks.delete(lockKey);}
  }

  function cursorEqual(a,b){
    return !!a&&!!b&&a.schema===ACTIVITY_CURSOR_SCHEMA&&b.schema===ACTIVITY_CURSOR_SCHEMA&&
      a.task_admission_id===b.task_admission_id&&a.activity_seq===b.activity_seq&&(a.receipt_sha256??null)===(b.receipt_sha256??null);
  }
  function unavailableDelta(cursor,to,reason){
    return {schema:'S4_ACTIVITY_DELTA_V1',available:false,from_cursor:cursor,to_cursor:to??null,request_count:0,charged_result_bytes:0,operation_counts:{},critical_events:[],safe_targets:[],epoch_rollovers:0,truncated:true,reason};
  }
  function verifyDelta(delta,cursor){
    if(!delta||delta.schema!=='S4_ACTIVITY_DELTA_V1'||delta.available!==true)return {ok:false,reason:delta?.reason||'ACTIVITY_DELTA_UNAVAILABLE'};
    if(!cursorEqual(delta.from_cursor,cursor))return {ok:false,reason:'ACTIVITY_CURSOR_MISMATCH'};
    if(!delta.to_cursor||delta.to_cursor.schema!==ACTIVITY_CURSOR_SCHEMA)return {ok:false,reason:'ACTIVITY_DELTA_INVALID'};
    if(!Number.isInteger(delta.request_count)||delta.request_count<0||!Number.isInteger(delta.charged_result_bytes)||delta.charged_result_bytes<0)return {ok:false,reason:'ACTIVITY_DELTA_INVALID'};
    return {ok:true};
  }
  function mergeCounts(a,b){
    const out={};for(const src of [a||{},b||{}])for(const [k,v] of Object.entries(src)){if(Number.isInteger(v)&&v>=0)out[k]=(out[k]||0)+v;}return out;
  }
  function summarizeDelta(cp,activity){
    const cursor=cp.activity_cursor;
    if(cp.task_admission_id===identity.task_admission_id){
      const d=activity?.activity_delta,check=verifyDelta(d,cursor);
      if(!check.ok)return unavailableDelta(cursor,activity?.activity_cursor_before,check.reason);
      return {
        schema:'S4_ACTIVITY_DELTA_V1',available:true,from_cursor:cursor,to_cursor:d.to_cursor,
        request_count:d.request_count,charged_result_bytes:d.charged_result_bytes,operation_counts:d.operation_counts||{},
        critical_events:(d.critical_events||[]).slice(0,6),safe_targets:(d.safe_targets||[]).slice(0,8),
        epoch_rollovers:Number(d.epoch_rollovers||0),truncated:!!d.truncated,receipt_identity:d.receipt_identity??d.to_cursor?.receipt_sha256??null
      };
    }
    const pred=admission.predecessor||null;
    if(!pred||pred.task_admission_id!==cp.task_admission_id)return unavailableDelta(cursor,activity?.activity_cursor_before,'TASK_ADMISSION_ACTIVITY_UNAVAILABLE');
    const pd=activity?.predecessor_activity_delta,pcheck=verifyDelta(pd,cursor);
    if(!pcheck.ok)return unavailableDelta(cursor,activity?.activity_cursor_before,pcheck.reason);
    const zero={schema:ACTIVITY_CURSOR_SCHEMA,task_admission_id:identity.task_admission_id,activity_seq:0,receipt_sha256:null};
    const cd=activity?.activity_delta,ccheck=verifyDelta(cd,zero);
    if(!ccheck.ok)return unavailableDelta(cursor,activity?.activity_cursor_before,ccheck.reason);
    const targets=[];for(const x of [...(pd.safe_targets||[]),...(cd.safe_targets||[])])if(x&&!targets.includes(x)&&targets.length<8)targets.push(x);
    const critical=[...(pd.critical_events||[]),...(cd.critical_events||[])].slice(0,6);
    return {
      schema:'S4_ACTIVITY_DELTA_V1',available:true,from_cursor:cursor,to_cursor:cd.to_cursor,
      request_count:Number(pd.request_count||0)+Number(cd.request_count||0),
      charged_result_bytes:Number(pd.charged_result_bytes||0)+Number(cd.charged_result_bytes||0),
      operation_counts:mergeCounts(pd.operation_counts,cd.operation_counts),critical_events:critical,safe_targets:targets,
      epoch_rollovers:Number(pd.epoch_rollovers||0)+Number(cd.epoch_rollovers||0),truncated:!!pd.truncated||!!cd.truncated,
      receipt_identity:cd.receipt_identity??cd.to_cursor?.receipt_sha256??pd.receipt_identity??pd.to_cursor?.receipt_sha256??null,
      crossed_task_admission:true
    };
  }
  function compatibility(cp){
    if(cp.task_goal_sha256!==identity.task_goal_sha256)return {compatibility:'TASK_GOAL_MISMATCH',continued:false};
    if(cp.source_snapshot_id!==identity.source_snapshot_id||cp.manifest_sha256!==identity.manifest_sha256)return {compatibility:'SOURCE_SNAPSHOT_STALE',continued:false};
    if(cp.task_admission_id===identity.task_admission_id)return {compatibility:cp.status==='COMPLETED'?'COMPLETED':'CURRENT',continued:false};
    const pred=admission.predecessor||null;
    if(pred&&pred.task_admission_id===cp.task_admission_id){
      if(pred.checkpoint_sha256!==cp.checkpoint_sha256)return {compatibility:'SUPERSEDED',continued:true};
      return {compatibility:cp.status==='COMPLETED'?'COMPLETED':'CURRENT',continued:true};
    }
    return {compatibility:'TASK_ADMISSION_STALE',continued:false};
  }
  function boundedRecovery(cp,comp,delta,maxBytes){
    const sourceStale=comp.compatibility==='SOURCE_SNAPSHOT_STALE';
    const required={
      schema:RECOVERY_PACKAGE_SCHEMA,compatibility:comp.compatibility,continued_from_predecessor:comp.continued,
      checkpoint:{checkpoint_id:cp.checkpoint_id,seq:cp.seq,sha256:cp.checkpoint_sha256,created_utc:cp.created_utc,phase:cp.phase,status:cp.status,progress_summary:cp.progress_summary,first_unfinished_step:cp.first_unfinished_step},
      activity_delta:delta,recovery_next_action:cp.status==='COMPLETED'?'TASK_COMPLETE':cp.first_unfinished_step,
      invalidated_sections:sourceStale?['source_evidence_refs','do_not_replay']:[],recovery_complete:true,truncated:false
    };
    const optional=[
      ['completed_steps',cp.completed_steps],['decisions_constraints',cp.decisions_constraints],['unresolved_questions',cp.unresolved_questions],
      ['do_not_replay',sourceStale?[]:cp.do_not_replay],['source_evidence_refs',sourceStale?[]:cp.source_evidence_refs],
      ['proposal_refs',cp.proposal_refs],['machine_operation_refs',cp.machine_operation_refs],['assumptions_requiring_confirmation',cp.assumptions_requiring_confirmation]
    ];
    const out=structuredClone(required);
    for(const [k,v] of optional){
      if(!v||!v.length)continue;
      const candidate={...out,checkpoint:{...out.checkpoint,[k]:v}};
      if(bytes(stableBytes(candidate))<=maxBytes)out.checkpoint[k]=v;
      else{out.recovery_complete=false;out.truncated=true;}
    }
    if(!delta.available||delta.truncated){out.recovery_complete=false;out.truncated=true;}
    if(bytes(stableBytes(out))>maxBytes){
      out.activity_delta={available:delta.available,from_cursor:delta.from_cursor,to_cursor:delta.to_cursor,request_count:delta.request_count,charged_result_bytes:delta.charged_result_bytes,operation_counts:delta.operation_counts,truncated:true,reason:delta.reason,receipt_identity:delta.receipt_identity};
      out.recovery_complete=false;out.truncated=true;
    }
    if(bytes(stableBytes(out))>maxBytes)fail('RECOVERY_PACKAGE_HARD_CAP');
    return out;
  }
  async function recovery(activity,maxBytes=1450){
    let hv;try{hv=await readHeadVerified();}catch(e){return {schema:RECOVERY_PACKAGE_SCHEMA,compatibility:'CORRUPT',recovery_available:true,first_unfinished_step:'Repair corrupt local task checkpoint state before continuing.',activity_delta:{available:false,truncated:true,reason:'CHECKPOINT_STATE_CORRUPT'},recovery_complete:false,truncated:true};}
    if(!hv)return {schema:RECOVERY_PACKAGE_SCHEMA,compatibility:'CURRENT',recovery_available:false,first_unfinished_step:null,activity_delta:{available:true,request_count:0,charged_result_bytes:0,operation_counts:{},critical_events:[],safe_targets:[],epoch_rollovers:0,truncated:false},recovery_complete:true,truncated:false};
    const comp=compatibility(hv.checkpoint),delta=summarizeDelta(hv.checkpoint,activity||{});
    const out=boundedRecovery(hv.checkpoint,comp,delta,maxBytes);out.recovery_available=true;return out;
  }
  return {root,headPath,checkpoints,identity,write,recovery,readHeadVerified};
}
