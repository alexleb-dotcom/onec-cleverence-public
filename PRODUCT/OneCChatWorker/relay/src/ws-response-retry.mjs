// #108: retry transport delivery only, never reserve a second S4 activity.
// The helper durably caches every processed request_id and replays its result.
export const WS_RESPONSE_RETRY_DELAYS_MS=Object.freeze([2500,6500,10500]);

export function startBoundedResponseRetries({
  requestId,frame,dispatchedSocket,generation,
  isPending,currentSocket,currentGeneration,onResend,onRetry=()=>{},
  schedule=setTimeout,cancel=clearTimeout
}){
  let stopped=false;
  const handles=WS_RESPONSE_RETRY_DELAYS_MS.map(delay=>schedule(()=>{
    if(stopped||!isPending(requestId))return;
    if(currentGeneration()!==generation||currentSocket()!==dispatchedSocket||dispatchedSocket?.readyState!==1)return;
    try{
      onResend(dispatchedSocket,frame);
      onRetry(delay,'RESENT');
    }catch{
      onRetry(delay,'SEND_FAILED');
    }
  },delay));
  return ()=>{
    if(stopped)return;
    stopped=true;
    for(const handle of handles)cancel(handle);
  };
}
