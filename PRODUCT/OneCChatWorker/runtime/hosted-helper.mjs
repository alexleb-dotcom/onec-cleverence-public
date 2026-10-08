import { HttpsPullHelper } from './helper-https-pull.mjs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { SourceReaderIntegration, PROVIDER_VERSION } from '../provider/source-reader-integration.mjs';
import { LocalQualityAdapter, boundedTargetHints, reportBindingMatches } from './local-quality-adapter.mjs';
import { createTaskCheckpointStore } from './task-checkpoint-store.mjs';
import { createSerializedMessagePump, persistAndSendProcessed, saveStateAtomic, loadPersistedState, safePersistenceCode } from './helper-state-coordinator.mjs';

const PROGRAM_DATA = process.env.ONECCHAT_PROGRAM_DATA || 'C:\\ProgramData\\OneCChatWorker';
const ADMISSION_PATH = process.env.ONECCHAT_ADMISSION_PATH || path.join(PROGRAM_DATA,'runtime','active-admission.json');

const admission = JSON.parse(await fsp.readFile(ADMISSION_PATH,'utf8'));
if (![1,2,3].includes(admission.schema_version)) throw new Error('ADMISSION_SCHEMA_UNSUPPORTED');
const IS_S4 = admission.schema_version === 3;
const PROJECT = String(admission.project_id || '');
const TASK = String(admission.task_id || '');
if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(PROJECT)) throw new Error('ADMISSION_PROJECT_INVALID');
if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(TASK)) throw new Error('ADMISSION_TASK_INVALID');
const TASK_GOAL = admission.task_goal == null ? null : String(admission.task_goal);
if (TASK_GOAL !== null) {
  if (!TASK_GOAL.trim() || Buffer.byteLength(TASK_GOAL,'utf8') > 1024) throw new Error('ADMISSION_TASK_GOAL_INVALID');
  const expectedGoalHash=crypto.createHash('sha256').update(Buffer.from(TASK_GOAL,'utf8')).digest('hex');
  if (String(admission.task_goal_sha256||'') !== expectedGoalHash) throw new Error('ADMISSION_TASK_GOAL_HASH_MISMATCH');
} else if (admission.task_goal_sha256 != null) throw new Error('ADMISSION_TASK_GOAL_BINDING_INVALID');

const CONFIG_PATH = admission.provider_config_path || path.join(PROGRAM_DATA,'provider','provider-config.json');
const MANIFEST_PATH = admission.manifest_path;
const RELAY = admission.relay_url;
const SECRET_PATH = admission.helper_secret_path || path.join(PROGRAM_DATA,'secrets','helper-secret.txt');
const RUNTIME_DIR = admission.runtime_dir || path.join(PROGRAM_DATA,'runtime');
const STATE_PATH = path.join(RUNTIME_DIR,'hosted-helper-state.json');
const LOG_PATH = path.join(RUNTIME_DIR,'hosted-helper-log.jsonl');
const UI_PROJECTION_PATH = path.join(RUNTIME_DIR,'s4-ui-projection.json');
const VERSION = 'onecchat-hosted-helper/1.2.1';

if (typeof RELAY !== 'string' || !/^wss:\/\//.test(RELAY)) throw new Error('ADMISSION_RELAY_INVALID');
if (typeof MANIFEST_PATH !== 'string' || !MANIFEST_PATH) throw new Error('ADMISSION_MANIFEST_MISSING');

const manifestText = await fsp.readFile(MANIFEST_PATH,'utf8');
const manifestHash = crypto.createHash('sha256').update(Buffer.from(manifestText,'utf8')).digest('hex');
const manifest = JSON.parse(manifestText);
if (String(manifest.project_id) !== PROJECT) throw new Error('MANIFEST_PROJECT_MISMATCH');
if (admission.schema_version >= 2) {
  if (manifest.schema_version !== 2 || !manifest.accepted_snapshot) throw new Error('SNAPSHOT_MANIFEST_INVALID');
  if (admission.snapshot_contract !== 'ACCEPTED_SNAPSHOT_V1' || manifest.accepted_snapshot.snapshot_contract !== 'ACCEPTED_SNAPSHOT_V1') throw new Error('SNAPSHOT_CONTRACT_MISMATCH');
  if (String(admission.manifest_sha256 || '') !== manifestHash) throw new Error('ADMISSION_MANIFEST_HASH_MISMATCH');
  if (String(admission.source_snapshot_id || '') !== String(manifest.accepted_snapshot.source_snapshot_id || '')) throw new Error('ADMISSION_SOURCE_SNAPSHOT_MISMATCH');
}

const normalizePath = p => String(p).replaceAll('\\','/').replace(/^\/+|\/+$/g,'');
const safeArtifact = p => {
  const s = normalizePath(p);
  if (!s.startsWith('Participants/')) throw new Error('MANIFEST_ARTIFACT_SCOPE_INVALID');
  if (s.split('/').some(x => !x || x === '.' || x === '..')) throw new Error('MANIFEST_ARTIFACT_SCOPE_INVALID');
  return s;
};
function collectArtifacts(doc){
  const out=[];
  for(const p of Array.isArray(doc.participants)?doc.participants:[]){
    if(p?.active===false) continue;
    const pid=String(p?.participant_id||'');
    const platform=String(p?.platform||'');
    for(const side of ['target','reference']){
      const group=p?.[side]; if(!group) continue;
      const main=group.main;
      if(main && main.active!==false && main.canonical_path) out.push({participant_id:pid,platform,side:side.toUpperCase(),artifact_type:'MAIN',artifact_id:'main',path:safeArtifact(main.canonical_path)});
      for(const ext of Array.isArray(group.extensions)?group.extensions:[]){
        if(ext?.active===false || !ext?.canonical_path) continue;
        out.push({participant_id:pid,platform,side:side.toUpperCase(),artifact_type:'EXTENSION',artifact_id:String(ext.extension_id||ext.artifact_id||''),path:safeArtifact(ext.canonical_path)});
      }
    }
  }
  if(!out.length) throw new Error('MANIFEST_HAS_NO_ACTIVE_ARTIFACTS');
  return out;
}
const ARTIFACTS = collectArtifacts(manifest);
const artifactPrefixes = ARTIFACTS.map(x=>x.path);

const caps={
  ttl_minutes:Number(admission?.caps?.ttl_minutes||360),
  max_requests:Number(admission?.caps?.max_requests||32),
  max_cumulative_result_bytes:Number(admission?.caps?.max_cumulative_result_bytes||36000),
  task_request_limit:Number(admission?.caps?.task_request_limit||admission?.caps?.max_requests||32),
  task_result_byte_limit:Number(admission?.caps?.task_result_byte_limit||admission?.caps?.max_cumulative_result_bytes||36000),
  epoch_soft_request_limit:Number(admission?.caps?.epoch_soft_request_limit||32),
  epoch_soft_result_byte_limit:Number(admission?.caps?.epoch_soft_result_byte_limit||36000),
  max_result_bytes:Number(admission?.caps?.max_result_bytes||3000),
  max_search_matches:Number(admission?.caps?.max_search_matches||8),
  max_read_lines:Number(admission?.caps?.max_read_lines||20),
  max_write_file_bytes:Number(admission?.caps?.max_write_file_bytes||32768),
  max_task_bytes:Number(admission?.caps?.max_task_bytes||131072),
  max_task_files:Number(admission?.caps?.max_task_files||8),
  max_read_chunk_bytes:Number(admission?.caps?.max_read_chunk_bytes||1800),
};
for(const [k,v] of Object.entries(caps)) if(!Number.isInteger(v)||v<1) throw new Error('ADMISSION_CAP_INVALID:'+k);
const TASK_ADMISSION_ID=IS_S4?String(admission.task_admission_id||''):null;
const STABLE_SESSION_ID=IS_S4?String(admission.session_id||''):null;
const TASK_CREATED_UTC=IS_S4?String(admission.task_created_utc||admission.created_utc||''):null;
const TASK_EXPIRES_UTC=IS_S4?String(admission.task_expires_utc||''):null;
const OUTPUT_TASK_ROOT=IS_S4?String(admission.output_task_root||''):'Output/'+TASK;
if(IS_S4){
  if(!/^[A-Fa-f0-9]{32}$/.test(TASK_ADMISSION_ID)||!/^[A-Fa-f0-9]{32}$/.test(STABLE_SESSION_ID))throw new Error('S4_TASK_IDENTITY_INVALID');
  if(!TASK_CREATED_UTC||!TASK_EXPIRES_UTC||!Number.isFinite(Date.parse(TASK_CREATED_UTC))||!Number.isFinite(Date.parse(TASK_EXPIRES_UTC))||Date.parse(TASK_EXPIRES_UTC)<=Date.parse(TASK_CREATED_UTC))throw new Error('S4_TASK_EXPIRY_INVALID');
  if(OUTPUT_TASK_ROOT!=='Output/'+TASK)throw new Error('S4_OUTPUT_TASK_BINDING_INVALID');
  for(const k of ['task_request_limit','task_result_byte_limit','epoch_soft_request_limit','epoch_soft_result_byte_limit'])if(!(k in (admission.caps||{})))throw new Error('S4_TASK_CAP_MISSING:'+k);
  if(caps.epoch_soft_request_limit>caps.task_request_limit||caps.epoch_soft_result_byte_limit>caps.task_result_byte_limit||caps.max_result_bytes>caps.epoch_soft_result_byte_limit)throw new Error('S4_TASK_CAP_INVALID');
}

const PROV_PATH='_proposal_provenance.json';
const allowedProposalExt=new Set(['.md','.txt','.diff','.patch','.bsl','.json']);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function saveUiProjection(projection){
  if(!IS_S4||!projection||projection.schema!=='S4_UI_PROJECTION_V1')return;
  if(String(projection.task_admission_id||'')!==TASK_ADMISSION_ID)return;
  const bytes=Buffer.from(JSON.stringify(projection),'utf8');
  if(bytes.length>32768)throw new Error('UI_PROJECTION_CAP');
  const tmp=UI_PROJECTION_PATH+'.tmp';
  await fsp.writeFile(tmp,bytes);
  await fsp.rename(tmp,UI_PROJECTION_PATH);
}
const sha256=b=>crypto.createHash('sha256').update(b).digest('hex');
async function log(x){await fsp.appendFile(LOG_PATH,JSON.stringify({at_utc:new Date().toISOString(),...x})+'\n','utf8').catch(()=>{});}
async function saveState(s){await saveStateAtomic(STATE_PATH,s);}
const SNAPSHOT = admission.schema_version >= 2
  ? String(admission.source_snapshot_id)
  : (admission.source_snapshot_id || sha256(Buffer.from('OneCChatWorker-snapshot-v1\n'+manifestHash,'utf8')));
const checkpointStore=IS_S4?createTaskCheckpointStore({programDataRoot:PROGRAM_DATA,admission}):null;
async function loadState(){
  if(IS_S4){
    const existing=await loadPersistedState(STATE_PATH,{schema_version:2,task_admission_id:TASK_ADMISSION_ID,session_id:STABLE_SESSION_ID,project_id:PROJECT,task_id:TASK,snapshot_id:SNAPSHOT,manifest_sha256:manifestHash,expires_utc:TASK_EXPIRES_UTC});
    if(existing){if(Date.now()>=Date.parse(existing.expires_utc))throw new Error('TASK_EXPIRED');return existing;}
  }
  if(!IS_S4)try{
    const s=JSON.parse(await fsp.readFile(STATE_PATH,'utf8'));
    const s4ok=!IS_S4||(s.task_admission_id===TASK_ADMISSION_ID&&s.session_id===STABLE_SESSION_ID&&s.manifest_sha256===manifestHash&&s.expires_utc===TASK_EXPIRES_UTC);
    if(s.project_id===PROJECT && s.task_id===TASK && s.snapshot_id===SNAPSHOT && s4ok && Date.now()<Date.parse(s.expires_utc)) return s;
  }catch{}
  if(IS_S4){
    const s={schema_version:2,task_admission_id:TASK_ADMISSION_ID,session_id:STABLE_SESSION_ID,project_id:PROJECT,task_id:TASK,snapshot_id:SNAPSHOT,manifest_sha256:manifestHash,started_utc:TASK_CREATED_UTC,expires_utc:TASK_EXPIRES_UTC,processed:{},idempotency:{},quality_targets:[]};
    await saveState(s);return s;
  }
  const started=new Date(),expires=new Date(started.getTime()+caps.ttl_minutes*60000);
  const s={schema_version:1,session_id:crypto.randomBytes(16).toString('hex'),project_id:PROJECT,task_id:TASK,snapshot_id:SNAPSHOT,started_utc:started.toISOString(),expires_utc:expires.toISOString(),processed:{},idempotency:{},quality_targets:[]};
  await saveState(s); return s;
}

let state=await loadState();
if(!Array.isArray(state.quality_targets))state.quality_targets=[];
const provider=new SourceReaderIntegration({configPath:CONFIG_PATH,getDeviceId:()=> 'onecchat-hosted-helper'});
await provider.initialize();
const quality=new LocalQualityAdapter({projectRoot:String(manifest.project_root||''),artifacts:ARTIFACTS,projectId:PROJECT,taskId:TASK,sessionId:state.session_id,sourceSnapshotId:SNAPSHOT,manifestSha256:manifestHash});

function fail(code,msg=code){const e=new Error(msg);e.code=code;throw e;}
function pathAllowed(p){
  const s=normalizePath(p);
  if(/^[A-Za-z]:/.test(String(p))||String(p).startsWith('/')||String(p).startsWith('\\\\')) return false;
  if(s.split('/').some(x=>!x||x==='.'||x==='..')) return false;
  return artifactPrefixes.some(pre=>s===pre||s.startsWith(pre+'/'));
}
function proposalPath(p){
  if(typeof p!=='string'||p.length<1||p.length>180)fail('INVALID_PATH');
  if(/^[A-Za-z]:/.test(p)||p.startsWith('/')||p.startsWith('\\\\')||p.includes(':'))fail('PATH_ESCAPE');
  const s=normalizePath(p),parts=s.split('/');
  if(parts.some(x=>!x||x==='.'||x==='..'))fail('PATH_ESCAPE');
  if(s===PROV_PATH)fail('PROVENANCE_RESERVED');
  const ext=path.posix.extname(s).toLowerCase();
  if(!allowedProposalExt.has(ext))fail('FILE_TYPE_NOT_ALLOWED');
  return s;
}
function idemKey(v){if(typeof v!=='string'||!/^[A-Za-z0-9._-]{1,64}$/.test(v))fail('INVALID_IDEMPOTENCY_KEY');return v;}

async function artifactRead(rel){
  try{
    const r=await provider.callClientTool('artifact_read',{project_slug:PROJECT,task_slug:TASK,relative_path:rel,encoding:'utf8'},{transport:'onecchat-hosted'});
    return r.structuredContent;
  }catch(e){
    if(['TASK_OUTPUT_NOT_FOUND','NOT_FOUND'].includes(String(e?.code||''))) return null;
    throw e;
  }
}
async function loadProvenance(){
  const r=await artifactRead(PROV_PATH); if(!r)return {doc:null,sha256:null};
  let doc;try{doc=JSON.parse(r.content);}catch{fail('PROVENANCE_INVALID');}
  if(doc.project_id!==PROJECT||doc.task_id!==TASK||doc.source_snapshot_id!==SNAPSHOT||doc.status!=='PROPOSAL_NOT_APPLIED')fail('PROVENANCE_BINDING_MISMATCH');
  return {doc,sha256:r.sha256};
}
async function saveProvenance(doc,expected){
  doc.updated_utc=new Date().toISOString();
  const a={project_slug:PROJECT,task_slug:TASK,relative_path:PROV_PATH,content:JSON.stringify(doc,null,2)+'\n',encoding:'utf8'};
  if(expected){a.replace=true;a.expected_sha256=expected;}
  return (await provider.callClientTool('artifact_write',a,{transport:'onecchat-hosted'})).structuredContent;
}
async function updateProvenance(rel,size,hash){
  const cur=await loadProvenance();
  const doc=cur.doc||{schema_version:1,status:'PROPOSAL_NOT_APPLIED',project_id:PROJECT,source_snapshot_id:SNAPSHOT,manifest_sha256:manifestHash,task_id:TASK,created_utc:new Date().toISOString(),session_id:state.session_id,helper_version:VERSION,provider_version:PROVIDER_VERSION,artifact_scope:ARTIFACTS,files:[]};
  const files=Array.isArray(doc.files)?doc.files:[],i=files.findIndex(x=>x.path===rel),old=i>=0?Number(files[i].size||0):0;
  const count=i>=0?files.length:files.length+1,total=files.reduce((n,x)=>n+Number(x.size||0),0)-old+size;
  if(count>caps.max_task_files)fail('TASK_FILE_CAP');
  if(total>caps.max_task_bytes)fail('TASK_BYTE_CAP');
  const item={path:rel,size,sha256:hash,updated_utc:new Date().toISOString()};
  if(i>=0)files[i]=item;else files.push(item);
  doc.files=files.sort((a,b)=>a.path.localeCompare(b.path,'en'));
  doc.total_files=doc.files.length;doc.total_bytes=doc.files.reduce((n,x)=>n+Number(x.size||0),0);
  await saveProvenance(doc,cur.sha256);return doc;
}
async function proposalWrite(args){
  const key=idemKey(args?.idempotency_key),rel=proposalPath(args?.path);
  if(typeof args?.content!=='string')fail('INVALID_CONTENT');
  const buf=Buffer.from(args.content,'utf8'); if(buf.length>caps.max_write_file_bytes)fail('FILE_BYTE_CAP');
  const replace=args?.replace===true,expected=args?.expected_sha256;
  if(replace&&(!expected||!/^[A-Fa-f0-9]{64}$/.test(expected)))fail('EXPECTED_SHA256_REQUIRED');
  const hash=sha256(buf),fingerprint=sha256(Buffer.from(JSON.stringify({rel,hash,replace,expected:expected?.toLowerCase()||null}),'utf8'));
  const prior=state.idempotency?.[key];
  if(prior){if(prior.fingerprint!==fingerprint)fail('IDEMPOTENCY_KEY_REUSE');return {...prior.receipt,replayed:true};}
  const cur=await loadProvenance(),files=cur.doc?.files||[],old=files.find(x=>x.path===rel);
  if((old?files.length:files.length+1)>caps.max_task_files)fail('TASK_FILE_CAP');
  if(files.reduce((n,x)=>n+Number(x.size||0),0)-Number(old?.size||0)+buf.length>caps.max_task_bytes)fail('TASK_BYTE_CAP');
  let existing=await artifactRead(rel),recovered=false,result;
  if(existing&&!replace){
    if(existing.sha256!==hash)fail('FILE_EXISTS');
    result={relative_path:rel,size:existing.size,sha256:existing.sha256,replaced:false};recovered=true;
  }else if(existing&&replace&&existing.sha256===hash){
    result={relative_path:rel,size:existing.size,sha256:existing.sha256,replaced:true};recovered=true;
  }else{
    const w={project_slug:PROJECT,task_slug:TASK,relative_path:rel,content:args.content,encoding:'utf8',replace};
    if(replace)w.expected_sha256=expected;
    result=(await provider.callClientTool('artifact_write',w,{transport:'onecchat-hosted'})).structuredContent;
  }
  const rb=await artifactRead(rel);
  if(!rb||rb.sha256!==hash||rb.size!==buf.length)fail('READ_BACK_VERIFY_FAILED');
  await updateProvenance(rel,rb.size,rb.sha256);
  const receipt={status:'COMMITTED',project_id:PROJECT,task_id:TASK,relative_path:rel,size:rb.size,sha256:rb.sha256,replaced:!!result.replaced,recovered_commit:recovered,read_back_verified:true,provenance_path:PROV_PATH,source_snapshot_id:SNAPSHOT,idempotency_key:key};
  state.idempotency=state.idempotency||{};state.idempotency[key]={fingerprint,receipt};await saveState(state);return receipt;
}
async function proposalRead(args){
  const rel=args?.path===PROV_PATH?PROV_PATH:proposalPath(args?.path);
  const start=Number.isInteger(args?.start)?args.start:1,end=Number.isInteger(args?.end)?args.end:start+19;
  if(start<1||end<start||(end-start+1)>caps.max_read_lines)fail('INVALID_READ_ARGS');
  const r=await artifactRead(rel);if(!r)fail('NOT_FOUND');
  const lines=r.content.split(/\r?\n/),slice=lines.slice(start-1,end),content=slice.join('\n');
  if(Buffer.byteLength(content,'utf8')>caps.max_read_chunk_bytes)fail('READ_CHUNK_BYTE_CAP');
  return {project_id:PROJECT,task_id:TASK,relative_path:rel,range:[start,start+slice.length-1],total_lines:lines.length,size:r.size,sha256:r.sha256,complete:start-1+slice.length>=lines.length,content};
}
async function sourceSearch(args){
  if(!args||typeof args.query!=='string'||args.query.length<1||args.query.length>256)fail('INVALID_SEARCH_ARGS');
  const max=args.max_matches??caps.max_search_matches;if(!Number.isInteger(max)||max<1||max>caps.max_search_matches)fail('INVALID_SEARCH_LIMIT');
  const matches=[];let scans=0,complete=true,truncated=false;
  for(const a of ARTIFACTS){
    if(matches.length>=max){truncated=true;break;}
    const r=await provider.callClientTool('source_search',{project_slug:PROJECT,source_domain:'ONEC',pattern:args.query,relative_scope:a.path,glob:'*.bsl',max_matches:max-matches.length,before:1,after:1},{transport:'onecchat-hosted'});
    const v=r.structuredContent;scans+=Number(v.files_scanned||0);complete=complete&&!!v.scan_complete;truncated=truncated||!!v.results_truncated;
    for(const m of v.matches||[]) matches.push({participant_id:a.participant_id,artifact_type:a.artifact_type,artifact_id:a.artifact_id,path:m.path,line:m.line,range:[m.context.start_line,m.context.end_line],context:m.context.lines.map(x=>({line:x.line,text:x.text}))});
  }
  return {query:args.query,matches,files_scanned:scans,scan_complete:complete,results_truncated:truncated};
}
async function qualityPathHash(rel){
  const s=normalizePath(rel);
  if(!pathAllowed(s))return null;
  try{return sha256(await fsp.readFile(path.join(String(manifest.project_root),s.replaceAll('/',path.sep))));}catch{return null;}
}
async function reportFresh(report){
  if(!reportBindingMatches(report,{projectId:PROJECT,taskId:TASK,sessionId:state.session_id,sourceSnapshotId:SNAPSHOT,manifestSha256:manifestHash}))return false;
  if(!report.confirming_read||await qualityPathHash(report.confirming_read.relative_path)!==report.confirming_read.sha256)return false;
  if(!Array.isArray(report.input_closure)||!report.input_closure.length)return false;
  const rows=[];
  for(const row of report.input_closure){const h=await qualityPathHash(row.relative_path);if(!h||h!==row.sha256)return false;rows.push({relative_path:row.relative_path,sha256:h});}
  return sha256(Buffer.from(JSON.stringify(rows.sort((a,b)=>a.relative_path.localeCompare(b.relative_path,'en'))),'utf8'))===report.input_closure_sha256;
}
async function freshPreparedQuality(){
  try{await quality.verifyToolset();}catch{if(state.quality_targets.length){state.quality_targets=[];await saveState(state);}return null;}
  const keep=[];
  for(const item of state.quality_targets.slice(0,2)){
    let ok=Array.isArray(item.reports)&&item.reports.length>0;
    if(ok)for(const report of item.reports){if(!await reportFresh(report)){ok=false;break;}}
    if(ok)keep.push(item);
  }
  if(keep.length!==state.quality_targets.length){state.quality_targets=keep;await saveState(state);}
  return keep[0]?.prepared||null;
}
async function cacheQuality(result){
  if(!result?.prepared)return;
  const item={target_relative:result.binding.target_relative,confirmed_at_utc:new Date().toISOString(),prepared:result.prepared,reports:result.reports};
  state.quality_targets=[item,...state.quality_targets.filter(x=>x.target_relative!==item.target_relative)].slice(0,2);
  await saveState(state);
}

async function exec(op,args){
  const t=performance.now();
  try{
    if(Date.now()>=Date.parse(state.expires_utc))fail(IS_S4?'TASK_EXPIRED':'SESSION_EXPIRED');
    if(op==='context'){
      const payload={task_admission_id:TASK_ADMISSION_ID,session_id:state.session_id,snapshot_id:SNAPSHOT,manifest_sha256:manifestHash,helper_version:VERSION,provider_version:PROVIDER_VERSION,project_id:PROJECT,participants:ARTIFACTS,task_id:TASK,task_goal_sha256:admission.task_goal_sha256??null,canonical_project_root:manifest.project_root||null,output_task_root:OUTPUT_TASK_ROOT,status:'PROPOSAL_NOT_APPLIED',task_created_utc:IS_S4?TASK_CREATED_UTC:state.started_utc,task_expires_utc:state.expires_utc,checkpoint_support:IS_S4?'TASK_CHECKPOINT_V1':'UNAVAILABLE_LEGACY_ADMISSION',caps:{...caps,accounting_owner:'relay'}};
      if(IS_S4&&checkpointStore)payload.recovery=await checkpointStore.recovery(args?.__s4||{},1350);
      const prepared=await freshPreparedQuality();
      if(prepared){const c={...payload,prepared_quality:prepared};if(Buffer.byteLength(JSON.stringify(c),'utf8')<=caps.max_result_bytes)payload.prepared_quality=prepared;}
      const hints=await boundedTargetHints({taskGoal:TASK_GOAL,projectRoot:String(manifest.project_root||''),artifacts:ARTIFACTS}).catch(()=>[]);
      if(hints.length){const c={...payload,target_hints:hints};if(Buffer.byteLength(JSON.stringify(c),'utf8')<=caps.max_result_bytes)payload.target_hints=hints;}
      return {status:'OK',metadata:{op,elapsed_ms:+(performance.now()-t).toFixed(3)},payload};
    }
    if(op==='search')return {status:'OK',metadata:{op,elapsed_ms:+(performance.now()-t).toFixed(3)},payload:await sourceSearch(args)};
    if(op==='read'){
      if(!args||typeof args.path!=='string'||!Number.isInteger(args.start)||!Number.isInteger(args.end)||args.start<1||args.end<args.start||(args.end-args.start+1)>caps.max_read_lines)fail('INVALID_READ_ARGS');
      const rel=normalizePath(args.path);if(!pathAllowed(args.path))fail('PATH_OUTSIDE_ADMITTED_PROJECT');
      const r=await provider.callClientTool('source_read',{project_slug:PROJECT,source_domain:'ONEC',relative_path:rel,offset:args.start-1,length:args.end-args.start+1},{transport:'onecchat-hosted'});
      const v=r.structuredContent,payload={content:v.content},metadata={op,elapsed_ms:+(performance.now()-t).toFixed(3),relative_path:rel,range:[v.offset+1,v.offset+v.length],sha256:v.sha256,total_lines:v.total_lines};
      try{
        const q=await quality.runConfirmed(rel,v.sha256);
        if(q){await cacheQuality(q);const c={...payload,prepared_quality:q.prepared};if(q.prepared&&Buffer.byteLength(JSON.stringify(c),'utf8')<=caps.max_result_bytes)payload.prepared_quality=q.prepared;}
      }catch(qe){
        state.quality_targets=[];await saveState(state);
        metadata.quality_error_class=String(qe?.code||qe?.name||'QUALITY_EXECUTION_ERROR');
      }
      metadata.elapsed_ms=+(performance.now()-t).toFixed(3);
      return {status:'OK',metadata,payload};
    }
    if(op==='proposal_write')return {status:'OK',metadata:{op,elapsed_ms:+(performance.now()-t).toFixed(3)},payload:await proposalWrite(args)};
    if(op==='proposal_read')return {status:'OK',metadata:{op,elapsed_ms:+(performance.now()-t).toFixed(3)},payload:await proposalRead(args)};
    if(op==='task_checkpoint_write'){
      if(!IS_S4||!checkpointStore)fail('CHECKPOINT_SUPPORT_UNAVAILABLE_LEGACY_ADMISSION');
      for(const ref of (args?.source_evidence_refs||[]))if(!pathAllowed(ref?.path))fail('CHECKPOINT_SOURCE_REF_OUTSIDE_ADMISSION');
      for(const ref of (args?.proposal_refs||[]))proposalPath(ref?.path);
      const internal=args?.__s4;if(!internal)fail('ACTIVITY_CURSOR_UNAVAILABLE');
      const modelArgs={...args};delete modelArgs.__s4;
      const receipt=await checkpointStore.write(modelArgs,{activity_cursor_before:internal.activity_cursor_before,writer_epoch_seq:internal.writer_epoch_seq});
      return {status:'OK',metadata:{op,elapsed_ms:+(performance.now()-t).toFixed(3)},payload:receipt};
    }
    fail('UNKNOWN_OP');
  }catch(e){return {status:'ERROR',metadata:{op,elapsed_ms:+(performance.now()-t).toFixed(3),error_class:String(e?.code||e?.name||'ERROR')},payload:{error:String(e?.message||e).slice(0,400)}};}
}
// Advisory disk I/O must not hold the execution/readiness lane after a result
// has been persisted and sent. Keep projections/logs ordered across reconnects;
// this lane never reads or mutates the processed cache or Source.
const advisoryPump=createSerializedMessagePump({handle:async message=>{
  if(message.type==='ui_projection_slot'){
    try{
      while(pendingUiProjection){
        const projection=pendingUiProjection;pendingUiProjection=null;
        try{await saveUiProjection(projection);}catch(e){
          await log({event:'UI_PROJECTION_REJECTED',error:String(e?.message||e).slice(0,120)}).catch(()=>{});
        }
      }
    }finally{uiProjectionQueued=false;}
    return;
  }
  try{
    await log(message.entry);
  }catch{}
}});
let advisoryLogsQueued=0,pendingUiProjection=null,uiProjectionQueued=false;
const queueAdvisory=message=>{
  if(message.type==='ui_projection'){
    // Keep the newest projection when disk is delayed; never accumulate full
    // historical projections or replay an older UI state after reconnect.
    pendingUiProjection=message.projection;
    if(!uiProjectionQueued){uiProjectionQueued=true;void advisoryPump.dispatch({type:'ui_projection_slot'});}
    return;
  }
  // Logging is best effort. A stuck disk must not create an unbounded queue
  // as the authoritative request lane continues to make progress.
  if(advisoryLogsQueued>=64)return;
  message={...message,entry:{at_utc:new Date().toISOString(),...message.entry}};
  advisoryLogsQueued++;
  void advisoryPump.dispatch(message).finally(()=>{advisoryLogsQueued--;});
};
async function handleRelayMessage(ws,ev){
  let m;try{m=JSON.parse(ev.data);}catch{return;}
  // Transport-only challenge; no Source execution, processed cache or S4 usage.
  if(m.type==='transport_ping'){
    if(typeof m.nonce==='string'&&/^[0-9a-f-]{36}$/i.test(m.nonce))ws.send(JSON.stringify({type:'transport_pong',nonce:m.nonce}));
    return;
  }
  if(m.type==='hello_ack'){queueAdvisory({entry:{event:'S4_HELLO_ACK',task_admission_id:TASK_ADMISSION_ID,session_id:state.session_id,epoch_id:m.lifecycle?.epoch_id,epoch_seq:m.lifecycle?.epoch_seq,task_requests_used:m.lifecycle?.accounting?.task_requests_used,task_result_bytes_used:m.lifecycle?.accounting?.task_result_bytes_used}});return;}
  if(m.type==='ui_projection'){queueAdvisory(m);return;}
  if(m.type==='hello_error'){queueAdvisory({entry:{event:'S4_HELLO_REJECTED',error:String(m.error||'TASK_ADMISSION_REJECTED')}});return;}
  if(m.type!=='request'||!m.request_id)return;
  if(state.processed[m.request_id]){ws.send(JSON.stringify(state.processed[m.request_id]));return;}
  const res=await exec(m.op,m.args);
  const attemptedPayloadBytes=Buffer.byteLength(JSON.stringify(res.payload??null),'utf8');
  if(attemptedPayloadBytes>caps.max_result_bytes){
    res.status='ERROR';res.metadata={...res.metadata,error_class:'RESULT_CAP',attempted_payload_bytes:attemptedPayloadBytes,max_result_bytes:caps.max_result_bytes};res.payload={error:'RESULT_CAP'};
  }else res.metadata={...res.metadata,attempted_payload_bytes:attemptedPayloadBytes,max_result_bytes:caps.max_result_bytes};
  const out={type:'result',request_id:m.request_id,status:res.status,metadata:res.metadata,payload:res.payload};
  await persistAndSendProcessed({
    state,requestId:m.request_id,result:out,
    persist:saveState,
    send:async stored=>ws.send(JSON.stringify(stored))
  });
  queueAdvisory({entry:{event:'RESULT',request_id:m.request_id,op:m.op,status:res.status,attempted_payload_bytes:attemptedPayloadBytes,elapsed_ms:res.metadata.elapsed_ms}});
}
async function connectLoop(){
  const secret=(await fsp.readFile(SECRET_PATH,'utf8')).trim(); if(secret.length<20)throw new Error('HELPER_SECRET_INVALID');
  if(IS_S4){
    const hello={
        type:'hello',admission_schema_version:3,task_admission_id:TASK_ADMISSION_ID,session_id:state.session_id,project_id:PROJECT,task_id:TASK,task_goal_sha256:admission.task_goal_sha256??null,
        manifest_sha256:manifestHash,snapshot_id:SNAPSHOT,output_task_root:OUTPUT_TASK_ROOT,helper_version:VERSION,task_created_utc:TASK_CREATED_UTC,task_expires_utc:TASK_EXPIRES_UTC,
        predecessor:admission.predecessor??null,
        controlled_restart_done:false,caps:{task_request_limit:caps.task_request_limit,task_result_byte_limit:caps.task_result_byte_limit,epoch_soft_request_limit:caps.epoch_soft_request_limit,epoch_soft_result_byte_limit:caps.epoch_soft_result_byte_limit,max_result_bytes:caps.max_result_bytes}
      };
    await new HttpsPullHelper({relayUrl:RELAY,secret,hello,state,persist:saveState,handle:handleRelayMessage,onProjection:projection=>queueAdvisory({type:'ui_projection',projection})}).run();
    return;
  }
  while(Date.now()<Date.parse(state.expires_utc)){
    try{
      const ws=new WebSocket(RELAY+'?token='+encodeURIComponent(secret));
      await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
      const hello=IS_S4?{
        type:'hello',admission_schema_version:3,task_admission_id:TASK_ADMISSION_ID,session_id:state.session_id,project_id:PROJECT,task_id:TASK,task_goal_sha256:admission.task_goal_sha256??null,
        manifest_sha256:manifestHash,snapshot_id:SNAPSHOT,output_task_root:OUTPUT_TASK_ROOT,helper_version:VERSION,task_created_utc:TASK_CREATED_UTC,task_expires_utc:TASK_EXPIRES_UTC,
        predecessor:admission.predecessor??null,
        controlled_restart_done:false,caps:{task_request_limit:caps.task_request_limit,task_result_byte_limit:caps.task_result_byte_limit,epoch_soft_request_limit:caps.epoch_soft_request_limit,epoch_soft_result_byte_limit:caps.epoch_soft_result_byte_limit,max_result_bytes:caps.max_result_bytes}
      }:{type:'hello',session_id:state.session_id,snapshot_id:SNAPSHOT,helper_version:VERSION,started_utc:state.started_utc,expires_utc:state.expires_utc,task_id:TASK,caps:{max_requests:caps.max_requests,max_cumulative_result_bytes:caps.max_cumulative_result_bytes,max_result_bytes:caps.max_result_bytes}};
      let fatalPersistenceError=null;
      await new Promise(resolve=>{
        const pump=createSerializedMessagePump({
          handle:ev=>handleRelayMessage(ws,ev),
          onFailure:async(error,ev)=>{
            let failedMessage=null;try{failedMessage=JSON.parse(ev?.data);}catch{}
            const errorClass=String(error?.code||error?.name||'MESSAGE_HANDLER_ERROR');
            await log({event:'MESSAGE_HANDLER_ERROR',request_id:failedMessage?.request_id??null,op:failedMessage?.op??null,error_class:errorClass,error:String(error?.message||error).slice(0,240)});
            if(errorClass==='HELPER_STATE_PERSIST_FAILED')fatalPersistenceError=error;
            try{ws.close(1011,'message handler failure');}catch{}
          }
        });
        ws.addEventListener('message',ev=>{void pump.dispatch(ev);});
        const settle=()=>{void pump.drain().finally(resolve);};
        ws.addEventListener('close',settle,{once:true});
        ws.addEventListener('error',settle,{once:true});
        // Install listeners before hello: an immediate ACK/probe/close must
        // not be lost while CONNECTED logging waits for Windows disk I/O.
        ws.send(JSON.stringify(hello));
        queueAdvisory({entry:{event:'CONNECTED',session_id:state.session_id,snapshot_id:SNAPSHOT,project_id:PROJECT,task_id:TASK}});
      });
      if(fatalPersistenceError)throw fatalPersistenceError;
    }catch(e){
      const errorClass=String(e?.code||e?.name||'ERROR');
      if(errorClass==='HELPER_STATE_PERSIST_FAILED'){
        await log({event:'HELPER_STATE_PERSISTENCE_FATAL',error_class:errorClass,cause_code:String(e?.cause_code||''),error:String(e?.message||e).slice(0,240)});
        throw e;
      }
      await log({event:'CONNECT_ERROR',error_class:errorClass,error:String(e?.message||e).slice(0,300)});
    }
    await sleep(1000);
  }
}
let fatalHelperError=null;
try{await connectLoop();}
catch(e){
  fatalHelperError=e;
  await log({event:'HELPER_FATAL',error_class:String(e?.code||e?.name||'ERROR'),cause_code:safePersistenceCode(e),persist_phase:e?.persist_phase??null,error:String(e?.message||e).slice(0,240)});
}
finally{await advisoryPump.drain();await provider.shutdown().catch(()=>{});}
if(fatalHelperError)process.exitCode=1;
