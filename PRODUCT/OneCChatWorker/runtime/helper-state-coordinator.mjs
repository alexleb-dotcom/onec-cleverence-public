import fsp from 'node:fs/promises';

function persistError(error){
  const e=new Error('HELPER_STATE_PERSIST_FAILED');
  e.code='HELPER_STATE_PERSIST_FAILED';
  e.cause_code=String(error?.code||error?.name||'ERROR');
  e.cause_message=String(error?.message||error).slice(0,240);
  return e;
}

export async function saveStateAtomic(statePath,state,{fsApi=fsp}={}){
  const tmp=statePath+'.tmp';
  let text;
  try{text=JSON.stringify(state,null,2);}catch(error){throw persistError(error);}
  try{
    await fsApi.writeFile(tmp,text,'utf8');
    await fsApi.rename(tmp,statePath);
  }catch(error){
    throw persistError(error);
  }
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
