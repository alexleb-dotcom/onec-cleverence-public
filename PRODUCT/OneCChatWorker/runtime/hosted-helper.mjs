import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { SourceReaderIntegration, PROVIDER_VERSION } from '../provider/source-reader-integration.mjs';

const PROGRAM_DATA = process.env.ONECCHAT_PROGRAM_DATA || 'C:\\ProgramData\\OneCChatWorker';
const ADMISSION_PATH = process.env.ONECCHAT_ADMISSION_PATH || path.join(PROGRAM_DATA,'runtime','active-admission.json');

const admission = JSON.parse(await fsp.readFile(ADMISSION_PATH,'utf8'));
if (admission.schema_version !== 1) throw new Error('ADMISSION_SCHEMA_UNSUPPORTED');
const PROJECT = String(admission.project_id || '');
const TASK = String(admission.task_id || '');
if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(PROJECT)) throw new Error('ADMISSION_PROJECT_INVALID');
if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(TASK)) throw new Error('ADMISSION_TASK_INVALID');

const CONFIG_PATH = admission.provider_config_path || path.join(PROGRAM_DATA,'provider','provider-config.json');
const MANIFEST_PATH = admission.manifest_path;
const RELAY = admission.relay_url;
const SECRET_PATH = admission.helper_secret_path || path.join(PROGRAM_DATA,'secrets','helper-secret.txt');
const RUNTIME_DIR = admission.runtime_dir || path.join(PROGRAM_DATA,'runtime');
const STATE_PATH = path.join(RUNTIME_DIR,'hosted-helper-state.json');
const LOG_PATH = path.join(RUNTIME_DIR,'hosted-helper-log.jsonl');
const VERSION = 'onecchat-hosted-helper/1.0.0';

if (typeof RELAY !== 'string' || !/^wss:\/\//.test(RELAY)) throw new Error('ADMISSION_RELAY_INVALID');
if (typeof MANIFEST_PATH !== 'string' || !MANIFEST_PATH) throw new Error('ADMISSION_MANIFEST_MISSING');

const manifestText = await fsp.readFile(MANIFEST_PATH,'utf8');
const manifest = JSON.parse(manifestText);
if (String(manifest.project_id) !== PROJECT) throw new Error('MANIFEST_PROJECT_MISMATCH');

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
  max_result_bytes:Number(admission?.caps?.max_result_bytes||3000),
  max_search_matches:Number(admission?.caps?.max_search_matches||8),
  max_read_lines:Number(admission?.caps?.max_read_lines||20),
  max_write_file_bytes:Number(admission?.caps?.max_write_file_bytes||32768),
  max_task_bytes:Number(admission?.caps?.max_task_bytes||131072),
  max_task_files:Number(admission?.caps?.max_task_files||8),
  max_read_chunk_bytes:Number(admission?.caps?.max_read_chunk_bytes||1800),
};
for(const [k,v] of Object.entries(caps)) if(!Number.isInteger(v)||v<1) throw new Error('ADMISSION_CAP_INVALID:'+k);

const PROV_PATH='_proposal_provenance.json';
const allowedProposalExt=new Set(['.md','.txt','.diff','.patch','.bsl','.json']);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sha256=b=>crypto.createHash('sha256').update(b).digest('hex');
async function log(x){await fsp.appendFile(LOG_PATH,JSON.stringify({at_utc:new Date().toISOString(),...x})+'\n','utf8').catch(()=>{});}
async function saveState(s){const t=STATE_PATH+'.tmp';await fsp.writeFile(t,JSON.stringify(s,null,2),'utf8');await fsp.rename(t,STATE_PATH);}
async function loadState(){
  try{
    const s=JSON.parse(await fsp.readFile(STATE_PATH,'utf8'));
    if(s.project_id===PROJECT && s.task_id===TASK && Date.now()<Date.parse(s.expires_utc)) return s;
  }catch{}
  const started=new Date(),expires=new Date(started.getTime()+caps.ttl_minutes*60000);
  const s={schema_version:1,session_id:crypto.randomBytes(16).toString('hex'),project_id:PROJECT,task_id:TASK,started_utc:started.toISOString(),expires_utc:expires.toISOString(),processed:{},idempotency:{}};
  await saveState(s); return s;
}

const manifestHash=sha256(Buffer.from(manifestText,'utf8'));
const SNAPSHOT = admission.source_snapshot_id || sha256(Buffer.from('OneCChatWorker-snapshot-v1\n'+manifestHash,'utf8'));
let state=await loadState();
const provider=new SourceReaderIntegration({configPath:CONFIG_PATH,getDeviceId:()=> 'onecchat-hosted-helper'});
await provider.initialize();

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
async function exec(op,args){
  const t=performance.now();
  try{
    if(Date.now()>=Date.parse(state.expires_utc))fail('SESSION_EXPIRED');
    if(op==='context')return {status:'OK',metadata:{op,local_ms:+(performance.now()-t).toFixed(3)},payload:{session_id:state.session_id,snapshot_id:SNAPSHOT,manifest_sha256:manifestHash,helper_version:VERSION,provider_version:PROVIDER_VERSION,project_id:PROJECT,participants:ARTIFACTS,task_id:TASK,canonical_project_root:manifest.project_root||null,output_task_root:'Output/'+TASK,status:'PROPOSAL_NOT_APPLIED',expires_utc:state.expires_utc,caps:{...caps,accounting_owner:'relay'}}};
    if(op==='search')return {status:'OK',metadata:{op,local_ms:+(performance.now()-t).toFixed(3)},payload:await sourceSearch(args)};
    if(op==='read'){
      if(!args||typeof args.path!=='string'||!Number.isInteger(args.start)||!Number.isInteger(args.end)||args.start<1||args.end<args.start||(args.end-args.start+1)>caps.max_read_lines)fail('INVALID_READ_ARGS');
      const rel=normalizePath(args.path);if(!pathAllowed(args.path))fail('PATH_OUTSIDE_ADMITTED_PROJECT');
      const r=await provider.callClientTool('source_read',{project_slug:PROJECT,source_domain:'ONEC',relative_path:rel,offset:args.start-1,length:args.end-args.start+1},{transport:'onecchat-hosted'});
      const v=r.structuredContent;return {status:'OK',metadata:{op,local_ms:+(performance.now()-t).toFixed(3),relative_path:rel,range:[v.offset+1,v.offset+v.length],sha256:v.sha256,total_lines:v.total_lines},payload:{content:v.content}};
    }
    if(op==='proposal_write')return {status:'OK',metadata:{op,local_ms:+(performance.now()-t).toFixed(3)},payload:await proposalWrite(args)};
    if(op==='proposal_read')return {status:'OK',metadata:{op,local_ms:+(performance.now()-t).toFixed(3)},payload:await proposalRead(args)};
    fail('UNKNOWN_OP');
  }catch(e){return {status:'ERROR',metadata:{op,local_ms:+(performance.now()-t).toFixed(3),error_class:String(e?.code||e?.name||'ERROR')},payload:{error:String(e?.message||e).slice(0,400)}};}
}
async function connectLoop(){
  const secret=(await fsp.readFile(SECRET_PATH,'utf8')).trim(); if(secret.length<20)throw new Error('HELPER_SECRET_INVALID');
  while(Date.now()<Date.parse(state.expires_utc)){
    try{
      const ws=new WebSocket(RELAY+'?token='+encodeURIComponent(secret));
      await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
      ws.send(JSON.stringify({type:'hello',session_id:state.session_id,snapshot_id:SNAPSHOT,helper_version:VERSION,started_utc:state.started_utc,expires_utc:state.expires_utc,task_id:TASK,caps:{max_requests:caps.max_requests,max_cumulative_result_bytes:caps.max_cumulative_result_bytes,max_result_bytes:caps.max_result_bytes}}));
      await log({event:'CONNECTED',session_id:state.session_id,snapshot_id:SNAPSHOT,project_id:PROJECT,task_id:TASK});
      await new Promise(resolve=>{
        ws.addEventListener('message',async ev=>{
          let m;try{m=JSON.parse(ev.data);}catch{return;}
          if(m.type!=='request'||!m.request_id)return;
          if(state.processed[m.request_id]){ws.send(JSON.stringify(state.processed[m.request_id]));return;}
          const res=await exec(m.op,m.args);
          const attemptedPayloadBytes=Buffer.byteLength(JSON.stringify(res.payload??null),'utf8');
          if(attemptedPayloadBytes>caps.max_result_bytes){
            res.status='ERROR';res.metadata={...res.metadata,error_class:'RESULT_CAP',attempted_payload_bytes:attemptedPayloadBytes,max_result_bytes:caps.max_result_bytes};res.payload={error:'RESULT_CAP'};
          }else res.metadata={...res.metadata,attempted_payload_bytes:attemptedPayloadBytes,max_result_bytes:caps.max_result_bytes};
          const out={type:'result',request_id:m.request_id,status:res.status,metadata:res.metadata,payload:res.payload};
          state.processed[m.request_id]=out;await saveState(state);ws.send(JSON.stringify(out));
          await log({event:'RESULT',request_id:m.request_id,op:m.op,status:res.status,attempted_payload_bytes:attemptedPayloadBytes,local_ms:res.metadata.local_ms});
        });
        ws.addEventListener('close',resolve,{once:true});ws.addEventListener('error',resolve,{once:true});
      });
    }catch(e){await log({event:'CONNECT_ERROR',error:String(e?.message||e).slice(0,300)});}
    await sleep(1000);
  }
}
try{await connectLoop();}finally{await provider.shutdown().catch(()=>{});}
