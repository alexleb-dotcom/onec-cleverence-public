import {PullMailbox} from '../experiments/https-pull/mailbox.mjs';
import {PULL_PREFIX,verifyPullRequest,pullDigest,consumePullNonce} from '../../runtime/https-pull-auth.mjs';
import {createTaskRecord,validateS4Hello,reconcileTaskHello,reserveRequest,commitRequest,chargeAmbiguousRequest,lifecycleProjection,minimalControlPayload,activityDelta,latestCheckpointRequestCursor,S4_ACTIVITY_CURSOR_SCHEMA} from './s4-accounting.js';

const key='https_pull_v1';
const clone=x=>structuredClone(x);
const binding=r=>({admission:r.task_admission_id,session:r.session_id,snapshot:r.snapshot_id,
  manifest:r.manifest_sha256,project:r.project_id,task:r.task_id});
const equal=(a,b)=>Object.keys(a).every(k=>a[k]===b?.[k]);
const fail=code=>{throw new Error(code);};
const bytes=v=>new TextEncoder().encode(JSON.stringify(v??null)).length;

/** One SQLite DO owns both existing S4 KV rows and the bounded mailbox KV row.
 * No independent database, migration, counter copy, or accounting surrogate.
 */
export class DurablePullTransport {
  constructor(owner,hooks){
    this.owner=owner;this.storage=owner.state.storage;this.hooks=hooks;
    this.waiters=new Set();this.polling=false;
    this.store={tx:fn=>this.transaction(fn)};
    this.mailbox=new PullMailbox({store:this.store,maxArgsBytes:262144,accounting:{
      lookup:(r,j)=>this.lookup(r,j),reserve:(r,j,d)=>this.reserve(r,j,d),commit:(r,j,v,d)=>this.commit(r,j,v,d),ambiguous:(r,j)=>this.ambiguous(r,j)
    }});
  }
  async transaction(fn){
    return this.storage.transaction(async txn=>{
      const id=await txn.get('active_task_id');const record=id?await txn.get('task:'+id):null;
      const mailbox=await txn.get(key)||{job:null,receipts:{},nonces:[],helper:null};
      const mailboxBefore=JSON.stringify(mailbox);
      const data={...mailbox,s4:record,task:record?{...binding(record),expires:Date.parse(record.task_expires_utc)}:null,txn};
      const before=JSON.stringify(record),result=await fn(data);
      const {s4,task,txn:unused,...persisted}=data;
      if(JSON.stringify(s4)!==before&&s4)await txn.put('task:'+s4.task_admission_id,s4);
      if(JSON.stringify(persisted)!==mailboxBefore)await txn.put(key,persisted);
      const alarm=data.job?(['PENDING','LEASED'].includes(data.job.status)?data.job.deadline:Math.max(Date.now()+1000,data.job.deadline+60000)):null;
      if(await txn.getAlarm()!==alarm){if(alarm===null)await txn.deleteAlarm();else await txn.setAlarm(alarm);}
      return result;
    });
  }
  notify(){for(const wake of this.waiters)wake();this.waiters.clear();}
  async wait(ms){
    if(ms<=0)return;
    await new Promise(resolve=>{
      const wake=()=>{clearTimeout(timer);this.waiters.delete(wake);resolve();};
      const timer=setTimeout(wake,ms);this.waiters.add(wake);
    });
  }
  async alarm(){
    await this.mailbox.expire();
    await this.transaction(data=>{
      if(data.job&&Date.now()>=data.job.deadline+60000){data.job=null;data.receipts={};}
    });
    this.notify();
  }
  async reserve(record,job,data){
    if(Object.values(record.request_receipts||{}).some(r=>r.state==='RESERVED'))fail('REQUEST_ALREADY_ACCOUNTED_RECOVERY_REQUIRED');
    const result=reserveRequest(record,{requestId:job.requestId,fingerprint:job.fingerprint,op:job.op,safeRequest:this.hooks.safeRequestMeta(job.op,job.args)});
    if(result.action!=='EXECUTE')return result.action==='REPLAY_BLOCKED'?{action:result.action,receipt:result.receipt}:{action:result.action,error:result.error};
    const cursor=result.reservation.activity_cursor_before;
    if(job.op==='task_checkpoint_write')job.args={...job.args,__s4:{activity_cursor_before:cursor,writer_epoch_seq:result.reservation.epoch_seq}};
    if(job.op==='context'){
      const from=latestCheckpointRequestCursor(record)||{schema:S4_ACTIVITY_CURSOR_SCHEMA,task_admission_id:record.task_admission_id,activity_seq:0,receipt_sha256:null};
      let previous=null;
      if(record.predecessor?.task_admission_id){const p=await data.txn.get('task:'+record.predecessor.task_admission_id);
        if(p)previous=activityDelta(p,{fromCursor:record.predecessor.activity_cursor,throughSeq:p.activity_committed_seq,limit:48});}
      job.args={...job.args,__s4:{activity_cursor_before:cursor,activity_delta:activityDelta(record,{fromCursor:from,throughSeq:cursor.activity_seq,limit:48}),predecessor_activity_delta:previous}};
    }
    return result;
  }
  lookup(record,job){
    const receipt=record.request_receipts?.[job.requestId];if(!receipt)return null;
    if(receipt.fingerprint!==job.fingerprint)return {status:'ID_COLLISION'};
    const payload=receipt.safe_result?.proposal_receipt||receipt.safe_result?.checkpoint_receipt;
    if(receipt.state==='COMMITTED'&&payload?.status==='COMMITTED')return {status:'REPLAY',response:{status:'OK',metadata:{op:job.op,replayed_transport:true},payload:{...payload,replayed:true},usage:lifecycleProjection(record).accounting}};
    return {status:'ALREADY_ACCOUNTED'};
  }
  async ambiguous(record,job,reason='HELPER_TIMEOUT'){
    chargeAmbiguousRequest(record,{requestId:job.requestId,fingerprint:job.fingerprint,reason});
    await this.hooks.sealOneActivity(record,job.requestId,{status:'ERROR',error_class:reason});
  }
  async commit(record,job,result,data){
    const digest=await pullDigest(JSON.stringify(result));
    data.acks=(data.acks||[]).filter(a=>Date.now()<a.until&&a.requestId!==job.requestId);
    data.acks.push({requestId:job.requestId,helperId:job.helperId,token:job.token,identity:binding(record),digest,until:Date.now()+60000});
    data.acks=data.acks.slice(-8);
    const payload=this.hooks.finalPayload(record,job.op,result);
    if(bytes(payload)>record.max_result_bytes||result.metadata?.error_class==='HELPER_EXECUTION_AMBIGUOUS'){
      const error=bytes(payload)>record.max_result_bytes?'RESULT_CAP':'HELPER_EXECUTION_AMBIGUOUS';
      await this.ambiguous(record,job,error);return {error,usage:lifecycleProjection(record).accounting};
    }
    commitRequest(record,{requestId:job.requestId,fingerprint:job.fingerprint,payloadBytes:bytes(payload)});
    const safe=this.hooks.safeResultMeta(job.op,{...result,payload});
    if(job.op==='proposal_write'&&result.status==='OK'&&payload?.status==='COMMITTED')safe.proposal_receipt=clone(payload);
    await this.hooks.sealOneActivity(record,job.requestId,safe);
    return {status:result.status,metadata:{...result.metadata,epoch_id:record.epoch_id,epoch_seq:record.epoch_seq,activity_seq:record.activity_committed_seq},payload,usage:lifecycleProjection(record).accounting};
  }
  async endpoint(request){
    let auth;
    try{auth=await verifyPullRequest(request,this.owner.env.HELPER_SECRET);}catch(e){return Response.json({error:e.message},{status:401});}
    const route=new URL(request.url).pathname.slice(PULL_PREFIX.length),value=auth.value;
    // Authenticate and consume a nonce once, before the business transaction.
    // Business retries use new signed nonces and the same durable lease.
    try{await this.transaction(data=>{
      const now=Date.now();data.nonces=consumePullNonce(data.nonces,auth,now);
      if(route==='hello'){
        validateS4Hello(value.hello);
        if(!equal(binding(value.hello),value.identity))fail('PULL_IDENTITY_REJECTED');
        if(data.s4?.task_admission_id===value.identity.admission&&!equal(binding(data.s4),value.identity))fail('PULL_IDENTITY_REJECTED');
      }else if(!data.s4||!equal(binding(data.s4),value.identity))fail('PULL_IDENTITY_REJECTED');
      if(!/^[a-f0-9-]{36}$/i.test(value.helper_id||''))fail('PULL_HELPER_INVALID');
      if(route!=='hello'&&data.helper?.id!==value.helper_id)fail('PULL_HELPER_REJECTED');
      if(route==='claim')data.helper.lastSeen=now;
    });}catch(e){return Response.json({error:e.message},{status:e.message==='PULL_RATE_LIMIT'?429:403});}
    try{
      if(route==='hello')return await this.hello(value);
      if(route==='claim'){
        if(this.polling)return Response.json({status:'BUSY'},{status:429});
        this.polling=true;
        try{
          const until=Date.now()+8000;let result;
          do{
            result=await this.mailbox.claim({identity:value.identity,helperId:value.helper_id});
            if(result.status!=='EMPTY')break;
            await this.wait(Math.min(1000,until-Date.now()));
          }while(Date.now()<until);
          return Response.json(result,{headers:{'cache-control':'no-store'}});
        }finally{this.polling=false;}
      }
      if(route==='result'){
        if(bytes(value.result)>10000)fail('PULL_BODY_CAP');
        const digest=await pullDigest(JSON.stringify(value.result));
        const receipt=await this.transaction(data=>data.acks?.find(a=>Date.now()<a.until&&a.requestId===value.request_id&&a.helperId===value.helper_id&&a.token===value.token&&equal(a.identity,value.identity)));
        if(receipt)return Response.json({status:receipt.digest===digest?'COMMITTED':'RESULT_CONFLICT',replay:true});
        const result=await this.mailbox.complete({identity:value.identity,helperId:value.helper_id,requestId:value.request_id,token:value.token,result:value.result});
        this.notify();return Response.json(result);
      }
    }catch(e){return Response.json({error:String(e.message||'PULL_FAILED')},{status:409});}
    return new Response('not found',{status:404});
  }
  async hello(value){
    if(this.owner.pending.size||(this.owner.busy&&await this.storage.get('active_transport')!=='https-pull'))fail('RELAY_BUSY');
    await this.mailbox.expire();
    const response=await this.transaction(async data=>{
      const same=data.s4?.task_admission_id===value.identity.admission;
      if(!same&&['PENDING','LEASED'].includes(data.job?.status))fail('RELAY_BUSY');
      // Same trusted helper credential and accepted S4 hello owner as the old
      // transport. The relay never generates an admission or extends its TTL.
      // Keep every prior task row; registration of an operator-issued identity
      // is not a reset or migration of the currently accepted S4 record.
      const stored=same?data.s4:await data.txn.get('task:'+value.identity.admission);
      const record=stored||createTaskRecord(value.hello);
      const enrolled=await data.txn.get('https_pull_helper:'+value.identity.admission);
      if(enrolled&&enrolled!==value.helper_id)fail('PULL_HELPER_REJECTED');
      if(same&&data.helper&&data.helper.id!==value.helper_id)fail('PULL_HELPER_REJECTED');
      if(!same&&data.s4){
        const previous=data.s4;
        for(const r of Object.values(previous.request_receipts||{}))if(r.state==='RESERVED'){
          chargeAmbiguousRequest(previous,{requestId:r.request_id,fingerprint:r.fingerprint,reason:'RECONNECT_WITH_UNRESOLVED_RESERVATION'});
        }
        await this.hooks.sealPendingActivity(previous);
        await data.txn.put('task:'+previous.task_admission_id,previous);
      }
      // Validate ALL existing hello bindings/caps using the real S4 function.
      // A live mailbox reservation belongs to its durable lease, not reconnect.
      const validation=clone(record);validation.request_receipts={};
      reconcileTaskHello(validation,value.hello);
      const live=data.job?.status==='LEASED'?data.job.requestId:null;
      const orphans=Object.values(record.request_receipts||{}).filter(r=>r.state==='RESERVED'&&r.request_id!==live);
      for(const r of orphans){
        chargeAmbiguousRequest(record,{requestId:r.request_id,fingerprint:r.fingerprint,reason:'RECONNECT_WITH_UNRESOLVED_RESERVATION'});
      }
      await this.hooks.sealPendingActivity(record);
      record.connected=true;record.helper_version=value.hello.helper_version;
      data.s4=record;
      if(!same){data.job=null;data.receipts={};data.acks=[];}
      data.helper={id:value.helper_id,lastSeen:Date.now()};
      await data.txn.put('https_pull_helper:'+record.task_admission_id,value.helper_id);
      await data.txn.put('active_task_id',record.task_admission_id);
      await data.txn.put('active_mode','s4');
      await data.txn.put('active_transport','https-pull');
      return {status:'READY',lifecycle:lifecycleProjection(record),projection:this.hooks.s4UiProjection(record)};
    });
    if(this.owner.helper){try{this.owner.helper.close(4001,'HTTPS pull selected');}catch{}this.owner.helper=null;this.owner.helperReady=false;}
    return Response.json(response,{headers:{'cache-control':'no-store'}});
  }
  async rpc(body,started){
    await this.mailbox.expire();
    const record=await this.owner.activeTaskRecord();
    if(!record)return Response.json({error:'ACCOUNTING_STATE_UNAVAILABLE'},{status:503});
    const lifecycle=lifecycleProjection(record);
    if(!['ACTIVE','LOW_BUDGET'].includes(lifecycle.task_state))return body.op==='context'
      ?Response.json({status:'OK',metadata:{op:'context',control_only:true},payload:minimalControlPayload(record),usage:lifecycle.accounting})
      :Response.json({error:'TASK_'+lifecycle.task_state,usage:lifecycle.accounting},{status:429});
    let requestId;try{requestId=await this.hooks.mcpAccountingRequestId(record,body.op,body.args);}catch{return Response.json({error:'REQUEST_IDENTITY_INVALID'},{status:400});}
    const fingerprint=await this.hooks.requestFingerprint(body.op,body.args),identity=binding(record);
    const deadline=Math.min(started+15000,Date.parse(record.task_expires_utc));
    const queued=await this.mailbox.enqueue({requestId,fingerprint,identity,op:body.op,args:body.args||{},deadline});
    if(queued.status==='REPLAY')return Response.json(queued.response);
    if(!['PENDING','COMMITTED'].includes(queued.status))return Response.json({error:queued.status},{status:409});
    this.notify();
    for(;;){
      const status=await this.mailbox.status({identity,requestId});
      if(status.status==='COMMITTED'){
        const response=status.response;
        if(queued.replay&&['proposal_write','task_checkpoint_write'].includes(body.op))return Response.json({...response,metadata:{...response.metadata,replayed_transport:true},payload:{...response.payload,replayed:true}});
        return Response.json(response);
      }
      if(status.status==='AMBIGUOUS_CHARGED')return Response.json(status.response||{error:'HELPER_TIMEOUT',usage:lifecycleProjection(await this.owner.activeTaskRecord()).accounting},{status:504});
      if(status.status==='EXPIRED_UNCLAIMED')return Response.json({error:'HELPER_OFFLINE',usage:lifecycleProjection(await this.owner.activeTaskRecord()).accounting},{status:503});
      if(status.status==='BLOCKED'){
        if(status.blocked.action==='CONTROL_ONLY')return Response.json({status:'OK',metadata:{op:'context',control_only:true},payload:minimalControlPayload(await this.owner.activeTaskRecord()),usage:lifecycle.accounting});
        return Response.json({error:status.blocked.error||'REQUEST_ALREADY_ACCOUNTED_RECOVERY_REQUIRED',receipt:status.blocked.receipt},{status:409});
      }
      await this.wait(Math.min(1000,deadline-Date.now()));
    }
  }
}
