import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {saveStateAtomic,loadPersistedState,persistAndSendProcessed,safePersistenceCode} from '../runtime/helper-state-coordinator.mjs';
import {HttpsPullHelper} from '../runtime/helper-https-pull.mjs';
import {createTaskRecord,reserveRequest,commitRequest,chargeAmbiguousRequest} from '../relay/src/s4-accounting.js';

const root=await fs.mkdtemp(path.join(os.tmpdir(),'onec-persistence-'));
let checks=0;
const test=async(name,fn)=>{await fn(path.join(root,String(++checks)+'.json'));console.log('PASS '+name);};
const fault=code=>Object.assign(new Error('redacted private path and credential must never be logged'),{code});
const result=id=>({type:'result',request_id:id,status:'OK',metadata:{op:'read'},payload:{value:'persisted'}});
const binding={schema_version:2,task_admission_id:'a'.repeat(32),session_id:'b'.repeat(32),project_id:'P',task_id:'T',snapshot_id:'s'.repeat(64),manifest_sha256:'d'.repeat(64),expires_utc:new Date(Date.now()+600000).toISOString()};
const state=()=>({...binding,pull_helper_id:crypto.randomUUID(),processed:{},idempotency:{kept:{fingerprint:'unchanged',receipt:{status:'COMMITTED'}}},quality_targets:[]});
const noSleep=async()=>{};
try{
 await test('durable write and read preserve caches',async p=>{const s=state();s.processed.one=result('one');await saveStateAtomic(p,s);assert.deepEqual(await loadPersistedState(p,binding),s);});
 await test('exclusive open retries transient Windows failure within 350ms budget',async p=>{
  let attempts=0;const delays=[];await saveStateAtomic(p,state(),{fsApi:{...fs,open:async(...a)=>{if(attempts++<3)throw fault('EACCES');return fs.open(...a);}},sleepImpl:async ms=>delays.push(ms)});
  assert.equal(attempts,4);assert.deepEqual(delays,[50,100,200]);
 });
 await test('rename retries same synced bytes without writing again',async p=>{
  let writes=0,syncs=0,renames=0;const s=state();s.processed.one=result('one');
  await saveStateAtomic(p,s,{fsApi:{...fs,open:async(...a)=>{const f=await fs.open(...a);return {writeFile:async(...b)=>{writes++;return f.writeFile(...b);},sync:async()=>{syncs++;return f.sync();},close:()=>f.close()};},rename:async(...a)=>{if(renames++<3)throw fault('EPERM');return fs.rename(...a);}},sleepImpl:noSleep});
  assert.equal(writes,1);assert.equal(syncs,1);assert.equal(renames,4);assert.deepEqual(await loadPersistedState(p,binding),s);
 });
 await test('permanent permission failure is bounded and classified',async p=>{
  let attempts=0;await assert.rejects(saveStateAtomic(p,state(),{fsApi:{...fs,open:async()=>{attempts++;throw fault('EACCES');}},sleepImpl:noSleep}),e=>e.code==='HELPER_STATE_PERSIST_FAILED'&&e.cause_code==='EACCES'&&e.persist_phase==='open'&&!e.cause_message);assert.equal(attempts,4);
 });
 await test('partial write ENOSPC preserves final and temp; no retry or send',async p=>{
  const s=state();await saveStateAtomic(p,s);const before=await fs.readFile(p);let writes=0,sent=0;
  const api={...fs,open:async(...a)=>{const f=await fs.open(...a);return {writeFile:async()=>{writes++;await f.writeFile('partial');throw fault('ENOSPC');},close:()=>f.close()};}};
  await assert.rejects(persistAndSendProcessed({state:s,requestId:'one',result:result('one'),persist:x=>saveStateAtomic(p,x,{fsApi:api,sleepImpl:noSleep}),send:async()=>sent++}),e=>e.cause_code==='ENOSPC'&&e.persist_phase==='write');
  assert.equal(writes,1);assert.equal(sent,0);assert.deepEqual(await fs.readFile(p),before);assert.equal(await fs.readFile(p+'.tmp','utf8'),'partial');
  await assert.rejects(saveStateAtomic(p,state()));assert.equal(await fs.readFile(p+'.tmp','utf8'),'partial');
 });
 await test('rename failure retains complete recoverable processed/idempotency',async p=>{
  const s=state();await saveStateAtomic(p,s);const before=await fs.readFile(p);s.processed.one=result('one');let n=0;
  await assert.rejects(saveStateAtomic(p,s,{fsApi:{...fs,rename:async()=>{n++;throw fault('EBUSY');}},sleepImpl:noSleep}),e=>e.cause_code==='EBUSY'&&e.persist_phase==='rename');
  assert.equal(n,4);assert.deepEqual(await fs.readFile(p),before);assert.deepEqual(JSON.parse(await fs.readFile(p+'.tmp','utf8')),s);
  await assert.rejects(loadPersistedState(p,binding),/TMP_RECOVERY_REQUIRED/);
 });
 await test('nontransient rename failure is not retried',async p=>{
  let n=0;await assert.rejects(saveStateAtomic(p,state(),{fsApi:{...fs,rename:async()=>{n++;throw fault('EIO');}},sleepImpl:noSleep}),e=>e.cause_code==='EIO');assert.equal(n,1);
 });
 await test('rename error after publication stays fatal; disk cache remains replayable',async p=>{
  const s=state();let sent=0;
  await assert.rejects(persistAndSendProcessed({state:s,requestId:'one',result:result('one'),persist:x=>saveStateAtomic(p,x,{fsApi:{...fs,rename:async(...a)=>{await fs.rename(...a);throw fault('EIO');}},sleepImpl:noSleep}),send:async()=>sent++}));
  assert.equal(sent,0);assert.deepEqual((await loadPersistedState(p,binding)).processed.one,result('one'));
 });
 await test('existing divergent temp is never truncated',async p=>{
  await fs.writeFile(p+'.tmp','previous recovery evidence');await assert.rejects(saveStateAtomic(p,state()),e=>e.cause_code==='EEXIST');assert.equal(await fs.readFile(p+'.tmp','utf8'),'previous recovery evidence');
 });
 await test('direct overlapping saves are serialized',async p=>{
  let active=0,max=0;const api={...fs,open:async(...a)=>{active++;max=Math.max(max,active);return fs.open(...a);},rename:async(...a)=>{await fs.rename(...a);active--;}};
  const s=state(),tasks=[];for(let i=0;i<4;i++){s.processed[String(i)]=result(String(i));tasks.push(saveStateAtomic(p,s,{fsApi:api}));}await Promise.all(tasks);assert.equal(max,1);assert.equal(Object.keys((await loadPersistedState(p,binding)).processed).length,4);
 });
 await test('actual process crash after sync preserves old final and full temp',async p=>{
  const s=state();await saveStateAtomic(p,s);const before=await fs.readFile(p);s.processed.one=result('one');
  const source=`import fs from 'node:fs/promises';import {saveStateAtomic} from ${JSON.stringify(new URL('../runtime/helper-state-coordinator.mjs',import.meta.url).href)};await saveStateAtomic(${JSON.stringify(p)},${JSON.stringify(s)},{fsApi:{...fs,rename:async()=>process.exit(77)}});`;
  const child=spawnSync(process.execPath,['--input-type=module','-e',source],{encoding:'utf8',timeout:10000});assert.equal(child.status,77,child.stderr);assert.deepEqual(await fs.readFile(p),before);assert.deepEqual(JSON.parse(await fs.readFile(p+'.tmp','utf8')),s);await assert.rejects(loadPersistedState(p,binding),/TMP_RECOVERY_REQUIRED/);
 });
 await test('corrupt or mismatched cache cannot silently reset',async p=>{
  await fs.writeFile(p,'{broken');await assert.rejects(loadPersistedState(p,binding),/RECOVERY_REQUIRED/);const s=state();await fs.writeFile(p,JSON.stringify({...s,session_id:'wrong'}));await assert.rejects(loadPersistedState(p,binding),/RECOVERY_REQUIRED/);assert.equal(JSON.parse(await fs.readFile(p,'utf8')).session_id,'wrong');
 });
 await test('redacted codes reject paths, secrets and raw messages',async()=>{
  assert.equal(safePersistenceCode(fault('EPERM')),'EPERM');assert.equal(safePersistenceCode(fault('secret / private')),'ERROR');assert.equal(safePersistenceCode({cause_code:'ENOSPC',message:'private'}),'ENOSPC');
  assert.equal(safePersistenceCode(fault('PRIVATE_CREDENTIAL')),'ERROR');
 });
 await test('actual HTTPS Pull fatal log includes sanitized cause and phase only',async()=>{
  const source=await fs.readFile(new URL('../runtime/hosted-helper.mjs',import.meta.url),'utf8');
  const block=source.slice(source.lastIndexOf('catch(e){')+'catch(e){'.length,source.lastIndexOf('\n}\nfinally'));
  const entries=[];await new (Object.getPrototypeOf(async function(){}).constructor)('e','log','safePersistenceCode','let fatalHelperError;'+block)(Object.assign(new Error('HELPER_STATE_PERSIST_FAILED'),{code:'HELPER_STATE_PERSIST_FAILED',cause_code:'EPERM',persist_phase:'rename',cause_message:'private credential and path'}),async x=>entries.push(x),safePersistenceCode);
  assert.equal(entries[0].event,'HELPER_FATAL');assert.equal(entries[0].cause_code,'EPERM');assert.equal(entries[0].persist_phase,'rename');assert(!JSON.stringify(entries).includes('private'));
 });
 await test('same admission reconnect replays persisted cache; real S4 charge once despite lost ACK',async p=>{
  const s=state(),id='mcp-'+'1'.repeat(64);s.processed[id]=result(id);await saveStateAtomic(p,s);const current=await loadPersistedState(p,binding);
  const hello={admission_schema_version:3,task_admission_id:binding.task_admission_id,session_id:binding.session_id,project_id:'P',task_id:'T',snapshot_id:binding.snapshot_id,manifest_sha256:binding.manifest_sha256,task_created_utc:new Date(Date.now()-1000).toISOString(),task_expires_utc:binding.expires_utc,output_task_root:'Output/T',caps:{task_request_limit:2048,task_result_byte_limit:2097152,epoch_soft_request_limit:32,epoch_soft_result_byte_limit:36000,max_result_bytes:3000}};
  const record=createTaskRecord(hello),lease={status:'CLAIMED',requestId:id,token:crypto.randomUUID(),deadline:Date.now()+10000};reserveRequest(record,{requestId:id,fingerprint:'fp',op:'read'});let executes=0,posts=0;
  const helper=new HttpsPullHelper({relayUrl:'https://relay.invalid',secret:'isolated-not-production',hello,state:current,persist:x=>saveStateAtomic(p,x),handle:async()=>executes++,sleepImpl:noSleep});
  helper.post=async(route,fields)=>{if(route==='hello'){assert.deepEqual(fields.hello,hello);return {status:'READY'};}posts++;commitRequest(record,{requestId:id,fingerprint:'fp',payloadBytes:12});if(posts===1)throw new Error('lost accepted ACK');return {status:'COMMITTED'};};
  await helper.connect();await helper.processClaim(lease);await helper.processClaim(lease);assert.equal(executes,0);assert.equal(record.task_requests_used,1);assert.equal(record.task_result_bytes_used,12);assert.equal(current.task_admission_id,binding.task_admission_id);assert.deepEqual(current.idempotency,s.idempotency);
 });
 console.log('HELPER_PERSISTENCE_REGRESSION_PASS checks='+checks);
}finally{await fs.rm(root,{recursive:true,force:true});}
