import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import { executeRequest, CONTRACT, INTAKE_CONTRACT, PROMOTION_CONTRACT, ALLOWED_VERBS } from '../runtime/source-acquisition.mjs';

const root = process.argv[2];
if (!root) throw new Error('SCRATCH_ROOT_REQUIRED');
const results=[];
function rec(name,ok,detail=''){results.push({name,pass:!!ok,detail});if(!ok)throw new Error('ASSERTION_FAILED:'+name+':'+detail)}
const ns=(p)=>path.toNamespacedPath(p);
const hash=(b)=>crypto.createHash('sha256').update(b).digest('hex');
async function write(p,data){await fsp.mkdir(ns(path.dirname(p)),{recursive:true});await fsp.writeFile(ns(p),data)}
async function rm(p){await fsp.rm(ns(p),{recursive:true,force:true}).catch(()=>{})}
async function expectCode(name,request,code){let got='';try{await executeRequest(request)}catch(e){got=e?.code||String(e?.message||e).split(':')[0]}rec(name,got===code,'expected='+code+' got='+got)}
function req(source,stageParent,token='deadbeef'){const stage=path.join(stageParent,'a.stage-'+token);return{verb:'EXTERNAL_FULL_SAFE_IMPORT',source_root:source,stage_parent:stageParent,stage_root:stage,fingerprint_path:stage+'.fingerprints.jsonl',progress_path:stage+'.progress.json',culture:process.env.ONEC_TEST_CULTURE||'en-US',max_files:10000,max_bytes:1024*1024*1024,timeout_ms:120000}}
async function fingerprintRows(p){return (await fsp.readFile(ns(p),'utf8')).trim().split(/\r?\n/).filter(Boolean).map(JSON.parse)}
async function runOne(source,stageParent,token){
  await fsp.mkdir(ns(stageParent),{recursive:true});
  const r=req(source,stageParent,token);
  const out=await executeRequest(r);
  return {request:r,out,rows:await fingerprintRows(r.fingerprint_path)};
}
try{
  rec('contract_exact',CONTRACT==='S82_1_EXTERNAL_XML_FULL_SAFE_IMPORT_V1',CONTRACT);
  rec('allowlist_exact_bounded',JSON.stringify(ALLOWED_VERBS)===JSON.stringify(['EXTERNAL_FULL_SAFE_IMPORT','INTAKE_VALIDATE_HASH','INTAKE_METADATA_VERIFY','ZERO_COPY_PROMOTE_ARTIFACT']),JSON.stringify(ALLOWED_VERBS));
  const source=path.join(root,'source-Юникод');
  await write(path.join(source,'Configuration.xml'),Buffer.from('<Configuration name="LongPath"/>','utf8'));
  const parts=['д'.repeat(48),'a'.repeat(52),'b'.repeat(52),'c'.repeat(52),'d'.repeat(52)];
  const deep=path.join(source,...parts,'МодульОченьДлинногоИмени.bsl');
  const payload=Buffer.from('Procedure LongPath()\nEndProcedure\n','utf8');
  await write(deep,payload);
  await write(path.join(source,'Catalogs','Товары','Ext','ObjectModule.bsl'),Buffer.from('Procedure Unicode()\nEndProcedure\n','utf8'));
  rec('source_absolute_file_over_260',deep.length>260,String(deep.length));
  const sourceBefore=await fsp.readFile(ns(deep));
  const local=await runOne(source,path.join(root,'stage-local'),'11111111');
  rec('local_pass',local.out.result==='PASS',JSON.stringify(local.out));
  rec('stage_absolute_file_over_260',local.out.metrics.max_stage_path_chars>260,String(local.out.metrics.max_stage_path_chars));
  rec('source_metric_over_260',local.out.metrics.max_source_path_chars>260,String(local.out.metrics.max_source_path_chars));
  const deepRow=local.rows.find(x=>x.path.endsWith('МодульОченьДлинногоИмени.bsl'));
  rec('exact_sha_preserved',deepRow?.sha256===hash(payload),JSON.stringify(deepRow));
  rec('configuration_xml_detected',local.out.configuration_xml_sha256===hash(Buffer.from('<Configuration name="LongPath"/>','utf8')),local.out.configuration_xml_sha256);
  rec('one_content_pass_no_stage_rehash',local.out.metrics.recursive_passes.source_content===1&&local.out.metrics.recursive_passes.stage_content_rehash===0,JSON.stringify(local.out.metrics.recursive_passes));
  rec('source_unchanged',Buffer.compare(sourceBefore,await fsp.readFile(ns(deep)))===0,'');
  rec('no_subst_registry_ps7_contract',local.out.metrics.subst_required===false&&local.out.metrics.long_paths_registry_required===false&&local.out.metrics.powershell7_required===false,JSON.stringify(local.out.metrics));


  rec('intake_contract_exact',INTAKE_CONTRACT==='S82_2_INCOMING_VALIDATE_HASH_V1',INTAKE_CONTRACT);
  rec('promotion_contract_exact',PROMOTION_CONTRACT==='S82_2_ZERO_COPY_PROMOTION_V1',PROMOTION_CONTRACT);
  const incomingParent=path.join(root,'incoming');
  const slot=path.join(incomingParent,'slot-Юникод');
  const receipts=path.join(root,'intake-receipts');
  await fsp.mkdir(ns(receipts),{recursive:true});
  await write(path.join(slot,'Configuration.xml'),Buffer.from('<Configuration name="Intake"/>','utf8'));
  const dumpInfo=Buffer.from('<ConfigDumpInfo generation="1"/>','utf8');
  await write(path.join(slot,'ConfigDumpInfo.xml'),dumpInfo);
  const intakeDeep=path.join(slot,'ОченьДлинный'.repeat(18),'Ext','Module.bsl');
  const intakePayload=Buffer.from('Procedure Intake()\\nEndProcedure\\n','utf8');
  await write(intakeDeep,intakePayload);
  rec('intake_long_unicode_path_over_260',intakeDeep.length>260,String(intakeDeep.length));
  const intakeReq={verb:'INTAKE_VALIDATE_HASH',source_root:slot,output_parent:receipts,fingerprint_path:path.join(receipts,'slot.fingerprints.jsonl'),progress_path:path.join(receipts,'slot.progress.json'),culture:process.env.ONEC_TEST_CULTURE||'en-US',max_files:10000,max_bytes:1024*1024*1024,timeout_ms:120000};
  const intake=await executeRequest(intakeReq);
  rec('intake_validate_hash_pass',intake.result==='PASS'&&intake.contract===INTAKE_CONTRACT,JSON.stringify(intake));
  rec('intake_zero_copy_one_hash_pass',intake.metrics.copied_bytes===0&&intake.metrics.copied_files===0&&intake.metrics.hashed_bytes===intake.digest.bytes&&intake.metrics.recursive_passes.source_content===1&&intake.metrics.recursive_passes.stage_content_rehash===0,JSON.stringify(intake.metrics));
  const intakeRows=await fingerprintRows(intakeReq.fingerprint_path);
  const dumpRow=intakeRows.find(x=>x.path.toLowerCase()==='configdumpinfo.xml');
  rec('configdumpinfo_preserved_and_hashed',dumpRow?.sha256===hash(dumpInfo),JSON.stringify(dumpRow));
  const deepIntakeRow=intakeRows.find(x=>x.path.endsWith('Module.bsl'));
  rec('intake_exact_sha',deepIntakeRow?.sha256===hash(intakePayload),JSON.stringify(deepIntakeRow));
  const verifyReq={verb:'INTAKE_METADATA_VERIFY',source_root:slot,output_parent:receipts,progress_path:path.join(receipts,'verify.progress.json'),expected_metadata_identity_sha256:intake.metadata_identity_sha256,culture:process.env.ONEC_TEST_CULTURE||'en-US',max_files:10000,max_bytes:1024*1024*1024,timeout_ms:120000};
  const verified=await executeRequest(verifyReq);
  rec('metadata_recheck_content_zero',verified.result==='PASS'&&verified.metrics.hashed_bytes===0&&verified.metrics.copied_bytes===0&&verified.metrics.source_content_passes===0,JSON.stringify(verified.metrics));
  const destParent=path.join(root,'canonical-parent');await fsp.mkdir(ns(destParent),{recursive:true});
  const dest=path.join(destParent,'Extension');
  const promoted=await executeRequest({verb:'ZERO_COPY_PROMOTE_ARTIFACT',source_parent:incomingParent,source_root:slot,destination_parent:destParent,destination_root:dest,timeout_ms:120000});
  rec('same_volume_zero_copy_promote',promoted.result==='PASS'&&promoted.contract===PROMOTION_CONTRACT&&promoted.same_volume===true&&promoted.copied_content_bytes===0&&promoted.copied_content_files===0,JSON.stringify(promoted));
  rec('promotion_moves_same_bytes',!(await fsp.stat(ns(slot)).then(()=>true,()=>false))&&(await fsp.readFile(ns(path.join(dest,'ConfigDumpInfo.xml')))).equals(dumpInfo),'');
  await expectCode('cross_volume_zero_copy_rejected',{verb:'ZERO_COPY_PROMOTE_ARTIFACT',source_parent:'C:\\\\Intake',source_root:'C:\\\\Intake\\\\slot',destination_parent:'D:\\\\Target',destination_root:'D:\\\\Target\\\\slot',timeout_ms:120000},'CROSS_VOLUME_ZERO_COPY_REJECTED');
  const uncParent='\\\\\\\\'+os.hostname()+'\\\\C$\\\\Incoming';const uncSlot=uncParent+'\\\\slot';
  await expectCode('unc_zero_copy_rejected',{verb:'ZERO_COPY_PROMOTE_ARTIFACT',source_parent:uncParent,source_root:uncSlot,destination_parent:'C:\\\\Target',destination_root:'C:\\\\Target\\\\slot',timeout_ms:120000},'INVALID_NAMESPACE');
  const driftSlot=path.join(incomingParent,'drift-slot');await write(path.join(driftSlot,'Configuration.xml'),Buffer.from('<Configuration/>'));await write(path.join(driftSlot,'a.txt'),Buffer.from('a'));
  const driftFp=path.join(receipts,'drift.fingerprints.jsonl'),driftPg=path.join(receipts,'drift.progress.json');
  const driftValidated=await executeRequest({verb:'INTAKE_VALIDATE_HASH',source_root:driftSlot,output_parent:receipts,fingerprint_path:driftFp,progress_path:driftPg,max_files:100,max_bytes:1024*1024,timeout_ms:120000});
  await fsp.appendFile(ns(path.join(driftSlot,'a.txt')),Buffer.from('b'));
  await expectCode('sealed_metadata_drift_rejected',{verb:'INTAKE_METADATA_VERIFY',source_root:driftSlot,output_parent:receipts,progress_path:path.join(receipts,'drift-verify.progress.json'),expected_metadata_identity_sha256:driftValidated.metadata_identity_sha256,max_files:100,max_bytes:1024*1024,timeout_ms:120000},'SEALED_SOURCE_DRIFT');
  const noConfig=path.join(incomingParent,'no-config');await write(path.join(noConfig,'a.txt'),Buffer.from('x'));
  await expectCode('intake_configuration_required',{verb:'INTAKE_VALIDATE_HASH',source_root:noConfig,output_parent:receipts,fingerprint_path:path.join(receipts,'noconfig.fingerprints.jsonl'),progress_path:path.join(receipts,'noconfig.progress.json'),max_files:100,max_bytes:1024*1024,timeout_ms:120000},'ONEC_CONFIGURATION_XML_MISSING');

  const host=os.hostname();if(!host)throw new Error('HOSTNAME_REQUIRED_FOR_UNC_GATE');
  const unc='\\\\'+host+'\\C$'+source.slice(2);
  const uncRun=await runOne(unc,path.join(root,'stage-unc'),'22222222');
  rec('unc_long_path_pass',uncRun.out.result==='PASS'&&uncRun.out.metrics.max_source_path_chars>260,JSON.stringify({max:uncRun.out.metrics.max_source_path_chars,files:uncRun.out.digest.files}));
  rec('unc_exact_identity',uncRun.out.digest.sha256===local.out.digest.sha256,uncRun.out.digest.sha256+' vs '+local.out.digest.sha256);

  await expectCode('traversal_rejected',req(source+'\\..\\source-Юникод',path.join(root,'bad1'),'33333333'),'TRAVERSAL_REJECTED');
  await expectCode('ads_rejected',req(source+'\\x:ads',path.join(root,'bad2'),'44444444'),'ADS_REJECTED');
  await expectCode('invalid_namespace_rejected',req('\\\\?\\'+source,path.join(root,'bad3'),'55555555'),'INVALID_NAMESPACE');
  const escapeReq=req(source,path.join(root,'parentA'),'66666666');escapeReq.stage_root=path.join(root,'parentB','a.stage-66666666');escapeReq.fingerprint_path=escapeReq.stage_root+'.fingerprints.jsonl';escapeReq.progress_path=escapeReq.stage_root+'.progress.json';
  await expectCode('stage_root_escape_rejected',escapeReq,'STAGE_ROOT_ESCAPE');
  const overlap=req(source,source,'77777777');
  await expectCode('source_stage_overlap_rejected',overlap,'SOURCE_STAGE_OVERLAP');

  const outside=path.join(root,'outside');await write(path.join(outside,'escape.txt'),Buffer.from('escape'));
  const reparseSource=path.join(root,'source-reparse');await write(path.join(reparseSource,'Configuration.xml'),Buffer.from('<Configuration/>'));
  const junction=path.join(reparseSource,'escape-link');
  await fsp.symlink(ns(outside),ns(junction),'junction');
  await expectCode('reparse_escape_rejected',req(reparseSource,path.join(root,'bad-reparse'),'88888888'),'REPARSE_POINT');
  const stageReal=path.join(root,'stage-real');await fsp.mkdir(ns(stageReal),{recursive:true});
  const stageLink=path.join(root,'stage-link');await fsp.symlink(ns(stageReal),ns(stageLink),'junction');
  await expectCode('stage_parent_reparse_rejected',req(source,stageLink,'89898989'),'REPARSE_POINT');

  process.stdout.write(JSON.stringify({result:'PASS',checks:results.length,results,source_root:source,local_metrics:local.out.metrics,unc_metrics:uncRun.out.metrics,tree_sha256:local.out.digest.sha256,configuration_xml_sha256:local.out.configuration_xml_sha256}));
}catch(e){
  process.stderr.write(JSON.stringify({result:'FAIL',error:String(e?.stack||e),results}));
  process.exitCode=2;
}
