import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import { executeRequest, CONTRACT, ALLOWED_VERBS } from '../runtime/source-acquisition.mjs';

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
  rec('allowlist_exact_one',JSON.stringify(ALLOWED_VERBS)===JSON.stringify(['EXTERNAL_FULL_SAFE_IMPORT']),JSON.stringify(ALLOWED_VERBS));
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
