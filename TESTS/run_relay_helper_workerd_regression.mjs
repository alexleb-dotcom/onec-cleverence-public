// Opt-in host integration; dependencies are installed in a separate scratch
// directory, never in the deployed relay. See TRANSPORT_RELIABILITY.md.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {createSerializedMessagePump,persistAndSendProcessed} from '../PRODUCT/OneCChatWorker/runtime/helper-state-coordinator.mjs';

if(!process.argv[2])throw Error('DEPENDENCY_SCRATCH_ROOT_REQUIRED');
const dependencyRoot=path.resolve(process.argv[2]);
const require=createRequire(path.join(dependencyRoot,'package.json'));
const {Miniflare,convertV4MiniflareOptions}=require('miniflare');
const {build}=require('esbuild');
const baseline=process.argv.includes('--baseline');
const root=fileURLToPath(new URL('../',import.meta.url));
const read=async rel=>baseline?execFileSync('git',['show','7af5073a23e4be8e86ac04c42fb6db427d491bd7:'+rel],{cwd:root,encoding:'utf8'}):fs.readFile(path.join(root,rel),'utf8');
const relay=await read('PRODUCT/OneCChatWorker/relay/src/index.js');
const helper=await read('PRODUCT/OneCChatWorker/runtime/hosted-helper.mjs');
const begin=relay.indexOf('import { startBoundedResponseRetries');
const end=relay.indexOf('\nfunction mcpError(');
assert(begin>=0&&end>begin);
const script=relay.slice(begin,end)+`
// Test-only constructor counter proves actual host reconstruction after idle.
export class FixtureRelay extends RelaySession {
 constructor(state,env){super(state,env);state.blockConcurrencyWhile(async()=>{
   await state.storage.put('fixture_boots',(await state.storage.get('fixture_boots')||0)+1);
 });}
 async status(){const r=await super.status();return Response.json({...await r.json(),fixture_boots:await this.state.storage.get('fixture_boots')});}
}
export default {fetch(request,env){return env.RELAY.get(env.RELAY.idFromName("synthetic-fixture")).fetch(request);}};`;
const bundle=await build({stdin:{contents:script,resolveDir:path.join(root,'PRODUCT/OneCChatWorker/relay/src'),sourcefile:'fixture.js'},bundle:true,write:false,format:'esm',platform:'browser'});
// Miniflare's CF cache also uses process.cwd(), independently of rootPath.
// Keep all host scratch outside the governed public snapshot.
process.chdir(dependencyRoot);
const options={rootPath:dependencyRoot,workers:[{name:'synthetic-fixture',modules:true,script:bundle.outputFiles[0].text,compatibilityDate:'2026-10-01',durableObjects:{RELAY:{className:'FixtureRelay',useSQLite:true}},bindings:{HELPER_SECRET:'fixture-secret-not-real'}}]};
const mf=new Miniflare(convertV4MiniflareOptions?convertV4MiniflareOptions(options):options);
const now=Date.now(),state={processed:{},session_id:'b'.repeat(32)};
const hello={type:'hello',admission_schema_version:3,task_admission_id:'a'.repeat(32),session_id:state.session_id,project_id:'P',task_id:'T',task_goal_sha256:'c'.repeat(64),manifest_sha256:'d'.repeat(64),snapshot_id:'s'.repeat(64),output_task_root:'Output/T',helper_version:'synthetic',task_created_utc:new Date(now-10000).toISOString(),task_expires_utc:new Date(now+3600000).toISOString(),caps:{task_request_limit:96,task_result_byte_limit:108000,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000}};
let executions=0,persists=0,onLog=async()=>{},onProjection=async()=>{},client,pump,helperErrors=[];
const helperStart=helper.indexOf(baseline?'async function handleRelayMessage(':'const advisoryPump=');
assert(helperStart>=0);
const helperBody=helper.slice(helperStart,helper.indexOf('\nasync function connectLoop('));
const deps={state,caps:hello.caps,persistAndSendProcessed,createSerializedMessagePump,
 saveState:async()=>{persists++;},exec:async op=>{executions++;return {status:'OK',metadata:{op},payload:{content:'synthetic bounded fixture'}};},
 log:async entry=>onLog(entry),saveUiProjection:async p=>onProjection(p),TASK_ADMISSION_ID:hello.task_admission_id};
const handlers=new Function(...Object.keys(deps),helperBody+'\nreturn {handle:handleRelayMessage,drain:()=>'+(baseline?'Promise.resolve()':'advisoryPump.drain()')+'};')(...Object.values(deps));
const tick=()=>new Promise(resolve=>setTimeout(resolve,5));
async function until(test){const deadline=Date.now()+4000;while(!test()){assert(Date.now()<deadline,'host phase deadline exceeded');await tick();}}
let passed=0;
async function check(name,fn){await fn();passed++;console.log('PASS '+name);}
async function connect(){
 const url=new URL('/helper?token=fixture-secret-not-real',await mf.ready);url.protocol='ws:';
 client=new WebSocket(url);
 pump=createSerializedMessagePump({handle:ev=>handlers.handle(client,ev),onFailure:async e=>{helperErrors.push(e);client.close();}});
 client.addEventListener('message',ev=>{void pump.dispatch(ev);});
 await new Promise((resolve,reject)=>{client.addEventListener('open',resolve,{once:true});client.addEventListener('error',reject,{once:true});});
 client.send(JSON.stringify(hello));
 await tick();
 for(let i=0;i<100;i++){const s=await status();if(s.meta?.connected)return;await tick();}
 assert.fail('hello not committed');
}
async function status(){return (await mf.dispatchFetch('http://fixture/status')).json();}
async function rpc(op='read'){const r=await mf.dispatchFetch('http://fixture/rpc',{method:'POST',body:JSON.stringify({op,args:op==='context'?{}:{path:'fixture.bsl',start:1,end:20}})});return {status:r.status,data:await r.json()};}
try{
 await connect();
 await check('NATIVE_NODE_WS_CONTEXT_READ_CONTEXT',async()=>{
   for(const op of ['context','read','context'])assert.equal((await rpc(op)).status,200);
   assert.equal((await status()).meta.task_requests_used,3);
 });
 await check('RESULT_LOG_STALL_CROSSES_2500MS_WITHOUT_FALSE_OFFLINE',async()=>{
   let release,blocked=false;const barrier=new Promise(resolve=>{release=resolve;});
   onLog=async entry=>{if(entry.event==='RESULT'){blocked=true;await barrier;}};
   try{
     assert.equal((await rpc('context')).status,200);await until(()=>blocked);
     const before=(await status()).meta.task_requests_used;
     const pending=rpc();await new Promise(resolve=>setTimeout(resolve,2600));
     const result=await pending;assert.equal(result.status,baseline?503:200);
     console.log('HOST_PROBE_OUTCOME',JSON.stringify({lane:'result-log',baseline,http_status:result.status}));
     assert.equal((await status()).meta.task_requests_used,before+(baseline?0:1));
   }finally{release();onLog=async()=>{};await pump.drain();await handlers.drain();}
   if(baseline)await connect();
 });
 await check('PROJECTION_STALL_CROSSES_2500MS_WITHOUT_FALSE_OFFLINE',async()=>{
   let release,blocked=false;const barrier=new Promise(resolve=>{release=resolve;});
   onProjection=async()=>{blocked=true;await barrier;};
   try{
     assert.equal((await rpc('context')).status,200);await until(()=>blocked);
     const before=(await status()).meta.task_requests_used;
     const pending=rpc();await new Promise(resolve=>setTimeout(resolve,2600));
     const result=await pending;assert.equal(result.status,baseline?503:200);
     console.log('HOST_PROBE_OUTCOME',JSON.stringify({lane:'ui-projection',baseline,http_status:result.status}));
     assert.equal((await status()).meta.task_requests_used,before+(baseline?0:1));
   }finally{release();onProjection=async()=>{};await pump.drain();await handlers.drain();}
   if(baseline)await connect();
 });
 await check('IDLE_WAKE_PRESERVES_SOCKET_AND_ACCOUNTING',async()=>{
   const initial=await status(),before=initial.meta;
   await new Promise(resolve=>setTimeout(resolve,12000));
   assert.equal((await rpc()).status,200);
   const final=await status(),after=final.meta;
   assert(final.fixture_boots>initial.fixture_boots,'workerd must reconstruct the hibernated actor');
   assert.equal(after.task_requests_used,before.task_requests_used+1);
   assert.equal(after.session_id,before.session_id);assert.equal(after.task_expires_utc,before.task_expires_utc);
 });
 await check('RECONNECT_RETAINS_PROCESSED_RESULTS_AND_NO_RESERVED',async()=>{
   const before=(await status()).meta,cache=structuredClone(state.processed);
   client.close();await pump.drain();await connect();assert.equal((await rpc()).status,200);
   const after=(await status()).meta;
   assert.equal(after.task_requests_used,before.task_requests_used+1);
   assert(Object.values(after.request_receipts).every(r=>r.state!=='RESERVED'));
   for(const [id,result] of Object.entries(cache))assert.deepEqual(state.processed[id],result);
   assert.equal(executions,persists);if(!baseline)assert.equal(helperErrors.length,0);
 });
 console.log(JSON.stringify({result:'PASS',baseline,checks:passed,executions,persists,claims_production_pass:false,miniflare:require('miniflare/package.json').version,workerd:require('workerd/package.json').version}));
}finally{client?.close();await mf.dispose();}
