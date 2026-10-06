import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import {
  LocalQualityAdapter, __test, compactPreparedQuality, reportBindingMatches, ADAPTER_CONTRACT, REPORT_SCHEMA,
  UPSTREAM_COMMIT, OVERLAY_SHA256, POWERSHELL51
} from '../runtime/local-quality-adapter.mjs';

const HERE=path.dirname(fileURLToPath(import.meta.url));
const PRODUCT=path.resolve(HERE,'..');
const results=[];
function ok(name,fn){try{fn();results.push({case:name,pass:true});}catch(e){results.push({case:name,pass:false,error:String(e.stack||e)});}}
async function aok(name,fn){try{await fn();results.push({case:name,pass:true});}catch(e){results.push({case:name,pass:false,error:String(e.stack||e)});}}
const sha256=b=>crypto.createHash('sha256').update(b).digest('hex');
const gitBlob=b=>crypto.createHash('sha1').update(Buffer.concat([Buffer.from('blob '+b.length+'\0'),b])).digest('hex');

ok('contract_constants',()=>{
  assert.equal(ADAPTER_CONTRACT,'LOCAL_QUALITY_ADAPTER_Q0_V1');
  assert.equal(REPORT_SCHEMA,'LOCAL_QUALITY_REPORT_V1');
  assert.equal(UPSTREAM_COMMIT,'1fa205b961f4ed3659f58f4b55d2d9b1d5e4810e');
  assert.equal(POWERSHELL51,'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe');
});
ok('selected_scripts_exact_pin_hashes',()=>{
  for(const [op,x] of Object.entries(__test.SCRIPT_INFO)){
    const b=fs.readFileSync(path.join(PRODUCT,'runtime','quality','cc-1c-skills',x.file));
    assert.equal(gitBlob(b),x.blob,op+' blob');
    assert.equal(sha256(b),x.sha256,op+' sha256');
  }
});
ok('adapter_shell_false_and_no_generic_exec_surface',()=>{
  const t=fs.readFileSync(path.join(PRODUCT,'runtime','local-quality-adapter.mjs'),'utf8');
  assert.match(t,/spawn\(exe,args,\{shell:false/);
  assert.doesNotMatch(t,/exec\(|execFile\(|shell:true|args\?\.executable|args\?\.root|args\?\.script/);
  assert.match(t,/stdout.*65536/);
  assert.match(t,/stderr.*16384/);
});

const root=await fsp.mkdtemp(path.join(os.tmpdir(),'onec-quality-reg-'));
const artRel='Participants/p/Target/Main';
const art=path.join(root,...artRel.split('/'));
await fsp.mkdir(path.join(art,'Documents','Order','Forms','Main','Ext','Form'),{recursive:true});
await fsp.writeFile(path.join(art,'Documents','Order.xml'),'<MetaDataObject/>','utf8');
await fsp.writeFile(path.join(art,'Documents','Order','Ext','ObjectModule.bsl'),'// module','utf8').catch(()=>{});
await fsp.mkdir(path.join(art,'Documents','Order','Ext'),{recursive:true});
await fsp.writeFile(path.join(art,'Documents','Order','Ext','ObjectModule.bsl'),'// module','utf8');
await fsp.writeFile(path.join(art,'Documents','Order','Forms','Main','Ext','Form.xml'),'<Form><Action>DoIt</Action></Form>','utf8');
await fsp.writeFile(path.join(art,'Documents','Order','Forms','Main','Ext','Form','Module.bsl'),'&НаКлиенте\nПроцедура DoIt()\nКонецПроцедуры','utf8');
const artifacts=[{participant_id:'p',platform:'ONEC',side:'TARGET',artifact_type:'MAIN',artifact_id:'main',path:artRel}];

await aok('binding_direct_metadata',async()=>{
  const b=await __test.exactTarget(root,artifacts,artRel+'/Documents/Order.xml');
  assert.equal(b.target_kind,'METADATA_OBJECT');assert.deepEqual(b.operations,['META_INFO']);
});
await aok('binding_direct_form',async()=>{
  const b=await __test.exactTarget(root,artifacts,artRel+'/Documents/Order/Forms/Main/Ext/Form.xml');
  assert.equal(b.target_kind,'FORM');assert.deepEqual(b.operations,['FORM_INFO','FORM_VALIDATE']);
});
await aok('binding_form_module_to_sibling',async()=>{
  const b=await __test.exactTarget(root,artifacts,artRel+'/Documents/Order/Forms/Main/Ext/Form/Module.bsl');
  assert.equal(b.target_relative,artRel+'/Documents/Order/Forms/Main/Ext/Form.xml');
});
await aok('binding_object_subtree_to_descriptor',async()=>{
  const b=await __test.exactTarget(root,artifacts,artRel+'/Documents/Order/Ext/ObjectModule.bsl');
  assert.equal(b.target_relative,artRel+'/Documents/Order.xml');
});
await aok('binding_zero_match_no_binding',async()=>{
  assert.equal(await __test.exactTarget(root,artifacts,artRel+'/Catalogs/Missing/Ext/ObjectModule.bsl'),null);
});
await aok('binding_multiple_artifacts_no_binding',async()=>{
  assert.equal(await __test.exactTarget(root,[...artifacts,{...artifacts[0]}],artRel+'/Documents/Order.xml'),null);
});
await aok('binding_outside_admitted_no_binding',async()=>{
  assert.equal(await __test.exactTarget(root,artifacts,'Elsewhere/Documents/Order.xml'),null);
});

ok('classifier_clean_exit0',()=>{
  assert.equal(__test.parseValidation('=== Validation OK: Form.X (16 checks) ===','',0).result_class,'OK');
});
ok('classifier_findings_exit1_canonical',()=>{
  const r=__test.parseValidation('=== Result: 2 errors, 1 warnings (16 checks) ===','',1);
  assert.equal(r.result_class,'FINDINGS');assert.equal(r.errors,2);
});
ok('classifier_early_failure_not_findings',()=>{
  assert.equal(__test.parseValidation('[ERROR] XML parse error: bad','','1'===1?1:1).result_class,'TOOL_INPUT_ERROR');
});
ok('classifier_unknown_exit',()=>{
  assert.equal(__test.parseValidation('mystery','',7).result_class,'TOOL_EXIT_UNEXPECTED');
});
ok('classifier_maxerrors_truncated',()=>{
  const r=__test.parseValidation('Stopped after 30 errors. Fix and re-run.\n=== Result: 30 errors, 0 warnings (30 checks) ===','',1);
  assert.equal(r.result_class,'FINDINGS');assert.equal(r.truncated,true);
});

ok('overlay_missing_handler',()=>{
  assert(__test.overlay('<Action>Missing</Action>','').some(x=>x.code==='FORM_HANDLER_MISSING'));
});
ok('overlay_duplicate_declaration',()=>{
  const m='&НаКлиенте\nПроцедура H()\nКонецПроцедуры\n&НаСервере\nПроцедура H()\nКонецПроцедуры';
  assert(__test.overlay('<Action>H</Action>',m).some(x=>x.code==='FORM_HANDLER_DUPLICATE'));
});
ok('overlay_contextless_handler',()=>{
  const m='&НаСервереБезКонтекста\nПроцедура H()\nКонецПроцедуры';
  assert(__test.overlay('<Action>H</Action>',m).some(x=>x.code==='FORM_HANDLER_CONTEXT_MISMATCH'));
});
ok('overlay_conversion_context_only',()=>{
  const bad='&НаКлиенте\nПроцедура H()\nРеквизитФормыВЗначение(Объект);\nКонецПроцедуры';
  const good='&НаСервере\nПроцедура H()\nРеквизитФормыВЗначение(Объект);\nКонецПроцедуры';
  assert(__test.overlay('',bad).some(x=>x.code==='FORM_VALUE_CONVERSION_CONTEXT'));
  assert(!__test.overlay('',good).some(x=>x.code==='FORM_VALUE_CONVERSION_CONTEXT'));
});
ok('overlay_hash_stable_present',()=>assert.match(OVERLAY_SHA256,/^[a-f0-9]{64}$/));

const baseReport={
  schema_version:REPORT_SCHEMA,project_id:'P',task_id:'T',session_id:'S',source_snapshot_id:'SS',manifest_sha256:'M',
  adapter_contract_version:ADAPTER_CONTRACT,upstream_commit:UPSTREAM_COMMIT,operation:'FORM_VALIDATE',overlay_sha256:OVERLAY_SHA256
};
const expected={projectId:'P',taskId:'T',sessionId:'S',sourceSnapshotId:'SS',manifestSha256:'M'};
ok('cache_binding_accepts_exact',()=>assert(reportBindingMatches(baseReport,expected)));
for(const field of ['project_id','task_id','session_id','source_snapshot_id','manifest_sha256','adapter_contract_version','upstream_commit','overlay_sha256']){
  ok('cache_invalidate_'+field,()=>{
    const r={...baseReport,[field]:'changed'};
    assert.equal(reportBindingMatches(r,expected),false);
  });
}
ok('cache_input_closure_digest_changes',()=>{
  const a=__test.closureDigest([{relative_path:'a',sha256:'1'}]);
  const b=__test.closureDigest([{relative_path:'a',sha256:'2'}]);
  assert.notEqual(a,b);
});
ok('prepared_quality_bounded_1200',()=>{
  const binding={target_kind:'FORM',target_relative:artRel+'/Documents/Order/Forms/Main/Ext/Form.xml'};
  const reports=[0,1].map(i=>({operation:i?'FORM_VALIDATE':'FORM_INFO',result_class:'FINDINGS',report_sha256:'a'.repeat(64),truncated:false,findings:Array.from({length:20},(_,j)=>({code:'X'+j,message:'x'.repeat(400)}))}));
  const p=compactPreparedQuality(binding,reports,1200);
  assert(p);assert(Buffer.byteLength(JSON.stringify(p),'utf8')<=1200);
});

if(process.argv.includes('--windows-live')){
  await aok('windows_live_source_drift_discards_report',async()=>{
    assert.equal(process.platform,'win32');
    const liveRoot=await fsp.mkdtemp(path.join(os.tmpdir(),'onec-quality-drift-'));
    const liveRel='Participants/p/Target/Main',liveArt=path.join(liveRoot,...liveRel.split('/'));
    await fsp.mkdir(path.join(liveArt,'Documents'),{recursive:true});
    const target=path.join(liveArt,'Documents','Drift.xml');
    const xml='<?xml version="1.0" encoding="UTF-8"?><MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Document><Properties><Name>Drift</Name></Properties></Document></MetaDataObject>';
    await fsp.writeFile(target,xml,'utf8');
    const initial=sha256(await fsp.readFile(target));
    const adapter=new LocalQualityAdapter({projectRoot:liveRoot,artifacts:[{participant_id:'p',platform:'ONEC',side:'TARGET',artifact_type:'MAIN',artifact_id:'main',path:liveRel}],projectId:'P',taskId:'T',sessionId:'S',sourceSnapshotId:'SS',manifestSha256:'M'});
    const timer=setTimeout(()=>fs.appendFileSync(target,' '),120);
    let code=null;
    try{await adapter.runConfirmed(liveRel+'/Documents/Drift.xml',initial);}catch(e){code=e.code;}
    clearTimeout(timer);
    assert.equal(code,'SOURCE_CHANGED_DURING_RUN');
    await fsp.rm(liveRoot,{recursive:true,force:true});
  });
}

await fsp.rm(root,{recursive:true,force:true});
const failed=results.filter(x=>!x.pass);
console.log(JSON.stringify({status:failed.length?'FAIL':'PASS',cases:results.length,failed,results},null,2));
if(failed.length)process.exit(1);
