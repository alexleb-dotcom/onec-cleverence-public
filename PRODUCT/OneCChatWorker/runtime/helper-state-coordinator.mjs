import fsp from 'node:fs/promises';

export function safePersistenceCode(error){
  const code=String(error?.cause_code||error?.code||'ERROR');
  return ['EPERM','EACCES','EBUSY','ENOSPC','ENOENT','EEXIST','EIO','EROFS','EMFILE','ENFILE','EINVAL','ENAMETOOLONG','ENOTDIR','EISDIR','EDQUOT','EBADF','EFBIG','UNKNOWN','ERROR'].includes(code)?code:'ERROR';
}

function persistError(error,phase){
  const e=new Error('HELPER_STATE_PERSIST_FAILED');
  e.code='HELPER_STATE_PERSIST_FAILED';
  e.cause_code=safePersistenceCode(error);
  e.persist_phase=phase;
  return e;
}

const saves=new Map();
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
// Retry only operations that cannot truncate evidence: exclusive open before
// any bytes were written, and rename of the SAME completed/synced temp file.
async function retryTransient(operation,sleepImpl){
  for(let attempt=0;;attempt++){
    try{return await operation();}catch(error){
      if(!['EPERM','EACCES','EBUSY'].includes(error?.code)||attempt===3)throw error;
      await sleepImpl([50,100,200][attempt]);
    }
  }
}

export async function saveStateAtomic(statePath,state,{fsApi=fsp,sleepImpl=sleep}={}){
  const tmp=statePath+'.tmp';
  let text;
  try{text=JSON.stringify(state,null,2);}catch(error){throw persistError(error,'serialize');}
  const prior=saves.get(statePath)||Promise.resolve();
  const current=prior.then(async()=>{
    let file,phase='open';
    try{
      // An existing temp is unresolved recovery evidence, never overwrite it.
      file=await retryTransient(()=>fsApi.open(tmp,'wx'),sleepImpl);
      phase='write';await file.writeFile(text,'utf8');
      phase='sync';await file.sync();
      phase='close';await file.close();file=null;
      phase='rename';await retryTransient(()=>fsApi.rename(tmp,statePath),sleepImpl);
    }catch(error){
      if(file)await file.close().catch(()=>{});
      throw persistError(error,phase);
    }
  });
  saves.set(statePath,current);
  // A failed lane stays poisoned until process restart/recover-first. No later
  // save can overwrite its temp or silently send an unpersisted cached result.
  await current;
  if(saves.get(statePath)===current)saves.delete(statePath);
}

export async function loadPersistedState(statePath,binding,{fsApi=fsp}={}){
  // Crash residue must be adjudicated by the existing Core recovery owner.
  // Missing/corrupt/mismatched caches are never replaced with an empty cache.
  try{await fsApi.stat(statePath+'.tmp');}catch(error){
    if(error?.code!=='ENOENT')throw persistError(error,'read');
    try{
      const state=JSON.parse(await fsApi.readFile(statePath,'utf8'));
      if(Object.entries(binding).some(([key,value])=>state[key]!==value))throw new Error('binding');
      for(const name of ['processed','idempotency'])if(!state[name]||typeof state[name]!=='object'||Array.isArray(state[name]))throw new Error('cache');
      if(Object.entries(state.processed).some(([id,r])=>!r||r.type!=='result'||r.request_id!==id||!['OK','ERROR'].includes(r.status)||!r.metadata||!Object.hasOwn(r,'payload')))throw new Error('cache');
      if(Object.keys(state.processed).length&& !/^[a-f0-9-]{36}$/i.test(state.pull_helper_id||''))throw new Error('helper');
      return state;
    }catch(error){
      if(error?.code==='ENOENT')return null;
      const e=new Error('HELPER_STATE_RECOVERY_REQUIRED');e.code=e.message;throw e;
    }
  }
  const e=new Error('HELPER_STATE_TMP_RECOVERY_REQUIRED');e.code=e.message;throw e;
}

export async function persistAndSendProcessed({state,requestId,result,persist,send}){
  state.processed=state.processed||{};
  const prior=state.processed[requestId];
  if(prior){
    await send(prior);
    return {replayed:true};
  }
  state.processed[requestId]=result;
  try{
    await persist(state);
  }catch(error){
    delete state.processed[requestId];
    throw error;
  }
  await send(result);
  return {replayed:false};
}

export function createSerializedMessagePump({handle,onFailure}){
  let tail=Promise.resolve();
  let failed=false;
  let failure=null;
  const dispatch=message=>{
    const run=tail.then(async()=>{
      if(failed)return {status:'SKIPPED_AFTER_FAILURE'};
      try{
        await handle(message);
        return {status:'OK'};
      }catch(error){
        failed=true;
        failure=error;
        try{await onFailure?.(error,message);}catch{}
        return {status:'FAILED',error};
      }
    });
    tail=run.then(()=>undefined,()=>undefined);
    return run;
  };
  return {
    dispatch,
    drain:()=>tail,
    failed:()=>failed,
    failure:()=>failure
  };
}
