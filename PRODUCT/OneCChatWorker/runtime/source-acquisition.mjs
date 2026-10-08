import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

export const CONTRACT = 'S82_1_EXTERNAL_XML_FULL_SAFE_IMPORT_V1';
export const INTAKE_CONTRACT = 'S82_2_INCOMING_VALIDATE_HASH_V1';
export const PROMOTION_CONTRACT = 'S82_2_ZERO_COPY_PROMOTION_V1';
export const ALLOWED_VERBS = Object.freeze(['EXTERNAL_FULL_SAFE_IMPORT','INTAKE_VALIDATE_HASH','INTAKE_METADATA_VERIFY','ZERO_COPY_PROMOTE_ARTIFACT']);
const DEFAULT_MAX_FILES = 2000000;
const HARD_MAX_FILES = 5000000;
const DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024 * 1024;
const HARD_MAX_BYTES = Number.MAX_SAFE_INTEGER;
const DEFAULT_TIMEOUT_MS = 6 * 60 * 60 * 1000;
const HARD_TIMEOUT_MS = 12 * 60 * 60 * 1000;
const COPY_BUFFER_BYTES = 1024 * 1024;
const MAX_REQUEST_BYTES = 16384;
const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i;
const INVALID_SEGMENT = /[<>"|?*\x00-\x1f]/;

class AcquisitionError extends Error {
  constructor(code, message) {
    super(message);
    this.name = 'AcquisitionError';
    this.code = code;
  }
}

function fail(code, message) {
  throw new AcquisitionError(code, message);
}

function assertBoundedInt(value, fallback, min, max, name) {
  const v = value == null ? fallback : Number(value);
  if (!Number.isSafeInteger(v) || v < min || v > max) fail('REQUEST_LIMIT_INVALID', name);
  return v;
}

function stripNamespace(p) {
  if (p.startsWith('\\\\?\\UNC\\')) return '\\\\' + p.slice(8);
  if (p.startsWith('\\\\?\\')) return p.slice(4);
  return p;
}

function normCase(p) {
  return path.win32.resolve(stripNamespace(p)).replace(/[\\/]+$/, '').toLowerCase();
}

function within(root, candidate) {
  const r = normCase(root);
  const c = normCase(candidate);
  return c === r || c.startsWith(r + '\\');
}

function validateWindowsPath(raw, label) {
  if (process.platform !== 'win32') fail('WINDOWS_REQUIRED', label);
  if (typeof raw !== 'string' || !raw.trim()) fail('PATH_REQUIRED', label);
  if (raw.includes('\0')) fail('PATH_NUL_REJECTED', label);
  if (/^(\\\\[?.]\\|\\\\\?\\|\\\?\?\\)/.test(raw)) fail('INVALID_NAMESPACE', label);

  const normalizedInput = raw.replace(/\//g, '\\');
  const isDrive = /^[A-Za-z]:\\/.test(normalizedInput);
  const isUnc = /^\\\\[^\\]+\\[^\\]+(?:\\|$)/.test(normalizedInput);
  if (!isDrive && !isUnc) fail('INVALID_NAMESPACE', label);

  const rootPart = path.win32.parse(normalizedInput).root;
  const tail = normalizedInput.slice(rootPart.length);
  const segments = tail.split('\\').filter(Boolean);
  if (segments.some((s) => s === '.' || s === '..')) fail('TRAVERSAL_REJECTED', label);

  for (const segment of segments) {
    if (segment.includes(':')) fail('ADS_REJECTED', label);
    if (INVALID_SEGMENT.test(segment)) fail('INVALID_PATH_SEGMENT', label);
    if (segment.endsWith(' ') || segment.endsWith('.')) fail('AMBIGUOUS_PATH_SEGMENT', label);
    if (RESERVED.test(segment)) fail('RESERVED_PATH_SEGMENT', label);
  }
  if (isUnc) {
    const uncParts = normalizedInput.slice(2).split('\\').filter(Boolean);
    if (uncParts.length < 2) fail('INVALID_NAMESPACE', label);
    for (const segment of uncParts.slice(0, 2)) {
      if (segment.includes(':') || INVALID_SEGMENT.test(segment) || segment === '.' || segment === '..') fail('INVALID_NAMESPACE', label);
    }
  }
  const canonical = path.win32.resolve(normalizedInput);
  if (canonical.length >= 32760) fail('PATH_TOO_LONG_FOR_WINDOWS_NAMESPACE', label);
  return canonical;
}

function fsPath(p) {
  return process.platform === 'win32' ? path.win32.toNamespacedPath(p) : p;
}

async function statBig(p) {
  return fsp.lstat(fsPath(p), { bigint: true });
}

function sameStat(actual, expected, type) {
  if (type === 'file') {
    return actual.isFile() && !actual.isSymbolicLink() &&
      actual.size.toString() === expected.size &&
      actual.mtimeNs.toString() === expected.mtimeNs;
  }
  return actual.isDirectory() && !actual.isSymbolicLink() &&
    actual.mtimeNs.toString() === expected.mtimeNs;
}

async function realPathNormal(p) {
  return stripNamespace(await fsp.realpath(fsPath(p)));
}

function compareFactory(culture) {
  let collator;
  try {
    collator = new Intl.Collator(culture || 'en-US', { usage: 'sort', sensitivity: 'accent', numeric: false });
  } catch {
    collator = new Intl.Collator('en-US', { usage: 'sort', sensitivity: 'accent', numeric: false });
  }
  return (a, b) => {
    const c = collator.compare(a.relativePath, b.relativePath);
    return c || (a.relativePath < b.relativePath ? -1 : a.relativePath > b.relativePath ? 1 : 0);
  };
}

function checkDeadline(deadline) {
  if (Date.now() > deadline) fail('ACQUISITION_TIMEOUT', 'deadline exceeded');
}

async function writeProgress(progressPath, value) {
  await fsp.writeFile(fsPath(progressPath), JSON.stringify(value), 'utf8');
}

async function enumerateSource(root, limits, culture, deadline, progressPath) {
  const rootStat = await statBig(root).catch(() => null);
  if (!rootStat || !rootStat.isDirectory()) fail('SOURCE_FOLDER_NOT_FOUND', root);
  if (rootStat.isSymbolicLink()) fail('REPARSE_POINT', root);
  const rootReal = validateWindowsPath(await realPathNormal(root), 'source_real_root');
  const files = [];
  const directories = [];
  let bytes = 0;
  let maxSourcePathChars = root.length;
  let maxRelativePathChars = 0;
  let maxRelativePath = null;

  async function walk(current, relativeDir) {
    checkDeadline(deadline);
    const currentReal = validateWindowsPath(await realPathNormal(current), 'source_directory_realpath');
    if (!within(rootReal, currentReal)) fail('REPARSE_ESCAPE', relativeDir || '.');
    const dirStat = await statBig(current);
    if (!dirStat.isDirectory() || dirStat.isSymbolicLink()) fail('REPARSE_POINT', relativeDir || '.');
    if (relativeDir) directories.push({ fullPath: current, relativePath: relativeDir, mtimeNs: dirStat.mtimeNs.toString() });

    const dir = await fsp.opendir(fsPath(current));
    try {
      for await (const ent of dir) {
        checkDeadline(deadline);
        if (ent.name === '.' || ent.name === '..' || ent.name.includes(':')) fail(ent.name.includes(':') ? 'ADS_REJECTED' : 'TRAVERSAL_REJECTED', ent.name);
        if (INVALID_SEGMENT.test(ent.name) || ent.name.endsWith(' ') || ent.name.endsWith('.') || RESERVED.test(ent.name)) fail('INVALID_PATH_SEGMENT', ent.name);
        const child = path.win32.join(current, ent.name);
        if (!within(root, child)) fail('ROOT_ESCAPE', ent.name);
        const rel = relativeDir ? relativeDir + '/' + ent.name : ent.name;
        const st = await statBig(child);
        if (st.isSymbolicLink() || ent.isSymbolicLink()) fail('REPARSE_POINT', rel);
        const childReal = validateWindowsPath(await realPathNormal(child), 'source_entry_realpath');
        if (!within(rootReal, childReal)) fail('REPARSE_ESCAPE', rel);
        maxSourcePathChars = Math.max(maxSourcePathChars, child.length);
        if (st.isDirectory()) {
          await walk(child, rel);
        } else if (st.isFile()) {
          if (files.length + 1 > limits.maxFiles) fail('FILE_LIMIT_EXCEEDED', String(limits.maxFiles));
          const size = Number(st.size);
          if (!Number.isSafeInteger(size) || size < 0) fail('FILE_SIZE_UNSUPPORTED', rel);
          bytes += size;
          if (bytes > limits.maxBytes) fail('BYTE_LIMIT_EXCEEDED', String(limits.maxBytes));
          if (rel.length > maxRelativePathChars) {
            maxRelativePathChars = rel.length;
            maxRelativePath = rel;
          }
          files.push({ fullPath: child, relativePath: rel.replace(/\\/g, '/'), size: st.size.toString(), mtimeNs: st.mtimeNs.toString() });
          if (files.length === 1 || files.length % 250 === 0) {
            await writeProgress(progressPath, { phase: 'SCAN', files_processed: files.length, files_total: null, bytes_processed: bytes, bytes_total: null });
          }
        } else {
          fail('UNSUPPORTED_ENTRY_TYPE', rel);
        }
      }
    } finally {
      await dir.close().catch(() => {});
    }
  }

  await walk(root, '');
  const cmp = compareFactory(culture);
  files.sort(cmp);
  directories.sort((a, b) => {
    const da = a.relativePath.split('/').length;
    const db = b.relativePath.split('/').length;
    return da - db || cmp(a, b);
  });
  const config = files.find((f) => f.relativePath.toLowerCase() === 'configuration.xml');
  if (!config) fail('ONEC_CONFIGURATION_XML_MISSING', root);
  return {
    root,
    rootReal,
    rootMtimeNs: rootStat.mtimeNs.toString(),
    files,
    directories,
    fileCount: files.length,
    bytes,
    maxSourcePathChars,
    maxRelativePathChars,
    maxRelativePath,
    configurationRelativePath: config.relativePath,
  };
}

async function verifyStable(plan, deadline) {
  checkDeadline(deadline);
  const root = await statBig(plan.root).catch(() => null);
  if (!root || !sameStat(root, { mtimeNs: plan.rootMtimeNs }, 'dir')) fail('SOURCE_CHANGED_DURING_SYNC', 'root metadata changed');
  for (const d of plan.directories) {
    checkDeadline(deadline);
    const st = await statBig(d.fullPath).catch(() => null);
    if (!st || !sameStat(st, d, 'dir')) fail('SOURCE_CHANGED_DURING_SYNC', 'directory metadata changed: ' + d.relativePath);
    const real = validateWindowsPath(await realPathNormal(d.fullPath), 'stable_directory_realpath');
    if (!within(plan.rootReal, real)) fail('SOURCE_CHANGED_DURING_SYNC', 'reparse escape: ' + d.relativePath);
  }
  for (const f of plan.files) {
    checkDeadline(deadline);
    const st = await statBig(f.fullPath).catch(() => null);
    if (!st || !sameStat(st, f, 'file')) fail('SOURCE_CHANGED_DURING_SYNC', 'file metadata changed: ' + f.relativePath);
    const real = validateWindowsPath(await realPathNormal(f.fullPath), 'stable_file_realpath');
    if (!within(plan.rootReal, real)) fail('SOURCE_CHANGED_DURING_SYNC', 'reparse escape: ' + f.relativePath);
  }
}

async function writeChunk(handle, buffer, length, position) {
  let offset = 0;
  while (offset < length) {
    const { bytesWritten } = await handle.write(buffer, offset, length - offset, position + offset);
    if (!bytesWritten) fail('STAGE_WRITE_FAILED', 'zero-byte write');
    offset += bytesWritten;
  }
}

async function copyHashFile(source, destination, expected, deadline) {
  const input = await fsp.open(fsPath(source), 'r');
  let output;
  const sha = crypto.createHash('sha256');
  let written = 0;
  try {
    output = await fsp.open(fsPath(destination), 'wx');
    const buffer = Buffer.allocUnsafe(COPY_BUFFER_BYTES);
    while (true) {
      checkDeadline(deadline);
      const { bytesRead } = await input.read(buffer, 0, buffer.length, null);
      if (!bytesRead) break;
      await writeChunk(output, buffer, bytesRead, written);
      sha.update(buffer.subarray(0, bytesRead));
      written += bytesRead;
    }
    await output.sync();
  } finally {
    await output?.close().catch(() => {});
    await input.close().catch(() => {});
  }
  if (written !== Number(expected.size)) fail('SOURCE_CHANGED_DURING_SYNC', 'length changed while copying: ' + expected.relativePath);
  const post = await statBig(source);
  if (!sameStat(post, expected, 'file')) fail('SOURCE_CHANGED_DURING_SYNC', 'file metadata changed while copying: ' + expected.relativePath);
  const destStat = await statBig(destination);
  if (!destStat.isFile() || Number(destStat.size) !== written) fail('APPLY_COPY_LENGTH_MISMATCH', expected.relativePath);
  return { sha256: sha.digest('hex'), bytes: written };
}

async function hashFileNoCopy(source, expected, deadline) {
  const input = await fsp.open(fsPath(source), 'r');
  const sha = crypto.createHash('sha256');
  let read = 0;
  try {
    const buffer = Buffer.allocUnsafe(COPY_BUFFER_BYTES);
    while (true) {
      checkDeadline(deadline);
      const r = await input.read(buffer, 0, buffer.length, null);
      if (!r.bytesRead) break;
      sha.update(buffer.subarray(0, r.bytesRead));
      read += r.bytesRead;
    }
  } finally {
    await input.close().catch(() => {});
  }
  if (read !== Number(expected.size)) fail('SOURCE_CHANGED_DURING_SYNC', 'length changed while hashing: ' + expected.relativePath);
  const post = await statBig(source);
  if (!sameStat(post, expected, 'file')) fail('SOURCE_CHANGED_DURING_SYNC', 'file metadata changed while hashing: ' + expected.relativePath);
  return { sha256: sha.digest('hex'), bytes: read };
}

function metadataIdentity(plan) {
  const h = crypto.createHash('sha256');
  h.update('root\t' + plan.rootMtimeNs + '\n');
  for (const d of plan.directories) h.update('d\t' + d.relativePath + '\t' + d.mtimeNs + '\n');
  for (const f of plan.files) h.update('f\t' + f.relativePath + '\t' + f.size + '\t' + f.mtimeNs + '\n');
  return h.digest('hex');
}

function requireLocalDrive(p, label) {
  const x = validateWindowsPath(p, label);
  if (!/^[A-Za-z]:\\/.test(x)) fail('LOCAL_VOLUME_REQUIRED', label);
  return x;
}

function directChild(parent, child, code) {
  if (normCase(path.win32.dirname(child)) !== normCase(parent)) fail(code, child);
}

function validateCommonLimits(input) {
  return {
    maxFiles: assertBoundedInt(input.max_files, DEFAULT_MAX_FILES, 1, HARD_MAX_FILES, 'max_files'),
    maxBytes: assertBoundedInt(input.max_bytes, DEFAULT_MAX_BYTES, 1, HARD_MAX_BYTES, 'max_bytes'),
    timeoutMs: assertBoundedInt(input.timeout_ms, DEFAULT_TIMEOUT_MS, 1000, HARD_TIMEOUT_MS, 'timeout_ms'),
    culture: typeof input.culture === 'string' && input.culture.length <= 32 ? input.culture : 'en-US',
  };
}

function validateIntakeRequest(input, verifyOnly=false) {
  const sourceRoot = validateWindowsPath(input.source_root, 'source_root');
  const progressPath = validateWindowsPath(input.progress_path, 'progress_path');
  const outputParent = validateWindowsPath(input.output_parent, 'output_parent');
  if (within(sourceRoot, outputParent) || within(outputParent, sourceRoot)) fail('SOURCE_OUTPUT_OVERLAP', 'source/output roots overlap');
  directChild(outputParent, progressPath, 'PROGRESS_PATH_INVALID');
  const limits = validateCommonLimits(input);
  if (verifyOnly) {
    const expectedMetadataIdentity = String(input.expected_metadata_identity_sha256 || '').toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(expectedMetadataIdentity)) fail('METADATA_IDENTITY_REQUIRED', 'expected_metadata_identity_sha256');
    return {verb:input.verb,sourceRoot,progressPath,outputParent,expectedMetadataIdentity,...limits};
  }
  const fingerprintPath = validateWindowsPath(input.fingerprint_path, 'fingerprint_path');
  directChild(outputParent, fingerprintPath, 'FINGERPRINT_PATH_INVALID');
  if (!/\.fingerprints\.jsonl$/i.test(path.win32.basename(fingerprintPath))) fail('FINGERPRINT_PATH_INVALID', fingerprintPath);
  return {verb:input.verb,sourceRoot,progressPath,outputParent,fingerprintPath,...limits};
}

function validatePromotionRequest(input) {
  const sourceParent = requireLocalDrive(input.source_parent, 'source_parent');
  const sourceRoot = requireLocalDrive(input.source_root, 'source_root');
  const destinationParent = requireLocalDrive(input.destination_parent, 'destination_parent');
  const destinationRoot = requireLocalDrive(input.destination_root, 'destination_root');
  directChild(sourceParent, sourceRoot, 'PROMOTION_SOURCE_ESCAPE');
  directChild(destinationParent, destinationRoot, 'PROMOTION_DESTINATION_ESCAPE');
  if (path.win32.parse(sourceRoot).root.toLowerCase() !== path.win32.parse(destinationRoot).root.toLowerCase()) fail('CROSS_VOLUME_ZERO_COPY_REJECTED', 'source/destination volume mismatch');
  if (normCase(sourceRoot) === normCase(destinationRoot)) fail('PROMOTION_PATH_COLLISION', sourceRoot);
  const timeoutMs = assertBoundedInt(input.timeout_ms, 120000, 1000, HARD_TIMEOUT_MS, 'timeout_ms');
  return {verb:input.verb,sourceParent,sourceRoot,destinationParent,destinationRoot,timeoutMs};
}

async function executeIntake(req) {
  const started=Date.now(),deadline=started+req.timeoutMs;
  const outputStat=await statBig(req.outputParent).catch(()=>null);
  if(!outputStat||!outputStat.isDirectory()||outputStat.isSymbolicLink()) fail('OUTPUT_PARENT_INVALID',req.outputParent);
  const outputReal=validateWindowsPath(await realPathNormal(req.outputParent),'output_parent_realpath');
  if(normCase(outputReal)!==normCase(req.outputParent)) fail('REPARSE_ESCAPE','output_parent');
  await writeProgress(req.progressPath,{phase:'SCAN',files_processed:0,files_total:null,bytes_processed:0,bytes_total:null});
  const plan=await enumerateSource(req.sourceRoot,{maxFiles:req.maxFiles,maxBytes:req.maxBytes},req.culture,deadline,req.progressPath);
  const meta=metadataIdentity(plan);
  if(req.verb==='INTAKE_METADATA_VERIFY'){
    await verifyStable(plan,deadline);
    if(meta!==req.expectedMetadataIdentity) fail('SEALED_SOURCE_DRIFT','metadata identity mismatch');
    await writeProgress(req.progressPath,{phase:'COMPLETE',files_processed:plan.fileCount,files_total:plan.fileCount,bytes_processed:0,bytes_total:plan.bytes});
    return {contract:INTAKE_CONTRACT,verb:req.verb,result:'PASS',metadata_identity_sha256:meta,digest:{files:plan.fileCount,bytes:plan.bytes},metrics:{hashed_files:0,hashed_bytes:0,copied_files:0,copied_bytes:0,source_content_passes:0,source_metadata_passes:2,stage_content_rehash:0,shell:false}};
  }
  try{await fsp.lstat(fsPath(req.fingerprintPath));fail('FINGERPRINT_OUTPUT_EXISTS',req.fingerprintPath)}catch(e){if(e instanceof AcquisitionError)throw e;if(e?.code!=='ENOENT')throw e}
  await writeProgress(req.progressPath,{phase:'HASH',files_processed:0,files_total:plan.fileCount,bytes_processed:0,bytes_total:plan.bytes});
  const aggregate=crypto.createHash('sha256'),fingerprintHash=crypto.createHash('sha256');
  const fp=await fsp.open(fsPath(req.fingerprintPath),'wx');
  let hashedBytes=0,hashedFiles=0,fingerprintBytes=0,configSha=null;
  try{
    for(const f of plan.files){
      const hv=await hashFileNoCopy(f.fullPath,f,deadline);
      hashedBytes+=hv.bytes;hashedFiles++;
      if(f.relativePath.toLowerCase()==='configuration.xml')configSha=hv.sha256;
      aggregate.update(Buffer.from(f.relativePath+'\t'+f.size+'\t'+hv.sha256+'\r\n','utf8'));
      const line=Buffer.from(JSON.stringify({path:f.relativePath,size:Number(f.size),sha256:hv.sha256})+'\n','utf8');
      fingerprintHash.update(line);await writeChunk(fp,line,line.length,fingerprintBytes);fingerprintBytes+=line.length;
      if(hashedFiles===1||hashedFiles%250===0||hashedFiles===plan.fileCount)await writeProgress(req.progressPath,{phase:'HASH',files_processed:hashedFiles,files_total:plan.fileCount,bytes_processed:hashedBytes,bytes_total:plan.bytes});
    }
    await fp.sync();
  }finally{await fp.close().catch(()=>{})}
  await verifyStable(plan,deadline);
  if(!configSha)fail('ONEC_CONFIGURATION_XML_MISSING',req.sourceRoot);
  return {contract:INTAKE_CONTRACT,verb:req.verb,result:'PASS',digest:{sha256:aggregate.digest('hex'),files:plan.fileCount,bytes:plan.bytes,max_relative_path_chars:plan.maxRelativePathChars,max_relative_path:plan.maxRelativePath},configuration_xml_sha256:configSha,fingerprint_file:{path:req.fingerprintPath,sha256:fingerprintHash.digest('hex'),rows:plan.fileCount},metadata_identity_sha256:meta,metrics:{discovered_files:plan.fileCount,discovered_bytes:plan.bytes,hashed_files:hashedFiles,hashed_bytes:hashedBytes,copied_files:0,copied_bytes:0,max_source_path_chars:plan.maxSourcePathChars,source_stable:true,source_unchanged:true,recursive_passes:{source_enumeration_metadata:1,source_content:1,source_stability_metadata:1,stage_content_rehash:0},shell:false,subst_required:false,long_paths_registry_required:false,powershell7_required:false,elapsed_ms:Date.now()-started}};
}

async function executePromotion(req) {
  const started=Date.now(),deadline=started+req.timeoutMs;checkDeadline(deadline);
  for(const pair of [['source_parent',req.sourceParent],['destination_parent',req.destinationParent]]){
    const label=pair[0],p=pair[1],st=await statBig(p).catch(()=>null);
    if(!st||!st.isDirectory()||st.isSymbolicLink())fail('PROMOTION_PARENT_INVALID',label);
    const real=validateWindowsPath(await realPathNormal(p),label+'_realpath');if(normCase(real)!==normCase(p))fail('REPARSE_ESCAPE',label);
  }
  const sourceStat=await statBig(req.sourceRoot).catch(()=>null);if(!sourceStat||!sourceStat.isDirectory()||sourceStat.isSymbolicLink())fail('PROMOTION_SOURCE_INVALID',req.sourceRoot);
  const sourceReal=validateWindowsPath(await realPathNormal(req.sourceRoot),'promotion_source_realpath');if(!within(req.sourceParent,sourceReal))fail('REPARSE_ESCAPE','source_root');
  try{await fsp.lstat(fsPath(req.destinationRoot));fail('PROMOTION_DESTINATION_EXISTS',req.destinationRoot)}catch(e){if(e instanceof AcquisitionError)throw e;if(e?.code!=='ENOENT')throw e}
  await fsp.rename(fsPath(req.sourceRoot),fsPath(req.destinationRoot));checkDeadline(deadline);
  const srcAfter=await statBig(req.sourceRoot).catch(()=>null);if(srcAfter)fail('PROMOTION_SOURCE_STILL_PRESENT',req.sourceRoot);
  const dst=await statBig(req.destinationRoot).catch(()=>null);if(!dst||!dst.isDirectory()||dst.isSymbolicLink())fail('PROMOTION_DESTINATION_INVALID',req.destinationRoot);
  const dstReal=validateWindowsPath(await realPathNormal(req.destinationRoot),'promotion_destination_realpath');if(!within(req.destinationParent,dstReal))fail('REPARSE_ESCAPE','destination_root');
  return {contract:PROMOTION_CONTRACT,verb:req.verb,result:'PASS',same_volume:true,source_volume:path.win32.parse(req.sourceRoot).root.toUpperCase(),destination_volume:path.win32.parse(req.destinationRoot).root.toUpperCase(),source_absent:true,destination_present:true,copied_content_bytes:0,copied_content_files:0,elapsed_ms:Date.now()-started,shell:false};
}

function validateFullImportRequest(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) fail('REQUEST_INVALID', 'object required');
  if (!ALLOWED_VERBS.includes(input.verb)) fail('VERB_NOT_ALLOWED', String(input.verb || ''));
  const sourceRoot = validateWindowsPath(input.source_root, 'source_root');
  const stageParent = validateWindowsPath(input.stage_parent, 'stage_parent');
  const stageRoot = validateWindowsPath(input.stage_root, 'stage_root');
  const fingerprintPath = validateWindowsPath(input.fingerprint_path, 'fingerprint_path');
  const progressPath = validateWindowsPath(input.progress_path, 'progress_path');
  if (path.win32.dirname(stageRoot).toLowerCase() !== stageParent.toLowerCase()) fail('STAGE_ROOT_ESCAPE', stageRoot);
  if (!/^a\.stage-[0-9a-f]{8}$/i.test(path.win32.basename(stageRoot))) fail('STAGE_NAME_INVALID', path.win32.basename(stageRoot));
  if (fingerprintPath.toLowerCase() !== (stageRoot + '.fingerprints.jsonl').toLowerCase()) fail('FINGERPRINT_PATH_INVALID', fingerprintPath);
  if (progressPath.toLowerCase() !== (stageRoot + '.progress.json').toLowerCase()) fail('PROGRESS_PATH_INVALID', progressPath);
  if (within(sourceRoot, stageRoot) || within(stageRoot, sourceRoot)) fail('SOURCE_STAGE_OVERLAP', 'source/stage roots overlap');
  const maxFiles = assertBoundedInt(input.max_files, DEFAULT_MAX_FILES, 1, HARD_MAX_FILES, 'max_files');
  const maxBytes = assertBoundedInt(input.max_bytes, DEFAULT_MAX_BYTES, 1, HARD_MAX_BYTES, 'max_bytes');
  const timeoutMs = assertBoundedInt(input.timeout_ms, DEFAULT_TIMEOUT_MS, 1000, HARD_TIMEOUT_MS, 'timeout_ms');
  const culture = typeof input.culture === 'string' && input.culture.length <= 32 ? input.culture : 'en-US';
  return { sourceRoot, stageParent, stageRoot, fingerprintPath, progressPath, maxFiles, maxBytes, timeoutMs, culture };
}

async function executeFullImport(req) {
  const started = Date.now();
  const deadline = started + req.timeoutMs;
  await fsp.mkdir(fsPath(req.stageParent), { recursive: true });
  const stageParentStat = await statBig(req.stageParent);
  if (!stageParentStat.isDirectory() || stageParentStat.isSymbolicLink()) fail('REPARSE_POINT', 'stage_parent');
  const stageParentReal = validateWindowsPath(await realPathNormal(req.stageParent), 'stage_parent_realpath');
  if (normCase(stageParentReal) !== normCase(req.stageParent)) fail('REPARSE_ESCAPE', 'stage_parent');
  try {
    await fsp.lstat(fsPath(req.stageRoot));
    fail('STAGE_ALREADY_EXISTS', req.stageRoot);
  } catch (e) {
    if (e instanceof AcquisitionError) throw e;
    if (e?.code !== 'ENOENT') throw e;
  }
  try {
    await fsp.lstat(fsPath(req.fingerprintPath));
    fail('FINGERPRINT_OUTPUT_EXISTS', req.fingerprintPath);
  } catch (e) {
    if (e instanceof AcquisitionError) throw e;
    if (e?.code !== 'ENOENT') throw e;
  }

  await writeProgress(req.progressPath, { phase: 'SCAN', files_processed: 0, files_total: null, bytes_processed: 0, bytes_total: null });
  const plan = await enumerateSource(req.sourceRoot, { maxFiles: req.maxFiles, maxBytes: req.maxBytes }, req.culture, deadline, req.progressPath);
  await writeProgress(req.progressPath, { phase: 'COPY_HASH', files_processed: 0, files_total: plan.fileCount, bytes_processed: 0, bytes_total: plan.bytes });
  await fsp.mkdir(fsPath(req.stageRoot), { recursive: false });
  for (const d of plan.directories) {
    checkDeadline(deadline);
    const dest = path.win32.join(req.stageRoot, d.relativePath.replace(/\//g, '\\'));
    if (!within(req.stageRoot, dest)) fail('STAGE_ROOT_ESCAPE', d.relativePath);
    await fsp.mkdir(fsPath(dest), { recursive: true });
  }

  const aggregate = crypto.createHash('sha256');
  const fingerprintHash = crypto.createHash('sha256');
  const fp = await fsp.open(fsPath(req.fingerprintPath), 'wx');
  let copiedBytes = 0;
  let copiedFiles = 0;
  let fingerprintBytes = 0;
  let maxStagePathChars = req.stageRoot.length;
  let configSha = null;
  try {
    for (const f of plan.files) {
      checkDeadline(deadline);
      const dest = path.win32.join(req.stageRoot, f.relativePath.replace(/\//g, '\\'));
      if (!within(req.stageRoot, dest)) fail('STAGE_ROOT_ESCAPE', f.relativePath);
      maxStagePathChars = Math.max(maxStagePathChars, dest.length);
      const parent = path.win32.dirname(dest);
      await fsp.mkdir(fsPath(parent), { recursive: true });
      const copied = await copyHashFile(f.fullPath, dest, f, deadline);
      copiedBytes += copied.bytes;
      copiedFiles += 1;
      if (f.relativePath.toLowerCase() === 'configuration.xml') configSha = copied.sha256;
      const treeRow = Buffer.from(`${f.relativePath}\t${f.size}\t${copied.sha256}\r\n`, 'utf8');
      aggregate.update(treeRow);
      const fpLine = Buffer.from(JSON.stringify({ path: f.relativePath, size: Number(f.size), sha256: copied.sha256 }) + '\n', 'utf8');
      fingerprintHash.update(fpLine);
      await writeChunk(fp, fpLine, fpLine.length, fingerprintBytes);
      fingerprintBytes += fpLine.length;
      if (copiedFiles === 1 || copiedFiles % 250 === 0 || copiedFiles === plan.fileCount) {
        await writeProgress(req.progressPath, { phase: 'COPY_HASH', files_processed: copiedFiles, files_total: plan.fileCount, bytes_processed: copiedBytes, bytes_total: plan.bytes });
      }
    }
    await fp.sync();
  } finally {
    await fp.close().catch(() => {});
  }
  await writeProgress(req.progressPath, { phase: 'STABILITY_CHECK', files_processed: copiedFiles, files_total: plan.fileCount, bytes_processed: copiedBytes, bytes_total: plan.bytes });
  await verifyStable(plan, deadline);
  if (!configSha) fail('ONEC_CONFIGURATION_XML_MISSING', req.sourceRoot);
  await writeProgress(req.progressPath, { phase: 'COMPLETE', files_processed: copiedFiles, files_total: plan.fileCount, bytes_processed: copiedBytes, bytes_total: plan.bytes });

  const fingerprintSha256 = fingerprintHash.digest('hex');
  const digest = aggregate.digest('hex');
  const ended = Date.now();
  return {
    contract: CONTRACT,
    verb: 'EXTERNAL_FULL_SAFE_IMPORT',
    result: 'PASS',
    digest: {
      sha256: digest,
      files: plan.fileCount,
      bytes: plan.bytes,
      max_relative_path_chars: plan.maxRelativePathChars,
      max_relative_path: plan.maxRelativePath,
    },
    configuration_xml_sha256: configSha,
    fingerprint_file: {
      path: req.fingerprintPath,
      sha256: fingerprintSha256,
      rows: plan.fileCount,
    },
    metrics: {
      discovered_files: plan.fileCount,
      discovered_bytes: plan.bytes,
      copied_files: copiedFiles,
      copied_bytes: copiedBytes,
      hashed_files: copiedFiles,
      hashed_bytes: copiedBytes,
      max_source_path_chars: plan.maxSourcePathChars,
      max_stage_path_chars: maxStagePathChars,
      source_stable: true,
      source_unchanged: true,
      stage_fingerprint_identity: digest,
      recursive_passes: {
        source_enumeration_metadata: 1,
        source_content: 1,
        source_stability_metadata: 1,
        stage_content_rehash: 0,
      },
      shell: false,
      subst_required: false,
      long_paths_registry_required: false,
      powershell7_required: false,
      elapsed_ms: ended - started,
    },
  };
}

export async function executeRequest(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) fail('REQUEST_INVALID', 'object required');
  if (!ALLOWED_VERBS.includes(input.verb)) fail('VERB_NOT_ALLOWED', String(input.verb || ''));
  if (input.verb === 'EXTERNAL_FULL_SAFE_IMPORT') return executeFullImport(validateFullImportRequest(input));
  if (input.verb === 'INTAKE_VALIDATE_HASH') return executeIntake(validateIntakeRequest(input, false));
  if (input.verb === 'INTAKE_METADATA_VERIFY') return executeIntake(validateIntakeRequest(input, true));
  if (input.verb === 'ZERO_COPY_PROMOTE_ARTIFACT') return executePromotion(validatePromotionRequest(input));
  fail('VERB_NOT_ALLOWED', String(input.verb || ''));
}

async function main() {
  const requestPathRaw = process.env.ONEC_ACQ_REQUEST;
  if (!requestPathRaw) fail('REQUEST_PATH_REQUIRED', 'ONEC_ACQ_REQUEST');
  const requestPath = validateWindowsPath(requestPathRaw, 'request_path');
  const st = await fsp.stat(fsPath(requestPath));
  if (!st.isFile() || st.size > MAX_REQUEST_BYTES) fail('REQUEST_FILE_INVALID', 'bounded request file required');
  const input = JSON.parse(await fsp.readFile(fsPath(requestPath), 'utf8'));
  const result = await executeRequest(input);
  process.stdout.write(JSON.stringify(result));
}

const invoked = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invoked) {
  main().catch((e) => {
    const code = e instanceof AcquisitionError ? e.code : 'ACQUISITION_EXECUTION_ERROR';
    const msg = String(e?.message || e || code).replace(/[\r\n\t]+/g, ' ').slice(0, 800);
    process.stderr.write(JSON.stringify({ contract: CONTRACT, result: 'FAIL', code, message: msg }));
    process.exitCode = 2;
  });
}
