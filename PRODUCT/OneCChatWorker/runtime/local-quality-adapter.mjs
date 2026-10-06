import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const ADAPTER_CONTRACT='LOCAL_QUALITY_ADAPTER_Q0_V1';
export const REPORT_SCHEMA='LOCAL_QUALITY_REPORT_V1';
export const UPSTREAM_COMMIT='1fa205b961f4ed3659f58f4b55d2d9b1d5e4810e';
export const POWERSHELL51='C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';
const HERE=path.dirname(fileURLToPath(import.meta.url));
const QUALITY_DIR=path.join(HERE,'quality','cc-1c-skills');
const SCRIPT_INFO={
  META_INFO:{file:'meta-info.ps1',blob:'cf1a233e7fb270325a91dd8403ca96794d26c7d9',sha256:'7ca179021cad602bbf326a483229d56e4c0a8ad9733137bd10049ee75eec815a',timeout:15000},
  FORM_INFO:{file:'form-info.ps1',blob:'0edda69123ce565938bf368ff26039a890ac23d1',sha256:'ad9d6881bf4d6c57c04f17cd76802d2d332afa575117c8d1e87cd7e608ac4727',timeout:15000},
  FORM_VALIDATE:{file:'form-validate.ps1',blob:'208e9ee4c543c7ef85ead5465f1abf5ecff19a3f',sha256:'b1ff7204d09d0e7435f035db8670a51a091924b0c3f6e9d40eae67ffb3fb49ec',timeout:30000},
};
const META_COLLECTIONS=new Set([
  'Catalogs','Documents','Enums','Constants','InformationRegisters','AccumulationRegisters',
  'AccountingRegisters','CalculationRegisters','ChartsOfAccounts','ChartsOfCharacteristicTypes',
  'ChartsOfCalculationTypes','BusinessProcesses','Tasks','ExchangePlans','DocumentJournals',
  'Reports','DataProcessors','DefinedTypes','CommonModules','ScheduledJobs','EventSubscriptions',
  'HTTPServices','WebServices','ExternalDataSources'
]);
const HINT_LEXICON=new Map([
 ['catalog','Catalogs'],['справочник','Catalogs'],['document','Documents'],['документ','Documents'],
 ['report','Reports'],['отчет','Reports'],['отчёт','Reports'],['dataprocessor','DataProcessors'],['обработка','DataProcessors'],
 ['commonmodule','CommonModules'],['общиймодуль','CommonModules'],['informationregister','InformationRegisters'],
 ['регистрсведений','InformationRegisters'],['accumulationregister','AccumulationRegisters'],['регистрнакопления','AccumulationRegisters']
]);
const sha256=b=>crypto.createHash('sha256').update(b).digest('hex');
const utf8Bytes=x=>Buffer.byteLength(String(x),'utf8');
const norm=p=>String(p).replaceAll('\\','/').replace(/^\/+|\/+$/g,'');
const stable=v=>{
  if(Array.isArray(v))return v.map(stable);
  if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])]));
  return v;
};
const stableText=v=>JSON.stringify(stable(v));
const clipUtf8=(value,max)=>{
  const s=String(value??''); if(utf8Bytes(s)<=max)return s;
  let out=''; for(const ch of s){if(utf8Bytes(out+ch+'…')>max)break;out+=ch;} return out+'…';
};

async function fileSha(file){return sha256(await fsp.readFile(file));}
async function isFile(file){try{return (await fsp.stat(file)).isFile();}catch{return false;}}
async function rejectReparse(root,file){
  const rr=path.resolve(root), ff=path.resolve(file);
  const rel=path.relative(rr,ff);
  if(!rel||rel.startsWith('..')||path.isAbsolute(rel))throw Object.assign(new Error('PATH_OUTSIDE_ADMISSION'),{code:'PATH_OUTSIDE_ADMISSION'});
  let cur=rr;
  for(const part of rel.split(path.sep)){
    cur=path.join(cur,part);
    const st=await fsp.lstat(cur);
    if(st.isSymbolicLink())throw Object.assign(new Error('REPARSE_ESCAPE'),{code:'PATH_OUTSIDE_ADMISSION'});
  }
}
function artifactFor(artifacts,rel){
  const r=norm(rel);
  const matches=artifacts.filter(a=>r===a.path||r.startsWith(a.path+'/'));
  return matches.length===1?matches[0]:null;
}
async function exactTarget(projectRoot,artifacts,readRel){
  const a=artifactFor(artifacts,readRel); if(!a)return null;
  const rel=norm(readRel), inside=rel.slice(a.path.length).replace(/^\//,'');
  const seg=inside.split('/');
  let target=null,kind=null,ops=[];
  if(seg.length===2 && META_COLLECTIONS.has(seg[0]) && seg[1].endsWith('.xml')){
    target=inside;kind='METADATA_OBJECT';ops=['META_INFO'];
  }else if(seg.length===6 && META_COLLECTIONS.has(seg[0]) && seg[2]==='Forms' && seg[4]==='Ext' && seg[5]==='Form.xml'){
    target=inside;kind='FORM';ops=['FORM_INFO','FORM_VALIDATE'];
  }else if(seg.length===7 && META_COLLECTIONS.has(seg[0]) && seg[2]==='Forms' && seg[4]==='Ext' && seg[5]==='Form' && seg[6]==='Module.bsl'){
    const candidate=seg.slice(0,5).concat('Form.xml').join('/');
    const full=path.join(projectRoot,a.path.replaceAll('/',path.sep),candidate.replaceAll('/',path.sep));
    if(await isFile(full)){target=candidate;kind='FORM';ops=['FORM_INFO','FORM_VALIDATE'];}
  }else if(seg.length>=3 && META_COLLECTIONS.has(seg[0])){
    const candidate=`${seg[0]}/${seg[1]}.xml`;
    const full=path.join(projectRoot,a.path.replaceAll('/',path.sep),candidate.replaceAll('/',path.sep));
    if(await isFile(full)){target=candidate;kind='METADATA_OBJECT';ops=['META_INFO'];}
  }
  if(!target)return null;
  const full=path.join(projectRoot,a.path.replaceAll('/',path.sep),target.replaceAll('/',path.sep));
  await rejectReparse(path.join(projectRoot,a.path.replaceAll('/',path.sep)),full);
  if(!await isFile(full))return null;
  return {artifact:a,target_relative:a.path+'/'+target,target_inside:target,target_native:full,target_kind:kind,operations:ops};
}
function parseValidation(stdout,stderr,exitCode){
  const text=String(stdout||'');
  const ok=/=== Validation OK: [^\r\n]+ ===\s*$/m.test(text);
  const ms=[...text.matchAll(/=== Result:\s*(\d+) errors,\s*(\d+) warnings\s*\((\d+) checks\) ===/g)];
  const result=ms.length?ms[ms.length-1]:null;
  const errors=result?Number(result[1]):null,warnings=result?Number(result[2]):0;
  const maxStop=/Stopped after\s+\d+\s+errors\./i.test(text);
  if(exitCode===0 && (ok || (result&&errors===0)))return {result_class:'OK',warnings,truncated:false};
  if(exitCode===1 && result&&errors>=1)return {result_class:'FINDINGS',warnings,truncated:maxStop,errors};
  if(!result && (/\[ERROR\]/i.test(text)||/cannot|not found|invalid xml|parse/i.test(text+'\n'+String(stderr||''))))return {result_class:'TOOL_INPUT_ERROR',warnings:0,truncated:false};
  return {result_class:'TOOL_EXIT_UNEXPECTED',warnings:0,truncated:false};
}
function normalizeLines(text,limit=20){
  const rows=String(text||'').split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  const picked=rows.filter(x=>/\b(ERROR|WARN|WARNING)\b|ошиб|предупреж|\[ERROR\]|\[WARN\]/i.test(x)).slice(0,limit);
  return picked.map(x=>clipUtf8(x,400));
}
function declarations(moduleText){
  const lines=String(moduleText||'').split(/\r?\n/),out=[];
  let directive=null;
  for(let i=0;i<lines.length;i++){
    const d=lines[i].match(/^\s*&([\p{L}0-9_]+)\s*$/u); if(d){directive=d[1];continue;}
    const m=lines[i].match(/^\s*(Процедура|Функция)\s+([\p{L}_][\p{L}0-9_]*)\s*\(/iu);
    if(m){out.push({kind:m[1],name:m[2],directive,line:i+1,start:i}); directive=null;}
    else if(lines[i].trim() && !lines[i].trim().startsWith('//'))directive=null;
  }
  return {lines,out};
}
function overlay(formText,moduleText){
  const findings=[]; const actions=[...String(formText||'').matchAll(/<Action>\s*([^<\r\n]+?)\s*<\/Action>/g)].map(m=>m[1].trim()).filter(Boolean);
  const {lines,out}=declarations(moduleText);
  for(const name of [...new Set(actions)]){
    const ds=out.filter(x=>x.name.toLocaleLowerCase('ru')===name.toLocaleLowerCase('ru'));
    if(ds.length===0)findings.push({code:'FORM_HANDLER_MISSING',message:`Action handler '${name}' is not declared in Ext/Form/Module.bsl`});
    if(ds.length>1)findings.push({code:'FORM_HANDLER_DUPLICATE',message:`Action handler '${name}' has ${ds.length} declarations`});
    if(ds.length===1 && /БезКонтекста/i.test(String(ds[0].directive||'')))findings.push({code:'FORM_HANDLER_CONTEXT_MISMATCH',message:`Action handler '${name}' uses contextless server directive`});
  }
  const decls=[...out].sort((a,b)=>a.start-b.start);
  for(let i=0;i<decls.length;i++){
    const x=decls[i],end=i+1<decls.length?decls[i+1].start:lines.length;
    const body=lines.slice(x.start,end).join('\n');
    if(/(?:РеквизитФормыВЗначение|ЗначениеВРеквизитФормы)\s*\(/iu.test(body) && String(x.directive||'').toLocaleLowerCase('ru')!=='насервере'){
      findings.push({code:'FORM_VALUE_CONVERSION_CONTEXT',message:`Form value conversion in '${x.name}' requires contextful &НаСервере procedure`});
    }
  }
  return findings.slice(0,20);
}
export const OVERLAY_SHA256=sha256(Buffer.from(overlay.toString(),'utf8'));
async function spawnBounded(exe,args,timeoutMs){
  return await new Promise((resolve,reject)=>{
    const child=spawn(exe,args,{shell:false,windowsHide:true,stdio:['ignore','pipe','pipe']});
    const out=[],err=[];let ob=0,eb=0,done=false,timed=false,limited=false;
    const finish=(code,signal)=>{if(done)return;done=true;clearTimeout(timer);resolve({exitCode:code,signal,stdout:Buffer.concat(out).toString('utf8'),stderr:Buffer.concat(err).toString('utf8'),timed,limited});};
    child.on('error',reject);
    child.stdout.on('data',b=>{ob+=b.length;if(ob>65536){limited=true;child.kill();}else out.push(b);});
    child.stderr.on('data',b=>{eb+=b.length;if(eb>16384){limited=true;child.kill();}else err.push(b);});
    child.on('close',finish);
    const timer=setTimeout(()=>{timed=true;child.kill();},timeoutMs);
  });
}
async function closureFor(binding,operation){
  const root=path.join(binding.projectRoot,binding.artifact.path.replaceAll('/',path.sep));
  const rows=[];
  const add=async(rel)=>{
    const abs=path.join(root,rel.replaceAll('/',path.sep));
    if(!await isFile(abs))return;
    await rejectReparse(root,abs);
    rows.push({relative_path:binding.artifact.path+'/'+norm(rel),sha256:await fileSha(abs)});
  };
  await add(binding.target_inside);
  const parts=binding.target_inside.split('/');
  for(let i=parts.length-1;i>=1;i--){
    const dir=parts.slice(0,i).join('/');
    await add(dir+'.xml');
    await add(dir+'/Configuration.xml');
    await add(dir+'/Ext/ParentConfigurations.bin');
  }
  await add('Configuration.xml');
  await add('Ext/ParentConfigurations.bin');
  if(binding.target_kind==='FORM'){
    await add(binding.target_inside.replace(/Form\.xml$/,'Form/Module.bsl'));
  }
  if(operation==='META_INFO'){
    const raw=await fsp.readFile(binding.target_native,'utf8');
    const names=[...new Set([...raw.matchAll(/(?:cfg:|d\d+p\d+:)DefinedType\.([\p{L}0-9_.-]+)/gu)].map(m=>m[1]))].sort();
    if(names.length>32)throw Object.assign(new Error('INPUT_CLOSURE_LIMIT'),{code:'INPUT_CLOSURE_LIMIT'});
    for(const name of names)await add('DefinedTypes/'+name+'.xml');
  }
  const dedup=new Map(rows.map(x=>[x.relative_path,x]));
  return [...dedup.values()].sort((a,b)=>a.relative_path.localeCompare(b.relative_path,'en'));
}
const closureDigest=rows=>sha256(Buffer.from(stableText(rows),'utf8'));
async function materializeClosure(binding,rows){
  const temp=await fsp.mkdtemp(path.join(os.tmpdir(),'onec-q0-quality-'));
  const sandboxArtifact=path.join(temp,'artifact');
  await fsp.mkdir(sandboxArtifact,{recursive:true});
  for(const row of rows){
    const inside=norm(row.relative_path).slice(binding.artifact.path.length).replace(/^\//,'');
    const src=path.join(binding.projectRoot,row.relative_path.replaceAll('/',path.sep));
    const dst=path.join(sandboxArtifact,inside.replaceAll('/',path.sep));
    await fsp.mkdir(path.dirname(dst),{recursive:true});
    await fsp.copyFile(src,dst);
  }
  const target=path.join(sandboxArtifact,binding.target_inside.replaceAll('/',path.sep));
  if(!await isFile(target)){await fsp.rm(temp,{recursive:true,force:true});throw Object.assign(new Error('INPUT_CLOSURE_TARGET_MISSING'),{code:'INPUT_CLOSURE_TARGET_MISSING'});}
  return {temp,target};
}
function scriptArgs(op,target){
  const s=path.join(QUALITY_DIR,SCRIPT_INFO[op].file);
  const common=['-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',s];
  if(op==='META_INFO')return [...common,'-ObjectPath',target,'-Mode','overview'];
  if(op==='FORM_INFO')return [...common,'-FormPath',target];
  return [...common,'-FormPath',target,'-MaxErrors','30'];
}
function projection(report){
  return {
    operation:report.operation,result_class:report.result_class,report_sha256:report.report_sha256,
    truncated:report.truncated===true,findings:(report.findings||[]).slice(0,3).map(x=>typeof x==='string'?clipUtf8(x,220):{code:x.code,message:clipUtf8(x.message,220)})
  };
}
export function reportBindingMatches(report,{projectId,taskId,sessionId,sourceSnapshotId,manifestSha256}){
  if(!report||report.schema_version!==REPORT_SCHEMA)return false;
  if(report.project_id!==projectId||report.task_id!==taskId||report.session_id!==sessionId)return false;
  if(report.source_snapshot_id!==sourceSnapshotId||report.manifest_sha256!==manifestSha256)return false;
  if(report.adapter_contract_version!==ADAPTER_CONTRACT||report.upstream_commit!==UPSTREAM_COMMIT)return false;
  if(report.operation==='FORM_VALIDATE'&&report.overlay_sha256!==OVERLAY_SHA256)return false;
  return true;
}
export function compactPreparedQuality(binding,reports,maxBytes=1200){
  const base={schema_version:'PREPARED_QUALITY_V1',binding_origin:'SOURCE_READ_CONFIRMED',target:{kind:binding.target_kind,path:binding.target_relative},reports:reports.map(projection)};
  while(utf8Bytes(JSON.stringify(base))>maxBytes && base.reports.some(r=>r.findings?.length)){
    const r=[...base.reports].reverse().find(x=>x.findings?.length);r.findings.pop();
  }
  if(utf8Bytes(JSON.stringify(base))>maxBytes)for(const r of base.reports)delete r.findings;
  return utf8Bytes(JSON.stringify(base))<=maxBytes?base:null;
}
export class LocalQualityAdapter{
  constructor({projectRoot,artifacts,projectId,taskId,sessionId,sourceSnapshotId,manifestSha256}){
    this.projectRoot=projectRoot;this.artifacts=artifacts;this.projectId=projectId;this.taskId=taskId;this.sessionId=sessionId;
    this.sourceSnapshotId=sourceSnapshotId;this.manifestSha256=manifestSha256;
  }
  async verifyToolset(){
    if(process.platform!=='win32')throw Object.assign(new Error('TOOL_UNAVAILABLE'),{code:'TOOL_UNAVAILABLE'});
    for(const [op,x] of Object.entries(SCRIPT_INFO)){const p=path.join(QUALITY_DIR,x.file);if(await fileSha(p)!==x.sha256)throw Object.assign(new Error('TOOLSET_INTEGRITY_FAIL:'+op),{code:'TOOLSET_INTEGRITY_FAIL'});}
  }
  async resolveConfirmed(readRel){const b=await exactTarget(this.projectRoot,this.artifacts,readRel);return b?{...b,projectRoot:this.projectRoot}:null;}
  async runConfirmed(readRel,confirmingSha){
    const b=await this.resolveConfirmed(readRel); if(!b)return null;
    await this.verifyToolset();
    const reports=[];
    for(const op of b.operations)reports.push(await this.runOne(b,op,readRel,confirmingSha));
    return {binding:b,reports,prepared:compactPreparedQuality(b,reports)};
  }
  async runOne(binding,op,confirmingPath,confirmingSha){
    const info=SCRIPT_INFO[op],before=await closureFor(binding,op),beforeDigest=closureDigest(before),started=performance.now();
    const sandbox=await materializeClosure(binding,before);
    let proc;
    try{proc=await spawnBounded(POWERSHELL51,scriptArgs(op,sandbox.target),info.timeout);}
    finally{await fsp.rm(sandbox.temp,{recursive:true,force:true}).catch(()=>{});}
    const elapsed_ms=+(performance.now()-started).toFixed(3),after=await closureFor(binding,op),afterDigest=closureDigest(after);
    if(beforeDigest!==afterDigest)throw Object.assign(new Error('SOURCE_CHANGED_DURING_RUN'),{code:'SOURCE_CHANGED_DURING_RUN'});
    let cls={result_class:'OK',truncated:false,warnings:0};
    if(proc.timed)cls={result_class:'TIMEOUT',truncated:false,warnings:0};
    else if(proc.limited)cls={result_class:'OUTPUT_LIMIT',truncated:true,warnings:0};
    else if(op==='FORM_VALIDATE')cls=parseValidation(proc.stdout,proc.stderr,proc.exitCode);
    else if(proc.exitCode!==0)cls={result_class:/\[ERROR\]/i.test(proc.stdout)?'TOOL_INPUT_ERROR':'TOOL_EXIT_UNEXPECTED',truncated:false,warnings:0};
    const findings=normalizeLines(proc.stdout);
    let overlayFindings=[];
    if(op==='FORM_VALIDATE'){
      const form=await fsp.readFile(binding.target_native,'utf8');
      const modulePath=binding.target_native.replace(/Form\.xml$/,'Form'+path.sep+'Module.bsl');
      const moduleText=await isFile(modulePath)?await fsp.readFile(modulePath,'utf8'):'';
      overlayFindings=overlay(form,moduleText);
      if(overlayFindings.length && cls.result_class==='OK')cls.result_class='FINDINGS';
    }
    const report={
      schema_version:REPORT_SCHEMA,project_id:this.projectId,participant_id:binding.artifact.participant_id,
      artifact_type:binding.artifact.artifact_type,artifact_id:binding.artifact.artifact_id,source_snapshot_id:this.sourceSnapshotId,
      manifest_sha256:this.manifestSha256,task_id:this.taskId,session_id:this.sessionId,relative_target:binding.target_relative,
      confirming_read:{relative_path:norm(confirmingPath),sha256:String(confirmingSha).toLowerCase()},
      operation:op,adapter_contract_version:ADAPTER_CONTRACT,upstream_commit:UPSTREAM_COMMIT,script_git_blob:info.blob,script_sha256:info.sha256,
      overlay_sha256:op==='FORM_VALIDATE'?OVERLAY_SHA256:null,
      normalized_args:op==='META_INFO'?['Mode=overview']:op==='FORM_VALIDATE'?['Detailed=false','MaxErrors=30']:[],
      input_closure:before,input_closure_sha256:beforeDigest,elapsed_ms,result_class:cls.result_class,
      warnings:Number(cls.warnings||0),findings:[...findings,...overlayFindings].slice(0,20),stdout_sha256:sha256(Buffer.from(proc.stdout,'utf8')),
      stderr_sha256:sha256(Buffer.from(proc.stderr,'utf8')),truncated:cls.truncated===true||findings.length+overlayFindings.length>20
    };
    report.report_sha256=sha256(Buffer.from(stableText(report),'utf8'));
    return report;
  }
}
export async function boundedTargetHints({taskGoal,projectRoot,artifacts}){
  if(typeof taskGoal!=='string'||!taskGoal.trim())return [];
  const n=taskGoal.normalize('NFKC').toLocaleLowerCase('ru').replace(/[ _-]+/g,'');
  const pairs=[];
  for(const [alias,collection] of HINT_LEXICON){const at=n.indexOf(alias);if(at<0)continue;const tail=n.slice(at+alias.length);const m=tail.match(/^([\p{L}0-9.]{1,80})/u);if(m)pairs.push({collection,name:m[1]});}
  const hints=[];
  for(const a of artifacts){
    let probes=0;
    for(const p of pairs){if(probes++>=8)break;const rel=`${p.collection}/${p.name}.xml`;const full=path.join(projectRoot,a.path.replaceAll('/',path.sep),rel.replaceAll('/',path.sep));if(await isFile(full))hints.push({participant_id:a.participant_id,artifact_type:a.artifact_type,artifact_id:a.artifact_id,path:a.path+'/'+rel,authoritative:false});}
  }
  return hints.length===1?hints:[];
}
export const __test={exactTarget,parseValidation,overlay,closureDigest,SCRIPT_INFO,META_COLLECTIONS};
