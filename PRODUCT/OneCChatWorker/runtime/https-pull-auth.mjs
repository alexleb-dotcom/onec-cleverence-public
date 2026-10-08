// Private transport protocol. Credentials never appear in URLs or diagnostics.
export const PULL_PREFIX='/helper/pull/';
export const PULL_BODY_LIMIT=262144;
const enc=new TextEncoder();
export function consumePullNonce(entries,auth,now=Date.now()){
  const live=entries.filter(entry=>now<(entry.until??entry.at+60000));
  if(live.some(entry=>entry.nonce===auth.nonce))throw new Error('PULL_REPLAY_REJECTED');
  if(live.length>=128)throw new Error('PULL_RATE_LIMIT');
  // A future timestamp within the allowed skew remains verifiable longer than
  // 60 seconds after receipt. Keep the nonce for its ENTIRE validity window.
  live.push({nonce:auth.nonce,at:now,until:Math.max(now,auth.time)+60000});
  return live;
}
export async function pullDigest(value){
  const digest=await crypto.subtle.digest('SHA-256',enc.encode(value));
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
async function signature(secret,method,path,time,nonce,body){
  const key=await crypto.subtle.importKey('raw',enc.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const value=[method,path,time,nonce,await pullDigest(body)].join('\n');
  const digest=await crypto.subtle.sign('HMAC',key,enc.encode(value));
  return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
export async function pullHeaders(secret,path,body,{now=Date.now(),nonce=crypto.randomUUID()}={}){
  const time=String(now);
  return {'content-type':'application/json',authorization:'Bearer '+secret,
    'x-helper-time':time,'x-helper-nonce':nonce,'x-helper-signature':await signature(secret,'POST',path,time,nonce,body)};
}
export async function readPullText(message,limit=PULL_BODY_LIMIT,timeoutMs=2000){
  const reader=message.body?.getReader();let size=0,parts=[];
  if(!reader)throw new Error('PULL_BODY_INVALID');
  const until=Date.now()+timeoutMs;
  try{for(;;){
    let timer;
    const timeout=new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('PULL_BODY_TIMEOUT')),Math.max(1,until-Date.now()));});
    let next;try{next=await Promise.race([reader.read(),timeout]);}finally{clearTimeout(timer);}
    const {done,value}=next;if(done)break;size+=value.length;
    if(size>limit)throw new Error('PULL_BODY_CAP');parts.push(value);
  }}catch(e){void reader.cancel().catch(()=>{});throw e;}
  const raw=new Uint8Array(size);let offset=0;for(const part of parts){raw.set(part,offset);offset+=part.length;}
  return new TextDecoder('utf-8',{fatal:true}).decode(raw);
}
export async function verifyPullRequest(request,secret,now=Date.now()){
  const url=new URL(request.url);
  if(request.method!=='POST'||url.search||!['hello','claim','result'].includes(url.pathname.slice(PULL_PREFIX.length)))throw new Error('PULL_ROUTE_INVALID');
  if(typeof secret!=='string'||secret.length<20||request.headers.get('authorization')!=='Bearer '+secret)throw new Error('PULL_UNAUTHORIZED');
  const time=request.headers.get('x-helper-time')||'',nonce=request.headers.get('x-helper-nonce')||'';
  if(!/^\d{13}$/.test(time)||Math.abs(now-Number(time))>60000||! /^[a-f0-9-]{36}$/i.test(nonce))throw new Error('PULL_AUTH_EXPIRED');
  const limit=url.pathname===PULL_PREFIX+'hello'?PULL_BODY_LIMIT:12288;
  const body=await readPullText(request,limit);
  const expected=await signature(secret,'POST',url.pathname,time,nonce,body);
  const actual=request.headers.get('x-helper-signature')||'';
  let diff=actual.length^expected.length;for(let i=0;i<expected.length;i++)diff|=expected.charCodeAt(i)^(actual.charCodeAt(i)||0);
  if(diff)throw new Error('PULL_SIGNATURE_INVALID');
  const value=JSON.parse(body);
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('PULL_BODY_INVALID');
  return {value,nonce,time:Number(time)};
}
