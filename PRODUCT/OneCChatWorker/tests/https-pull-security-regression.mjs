import assert from 'node:assert/strict';
import {pullHeaders,verifyPullRequest,readPullText,consumePullNonce} from '../runtime/https-pull-auth.mjs';
import {PullMailbox} from '../relay/experiments/https-pull/mailbox.mjs';
import {createTaskRecord,reserveRequest,commitRequest,chargeAmbiguousRequest,activityReceiptHashInput,sealActivityReceipt} from '../relay/src/s4-accounting.js';

const secret='isolated-security-fixture-credential';
const path='/helper/pull/claim',body=JSON.stringify({identity:{admission:'fixture'},helper_id:crypto.randomUUID()});
const headers=await pullHeaders(secret,path,body);
const request=(p=path,text=body,h=headers)=>new Request('https://relay.invalid'+p,{method:'POST',headers:h,body:text});
assert.equal((await verifyPullRequest(request(),secret)).value.identity.admission,'fixture');
await assert.rejects(verifyPullRequest(request(path,body+' '),secret),/SIGNATURE_INVALID/);
await assert.rejects(verifyPullRequest(request(path+'?token=fixture'),secret),/ROUTE_INVALID/);
await assert.rejects(verifyPullRequest(request(),secret,Date.now()+61000),/AUTH_EXPIRED/);
await assert.rejects(verifyPullRequest(request(path,'x'.repeat(12289)),secret),/BODY_CAP/);
let cancelled=false;
const slow=new Response(new ReadableStream({pull(){return new Promise(()=>{});},cancel(){cancelled=true;}}));
await assert.rejects(readPullText(slow,1024,10),/BODY_TIMEOUT/);assert.equal(cancelled,true);
console.log('PASS bounded private authentication, signed body, timestamp and slow-body fence');
const authNow=Date.now(),futureHeaders=await pullHeaders(secret,path,body,{now:authNow+59000});
const futureAuth=await verifyPullRequest(request(path,body,futureHeaders),secret,authNow);
const nonces=consumePullNonce([],futureAuth,authNow);
// Still inside signature validity after the naive receipt-time TTL elapsed.
await verifyPullRequest(request(path,body,futureHeaders),secret,authNow+61000);
assert.throws(()=>consumePullNonce(nonces,futureAuth,authNow+61000),/REPLAY_REJECTED/);
assert.equal(consumePullNonce(nonces,{nonce:crypto.randomUUID(),time:authNow+120000},authNow+120000).length,1);
assert.throws(()=>consumePullNonce(Array.from({length:128},(_,i)=>({nonce:String(i),until:authNow+60000})),{nonce:'overflow',time:authNow},authNow),/RATE_LIMIT/);
console.log('PASS nonce replay fence spans the full signed timestamp validity window, with bounded capacity');

let now=1000;
const hello={admission_schema_version:3,task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),project_id:'P',task_id:'T',manifest_sha256:'c'.repeat(64),snapshot_id:'snapshot',output_task_root:'Output/T',task_created_utc:new Date(0).toISOString(),task_expires_utc:new Date(1000000).toISOString(),caps:{task_request_limit:2048,task_result_byte_limit:2097152,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000}};
const identity={admission:hello.task_admission_id,session:hello.session_id,snapshot:hello.snapshot_id};
const record=createTaskRecord(hello,{nowMs:now});
let data={task:{...identity,expires:1000000},s4:record,receipts:{},job:null},tail=Promise.resolve(),gate=null;
const store={tx(fn){const result=tail.then(async()=>{await gate;const draft=structuredClone(data),out=await fn(draft);data=draft;return out;});tail=result.catch(()=>{});return result;}};
const seal=async(r,j,safe)=>{
 const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(activityReceiptHashInput(r,j.requestId,safe))));
 sealActivityReceipt(r,{requestId:j.requestId,safeResult:safe,activitySha256:[...new Uint8Array(hash)].map(v=>v.toString(16).padStart(2,'0')).join('')});
};
const mailbox=new PullMailbox({store,now:()=>now,accounting:{
 reserve(r,j){return reserveRequest(r,{requestId:j.requestId,fingerprint:j.fingerprint,op:j.op,nowMs:now});},
 async commit(r,j,result){commitRequest(r,{requestId:j.requestId,fingerprint:j.fingerprint,payloadBytes:new TextEncoder().encode(JSON.stringify(result.payload)).length,nowMs:now});await seal(r,j,{status:result.status});},
 async ambiguous(r,j){chargeAmbiguousRequest(r,{requestId:j.requestId,fingerprint:j.fingerprint,nowMs:now});await seal(r,j,{status:'ERROR'});}
}});
const id='mcp-'+'d'.repeat(64);
await mailbox.enqueue({requestId:id,fingerprint:'fp',identity,op:'read',args:{},deadline:16000});
const lease=await mailbox.claim({identity,helperId:'fixture'});
let release;gate=new Promise(r=>{release=r;});
const completing=mailbox.complete({identity,helperId:'fixture',requestId:id,token:lease.token,result:{status:'OK',payload:{content:'late'}}});
now=16000;release();gate=null;
assert.equal((await completing).status,'EXPIRED_RESERVED');
assert.equal(data.s4.task_requests_used,1);assert.equal(data.s4.task_result_bytes_used,3000);
assert.equal(data.s4.request_receipts[id].state,'AMBIGUOUS_CHARGED');
await mailbox.expire();assert.equal(data.s4.task_result_bytes_used,3000);
console.log('PASS transaction-time lease expiry with real S4, one ambiguous charge and one sealed receipt');
console.log(JSON.stringify({result:'PASS',real_s4:true,checks:3,production:false}));
