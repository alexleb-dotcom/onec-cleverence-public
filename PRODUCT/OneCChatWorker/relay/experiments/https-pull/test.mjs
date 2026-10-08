import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {PullMailbox} from './mailbox.mjs';
const copy = v => structuredClone(v);
const task={admission:'a'.repeat(32),session:'b'.repeat(32),snapshot:'c'.repeat(64),expires:1000000};
const identity={admission:task.admission,session:task.session,snapshot:task.snapshot};
let now=1000,seq=0,passes=0;
const id=()=> 'mcp-' + (++seq).toString(16).padStart(64,'0');
const accounting={
 reserve(s,j){assert(!s.states[j.requestId]);s.states[j.requestId]='RESERVED';s.used++},
 commit(s,j){assert.equal(s.states[j.requestId],'RESERVED');s.states[j.requestId]='COMMITTED';s.committed++},
 ambiguous(s,j){assert.equal(s.states[j.requestId],'RESERVED');s.states[j.requestId]='AMBIGUOUS_CHARGED';s.ambiguous++}
};
class AtomicStore {
 constructor(){this.data={task:copy(task),job:null,receipts:{},s4:{used:0,committed:0,ambiguous:0,states:{}}};this.tail=Promise.resolve()}
 tx(fn){const r=this.tail.then(()=>{const draft=copy(this.data),out=fn(draft);this.data=draft;return copy(out)});this.tail=r.then(()=>{},()=>{});return r}
}
const setup=()=>{now=1000;const store=new AtomicStore();return {store,box:new PullMailbox({store,accounting,now:()=>now,newToken:()=> 'lease-'+(++seq)})}};
const request=()=>({requestId:id(),fingerprint:'sha256-fixture',identity,op:'read',args:{path:'fixture.bsl',start:1,end:20},deadline:now+15000});
const test=async(name,fn)=>{await fn();passes++;console.log('PASS '+name)};
const claim=box=>box.claim({identity,helperId:'reader'});
const finish=(box,j,c,result={status:'OK',payload:{lines:'ok'}})=>box.complete({identity,helperId:'reader',requestId:j.requestId,token:c.token,result});
await test('unclaimed deadline has zero S4 charge',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);now+=15000;assert.equal((await box.expire()).status,'EXPIRED_UNCLAIMED');assert.equal(store.data.s4.used,0)});
await test('same reader claim is replay not double reserve',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);const a=await claim(box),b=await claim(box);assert.equal(a.token,b.token);assert.equal(b.replay,true);assert.equal(store.data.s4.used,1)});
await test('committed result survives duplicate POST',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);const c=await claim(box);assert.equal((await finish(box,j,c)).status,'COMMITTED');assert.equal((await finish(box,j,c)).replay,true);assert.equal(store.data.s4.committed,1)});
await test('conflicting result cannot overwrite',async()=>{const {box}=setup(),j=request();await box.enqueue(j);const c=await claim(box);await finish(box,j,c);assert.equal((await finish(box,j,c,{status:'OK',payload:{lines:'bad'}})).status,'RESULT_CONFLICT')});
await test('claimed timeout is fail-closed exactly once',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);const c=await claim(box);now+=15000;assert.equal((await box.expire()).status,'AMBIGUOUS_CHARGED');await box.expire();assert.equal(store.data.s4.ambiguous,1);assert.equal((await finish(box,j,c)).status,'EXPIRED_RESERVED')});
await test('foreign admission and stale lease rejected',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);assert.equal((await box.claim({identity:{...identity,session:'foreign'},helperId:'reader'})).status,'TASK_NOT_ACTIVE');const c=await claim(box);assert.equal((await box.complete({identity,helperId:'reader',requestId:j.requestId,token:'wrong',result:{status:'OK',payload:{}}})).status,'LEASE_REJECTED');assert.equal(store.data.s4.used,1);assert(c.token)});
await test('oversized result is not committed',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);const c=await claim(box);assert.equal((await finish(box,j,c,{status:'OK',payload:{blob:'x'.repeat(4000)}})).status,'RESULT_INVALID');assert.equal(store.data.s4.committed,0)});
await test('ten concurrent claims reserve once',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);const all=await Promise.all(Array.from({length:10},()=>claim(box)));assert.equal(new Set(all.map(x=>x.token)).size,1);assert.equal(store.data.s4.used,1)});
await test('reinstantiated mailbox preserves durable lease',async()=>{const {box,store}=setup(),j=request();await box.enqueue(j);const c=await claim(box),fresh=new PullMailbox({store,accounting,now:()=>now});assert.equal((await claim(fresh)).token,c.token);assert.equal((await finish(fresh,j,c)).status,'COMMITTED')});
await test('active lane rejects a second job and identity collision',async()=>{const {box}=setup(),j=request(),other=request();await box.enqueue(j);assert.equal((await box.enqueue(other)).status,'BUSY');assert.equal((await box.enqueue({...j,fingerprint:'different'})).status,'ID_COLLISION')});
await test('unexpired task identity is mandatory',async()=>{const {box,store}=setup();store.data.task.expires=now;assert.equal((await box.enqueue(request())).status,'TASK_NOT_ACTIVE')});
await test('loopback HTTP outbound pull: four sequential reads + virtual idle',async()=>{
 const {box,store}=setup();const token='test-only';const cached=new Map();let executions=0;
 const srv=createServer(async(req,res)=>{
  let raw='';for await(const c of req)raw+=c;const body=raw?JSON.parse(raw):{};
  const send=(status,obj)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(obj))};
  if(req.headers.authorization!=='Bearer '+token)return send(401,{status:'AUTH_REJECTED'});
  if(req.url==='/poll')return send(200,await claim(box));
  if(req.url==='/result')return send(200,await box.complete({identity,helperId:'reader',requestId:body.requestId,token:body.token,result:body.result}));
  send(404,{status:'NOT_FOUND'});
 });
 srv.listen(0,'localhost');await once(srv,'listening');
 const base='http://localhost:'+srv.address().port;
 const post=async(path,body={})=>(await fetch(base+path,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
 try{
  assert.equal((await fetch(base+'/poll',{method:'POST'})).status,401);
  for(let i=0;i<5;i++){
   if(i===4)now+=150000;
   const j=request();assert.equal((await box.enqueue(j)).status,'PENDING');const c=await post('/poll');assert.equal(c.status,'CLAIMED');
   assert.equal((await post('/poll')).token,c.token);
   if(!cached.has(c.requestId)){executions++;cached.set(c.requestId,{status:'OK',payload:{content:'lines-'+i}})}
   assert.equal((await post('/result',{requestId:c.requestId,token:c.token,result:cached.get(c.requestId)})).status,'COMMITTED');
   assert.equal((await box.status({identity,requestId:c.requestId})).status,'COMMITTED');
  }
  assert.equal(store.data.s4.used,5);assert.equal(store.data.s4.committed,5);assert.equal(executions,5);
 }finally{await new Promise(resolve=>srv.close(resolve))}
});
console.log(JSON.stringify({status:'PASS',checks:passes,production:false,real_s4:false}));
