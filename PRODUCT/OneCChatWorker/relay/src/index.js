import OAuthProvider, { AuthorizationError, CimdFetchError } from '@cloudflare/workers-oauth-provider';
import { createTaskRecord, reconcileTaskHello, reserveRequest, commitRequest, chargeAmbiguousRequest, lifecycleProjection, minimalControlPayload, projectCommittedRecord, activityReceiptHashInput, sealActivityReceipt, unsealedTerminalReceipts, activityDelta, latestCheckpointRequestCursor, S4_ACTIVITY_CURSOR_SCHEMA } from './s4-accounting.js';

const ORIGIN='https://onec-g1q1-relay.alex-lebad1.workers.dev';
const RESOURCE=ORIGIN+'/mcp';
const GITHUB_CALLBACK=ORIGIN+'/github/callback';
const ALLOWED_GITHUB_LOGIN='alexleb-dotcom';
const stable=v=>Array.isArray(v)?v.map(stable):(v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v);
async function requestFingerprint(op,args){
  const bytes=new TextEncoder().encode(JSON.stringify(stable({op,args})));
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
const payloadBytes=v=>new TextEncoder().encode(JSON.stringify(v??null)).length;
async function sha256HexValue(v){
  const bytes=new TextEncoder().encode(typeof v==='string'?v:JSON.stringify(stable(v)));
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
async function mcpAccountingRequestId(record,fingerprint){
  const taskAdmissionId=String(record?.task_admission_id||''),sessionId=String(record?.session_id||''),fp=String(fingerprint||'');
  if(!taskAdmissionId||!sessionId||!/^[a-f0-9]{64}$/.test(fp))throw new Error('REQUEST_IDENTITY_INVALID');
  return 'mcp-'+await sha256HexValue({schema:'MCP_ACCOUNTING_REQUEST_ID_V1',task_admission_id:taskAdmissionId,session_id:sessionId,fingerprint:fp});
}
function safeRequestMeta(op,args){
  const a=args||{};
  if(op==='search')return {query:String(a.query||'').slice(0,256),max_matches:Number(a.max_matches||8)};
  if(op==='read')return {path:String(a.path||'').slice(0,260),start:Number(a.start||0),end:Number(a.end||0)};
  if(op==='proposal_write')return {path:String(a.path||'').slice(0,180)};
  if(op==='proposal_read')return {path:String(a.path||'').slice(0,180),start:Number(a.start||1),end:Number(a.end||0)};
  if(op==='task_checkpoint_write')return {expected_seq:Number(a.expected_seq||0),phase:String(a.phase||'').slice(0,64),status:String(a.status||'').slice(0,16)};
  return {};
}
function safeResultMeta(op,result){
  const m=result?.metadata||{},p=result?.payload||{};
  const out={status:String(result?.status||'ERROR').slice(0,16)};
  if(Number.isFinite(Number(m.elapsed_ms)))out.duration_ms=Math.max(0,Math.round(Number(m.elapsed_ms)*1000)/1000);
  if(m.error_class)out.error_class=String(m.error_class).slice(0,96);
  if(op==='read'){if(m.relative_path)out.path=String(m.relative_path).slice(0,260);if(Array.isArray(m.range))out.range=m.range.slice(0,2);if(m.sha256)out.sha256=String(m.sha256).slice(0,64);}
  if(op==='proposal_write'){if(p.relative_path)out.path=String(p.relative_path).slice(0,180);if(p.sha256)out.sha256=String(p.sha256).slice(0,64);out.committed=p.status==='COMMITTED';out.read_back_verified=!!p.read_back_verified;out.recovered_commit=!!p.recovered_commit;}
  if(op==='proposal_read'){if(p.relative_path)out.path=String(p.relative_path).slice(0,180);if(p.sha256)out.sha256=String(p.sha256).slice(0,64);}
  if(op==='task_checkpoint_write'){
    out.checkpoint_receipt={
      status:String(p.status||result?.status||'ERROR').slice(0,32),checkpoint_id:p.checkpoint_id??null,seq:p.seq??null,sha256:p.sha256??null,
      current_head:p.current_head??null,replayed:!!p.replayed,superseded:!!p.superseded,size:p.size??null
    };
  }
  return out;
}
async function sealOneActivity(record,requestId,safeResult){
  const hashInput=activityReceiptHashInput(record,requestId,safeResult);
  const hash=await sha256HexValue(hashInput);
  sealActivityReceipt(record,{requestId,safeResult,activitySha256:hash});
}
async function sealPendingActivity(record){
  for(const r of unsealedTerminalReceipts(record))await sealOneActivity(record,r.request_id,r.safe_result||{status:'ERROR',error_class:r.reason||'AMBIGUOUS_DELIVERY'});
  return record;
}
function s4UiProjection(record){
  const lifecycle=lifecycleProjection(record);
  const from={schema:S4_ACTIVITY_CURSOR_SCHEMA,task_admission_id:record.task_admission_id,activity_seq:0,receipt_sha256:null};
  const delta=activityDelta(record,{fromCursor:from,throughSeq:record.activity_committed_seq,limit:24});
  return {
    schema:'S4_UI_PROJECTION_V1',generated_utc:new Date().toISOString(),
    task_admission_id:record.task_admission_id,session_id:record.session_id,project_id:record.project_id,task_id:record.task_id,
    task_state:lifecycle.task_state,task_created_utc:lifecycle.task_created_utc,task_expires_utc:lifecycle.task_expires_utc,
    continuation:lifecycle.continuation,epoch_id:lifecycle.epoch_id,epoch_seq:lifecycle.epoch_seq,
    accounting:lifecycle.accounting,activity:{
      available:delta.available,reason:delta.reason??null,request_count:delta.request_count??0,
      charged_result_bytes:delta.charged_result_bytes??0,epoch_rollovers:delta.epoch_rollovers??0,
      operation_counts:delta.operation_counts??{},events:Array.isArray(delta.events)?delta.events.slice(-24):[],
      truncated:!!delta.truncated,receipt_identity:delta.receipt_identity??null
    }
  };
}
function pushS4UiProjection(record){
  try{this.helper?.send(JSON.stringify({type:'ui_projection',projection:s4UiProjection(record)}));}catch{}
}

export class RelaySession {
  constructor(state, env) { this.state=state; this.env=env; this.helper=null; this.pending=new Map(); this.busy=false; }
  async fetch(request) {
    const url=new URL(request.url);
    if(url.pathname==='/helper') return this.acceptHelper(request);
    if(url.pathname==='/rpc') return this.rpc(request);
    if(url.pathname==='/status') return this.status();
    if(url.pathname==='/reset') return this.reset(request);
    return new Response('not found',{status:404});
  }
  async acceptHelper(request) {
    if(request.headers.get('Upgrade')?.toLowerCase()!=='websocket') return new Response('upgrade required',{status:426});
    const token=new URL(request.url).searchParams.get('token')||'';
    if(token!==this.env.HELPER_SECRET) return new Response('unauthorized',{status:401});
    const pair=new WebSocketPair(), client=pair[0], server=pair[1]; server.accept();
    if(this.helper){try{this.helper.close(4001,'replaced');}catch{}}
    this.helper=server;
    server.addEventListener('message',e=>this.onHelperMessage(e.data));
    server.addEventListener('close',()=>{if(this.helper===server)this.helper=null;});
    server.addEventListener('error',()=>{if(this.helper===server)this.helper=null;});
    return new Response(null,{status:101,webSocket:client});
  }
  async onHelperMessage(raw) {
    let msg;try{msg=JSON.parse(raw);}catch{return;}
    if(msg.type==='hello'){
      if(msg.admission_schema_version===3&&msg.task_admission_id){
        const key='task:'+msg.task_admission_id;
        let record=await this.state.storage.get(key);
        try{
          record=record?reconcileTaskHello(record,msg):createTaskRecord(msg);
        }catch(e){
          const code=String(e?.code||e?.message||'TASK_ADMISSION_REJECTED');
          if(record&&code==='SNAPSHOT_OR_MANIFEST_CHANGED'){
            record.invalid_reason='SNAPSHOT_MISMATCH';
            record.connected=false;
            await this.state.storage.put(key,record);
            await this.state.storage.put('active_task_id',msg.task_admission_id);
            await this.state.storage.put('active_mode','s4');
          }
          try{this.helper?.send(JSON.stringify({type:'hello_error',error:code}));}catch{}
          try{this.helper?.close(4003,'task admission rejected');}catch{}
          return;
        }
        record.connected=true;record.helper_version=msg.helper_version||record.helper_version;record.controlled_restart_done=!!msg.controlled_restart_done;
        await sealPendingActivity(record);
        await this.state.storage.put(key,record);
        await this.state.storage.put('active_task_id',msg.task_admission_id);
        await this.state.storage.put('active_mode','s4');
        try{this.helper?.send(JSON.stringify({type:'hello_ack',lifecycle:lifecycleProjection(record)}));}catch{}
        pushS4UiProjection.call(this,record);
        return;
      }
      const prev=await this.state.storage.get('meta'),c=msg.caps||{};
      const mr=Number.isInteger(c.max_requests)&&c.max_requests>=1&&c.max_requests<=64?c.max_requests:24;
      const mb=Number.isInteger(c.max_cumulative_result_bytes)&&c.max_cumulative_result_bytes>=1000&&c.max_cumulative_result_bytes<=65536?c.max_cumulative_result_bytes:18000;
      const mrb=Number.isInteger(c.max_result_bytes)&&c.max_result_bytes>=256&&c.max_result_bytes<=4096?c.max_result_bytes:3000;
      if(!prev||prev.session_id!==msg.session_id){
        await this.state.storage.put('meta',{session_id:msg.session_id,snapshot_id:msg.snapshot_id,helper_version:msg.helper_version,started_utc:msg.started_utc,expires_utc:msg.expires_utc,request_count:0,cumulative_result_bytes:0,controlled_restart_done:!!msg.controlled_restart_done,corpus:'Nendo/ONEC',task_id:msg.task_id||null,max_requests:mr,max_cumulative_result_bytes:mb,max_result_bytes:mrb,connected:true});
      }else{prev.connected=true;prev.helper_version=msg.helper_version;prev.controlled_restart_done=!!msg.controlled_restart_done;prev.task_id=msg.task_id||prev.task_id||null;prev.max_requests=mr;prev.max_cumulative_result_bytes=mb;prev.max_result_bytes=mrb;await this.state.storage.put('meta',prev);}
      await this.state.storage.put('active_mode','legacy');
      return;
    }
    if(msg.type==='result'&&msg.request_id){
      const p=this.pending.get(msg.request_id);
      if(p){this.pending.delete(msg.request_id);this.busy=false;p.resolve(msg);}
    }
  }
  async activeTaskRecord(){
    const id=await this.state.storage.get('active_task_id');
    if(!id)return null;
    return await this.state.storage.get('task:'+id)||null;
  }
  async status(){
    const mode=await this.state.storage.get('active_mode');
    if(mode==='s4')return Response.json({online:!!this.helper,mode,meta:await this.activeTaskRecord()});
    const meta=await this.state.storage.get('meta');return Response.json({online:!!this.helper,mode:mode||'legacy',meta:meta||null});
  }
  async reset(request){
    if(request.headers.get('x-reset-secret')!==this.env.HELPER_SECRET)return new Response('unauthorized',{status:401});
    const mode=await this.state.storage.get('active_mode');
    if(mode==='s4')return Response.json({error:'S4_TASK_ACCOUNTING_RESET_FORBIDDEN'},{status:409});
    await this.state.storage.delete('meta');return Response.json({reset:true});
  }
  async rpcLegacy(body){
    if(this.busy)return Response.json({error:'RELAY_BUSY'},{status:429});
    const meta=await this.state.storage.get('meta');
    if(!this.helper||!meta)return Response.json({error:'HELPER_OFFLINE'},{status:503});
    if(Date.now()>=Date.parse(meta.expires_utc))return Response.json({error:'SESSION_EXPIRED'},{status:410});
    const maxReq=meta.max_requests??24,maxCum=meta.max_cumulative_result_bytes??18000,maxRes=meta.max_result_bytes??3000;
    if(meta.request_count>=maxReq)return Response.json({error:'REQUEST_CAP'},{status:429});
    const request_id=crypto.randomUUID();this.busy=true;
    const resultP=new Promise((resolve,reject)=>{const timer=setTimeout(()=>{if(this.pending.delete(request_id)){this.busy=false;reject(new Error('HELPER_TIMEOUT'));}},15000);this.pending.set(request_id,{resolve:v=>{clearTimeout(timer);resolve(v);}});});
    this.helper.send(JSON.stringify({type:'request',request_id,op:body.op,args:body.args}));
    let result;try{result=await resultP;}catch(e){return Response.json({error:e.message},{status:504});}
    const bytes=payloadBytes(result.payload);
    if(bytes>maxRes)return Response.json({error:'RESULT_CAP'},{status:502});
    if(meta.cumulative_result_bytes+bytes>maxCum)return Response.json({error:'SESSION_BYTE_CAP'},{status:429});
    meta.request_count+=1;meta.cumulative_result_bytes+=bytes;meta.connected=!!this.helper;meta.controlled_restart_done=!!result.controlled_restart_done;await this.state.storage.put('meta',meta);
    return Response.json({status:result.status,metadata:result.metadata,payload:result.payload,usage:{request_count:meta.request_count,cumulative_result_bytes:meta.cumulative_result_bytes,limits:{max_requests:maxReq,max_cumulative_result_bytes:maxCum,max_result_bytes:maxRes,max_search_matches:8,max_read_lines:20}}});
  }
  async rpc(request){
    if(request.method!=='POST')return new Response('method',{status:405});
    const body=await request.json();
    const mode=await this.state.storage.get('active_mode');
    if(mode!=='s4')return this.rpcLegacy(body);
    const taskId=await this.state.storage.get('active_task_id');
    if(!taskId)return Response.json({error:'ACCOUNTING_STATE_UNAVAILABLE'},{status:503});
    const key='task:'+taskId;
    let record=await this.state.storage.get(key);
    if(!record)return Response.json({error:'ACCOUNTING_STATE_UNAVAILABLE'},{status:503});
    if(this.busy)return Response.json({error:'RELAY_BUSY'},{status:429});
    if(!this.helper){
      if(body.op==='context')return Response.json({status:'OK',metadata:{op:'context',control_only:true,helper_online:false},payload:minimalControlPayload(record),usage:lifecycleProjection(record).accounting});
      return Response.json({error:'HELPER_OFFLINE',usage:lifecycleProjection(record).accounting},{status:503});
    }
    const fingerprint=await requestFingerprint(body.op,body.args);
    let clientId;try{clientId=await mcpAccountingRequestId(record,fingerprint);}catch{return Response.json({error:'REQUEST_IDENTITY_INVALID'},{status:400});}
    let reservation;
    try{reservation=reserveRequest(record,{requestId:clientId,fingerprint,op:body.op,safeRequest:safeRequestMeta(body.op,body.args)});}
    catch(e){return Response.json({error:String(e?.code||e?.message||'ACCOUNTING_ERROR')},{status:409});}
    if(reservation.action==='CONTROL_ONLY')return Response.json({status:'OK',metadata:{op:'context',control_only:true},payload:minimalControlPayload(record),usage:lifecycleProjection(record).accounting});
    if(reservation.action==='REPLAY_BLOCKED'){
      if(body.op==='task_checkpoint_write'&&reservation.receipt.safe_result?.checkpoint_receipt){
        return Response.json({status:'OK',metadata:{op:body.op,replayed_transport:true},payload:{...reservation.receipt.safe_result.checkpoint_receipt,replayed:true},usage:lifecycleProjection(record).accounting});
      }
      return Response.json({error:'REQUEST_ALREADY_ACCOUNTED_RECOVERY_REQUIRED',receipt:{state:reservation.receipt.state,charged_bytes:reservation.receipt.charged_bytes,epoch_seq:reservation.receipt.epoch_seq,activity_seq:reservation.receipt.activity_seq}},{status:409});
    }
    if(reservation.action==='BLOCKED')return Response.json({error:reservation.error,usage:lifecycleProjection(record).accounting},{status:429});
    await this.state.storage.put(key,record);
    let helperArgs=body.args||{};
    const cursorBefore=reservation.reservation.activity_cursor_before;
    if(body.op==='task_checkpoint_write')helperArgs={...helperArgs,__s4:{activity_cursor_before:cursorBefore,writer_epoch_seq:reservation.reservation.epoch_seq}};
    if(body.op==='context'){
      const currentFrom=latestCheckpointRequestCursor(record)||{schema:S4_ACTIVITY_CURSOR_SCHEMA,task_admission_id:record.task_admission_id,activity_seq:0,receipt_sha256:null};
      const currentActivityDelta=activityDelta(record,{fromCursor:currentFrom,throughSeq:cursorBefore.activity_seq,limit:48});
      let predecessorActivityDelta=null;
      if(record.predecessor?.task_admission_id){
        const predecessorRecord=await this.state.storage.get('task:'+record.predecessor.task_admission_id);
        if(predecessorRecord)predecessorActivityDelta=activityDelta(predecessorRecord,{fromCursor:record.predecessor.activity_cursor,throughSeq:predecessorRecord.activity_committed_seq,limit:48});
      }
      helperArgs={...helperArgs,__s4:{activity_cursor_before:cursorBefore,activity_delta:currentActivityDelta,predecessor_activity_delta:predecessorActivityDelta}};
    }
    const request_id=clientId;this.busy=true;
    const resultP=new Promise((resolve,reject)=>{const timer=setTimeout(()=>{if(this.pending.delete(request_id)){this.busy=false;reject(new Error('HELPER_TIMEOUT'));}},15000);this.pending.set(request_id,{resolve:v=>{clearTimeout(timer);resolve(v);}});});
    this.helper.send(JSON.stringify({type:'request',request_id,op:body.op,args:helperArgs}));
    let result;
    try{result=await resultP;}
    catch(e){
      record=await this.state.storage.get(key);
      try{chargeAmbiguousRequest(record,{requestId:clientId,fingerprint,reason:'HELPER_TIMEOUT'});await sealOneActivity(record,clientId,{status:'ERROR',error_class:'HELPER_TIMEOUT'});await this.state.storage.put(key,record);pushS4UiProjection.call(this,record);}catch{}
      return Response.json({error:'HELPER_TIMEOUT',usage:lifecycleProjection(record).accounting},{status:504});
    }
    let finalPayload=result.payload;
    if(body.op==='context'){
      const base={...(result.payload||{})};
      delete base.caps;delete base.expires_utc;
      let guess=payloadBytes({...base,...lifecycleProjection(record)});
      for(let i=0;i<5;i++){
        const projected=projectCommittedRecord(record,{payloadBytes:guess});
        const candidate={...base,...lifecycleProjection(projected)};
        const next=payloadBytes(candidate);finalPayload=candidate;if(next===guess)break;guess=next;
      }
    }
    const bytes=payloadBytes(finalPayload);
    if(bytes>record.max_result_bytes){
      record=await this.state.storage.get(key);
      chargeAmbiguousRequest(record,{requestId:clientId,fingerprint,reason:'RESULT_CAP'});
      await sealOneActivity(record,clientId,{status:'ERROR',error_class:'RESULT_CAP'});
      await this.state.storage.put(key,record);
      pushS4UiProjection.call(this,record);
      return Response.json({error:'RESULT_CAP',usage:lifecycleProjection(record).accounting},{status:502});
    }
    record=await this.state.storage.get(key);
    try{
      commitRequest(record,{requestId:clientId,fingerprint,payloadBytes:bytes});
      await sealOneActivity(record,clientId,safeResultMeta(body.op,{...result,payload:finalPayload}));
      await this.state.storage.put(key,record);
      pushS4UiProjection.call(this,record);
    }catch(e){return Response.json({error:String(e?.code||e?.message||'ACCOUNTING_COMMIT_FAILED')},{status:503});}
    return Response.json({status:result.status,metadata:{...result.metadata,epoch_id:record.epoch_id,epoch_seq:record.epoch_seq,activity_seq:record.activity_committed_seq},payload:finalPayload,usage:lifecycleProjection(record).accounting});
  }
}

function mcpError(id,code,message){return Response.json({jsonrpc:'2.0',id,error:{code,message}},{headers:{'cache-control':'no-store'}});}
function mcpResult(id,result){return Response.json({jsonrpc:'2.0',id,result},{headers:{'cache-control':'no-store'}});}
const TOOLS=[
 {name:'source_context',description:'Get the current admitted Nendo ONEC session, fixed task binding, source snapshot, and caps.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}},
 {name:'source_search',description:'Fixed-string BSL search in the admitted Nendo ONEC Source only. Read-only and bounded.',inputSchema:{type:'object',properties:{query:{type:'string',minLength:1,maxLength:256},max_matches:{type:'integer',minimum:1,maximum:8}},required:['query'],additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}},
 {name:'source_read',description:'Read a bounded 1-based inclusive line range from an admitted direct canonical Nendo Source path.',inputSchema:{type:'object',properties:{path:{type:'string',minLength:1,maxLength:260},start:{type:'integer',minimum:1},end:{type:'integer',minimum:1}},required:['path','start','end'],additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}},
 {name:'proposal_write',description:'Create or CAS-replace one bounded proposal artifact in the single admitted Output task. Never writes Source.',inputSchema:{type:'object',properties:{path:{type:'string',minLength:1,maxLength:180},content:{type:'string',maxLength:32768},idempotency_key:{type:'string',minLength:1,maxLength:64,pattern:'^[A-Za-z0-9._-]+$'},replace:{type:'boolean',default:false},expected_sha256:{type:'string',pattern:'^[A-Fa-f0-9]{64}$'}},required:['path','content','idempotency_key'],additionalProperties:false},annotations:{readOnlyHint:false,destructiveHint:false,openWorldHint:false}},
 {name:'proposal_read',description:'Read back a bounded line window from one artifact or its machine-readable provenance in the admitted Output task.',inputSchema:{type:'object',properties:{path:{type:'string',minLength:1,maxLength:180},start:{type:'integer',minimum:1,default:1},end:{type:'integer',minimum:1}},required:['path'],additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false}},
 {name:'task_checkpoint_write',description:'Commit one bounded semantic TASK_CHECKPOINT_V1 for the active admitted task using CAS and idempotency. This is task handoff state, not Source/proof/proposal content.',inputSchema:{type:'object',properties:{
   idempotency_key:{type:'string',minLength:1,maxLength:64,pattern:'^[A-Za-z0-9._-]+$'},
   expected_seq:{type:'integer',minimum:0,maximum:1000000},
   expected_predecessor_sha256:{anyOf:[{type:'string',pattern:'^[A-Fa-f0-9]{64}$'},{type:'null'}]},
   phase:{type:'string',minLength:1,maxLength:64},
   status:{type:'string',enum:['IN_PROGRESS','BLOCKED','COMPLETED']},
   progress_summary:{type:'string',maxLength:640},
   completed_steps:{type:'array',maxItems:6,items:{type:'string',maxLength:192}},
   decisions_constraints:{type:'array',maxItems:6,items:{type:'string',maxLength:192}},
   unresolved_questions:{type:'array',maxItems:4,items:{type:'string',maxLength:192}},
   first_unfinished_step:{type:'string',maxLength:320},
   do_not_replay:{type:'array',maxItems:6,items:{type:'string',maxLength:192}},
   source_evidence_refs:{type:'array',maxItems:6,items:{type:'object',properties:{path:{type:'string',minLength:1,maxLength:260},sha256:{type:'string',pattern:'^[A-Fa-f0-9]{64}$'},start:{type:'integer',minimum:1},end:{type:'integer',minimum:1}},required:['path','sha256'],additionalProperties:false}},
   proposal_refs:{type:'array',maxItems:4,items:{type:'object',properties:{path:{type:'string',minLength:1,maxLength:180},sha256:{type:'string',pattern:'^[A-Fa-f0-9]{64}$'}},required:['path','sha256'],additionalProperties:false}},
   machine_operation_refs:{type:'array',maxItems:4,items:{type:'object',properties:{operation_id:{type:'string',minLength:1,maxLength:128},sha256:{type:'string',pattern:'^[A-Fa-f0-9]{64}$'}},required:['operation_id'],additionalProperties:false}},
   assumptions_requiring_confirmation:{type:'array',maxItems:4,items:{type:'string',maxLength:192}}
 },required:['idempotency_key','expected_seq','expected_predecessor_sha256','phase','status','progress_summary','first_unfinished_step'],additionalProperties:false},annotations:{readOnlyHint:false,destructiveHint:false,openWorldHint:false}}
];
const McpApiHandler={
 async fetch(request,env,ctx){
  if(!ctx?.props||ctx.props.githubLogin!==ALLOWED_GITHUB_LOGIN)return new Response('forbidden',{status:403});
  if(request.method!=='POST')return new Response('',{status:405,headers:{Allow:'POST'}});
  let msg;try{msg=await request.json();}catch{return mcpError(null,-32700,'Parse error');}
  if(Array.isArray(msg)||msg.jsonrpc!=='2.0')return mcpError(msg?.id??null,-32600,'Invalid Request');
  if(msg.method==='initialize')return mcpResult(msg.id,{protocolVersion:'2025-06-18',capabilities:{tools:{listChanged:false}},serverInfo:{name:'onec-g1q1-relay',version:'1.4.0-w1'}});
  if(msg.method==='notifications/initialized')return new Response(null,{status:202});
  if(msg.method==='ping')return mcpResult(msg.id,{});
  if(msg.method==='tools/list')return mcpResult(msg.id,{tools:TOOLS});
  if(msg.method==='tools/call'){
    const name=msg.params?.name,args=msg.params?.arguments||{};let op,opArgs;
    if(name==='source_context'){op='context';opArgs={};}
    else if(name==='source_search'){op='search';opArgs={query:args.query,max_matches:args.max_matches??8};}
    else if(name==='source_read'){op='read';opArgs={path:args.path,start:args.start,end:args.end};}
    else if(name==='proposal_write'){op='proposal_write';opArgs={path:args.path,content:args.content,idempotency_key:args.idempotency_key,replace:args.replace===true,expected_sha256:args.expected_sha256};}
    else if(name==='proposal_read'){op='proposal_read';opArgs={path:args.path,start:args.start??1,end:args.end};}
    else if(name==='task_checkpoint_write'){op='task_checkpoint_write';opArgs={
      idempotency_key:args.idempotency_key,expected_seq:args.expected_seq,expected_predecessor_sha256:args.expected_predecessor_sha256??null,
      phase:args.phase,status:args.status,progress_summary:args.progress_summary,completed_steps:args.completed_steps||[],decisions_constraints:args.decisions_constraints||[],
      unresolved_questions:args.unresolved_questions||[],first_unfinished_step:args.first_unfinished_step,do_not_replay:args.do_not_replay||[],
      source_evidence_refs:args.source_evidence_refs||[],proposal_refs:args.proposal_refs||[],machine_operation_refs:args.machine_operation_refs||[],
      assumptions_requiring_confirmation:args.assumptions_requiring_confirmation||[]
    };}
    else return mcpError(msg.id,-32602,'Unknown tool');
    const stub=env.RELAY.get(env.RELAY.idFromName('q1'));
    const rr=await stub.fetch('https://relay.invalid/rpc',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({op,args:opArgs})});
    const data=await rr.json(),isError=!rr.ok||data.status==='ERROR';
    return mcpResult(msg.id,{content:[{type:'text',text:JSON.stringify(data)}],structuredContent:data,isError});
  }
  return mcpError(msg.id??null,-32601,'Method not found');
 }
};

const esc=v=>String(v).replace(/[&<>"']/g,c=>'&#'+c.charCodeAt(0)+';');
function consentPage(details,handle){
 const scopes=details.scope.map(s=>'<label><input type="checkbox" name="scope" value="'+esc(s)+'" checked> '+esc(s)+'</label>').join('<br>');
 return '<!doctype html><meta charset="utf-8"><title>Authorize OneC G1Q1</title><h1>Authorize '+esc(details.clientName)+'</h1><p>Destination: <strong>'+esc(details.redirectHost)+'</strong>.</p><p>This private app exposes bounded Nendo Source reads and one task-bound Output proposal contour; it never writes Source.</p><form method="post"><input type="hidden" name="handle" value="'+esc(handle)+'">'+scopes+'<p><button name="decision" value="approve">Allow</button> <button name="decision" value="deny">Deny</button></p></form>';
}
async function sha256b64url(v){const b=new TextEncoder().encode(v),h=await crypto.subtle.digest('SHA-256',b);return btoa(String.fromCharCode(...new Uint8Array(h))).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');}
function randomVerifier(){const a=new Uint8Array(48);crypto.getRandomValues(a);return btoa(String.fromCharCode(...a)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');}
async function githubExchange(env,code,verifier){
 const body=new URLSearchParams();body.set('client_id',env.GITHUB_CLIENT_ID);body.set('client_'+'secret',env.GITHUB_CLIENT_SECRET);body.set('code',code);body.set('redirect_uri',GITHUB_CALLBACK);body.set('code_verifier',verifier);
 const r=await fetch('https://github.com/login/oauth/access_token',{method:'POST',headers:{Accept:'application/json','content-type':'application/x-www-form-urlencoded'},body});
 const x=await r.json();if(!r.ok||!x.access_token)throw new Error('GITHUB_TOKEN_EXCHANGE_FAILED');
 const u=await fetch('https://api.github.com/user',{headers:{Authorization:'Bearer '+x.access_token,Accept:'application/vnd.github+json','User-Agent':'onec-g1q1-oauth'}});
 const user=await u.json();if(!u.ok||!user.login)throw new Error('GITHUB_IDENTITY_FAILED');
 return {login:user.login,id:String(user.id)};
}
const DefaultHandler={
 async fetch(request,env){
  const url=new URL(request.url);
  if(url.pathname==='/health')return Response.json({service:'onec-g1q1-relay',version:'g1q1-relay/2-oauth',source_storage:'none',oauth:'cloudflare-workers-oauth-provider-1.2.1'});
  if(url.pathname==='/helper')return env.RELAY.get(env.RELAY.idFromName('q1')).fetch(request);
  if(url.pathname==='/authorize'){
   const oauth=env.OAUTH_PROVIDER;
   try{
    if(request.method==='GET'){
      const ar=await oauth.parseAuthRequest(request),details=await oauth.describeConsent(ar),consent=await oauth.beginConsent(ar);consent.headers.set('Content-Type','text/html; charset=utf-8');return new Response(consentPage(details,consent.handle),{headers:consent.headers});
    }
    if(request.method==='POST'){
      const form=await request.formData(),handle=String(form.get('handle')||'');
      if(form.get('decision')!=='approve'){const denied=await oauth.denyConsent(request,handle);return new Response(null,{status:302,headers:denied.headers});}
      const approved=await oauth.approveConsent(request,handle,{scope:form.getAll('scope').map(String)});
      const verifier=randomVerifier(),tx=await oauth.beginUpstream(approved.request,{data:{verifier},headers:approved.headers});
      const gh=new URL('https://github.com/login/oauth/authorize');gh.searchParams.set('client_id',env.GITHUB_CLIENT_ID);gh.searchParams.set('redirect_uri',GITHUB_CALLBACK);gh.searchParams.set('state',tx.state);gh.searchParams.set('code_challenge',await sha256b64url(verifier));gh.searchParams.set('code_challenge_method','S256');
      tx.headers.set('Location',gh.toString());return new Response(null,{status:302,headers:tx.headers});
    }
    return new Response('method',{status:405});
   }catch(e){
    if(e instanceof AuthorizationError&&e.redirectTo)return Response.redirect(e.redirectTo,302);
    if(e instanceof AuthorizationError||e instanceof CimdFetchError)return new Response(esc(e instanceof AuthorizationError?e.description:'Client verification failed'),{status:400,headers:{'content-type':'text/plain; charset=utf-8'}});
    throw e;
   }
  }
  if(url.pathname==='/github/callback'){
    let stage='finish_upstream';
    try{
      const oauth=env.OAUTH_PROVIDER, resumed=await oauth.finishUpstream(request);
      if(url.searchParams.get('error'))return new Response('GitHub authorization denied',{status:403});
      stage='github_exchange';
      const ident=await githubExchange(env,url.searchParams.get('code')||'',resumed.data.verifier);
      stage='principal_check';
      if(ident.login!==ALLOWED_GITHUB_LOGIN)return new Response('Wrong GitHub principal',{status:403});
      stage='complete_authorization';
      const done=await oauth.completeAuthorization({request:resumed.request,userId:'github-'+ident.id,metadata:{githubLogin:ident.login},scope:resumed.request.scope,props:{githubLogin:ident.login,githubId:ident.id}});
      resumed.headers.set('Location',done.redirectTo);return new Response(null,{status:302,headers:resumed.headers});
    }catch(e){console.error('Q1_OAUTH_CALLBACK_FAIL',stage);return new Response('OAuth callback failed at '+stage,{status:400,headers:{'cache-control':'no-store'}});}
  }
  return new Response('not found',{status:404});
 }
};

export default new OAuthProvider({
 apiRoute:'/mcp',
 apiHandler:McpApiHandler,
 defaultHandler:DefaultHandler,
 authorizeEndpoint:'/authorize',
 tokenEndpoint:'/oauth/token',
 clientRegistrationEndpoint:'/oauth/register',
 scopesSupported:['mcp:read','offline_access'],
 resourceMetadata:{resource:RESOURCE,authorization_servers:[ORIGIN]},
 requiredScopes:['mcp:read'],
 clientIdMetadataDocumentEnabled:true,
 clientRegistrationCallback:({clientMetadata})=>{
   const uris=Array.isArray(clientMetadata.redirect_uris)?clientMetadata.redirect_uris:[];
   if(uris.length<1||uris.some(u=>u!=='https://chatgpt.com/connector_platform_oauth_redirect'))return {code:'invalid_redirect_uri',description:'Only ChatGPT connector redirect is admitted',status:400};
 },
});
