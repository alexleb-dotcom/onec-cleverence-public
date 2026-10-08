import {PULL_PREFIX,pullHeaders,readPullText} from './https-pull-auth.mjs';

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export class HttpsPullHelper {
  constructor({relayUrl,secret,hello,state,persist,handle,fetchImpl=fetch,now=()=>Date.now(),sleepImpl=sleep,onProjection=()=>{}}){
    const url=new URL(relayUrl);
    if(url.protocol!=='wss:'&&url.protocol!=='https:')throw new Error('PULL_RELAY_INVALID');
    url.protocol='https:';url.pathname='/';url.search='';url.hash='';
    this.origin=url.origin;this.secret=secret;this.hello=hello;this.state=state;this.persist=persist;
    this.handle=handle;this.fetchImpl=fetchImpl;this.now=now;this.sleep=sleepImpl;this.onProjection=onProjection;
    this.identity={admission:hello.task_admission_id,session:hello.session_id,snapshot:hello.snapshot_id,
      manifest:hello.manifest_sha256,project:hello.project_id,task:hello.task_id};
  }
  async init(){
    if(!this.state.pull_helper_id){this.state.pull_helper_id=crypto.randomUUID();await this.persist(this.state);}
  }
  async post(route,fields={},timeout=9000){
    const pathname=PULL_PREFIX+route;
    const body=JSON.stringify({identity:this.identity,helper_id:this.state.pull_helper_id,...fields});
    const headers=await pullHeaders(this.secret,pathname,body,{now:this.now()});
    const response=await this.fetchImpl(this.origin+pathname,{method:'POST',body,headers,signal:AbortSignal.timeout(Math.max(1,Math.ceil(timeout)))});
    if(!response.ok)throw new Error('PULL_HTTP_'+response.status);
    const text=await readPullText(response,262144,Math.min(timeout,2000));
    return JSON.parse(text);
  }
  async connect(){
    await this.init();const response=await this.post('hello',{hello:this.hello});
    if(response.status!=='READY')throw new Error('PULL_NOT_READY');
    this.onProjection(response.projection);return response;
  }
  async processClaim(job){
    if(job.status!=='CLAIMED')return job;
    if(!/^mcp-[a-f0-9]{64}$/.test(job.requestId)||! /^[a-f0-9-]{36}$/i.test(job.token||'')||!Number.isSafeInteger(job.deadline))throw new Error('PULL_LEASE_INVALID');
    const state=this.state;state.processed=state.processed||{};
    let result=state.processed[job.requestId];
    if(!result){
      if(this.now()>=job.deadline)return {status:'EXPIRED'};
      if(state.pull_inflight?.request_id===job.requestId){
        // Crash after durable intent but before durable result: never execute
        // again, including reads. The relay seals one ambiguous S4 receipt.
        result={type:'result',request_id:job.requestId,status:'ERROR',metadata:{error_class:'HELPER_EXECUTION_AMBIGUOUS'},payload:{error:'HELPER_EXECUTION_AMBIGUOUS'}};
        state.processed[job.requestId]=result;await this.persist(state);
      }else{
        state.pull_inflight={request_id:job.requestId,token:job.token,deadline:job.deadline};
        await this.persist(state);
        await this.handle({send:raw=>{result=JSON.parse(raw);}}, {data:JSON.stringify({type:'request',request_id:job.requestId,op:job.op,args:job.args})});
        // The existing handler persists processed before calling send.
        if(!result||!state.processed[job.requestId])throw new Error('PULL_RESULT_NOT_PERSISTED');
      }
    }
    for(let attempt=0;attempt<4;attempt++){
      const remaining=job.deadline-this.now();
      // One bounded late ACK query can recover an accepted POST response.
      if(remaining<=0&&attempt>0)break;
      try{
        const ack=await this.post('result',{request_id:job.requestId,token:job.token,result},Math.min(3000,Math.max(1000,remaining)));
        if(ack.status==='COMMITTED'){
          if(state.pull_inflight?.request_id===job.requestId){delete state.pull_inflight;await this.persist(state);}
          return ack;
        }
        if(['EXPIRED_RESERVED','LEASE_REJECTED','RESULT_CONFLICT'].includes(ack.status))return ack;
      }catch(e){if(e.code==='HELPER_STATE_PERSIST_FAILED')throw e;}
      if(job.deadline-this.now()>200)await this.sleep(200);
    }
    return {status:'ACK_UNCERTAIN'};
  }
  async run(){
    let ready=false,backoff=250;
    while(this.now()<Date.parse(this.hello.task_expires_utc)){
      try{
        if(!ready){await this.connect();ready=true;}
        const job=await this.post('claim');
        if(job.status==='TASK_NOT_ACTIVE')return;
        await this.processClaim(job);backoff=250;
        if(job.status!=='CLAIMED')await this.sleep(250);
      }catch(e){
        if(e.code==='HELPER_STATE_PERSIST_FAILED')throw e;
        ready=false;await this.sleep(backoff);backoff=Math.min(2000,backoff*2);
      }
    }
  }
}
