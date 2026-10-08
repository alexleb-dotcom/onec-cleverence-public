import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {Miniflare} from 'miniflare';
import nodeCrypto from 'node:crypto';

const root=path.resolve(process.argv[2]),scratch=process.cwd();
const product=path.join(root,'PRODUCT/OneCChatWorker');
const {HttpsPullHelper}=await import(pathToFileURL(path.join(product,'runtime/helper-https-pull.mjs')));
const {pullHeaders}=await import(pathToFileURL(path.join(product,'runtime/https-pull-auth.mjs')));
const {saveStateAtomic,persistAndSendProcessed}=await import(pathToFileURL(path.join(product,'runtime/helper-state-coordinator.mjs')));
const {createSerializedMessagePump}=await import(pathToFileURL(path.join(product,'runtime/helper-state-coordinator.mjs')));
const {SourceReaderIntegration,PROVIDER_VERSION}=await import(pathToFileURL(path.join(product,'runtime/source-reader-integration.mjs')));
const {createTaskCheckpointStore}=await import(pathToFileURL(path.join(product,'runtime/task-checkpoint-store.mjs')));
const {boundedTargetHints,reportBindingMatches}=await import(pathToFileURL(path.join(product,'runtime/local-quality-adapter.mjs')));
const sha256=b=>nodeCrypto.createHash('sha256').update(b).digest('hex');
const relaySource=await fs.readFile(path.join(product,'relay/src/index.js'),'utf8');
const toolsSource=relaySource.slice(relaySource.indexOf('const TOOLS=['),relaySource.indexOf('const McpApiHandler='));
assert.equal(sha256(toolsSource),'b7b2c3baaba93ed8c81830d65d6df6e619f7161cea6b79391a590a7de17e993e','accepted six tool schemas, descriptions and argument limits');
const secret='isolated-native-test-secret-no-production';
const created=Date.now(),hello={type:'hello',admission_schema_version:3,task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),
  project_id:'P',task_id:'T',task_goal_sha256:'c'.repeat(64),manifest_sha256:'d'.repeat(64),snapshot_id:'s'.repeat(64),
  output_task_root:'Output/T',helper_version:'isolated-native-test',task_created_utc:new Date(created-1000).toISOString(),
  task_expires_utc:new Date(created+720000).toISOString(),caps:{task_request_limit:2048,task_result_byte_limit:2097152,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000}};
const fixture=`import {RelaySession,McpApiHandler,DefaultHandler,TOOLS} from ${JSON.stringify(path.join(product,'relay/src/index.js'))};
import {createTaskRecord} from ${JSON.stringify(path.join(product,'relay/src/s4-accounting.js'))};
export class TestRelay extends RelaySession {
 async fetch(request){
  const p=new URL(request.url).pathname;
  if(p==='/_test/seed'){
   const h=await request.json();if(await this.state.storage.get('active_task_id'))throw new Error('seed forbidden');
   await this.state.storage.put('task:'+h.task_admission_id,createTaskRecord(h));
   await this.state.storage.put('active_task_id',h.task_admission_id);await this.state.storage.put('active_mode','s4');
   return Response.json({seeded:true});
  }
  if(p==='/_test/inspect')return Response.json({record:await this.activeTaskRecord(),mailbox:await this.state.storage.get('https_pull_v1')});
  if(p.startsWith('/_test/record/'))return Response.json(await this.state.storage.get('task:'+p.slice('/_test/record/'.length)));
  if(p==='/_test/deadline'){
   const v=await request.json();await this.state.storage.transaction(async t=>{
    const m=await t.get('https_pull_v1');if(m.job)m.job.deadline=Date.now()-1;await t.put('https_pull_v1',m);
    if(v.task){const id=await t.get('active_task_id'),r=await t.get('task:'+id);r.task_expires_utc=new Date(Date.now()-1).toISOString();await t.put('task:'+id,r);}
   });await this.alarm();return Response.json({advanced:true});
  }
  if(p==='/_test/reserve-failure'){
   const transport=this.pullTransport(),original=transport.mailbox.accounting.reserve;
   transport.mailbox.accounting.reserve=async(...args)=>{transport.mailbox.accounting.reserve=original;await original(...args);throw new Error('isolated failure before lease commit');};
   return Response.json({armed:true});
  }
  return super.fetch(request);
 }
}
export default {fetch(request,env){
 if(new URL(request.url).pathname==='/_test/mcp')return McpApiHandler.fetch(request,env,{props:{githubLogin:'alexleb-dotcom'}});
 if(new URL(request.url).pathname.startsWith('/helper/pull/'))return DefaultHandler.fetch(request,env);
 return env.RELAY.get(env.RELAY.idFromName('q1')).fetch(request);
}};`;
await fs.writeFile(path.join(scratch,'worker-fixture.mjs'),fixture);
await build({entryPoints:[path.join(scratch,'worker-fixture.mjs')],outfile:path.join(scratch,'worker.mjs'),bundle:true,format:'esm',platform:'browser',external:['cloudflare:*'],nodePaths:[path.join(scratch,'node_modules')],logLevel:'silent',
 plugins:[{name:'isolated-exports',setup(builder){builder.onLoad({filter:/relay[/\\]src[/\\]index\.js$/},async args=>({contents:(await fs.readFile(args.path,'utf8'))+'\nexport {McpApiHandler,DefaultHandler,TOOLS};',loader:'js',resolveDir:path.dirname(args.path)}));}}]});
const config={modules:true,scriptPath:path.join(scratch,'worker.mjs'),compatibilityDate:'2026-10-01',compatibilityFlags:['global_fetch_strictly_public'],
 durableObjects:{RELAY:{className:'TestRelay',useSQLite:true}},durableObjectsPersist:path.join(scratch,'sqlite'),bindings:{HELPER_SECRET:secret}};
let mf=new Miniflare(config),passes=0,executions=0,latencies=[];
// Miniflare rewraps Undici's response stream. Consume it immediately: otherwise
// GC of the original Undici Response can cancel the still-owned wrapper stream.
// The test client retains bytes, as a client that reads while helper POST finishes.
const call=async(p,data)=>{
 const response=await mf.dispatchFetch('https://relay.invalid'+p,{method:data===undefined?'GET':'POST',body:data===undefined?undefined:JSON.stringify(data)});
 return new Response(await response.arrayBuffer(),{status:response.status,headers:response.headers});
};
const inspect=async()=>(await call('/_test/inspect')).json();
const test=async(name,fn)=>{await fn();passes++;console.log('PASS '+name);};
const until=async(fn)=>{const deadline=Date.now()+5000;while(!await fn()){if(Date.now()>deadline)assert.fail('phase timeout');await new Promise(r=>setTimeout(r,5));}};
await call('/_test/seed',hello);
const statePath=path.join(scratch,'persisted-helper-state.json');let state={processed:{},idempotency:{},quality_targets:[],session_id:hello.session_id,expires_utc:hello.task_expires_utc,started_utc:hello.task_created_utc};
const workerRoot=path.join(scratch,'worker-root'),projectRoot=path.join(workerRoot,'P'),sourceRel='Participants/ut/Target/Main/Module.bsl';
const sourcePath=path.join(projectRoot,sourceRel),source=Array.from({length:100},(_,i)=>`// Fixture line ${i+1}`).join('\n');
await fs.mkdir(path.dirname(sourcePath),{recursive:true});await fs.mkdir(path.join(projectRoot,'Output'),{recursive:true});
await fs.writeFile(sourcePath,source);const sourceBefore=await fs.readFile(sourcePath);
const configPath=path.join(scratch,'provider-config.json');
await fs.writeFile(configPath,JSON.stringify({schema_version:1,contract_id:'onecchatworker',contract_version:'1.0',worker_root:workerRoot,admitted_projects:['P'],rg_path:process.argv[3],audit_path:path.join(scratch,'reader-audit.jsonl'),limits:{max_list_depth:4,max_list_entries:2000,default_read_lines:120,max_read_lines:400,max_context_lines:20,max_pattern_chars:512,default_search_matches:20,max_search_matches:100,search_timeout_ms:30000,max_rg_output_bytes:33554432,max_source_file_bytes:16777216,max_artifact_read_bytes:4194304,max_artifact_file_bytes:4194304,max_encoded_content_chars:6000000,max_batch_files:16,max_batch_total_bytes:12582912}}));
const provider=new SourceReaderIntegration({configPath});await provider.initialize();
const admission={...hello,schema_version:3,source_snapshot_id:hello.snapshot_id};
const checkpointStore=createTaskCheckpointStore({programDataRoot:path.join(scratch,'program-data'),admission});
const hostedSource=await fs.readFile(path.join(product,'runtime/hosted-helper.mjs'),'utf8');
const executionSource=hostedSource.slice(hostedSource.indexOf('function fail(code'),hostedSource.indexOf('\nasync function connectLoop'));
const handler=current=>{
 const artifacts=[{participant_id:'ut',platform:'ONEC',side:'TARGET',artifact_type:'MAIN',artifact_id:'main',path:'Participants/ut/Target/Main'}];
 const deps={state:current,provider,checkpointStore,IS_S4:true,PROJECT:'P',TASK:'T',TASK_ADMISSION_ID:hello.task_admission_id,SNAPSHOT:hello.snapshot_id,manifestHash:hello.manifest_sha256,OUTPUT_TASK_ROOT:'Output/T',TASK_CREATED_UTC:hello.task_created_utc,VERSION:hello.helper_version,PROVIDER_VERSION,
  ARTIFACTS:artifacts,artifactPrefixes:artifacts.map(a=>a.path),admission,manifest:{project_root:projectRoot},TASK_GOAL:null,
  caps:{...hello.caps,max_read_lines:20,max_search_matches:8,max_write_file_bytes:32768,max_task_files:8,max_task_bytes:131072,max_read_chunk_bytes:1800},
  normalizePath:p=>String(p).replaceAll('\\','/').replace(/^\/+|\/+$/g,''),PROV_PATH:'_proposal_provenance.json',allowedProposalExt:new Set(['.md','.txt','.diff','.patch','.bsl','.json']),
  quality:{verifyToolset:async()=>{throw Error('isolated fixture has no quality executables');},runConfirmed:async()=>null},reportBindingMatches,boundedTargetHints,
  fsp:fs,path,sha256,Buffer,createSerializedMessagePump,persistAndSendProcessed,saveState:s=>saveStateAtomic(statePath,s),log:async()=>{},saveUiProjection:async()=>{}};
 const handle=new Function(...Object.keys(deps),executionSource+'\nreturn handleRelayMessage;')(...Object.values(deps));
 return async(ws,ev)=>{const m=JSON.parse(ev.data);if(m.type==='request'&&!current.processed[m.request_id])executions++;await handle(ws,ev);};
};
const makeHelper=current=>new HttpsPullHelper({relayUrl:'wss://relay.invalid/helper',secret,hello,state:current,persist:s=>saveStateAtomic(statePath,s),handle:handler(current),fetchImpl:(url,options)=>mf.dispatchFetch(url,options)});
let helper=makeHelper(state);await helper.connect();
const rpc=(op='read',args={path:sourceRel,start:1,end:20})=>call('/rpc',{op,args});
const rpcJob=async(op='read',args)=>{
 const start=performance.now(),pending=rpc(op,args);
 await until(async()=>(await inspect()).mailbox?.job?.status==='PENDING');
 const job=await helper.post('claim');assert.equal(job.status,'CLAIMED');
 await helper.processClaim(job);const response=await pending,result=await response.json();
 assert.equal(response.status,200,JSON.stringify(result));
 latencies.push(performance.now()-start);return {job,result};
};
const model=async(name,args={})=>{
 const response=await call('/_test/mcp',{jsonrpc:'2.0',id:17,method:'tools/call',params:{name,arguments:args}});
 return (await response.json()).result;
};
const modelJob=async(name,args={},expectError=false)=>{
 const start=performance.now(),pending=model(name,args);
 await until(async()=>(await inspect()).mailbox.job.status==='PENDING');
 const job=await helper.post('claim');await helper.processClaim(job);const result=await pending;
 assert.equal(result.isError,expectError,JSON.stringify(result.structuredContent));latencies.push(performance.now()-start);
 return {job,result:result.structuredContent};
};
try{
 await test('native client retains response bytes across forced GC',async()=>{
  assert.equal(typeof global.gc,'function');const response=await call('/status');
  for(let i=0;i<8;i++){global.gc();await new Promise(r=>setTimeout(r,20));}
  assert.equal(response.bodyUsed,false);assert.equal((await response.json()).online,true);
 });
 await test('four sequential source_read with real S4 and SQLite',async()=>{
  const before=(await inspect()).record;for(let i=0;i<4;i++)await rpcJob();const after=(await inspect()).record;
  assert.equal(after.task_requests_used-before.task_requests_used,4);assert.equal(after.activity_committed_seq-before.activity_committed_seq,4);
  assert.match(after.activity_integrity_sha256,/^[a-f0-9]{64}$/);
 });
 await test('context/read/context preserves charged lifecycle and hash chain',async()=>{
  const first=await rpcJob('context',{});await rpcJob();const last=await rpcJob('context',{});
  assert.equal(last.result.payload.accounting.task_requests_used,first.result.payload.accounting.task_requests_used+2);
  const record=(await inspect()).record;assert.equal(record.task_result_bytes_used,Object.values(record.request_receipts).reduce((n,r)=>n+r.charged_bytes,0));
 });
 await test('concurrent claims and lost claim response reserve and execute once',async()=>{
  const pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');
  const before=(await inspect()).record.task_requests_used;
  const [a,b]=await Promise.all([helper.post('claim'),helper.post('claim').catch(()=>({status:'BUSY'}))]);
  const claimed=[a,b].find(x=>x.status==='CLAIMED');assert(claimed);
  // The server accepted the claim but the proxy discarded its response.
  const recovered=await helper.post('claim');assert.equal(recovered.token,claimed.token);
  const count=executions;await helper.processClaim(recovered);assert.equal((await pending).status,200);
  assert.equal(executions,count+1);assert.equal((await inspect()).record.task_requests_used,before+1);
 });
 await test('lost claim HTTP response recovered after 9s proxy timeout within 15s',async()=>{
  const start=performance.now(),pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');
  const nativeFetch=helper.fetchImpl;let lost=true;
  helper.fetchImpl=async(url,options)=>{const response=await nativeFetch(url,options);
   if(lost&&url.endsWith('/claim')){lost=false;await response.text();await new Promise(r=>setTimeout(r,9000));throw Error('isolated claim response lost');}return response;};
  try{await helper.post('claim');assert.fail('proxy must drop accepted response');}catch{}
  helper.fetchImpl=nativeFetch;await helper.connect();const job=await helper.post('claim');
  await helper.processClaim(job);assert.equal((await pending).status,200);latencies.push(performance.now()-start);
  assert.equal((await inspect()).record.request_receipts[job.requestId].state,'COMMITTED');
 });
 await test('lost POST acknowledgement, duplicate POST, and conflicting POST',async()=>{
  const start=performance.now(),pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');const job=await helper.post('claim');
  const nativeFetch=helper.fetchImpl;let lost=true;
  helper.fetchImpl=async(url,options)=>{const response=await nativeFetch(url,options);
   if(lost&&url.endsWith('/result')){lost=false;await response.text();throw Error('isolated accepted POST acknowledgement lost');}return response;};
  const count=executions;await helper.processClaim(job);helper.fetchImpl=nativeFetch;
  assert.equal((await pending).status,200);assert.equal(executions,count+1);latencies.push(performance.now()-start);
  const body={request_id:job.requestId,token:job.token,result:state.processed[job.requestId]};
  const before=(await inspect()).record;assert.equal((await helper.post('result',body)).status,'COMMITTED');
  assert.equal((await helper.post('result',{...body,result:{...body.result,payload:{content:'conflict'}}})).status,'RESULT_CONFLICT');
  assert.deepEqual((await inspect()).record,before);
  // ACK tombstone survives the next mailbox occupant.
  await rpcJob();assert.equal((await helper.post('result',body)).status,'COMMITTED');
 });
 await test('DO restart and helper restart recover persisted processed cache',async()=>{
  const pending=rpc().catch(()=>null);await until(async()=>(await inspect()).mailbox.job.status==='PENDING');
  const job=await helper.post('claim');const before=executions;
  // Execute/persist, but lose the network before POST can reach the server.
  helper.fetchImpl=async()=>{throw new Error('isolated proxy loss');};await helper.processClaim(job);
  await mf.dispose();await pending;mf=new Miniflare(config);
  state=JSON.parse(await fs.readFile(statePath,'utf8'));helper=makeHelper(state);await helper.connect();
  const replay=await helper.post('claim');assert.equal(replay.token,job.token);await helper.processClaim(replay);
  assert.equal(executions,before+1);assert.equal((await inspect()).record.request_receipts[job.requestId].state,'COMMITTED');
 });
 await test('restart after intent without result charges ambiguity without execution',async()=>{
  const pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');const job=await helper.post('claim');
  state.pull_inflight={request_id:job.requestId,token:job.token,deadline:job.deadline};await saveStateAtomic(statePath,state);
  state=JSON.parse(await fs.readFile(statePath,'utf8'));helper=makeHelper(state);await helper.connect();const count=executions;
  await helper.processClaim(job);assert.equal((await pending).status,504);assert.equal(executions,count);
  const receipt=(await inspect()).record.request_receipts[job.requestId];assert.equal(receipt.state,'AMBIGUOUS_CHARGED');assert.equal(receipt.charged_bytes,3000);
 });
 await test('helper disconnect before claim costs zero; returns without readmission',async()=>{
  const before=(await inspect()).record;const pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');
  await call('/_test/deadline',{});assert.equal((await pending).status,503);assert.deepEqual((await inspect()).record,before);
  await helper.connect();await rpcJob();
 });
 await test('claimed deadline charges once and rejects late result',async()=>{
  const pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');const job=await helper.post('claim');
  await call('/_test/deadline',{});assert.equal((await pending).status,504);
  const before=(await inspect()).record;
  await call('/_test/deadline',{});
  assert.equal((await helper.post('result',{request_id:job.requestId,token:job.token,result:{status:'OK',payload:{content:'late'}}})).status,'EXPIRED_RESERVED');
  assert.deepEqual((await inspect()).record,before);
 });
 await test('identity, signature, nonce replay, and wrong helper fail closed',async()=>{
  const before=(await inspect()).record,path='/helper/pull/claim';
  const body=JSON.stringify({identity:helper.identity,helper_id:state.pull_helper_id});
  const headers=await pullHeaders(secret,path,body);
  const accepted=mf.dispatchFetch('https://relay.invalid'+path,{method:'POST',headers,body});
  const replay=await mf.dispatchFetch('https://relay.invalid'+path,{method:'POST',headers,body});assert.equal(replay.status,403);await accepted;
  for(const change of [{identity:{...helper.identity,session:'wrong'}},{helper_id:crypto.randomUUID()}]){
   const bad=JSON.stringify({identity:helper.identity,helper_id:state.pull_helper_id,...change});
   const response=await mf.dispatchFetch('https://relay.invalid'+path,{method:'POST',headers:await pullHeaders(secret,path,bad),body:bad});assert.equal(response.status,403);
  }
  const modified=await mf.dispatchFetch('https://relay.invalid'+path,{method:'POST',headers,body:body+' '});assert.equal(modified.status,401);
  assert.deepEqual((await inspect()).record,before);
 });
 await test('bounded polling wakes on queued work within MCP deadline',async()=>{
  const poll=helper.post('claim');await new Promise(r=>setTimeout(r,30));const start=performance.now(),pending=rpc();
  const job=await poll;assert.equal(job.status,'CLAIMED');await helper.processClaim(job);assert.equal((await pending).status,200);latencies.push(performance.now()-start);
 });
 for(let i=0;i<12;i++)await rpcJob();
 console.log('WAIT real idle 151 seconds (no traffic, no keepalive)');
 await test('real idle >150 seconds preserves SQLite S4 and next-call delivery',async()=>{
  const before=(await inspect()).record;await new Promise(r=>setTimeout(r,151000));
  assert.deepEqual((await inspect()).record,before);await helper.connect();await rpcJob();
 });
 await test('exact six public MCP schemas and all six actual product paths over Pull',async()=>{
  const listed=await call('/_test/mcp',{jsonrpc:'2.0',id:17,method:'tools/list'});
  const tools=(await listed.json()).result.tools;
  assert.deepEqual(tools,new Function(toolsSource+'\nreturn TOOLS;')());assert.equal(tools.length,6);
  await modelJob('source_context');
  const search=await modelJob('source_search',{query:'Fixture line 1',max_matches:1});assert.equal(search.result.payload.matches.length,1);
  const a=await modelJob('source_read',{path:sourceRel,start:1,end:20});
  const b=await modelJob('source_read',{path:sourceRel,start:1,end:20});assert.notEqual(a.job.requestId,b.job.requestId);
  const content=('x'.repeat(63)+'\n').repeat(128);assert.equal(Buffer.byteLength(content),8192);
  const writeArgs={path:'transport-canary.txt',content,idempotency_key:'pull-large-8192'};
  const written=await modelJob('proposal_write',writeArgs);
  assert.equal(written.result.payload.status,'COMMITTED');assert.equal(written.result.payload.read_back_verified,true);
  assert.equal(written.result.payload.sha256,sha256(content));
  const parts=[];for(let start=1;start<=129;start+=20){
   const read=await modelJob('proposal_read',{path:writeArgs.path,start,end:Math.min(start+19,129)});
   assert.equal(read.result.payload.sha256,sha256(content));parts.push(read.result.payload.content);
  }
  assert.equal(parts.join('\n'),content);
  const provenance=JSON.parse(await fs.readFile(path.join(projectRoot,'Output/T/_proposal_provenance.json'),'utf8'));
  assert.equal(provenance.status,'PROPOSAL_NOT_APPLIED');assert.equal(provenance.files[0].sha256,sha256(content));
  const before=(await inspect()).record.task_requests_used,count=executions;
  const replay=await model('proposal_write',writeArgs);assert.equal(replay.structuredContent.payload.replayed,true);
  assert.equal((await inspect()).record.task_requests_used,before);assert.equal(executions,count);
  const conflict=await model('proposal_write',{...writeArgs,content:'conflict'});assert.equal(conflict.isError,true);assert.equal(executions,count);
  const checkpoint={idempotency_key:'pull-checkpoint',expected_seq:0,expected_predecessor_sha256:null,phase:'IMPLEMENT',status:'IN_PROGRESS',progress_summary:'Pull integrated; independent review remains.',completed_steps:Array.from({length:6},(_,i)=>String(i).repeat(160)),decisions_constraints:['c'.repeat(160),'d'.repeat(160)],first_unfinished_step:'Independent review',do_not_replay:['No Source mutation']};
  const cp=await modelJob('task_checkpoint_write',checkpoint);assert.equal(cp.result.payload.status,'COMMITTED');assert.equal(cp.result.payload.seq,1);
  assert((await fs.stat((await checkpointStore.readHeadVerified()).path)).size<=4096);
  const cpReplay=await model('task_checkpoint_write',checkpoint);assert.equal(cpReplay.structuredContent.payload.replayed,true);
  const cpConflict=await model('task_checkpoint_write',{...checkpoint,progress_summary:'conflict'});assert.equal(cpConflict.isError,true);
  const cas=await modelJob('task_checkpoint_write',{...checkpoint,idempotency_key:'pull-checkpoint-stale',expected_seq:0});
  assert.equal(cas.result.payload.status,'STALE_CHECKPOINT_HEAD');
 });
 await test('21-line Source error is structured; next context remains usable',async()=>{
  const pending=model('source_read',{path:sourceRel,start:1,end:21});await until(async()=>(await inspect()).mailbox.job.status==='PENDING');
  await helper.processClaim(await helper.post('claim'));const result=await pending;
  assert.equal(result.isError,true);assert.equal(result.structuredContent.metadata.error_class,'INVALID_READ_ARGS');
  await modelJob('source_context');
 });
 await test('real SQLite transaction rolls back reserve and lease together',async()=>{
  const pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');const before=(await inspect()).record;
  await call('/_test/reserve-failure');await assert.rejects(helper.post('claim'));
  assert.deepEqual((await inspect()).record,before);assert.equal((await inspect()).mailbox.job.status,'PENDING');
  await helper.processClaim(await helper.post('claim'));assert.equal((await pending).status,200);
  assert.equal((await inspect()).record.task_requests_used,before.task_requests_used+1);
 });
 await test('client disconnect and stale lease cannot reset or charge twice',async()=>{
  const controller=new AbortController();const pending=mf.dispatchFetch('https://relay.invalid/rpc',{method:'POST',body:JSON.stringify({op:'read',args:{path:sourceRel,start:1,end:20}}),signal:controller.signal}).catch(()=>null);
  await until(async()=>(await inspect()).mailbox.job.status==='PENDING');const job=await helper.post('claim');const before=(await inspect()).record;
  const stale=await helper.post('result',{request_id:job.requestId,token:crypto.randomUUID(),result:{status:'OK',payload:{content:'wrong'}}});assert.equal(stale.status,'LEASE_REJECTED');
  assert.deepEqual((await inspect()).record,before);controller.abort();await pending;await helper.processClaim(job);
  const after=(await inspect()).record;assert.equal(after.task_requests_used,before.task_requests_used);
  assert.equal(after.request_receipts[job.requestId].state,'COMMITTED');
 });
 await test('internal idle HTTPS polling has zero model-facing S4 cost',async()=>{
  const before=(await inspect()).record,count=executions;assert.equal((await helper.post('claim')).status,'EMPTY');
  assert.deepEqual((await inspect()).record,before);assert.equal(executions,count);
  assert.equal((await call('/status')).status,200);assert.equal((await (await call('/status')).json()).online,true);
 });
 await test('task expiry never renews admission or spends unclaimed budget',async()=>{
  const before=(await inspect()).record.task_requests_used;
  const pending=rpc();await until(async()=>(await inspect()).mailbox.job.status==='PENDING');await call('/_test/deadline',{task:true});
  assert.equal((await pending).status,503);assert.equal((await helper.post('claim')).status,'TASK_NOT_ACTIVE');
  assert.equal((await inspect()).record.task_requests_used,before);
 });
 await test('normal authenticated operator-issued enrollment preserves the prior S4 row',async()=>{
  const previous=(await inspect()).record;
  const next={...hello,task_admission_id:'e'.repeat(32),session_id:'f'.repeat(32),task_id:'T2',output_task_root:'Output/T2'};
  const nextState={processed:{}};
  const nextHelper=new HttpsPullHelper({relayUrl:'wss://relay.invalid/helper',secret,hello:next,state:nextState,persist:s=>saveStateAtomic(path.join(scratch,'next-helper.json'),s),handle:async()=>{},fetchImpl:(url,options)=>mf.dispatchFetch(url,options)});
  await nextHelper.connect();assert.equal((await inspect()).record.task_admission_id,next.task_admission_id);
  assert.equal((await inspect()).record.task_requests_used,0);
  assert.deepEqual(await (await call('/_test/record/'+previous.task_admission_id)).json(),previous);
  await assert.rejects(helper.post('claim')); // Old task cannot claim new work.
 });
 assert.deepEqual(await fs.readFile(sourcePath),sourceBefore);
 const sorted=latencies.toSorted((a,b)=>a-b),p95=sorted[Math.ceil(sorted.length*.95)-1];assert(p95<15000);
 console.log(JSON.stringify({result:'PASS',native_workerd:true,sqlite:true,real_s4:true,source_unchanged:true,checks:passes,successful_calls:latencies.length,p95_ms:Math.round(p95),max_ms:Math.round(sorted.at(-1)),production:false}));
}finally{await mf.dispose();}
