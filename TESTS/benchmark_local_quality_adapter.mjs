import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { LocalQualityAdapter } from '../PRODUCT/OneCChatWorker/runtime/local-quality-adapter.mjs';

const argv=process.argv.slice(2);
const arg=n=>{const i=argv.indexOf(n);if(i<0||!argv[i+1])throw new Error('missing '+n);return argv[i+1];};
const projectRoot=arg('--project-root'),artifactPath=arg('--artifact-path'),metadataInside=arg('--metadata'),formInside=arg('--form');
const snapshot=arg('--snapshot'),manifestSha=arg('--manifest-sha');
const artifact={participant_id:'benchmark',platform:'ONEC',side:'TARGET',artifact_type:'MAIN',artifact_id:'main',path:artifactPath};
const sha256=b=>crypto.createHash('sha256').update(b).digest('hex');
const native=inside=>path.join(projectRoot,...artifactPath.split('/'),...inside.split('/'));
async function facts(inside){
  const b=await fsp.readFile(native(inside));
  const text=b.toString('utf8'),lines=text.split(/\r?\n/);
  return {relative_path:artifactPath+'/'+inside,sha256:sha256(b),bytes:b.length,lines:lines.length,confirm_bytes:Buffer.byteLength(lines[0]||'','utf8')};
}
const adapter=new LocalQualityAdapter({projectRoot,artifacts:[artifact],projectId:'BENCH',taskId:'Q0-BENCH',sessionId:'bench-session',sourceSnapshotId:snapshot,manifestSha256:manifestSha});
const cases=[];
for(const [kind,inside] of [['META_INFO',metadataInside],['FORM',formInside]]){
  const f=await facts(inside),started=performance.now();
  const q=await adapter.runConfirmed(f.relative_path,f.sha256);
  const elapsed=+(performance.now()-started).toFixed(3);
  const postSha=sha256(await fsp.readFile(native(inside)));
  const preparedBytes=q?.prepared?Buffer.byteLength(JSON.stringify(q.prepared),'utf8'):0;
  const baselineCalls=Math.ceil(f.lines/20),baselineBytes=f.bytes;
  const preparedCalls=1,preparedModelBytes=f.confirm_bytes+preparedBytes;
  const reduction=baselineBytes?100*(1-preparedModelBytes/baselineBytes):0;
  cases.push({
    case:kind,target:f.relative_path,input_sha256:f.sha256,post_sha256:postSha,source_unchanged:postSha===f.sha256,input_bytes:f.bytes,input_lines:f.lines,
    baseline:{source_read_calls:baselineCalls,model_bound_source_bytes:baselineBytes},
    prepared:{confirming_source_read_calls:preparedCalls,confirming_bytes:f.confirm_bytes,prepared_quality_bytes:preparedBytes,total_model_bound_bytes:preparedModelBytes,adapter_elapsed_ms:elapsed},
    source_bytes_reduction_pct:+reduction.toFixed(2),
    reports:(q?.reports||[]).map(r=>({operation:r.operation,result_class:r.result_class,warnings:r.warnings,findings:r.findings.length,truncated:r.truncated,report_sha256:r.report_sha256,input_closure_sha256:r.input_closure_sha256}))
  });
}
const m=cases.find(x=>x.case==='META_INFO'),f=cases.find(x=>x.case==='FORM');
const keepMeta=m.source_bytes_reduction_pct>=30;
const keepFormInfo=f.source_bytes_reduction_pct>=30;
const validate=f.reports.find(x=>x.operation==='FORM_VALIDATE');
const formBlockingFp=validate?.result_class==='FINDINGS'?validate.findings:0;
const output={schema:'Q0_LOCAL_QUALITY_AB_BENCH_V1',cases,roi:{META_INFO_KEEP:keepMeta,FORM_INFO_KEEP:keepFormInfo,FORM_VALIDATE_CLEAN_CONTROL_BLOCKING_FP:formBlockingFp},status:(keepMeta&&keepFormInfo&&formBlockingFp===0)?'PASS':'REVIEW'};
console.log(JSON.stringify(output,null,2));
if(!keepMeta||!keepFormInfo)process.exitCode=2;
