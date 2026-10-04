import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import { TextDecoder } from 'node:util';

export const CONTRACT_ID = 'onecchatworker';
export const CONTRACT_VERSION = '1.0';
export const PROVIDER_VERSION = '1.0.0';

export class ProviderError extends Error {
  constructor(code, message = code) {
    super(`${code}: ${message}`);
    this.name = 'ProviderError';
    this.code = code;
  }
}

const fail = (code, message) => { throw new ProviderError(code, message); };
const sha256 = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');
const sha256Text = (text) => sha256(Buffer.from(text, 'utf8'));
const nowIso = () => new Date().toISOString();

function jsonResult(value) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    structuredContent: value,
  };
}

function stringArg(value, name, { min = 0, max = 4096 } = {}) {
  if (typeof value !== 'string') fail('INVALID_ARGUMENT', `${name} must be a string`);
  if (value.length < min || value.length > max) fail('INVALID_ARGUMENT', `${name} length out of bounds`);
  if (value.includes('\0')) fail('INVALID_ARGUMENT', `${name} contains NUL`);
  return value;
}

const RESERVED_SEGMENT = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i;
const SAFE_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function safeSegment(value, name) {
  const segment = stringArg(value, name, { min: 1, max: 64 });
  if (!SAFE_SEGMENT.test(segment) || segment === '.' || segment === '..' || RESERVED_SEGMENT.test(segment)) {
    fail(`INVALID_${name.toUpperCase()}`, segment);
  }
  return segment;
}

function sourceDomain(value) {
  const domain = stringArg(value, 'source_domain', { min: 1, max: 32 }).toUpperCase();
  if (domain !== 'ONEC' && domain !== 'CLEVERENCE') fail('UNKNOWN_SOURCE_DOMAIN', domain);
  return domain;
}

function relativePath(value, name, allowEmpty = true) {
  const raw = stringArg(value ?? '', name, { min: allowEmpty ? 0 : 1, max: 2048 });
  if (!raw && allowEmpty) return '';
  if (/^[A-Za-z]:/.test(raw) || raw.startsWith('\\\\') || raw.startsWith('//') || path.win32.isAbsolute(raw)) {
    fail('PATH_ESCAPE', `${name} must be relative`);
  }
  if (raw.includes(':')) fail('PATH_ESCAPE', `${name} contains ':'`);
  const parts = raw.replaceAll('/', '\\').split('\\');
  for (const part of parts) {
    if (!part || part === '.' || part === '..') fail('PATH_ESCAPE', `${name} contains unsafe segment`);
    if (part.endsWith(' ') || part.endsWith('.') || RESERVED_SEGMENT.test(part)) {
      fail('INVALID_PATH', `${name} contains unsafe Windows segment`);
    }
  }
  return parts.join(path.sep);
}

function isWithin(root, target) {
  const rel = path.relative(root, target);
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel));
}

async function assertNoReparse(rootReal, targetAbs, includeTarget = true) {
  if (!isWithin(rootReal, targetAbs)) fail('PATH_ESCAPE', targetAbs);
  const rel = path.relative(rootReal, targetAbs);
  if (!rel) return;
  const parts = rel.split(path.sep).filter(Boolean);
  let current = rootReal;
  for (let i = 0; i < parts.length; i += 1) {
    current = path.join(current, parts[i]);
    if (!includeTarget && i === parts.length - 1) break;
    try {
      const st = await fsp.lstat(current);
      if (st.isSymbolicLink()) fail('REPARSE_POINT', current);
    } catch (error) {
      if (error?.code === 'ENOENT') break;
      throw error;
    }
  }
}

async function resolveExisting(rootReal, relative, kind = 'any') {
  const rel = relativePath(relative, 'relative_path', true);
  const lexical = path.resolve(rootReal, rel);
  if (!isWithin(rootReal, lexical)) fail('PATH_ESCAPE', rel);
  await assertNoReparse(rootReal, lexical, true);
  let real;
  try {
    real = await fsp.realpath(lexical);
  } catch (error) {
    if (error?.code === 'ENOENT') fail('NOT_FOUND', rel || '.');
    throw error;
  }
  if (!isWithin(rootReal, real)) fail('PATH_ESCAPE', rel);
  const stat = await fsp.stat(real);
  if (kind === 'file' && !stat.isFile()) fail('NOT_A_FILE', rel);
  if (kind === 'directory' && !stat.isDirectory()) fail('NOT_A_DIRECTORY', rel);
  return { rel, real, stat };
}

async function assertExistingAncestor(rootReal, targetAbs) {
  let current = targetAbs;
  while (true) {
    try {
      const st = await fsp.lstat(current);
      if (st.isSymbolicLink()) fail('REPARSE_POINT', current);
      const real = await fsp.realpath(current);
      if (!isWithin(rootReal, real)) fail('PATH_ESCAPE', targetAbs);
      return;
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
      const parent = path.dirname(current);
      if (parent === current) fail('PATH_ESCAPE', targetAbs);
      current = parent;
    }
  }
}

async function hashFile(filePath) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    const stream = fs.createReadStream(filePath);
    stream.on('error', reject);
    stream.on('data', (chunk) => h.update(chunk));
    stream.on('end', () => resolve(h.digest('hex')));
  });
}

async function readUtf8File(filePath, maxBytes) {
  const stat = await fsp.stat(filePath);
  if (!stat.isFile()) fail('NOT_A_FILE', filePath);
  if (stat.size > maxBytes) fail('FILE_TOO_LARGE', `${stat.size} > ${maxBytes}`);
  const buffer = await fsp.readFile(filePath);
  if (buffer.subarray(0, Math.min(buffer.length, 4096)).includes(0)) fail('BINARY_FILE', filePath);
  let text;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    fail('INVALID_UTF8', filePath);
  }
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
  return { text, size: stat.size, sha256: sha256(buffer) };
}

async function readWindow(filePath, zeroBasedLine, before, after, maxBytes) {
  const { text } = await readUtf8File(filePath, maxBytes);
  const lines = text.split(/\r?\n/);
  const start = Math.max(0, zeroBasedLine - before);
  const end = Math.min(lines.length, zeroBasedLine + after + 1);
  return {
    start_line: start + 1,
    end_line: end,
    lines: lines.slice(start, end).map((line, index) => ({ line: start + index + 1, text: line })),
  };
}

function spawnCollect(exe, args, { cwd, timeoutMs, maxBytes }) {
  return new Promise((resolve, reject) => {
    const child = spawn(exe, args, {
      cwd,
      shell: false,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = Buffer.alloc(0);
    let stderr = Buffer.alloc(0);
    let timedOut = false;
    let outputLimit = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill();
    }, timeoutMs);
    const append = (current, chunk) => {
      if (current.length + chunk.length > maxBytes) {
        outputLimit = true;
        child.kill();
        return current;
      }
      return Buffer.concat([current, chunk]);
    };
    child.stdout.on('data', (chunk) => { stdout = append(stdout, chunk); });
    child.stderr.on('data', (chunk) => { stderr = append(stderr, chunk); });
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (timedOut) return reject(new ProviderError('SEARCH_TIMEOUT', `${timeoutMs}ms`));
      if (outputLimit) return reject(new ProviderError('SEARCH_OUTPUT_LIMIT', `${maxBytes} bytes`));
      resolve({ code: code ?? -1, stdout: stdout.toString('utf8'), stderr: stderr.toString('utf8') });
    });
  });
}

async function createExact(filePath, buffer) {
  const handle = await fsp.open(filePath, 'wx', 0o600);
  try {
    await handle.writeFile(buffer);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function createTemp(parent, buffer) {
  for (let i = 0; i < 20; i += 1) {
    const temp = path.join(parent, `.onecchatworker-${process.pid}-${crypto.randomBytes(8).toString('hex')}.tmp`);
    try {
      const handle = await fsp.open(temp, 'wx', 0o600);
      try {
        await handle.writeFile(buffer);
        await handle.sync();
      } finally {
        await handle.close();
      }
      return temp;
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error;
    }
  }
  fail('TEMP_CREATE_FAILED', parent);
}

export class SourceReaderIntegration {
  constructor({ configPath, getDeviceId = () => null }) {
    this.configPath = configPath;
    this.getDeviceId = getDeviceId;
    this.ready = false;
    this.msUntilRestartAllowed = 0;
    this.writeChain = Promise.resolve();
    this.allowedTools = new Set(TOOL_DEFINITIONS.map((tool) => tool.name));
  }

  onDisconnect(handler) { this.disconnectHandler = handler; }
  hasTool(name) { return this.allowedTools.has(name); }

  async initialize() {
    const raw = JSON.parse(await fsp.readFile(this.configPath, 'utf8'));
    if (raw.schema_version !== 1 || raw.contract_id !== CONTRACT_ID || raw.contract_version !== CONTRACT_VERSION) {
      fail('CONFIG_INVALID', 'contract/schema mismatch');
    }
    this.config = raw;

    const rootStat = await fsp.lstat(raw.worker_root);
    if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) fail('CONFIG_INVALID', 'worker_root');
    this.workerRoot = await fsp.realpath(raw.worker_root);

    if (!Array.isArray(raw.admitted_projects) || raw.admitted_projects.length < 1) {
      fail('CONFIG_INVALID', 'admitted_projects');
    }
    this.admittedProjects = new Set();
    for (const value of raw.admitted_projects) {
      const slug = safeSegment(value, 'project_slug');
      if (this.admittedProjects.has(slug)) fail('CONFIG_INVALID', `duplicate project ${slug}`);
      const projectPath = path.join(this.workerRoot, slug);
      const stat = await fsp.lstat(projectPath);
      if (stat.isSymbolicLink() || !stat.isDirectory()) fail('CONFIG_INVALID', `project ${slug}`);
      const real = await fsp.realpath(projectPath);
      if (!isWithin(this.workerRoot, real)) fail('CONFIG_INVALID', `project escape ${slug}`);
      this.admittedProjects.add(slug);
    }

    const rgStat = await fsp.stat(raw.rg_path);
    if (!rgStat.isFile()) fail('CONFIG_INVALID', 'rg_path');

    await fsp.mkdir(path.dirname(raw.audit_path), { recursive: true });
    await fsp.appendFile(raw.audit_path, '', 'utf8');
    this.ready = true;
  }

  async ensureReady() {
    if (!this.ready) fail('PROVIDER_NOT_READY');
  }

  async shutdown() { this.ready = false; }

  listClientTools() { return { tools: TOOL_DEFINITIONS }; }

  async appendAudit(record) {
    await fsp.appendFile(this.config.audit_path, `${JSON.stringify(record)}\n`, 'utf8');
  }

  auditBase(toolName, args) {
    const base = {
      timestamp_utc: nowIso(),
      operation: toolName,
      contract_id: CONTRACT_ID,
      contract_version: CONTRACT_VERSION,
      provider_version: PROVIDER_VERSION,
      device_id: this.getDeviceId() || null,
      identity: `${os.hostname()}\\${os.userInfo().username}`,
      pid: process.pid,
    };
    if (toolName.startsWith('source_')) {
      base.project_slug = typeof args.project_slug === 'string' ? args.project_slug : undefined;
      base.source_domain = typeof args.source_domain === 'string' ? args.source_domain.toUpperCase() : undefined;
      base.path = typeof args.relative_path === 'string' ? args.relative_path : undefined;
      base.scope = typeof args.relative_scope === 'string' ? args.relative_scope : undefined;
      if (toolName === 'source_search') {
        const pattern = typeof args.pattern === 'string' ? args.pattern : '';
        base.pattern_length = pattern.length;
        base.pattern_sha256 = pattern ? sha256Text(pattern) : null;
        base.glob = typeof args.glob === 'string' ? args.glob : undefined;
      }
    } else {
      base.project_slug = typeof args.project_slug === 'string' ? args.project_slug : undefined;
      base.task_slug = typeof args.task_slug === 'string' ? args.task_slug : undefined;
      base.path = typeof args.relative_path === 'string' ? args.relative_path : undefined;
      if (toolName === 'artifact_write_batch') base.file_count = Array.isArray(args.files) ? args.files.length : 0;
    }
    return base;
  }

  async callClientTool(toolName, args = {}, metadata = {}) {
    await this.ensureReady();
    if (!this.allowedTools.has(toolName)) fail('TOOL_NOT_ALLOWED', toolName);
    const started = Date.now();
    const base = this.auditBase(toolName, args);
    await this.appendAudit({ ...base, phase: 'START', result: 'STARTED' });
    try {
      const { value, audit = {} } = await this.execute(toolName, args, metadata);
      await this.appendAudit({ ...base, ...audit, phase: 'END', result: 'SUCCESS', elapsed_ms: Date.now() - started });
      return jsonResult(value);
    } catch (error) {
      await this.appendAudit({
        ...base,
        phase: 'END',
        result: 'ERROR',
        error_class: String(error?.code || error?.name || 'ERROR'),
        elapsed_ms: Date.now() - started,
      });
      throw error;
    }
  }

  async projectRoot(projectSlugArg) {
    const slug = safeSegment(projectSlugArg, 'project_slug');
    if (!this.admittedProjects.has(slug)) fail('PROJECT_NOT_ADMITTED', slug);
    const lexical = path.join(this.workerRoot, slug);
    const stat = await fsp.lstat(lexical);
    if (stat.isSymbolicLink() || !stat.isDirectory()) fail('PROJECT_INVALID', slug);
    const real = await fsp.realpath(lexical);
    if (!isWithin(this.workerRoot, real)) fail('PATH_ESCAPE', slug);
    return { slug, root: real };
  }

  async domainRoot(projectSlugArg, sourceDomainArg) {
    const project = await this.projectRoot(projectSlugArg);
    const domain = sourceDomain(sourceDomainArg);

    if (domain === 'ONEC') {
      return { project, domain, root: project.root };
    }

    const segment = 'Cleverence';
    const lexical = path.join(project.root, segment);
    const stat = await fsp.lstat(lexical);

    if (stat.isSymbolicLink() || !stat.isDirectory()) {
      fail('DOMAIN_NOT_INSTALLED', `${project.slug}/${domain}`);
    }

    const real = await fsp.realpath(lexical);

    if (!isWithin(project.root, real)) {
      fail('PATH_ESCAPE', segment);
    }

    return { project, domain, root: real };
  }

  async outputRoot(projectSlugArg) {
    const project = await this.projectRoot(projectSlugArg);
    const lexical = path.join(project.root, 'Output');
    const stat = await fsp.lstat(lexical);
    if (stat.isSymbolicLink() || !stat.isDirectory()) fail('OUTPUT_ROOT_INVALID', project.slug);
    const real = await fsp.realpath(lexical);
    if (!isWithin(project.root, real)) fail('PATH_ESCAPE', 'Output');
    return { project, root: real };
  }

  async taskRoot(projectSlugArg, taskSlugArg, create = false) {
    const output = await this.outputRoot(projectSlugArg);
    const taskSlug = safeSegment(taskSlugArg, 'task_slug');
    const lexical = path.join(output.root, taskSlug);
    try {
      const stat = await fsp.lstat(lexical);
      if (stat.isSymbolicLink() || !stat.isDirectory()) fail('TASK_OUTPUT_INVALID', taskSlug);
      const real = await fsp.realpath(lexical);
      if (!isWithin(output.root, real)) fail('PATH_ESCAPE', taskSlug);
      return { project: output.project, taskSlug, root: real, existed: true };
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
      if (!create) fail('TASK_OUTPUT_NOT_FOUND', taskSlug);
      await fsp.mkdir(lexical, { recursive: false });
      const real = await fsp.realpath(lexical);
      if (!isWithin(output.root, real)) fail('PATH_ESCAPE', taskSlug);
      return { project: output.project, taskSlug, root: real, existed: false };
    }
  }

  serialized(fn) {
    const run = this.writeChain.then(fn, fn);
    this.writeChain = run.catch(() => {});
    return run;
  }

  async execute(toolName, args) {
    switch (toolName) {
      case 'source_list': return this.sourceList(args);
      case 'source_read': return this.sourceRead(args);
      case 'source_search': return this.sourceSearch(args);
      case 'artifact_list': return this.artifactList(args);
      case 'artifact_read': return this.artifactRead(args);
      case 'artifact_write': return this.serialized(() => this.artifactWrite(args));
      case 'artifact_write_batch': return this.serialized(() => this.artifactWriteBatch(args));
      default: fail('TOOL_NOT_ALLOWED', toolName);
    }
  }

  async sourceList(args) {
    const domain = await this.domainRoot(args.project_slug, args.source_domain);
    const rel = relativePath(args.relative_path ?? '', 'relative_path', true);
    const depth = Number.isInteger(args.depth) ? args.depth : 1;
    if (depth < 0 || depth > this.config.limits.max_list_depth) fail('INVALID_ARGUMENT', 'depth');
    const resolved = await resolveExisting(domain.root, rel, 'directory');
    const entries = [];
    let truncated = false;
    const walk = async (dir, baseRel, remaining) => {
      const dirents = await fsp.readdir(dir, { withFileTypes: true });
      dirents.sort((a, b) => a.name.localeCompare(b.name, 'en'));
      for (const entry of dirents) {
        if (entries.length >= this.config.limits.max_list_entries) { truncated = true; return; }
        const abs = path.join(dir, entry.name);
        const childRel = baseRel ? path.join(baseRel, entry.name) : entry.name;
        const stat = await fsp.lstat(abs);
        entries.push({
          path: childRel.replaceAll('\\', '/'),
          type: stat.isSymbolicLink() ? 'reparse' : stat.isDirectory() ? 'directory' : stat.isFile() ? 'file' : 'other',
          size: stat.isFile() ? stat.size : null,
          modified_utc: stat.mtime.toISOString(),
        });
        if (stat.isDirectory() && !stat.isSymbolicLink() && remaining > 0) {
          const real = await fsp.realpath(abs);
          if (!isWithin(domain.root, real)) fail('PATH_ESCAPE', childRel);
          await walk(abs, childRel, remaining - 1);
          if (truncated) return;
        }
      }
    };
    await walk(resolved.real, rel, depth);
    return {
      value: {
        project_slug: domain.project.slug,
        source_domain: domain.domain,
        relative_path: rel.replaceAll('\\', '/'),
        depth,
        entries,
        truncated,
      },
      audit: { entry_count: entries.length, truncated },
    };
  }

  async sourceRead(args) {
    const domain = await this.domainRoot(args.project_slug, args.source_domain);
    const rel = relativePath(args.relative_path, 'relative_path', false);
    const offset = Number.isInteger(args.offset) ? args.offset : 0;
    const length = Number.isInteger(args.length) ? args.length : this.config.limits.default_read_lines;
    if (offset < 0 || length < 1 || length > this.config.limits.max_read_lines) fail('INVALID_ARGUMENT', 'offset/length');
    const resolved = await resolveExisting(domain.root, rel, 'file');
    const read = await readUtf8File(resolved.real, this.config.limits.max_source_file_bytes);
    const lines = read.text.split(/\r?\n/);
    const slice = lines.slice(offset, offset + length);
    return {
      value: {
        project_slug: domain.project.slug,
        source_domain: domain.domain,
        relative_path: rel.replaceAll('\\', '/'),
        offset,
        length: slice.length,
        total_lines: lines.length,
        size: read.size,
        sha256: read.sha256,
        complete: offset + slice.length >= lines.length,
        content: slice.join('\n'),
      },
      audit: { size: read.size, sha256: read.sha256, lines_returned: slice.length, total_lines: lines.length },
    };
  }

  async sourceSearch(args) {
    const domain = await this.domainRoot(args.project_slug, args.source_domain);
    const scopeRel = relativePath(args.relative_scope ?? '', 'relative_scope', true);
    const pattern = stringArg(args.pattern, 'pattern', { min: 1, max: this.config.limits.max_pattern_chars });
    const glob = stringArg(args.glob ?? '*', 'glob', { min: 1, max: 256 });
    const maxMatches = Number.isInteger(args.max_matches) ? args.max_matches : this.config.limits.default_search_matches;
    const before = Number.isInteger(args.before) ? args.before : 2;
    const after = Number.isInteger(args.after) ? args.after : 2;
    if (maxMatches < 1 || maxMatches > this.config.limits.max_search_matches) fail('INVALID_ARGUMENT', 'max_matches');
    if (before < 0 || after < 0 || before > this.config.limits.max_context_lines || after > this.config.limits.max_context_lines) {
      fail('INVALID_ARGUMENT', 'context');
    }
    const scope = await resolveExisting(domain.root, scopeRel, 'directory');
    const run = await spawnCollect(this.config.rg_path, [
      '--json', '-F', '--hidden', '--glob', '!.git/**', '--glob', glob, '--', pattern, scope.real,
    ], {
      cwd: scope.real,
      timeoutMs: this.config.limits.search_timeout_ms,
      maxBytes: this.config.limits.max_rg_output_bytes,
    });

    const errors = run.stderr.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).slice(0, 50);
    const matches = [];
    let summary = null;
    for (const raw of run.stdout.split(/\r?\n/)) {
      if (!raw) continue;
      let event;
      try { event = JSON.parse(raw); } catch { continue; }
      if (event?.type === 'summary') {
        summary = event.data?.stats || null;
        continue;
      }
      if (event?.type !== 'match') continue;
      if (matches.length >= maxMatches) continue;
      const filePath = event.data?.path?.text;
      const lineNumber = event.data?.line_number;
      if (typeof filePath !== 'string' || !Number.isInteger(lineNumber)) continue;
      const realFile = await fsp.realpath(filePath);
      if (!isWithin(domain.root, realFile)) fail('PATH_ESCAPE', filePath);
      await assertNoReparse(domain.root, filePath, true);
      matches.push({
        path: path.relative(domain.root, realFile).replaceAll('\\', '/'),
        line: lineNumber,
        occurrences_on_line: Array.isArray(event.data?.submatches) ? event.data.submatches.length : 1,
        context: await readWindow(realFile, lineNumber - 1, before, after, this.config.limits.max_source_file_bytes),
      });
    }

    const filesScanned = Number(summary?.searches ?? 0);
    const filesWithMatch = Number(summary?.searches_with_match ?? 0);
    const totalMatchLines = Number(summary?.matched_lines ?? 0);
    const totalMatches = Number(summary?.matches ?? 0);
    const scanComplete = (run.code === 0 || run.code === 1) && errors.length === 0 && summary !== null;
    const resultsTruncated = totalMatchLines > matches.length;
    return {
      value: {
        project_slug: domain.project.slug,
        source_domain: domain.domain,
        relative_scope: scopeRel.replaceAll('\\', '/'),
        glob,
        fixed_string: true,
        case_sensitive: true,
        files_scanned: filesScanned,
        files_with_match: filesWithMatch,
        total_match_lines: totalMatchLines,
        total_matches: totalMatches,
        matches_returned: matches.length,
        scan_complete: scanComplete,
        results_truncated: resultsTruncated,
        complete: scanComplete && !resultsTruncated,
        errors,
        matches,
      },
      audit: {
        files_scanned: filesScanned,
        files_with_match: filesWithMatch,
        total_match_lines: totalMatchLines,
        total_matches: totalMatches,
        matches_returned: matches.length,
        scan_complete: scanComplete,
        results_truncated: resultsTruncated,
        error_count: errors.length,
        rg_exit: run.code,
      },
    };
  }

  async artifactList(args) {
    const task = await this.taskRoot(args.project_slug, args.task_slug, false);
    const rel = relativePath(args.relative_path ?? '', 'relative_path', true);
    const depth = Number.isInteger(args.depth) ? args.depth : 1;
    if (depth < 0 || depth > this.config.limits.max_list_depth) fail('INVALID_ARGUMENT', 'depth');
    const resolved = await resolveExisting(task.root, rel, 'directory');
    const entries = [];
    let truncated = false;
    const walk = async (dir, baseRel, remaining) => {
      const dirents = await fsp.readdir(dir, { withFileTypes: true });
      dirents.sort((a, b) => a.name.localeCompare(b.name, 'en'));
      for (const entry of dirents) {
        if (entries.length >= this.config.limits.max_list_entries) { truncated = true; return; }
        const abs = path.join(dir, entry.name);
        const childRel = baseRel ? path.join(baseRel, entry.name) : entry.name;
        const stat = await fsp.lstat(abs);
        entries.push({
          path: childRel.replaceAll('\\', '/'),
          type: stat.isSymbolicLink() ? 'reparse' : stat.isDirectory() ? 'directory' : stat.isFile() ? 'file' : 'other',
          size: stat.isFile() ? stat.size : null,
          modified_utc: stat.mtime.toISOString(),
        });
        if (stat.isDirectory() && !stat.isSymbolicLink() && remaining > 0) {
          const real = await fsp.realpath(abs);
          if (!isWithin(task.root, real)) fail('PATH_ESCAPE', childRel);
          await walk(abs, childRel, remaining - 1);
          if (truncated) return;
        }
      }
    };
    await walk(resolved.real, rel, depth);
    return {
      value: {
        project_slug: task.project.slug,
        task_slug: task.taskSlug,
        relative_path: rel.replaceAll('\\', '/'),
        depth,
        entries,
        truncated,
      },
      audit: { entry_count: entries.length, truncated },
    };
  }

  async artifactRead(args) {
    const task = await this.taskRoot(args.project_slug, args.task_slug, false);
    const rel = relativePath(args.relative_path, 'relative_path', false);
    const encoding = args.encoding ?? 'base64';
    if (encoding !== 'utf8' && encoding !== 'base64') fail('INVALID_ARGUMENT', 'encoding');
    const resolved = await resolveExisting(task.root, rel, 'file');
    if (resolved.stat.size > this.config.limits.max_artifact_read_bytes) {
      fail('FILE_TOO_LARGE', `${resolved.stat.size} > ${this.config.limits.max_artifact_read_bytes}`);
    }
    const buffer = await fsp.readFile(resolved.real);
    let content;
    if (encoding === 'base64') {
      content = buffer.toString('base64');
    } else {
      try { content = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
      catch { fail('INVALID_UTF8', rel); }
      if (content.charCodeAt(0) === 0xFEFF) content = content.slice(1);
    }
    const hash = sha256(buffer);
    return {
      value: {
        project_slug: task.project.slug,
        task_slug: task.taskSlug,
        relative_path: rel.replaceAll('\\', '/'),
        encoding,
        size: buffer.length,
        sha256: hash,
        content,
      },
      audit: { size: buffer.length, sha256: hash },
    };
  }

  decodeContent(args) {
    const encoding = args.encoding ?? 'utf8';
    if (encoding !== 'utf8' && encoding !== 'base64') fail('INVALID_ARGUMENT', 'encoding');
    const content = stringArg(args.content, 'content', { min: 0, max: this.config.limits.max_encoded_content_chars });
    let buffer;
    if (encoding === 'utf8') {
      buffer = Buffer.from(content, 'utf8');
    } else {
      if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(content)) {
        fail('INVALID_BASE64', 'content');
      }
      buffer = Buffer.from(content, 'base64');
    }
    if (buffer.length > this.config.limits.max_artifact_file_bytes) {
      fail('PAYLOAD_TOO_LARGE', `${buffer.length} > ${this.config.limits.max_artifact_file_bytes}`);
    }
    return { encoding, buffer };
  }

  async planWrite(task, args, decoded = null) {
    const rel = relativePath(args.relative_path, 'relative_path', false);
    const content = decoded || this.decodeContent(args);
    const target = path.resolve(task.root, rel);
    if (!isWithin(task.root, target)) fail('PATH_ESCAPE', rel);
    await assertExistingAncestor(task.root, target);
    await assertNoReparse(task.root, target, false);

    const replace = args.replace === true;
    const expected = args.expected_sha256;
    if (expected !== undefined && (typeof expected !== 'string' || !/^[A-Fa-f0-9]{64}$/.test(expected))) {
      fail('INVALID_ARGUMENT', 'expected_sha256');
    }

    let exists = false;
    let currentHash = null;
    try {
      const stat = await fsp.lstat(target);
      if (stat.isSymbolicLink()) fail('REPARSE_POINT', rel);
      if (!stat.isFile()) fail('NOT_A_FILE', rel);
      exists = true;
      currentHash = await hashFile(target);
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
    }

    if (exists) {
      if (!replace) fail('FILE_EXISTS', rel);
      if (!expected) fail('EXPECTED_SHA256_REQUIRED', rel);
      if (currentHash.toLowerCase() !== expected.toLowerCase()) fail('FILE_CHANGED', rel);
    } else if (replace) {
      fail('FILE_NOT_FOUND', rel);
    }

    return {
      task,
      rel,
      target,
      buffer: content.buffer,
      replace,
      expected: expected?.toLowerCase() ?? null,
      newHash: sha256(content.buffer),
    };
  }

  async commitPlan(plan) {
    const parent = path.dirname(plan.target);
    await fsp.mkdir(parent, { recursive: true });
    await assertNoReparse(plan.task.root, parent, true);
    const parentReal = await fsp.realpath(parent);
    if (!isWithin(plan.task.root, parentReal)) fail('PATH_ESCAPE', plan.rel);

    if (!plan.replace) {
      await createExact(plan.target, plan.buffer);
    } else {
      const before = await hashFile(plan.target);
      if (before.toLowerCase() !== plan.expected) fail('FILE_CHANGED', plan.rel);
      const temp = await createTemp(parent, plan.buffer);
      try {
        const again = await hashFile(plan.target);
        if (again.toLowerCase() !== plan.expected) fail('FILE_CHANGED', plan.rel);
        await fsp.rename(temp, plan.target);
      } finally {
        await fsp.unlink(temp).catch(() => {});
      }
    }

    const finalStat = await fsp.stat(plan.target);
    const finalHash = await hashFile(plan.target);
    if (finalHash !== plan.newHash) fail('WRITE_VERIFY_FAILED', plan.rel);
    return {
      project_slug: plan.task.project.slug,
      task_slug: plan.task.taskSlug,
      relative_path: plan.rel.replaceAll('\\', '/'),
      size: finalStat.size,
      sha256: finalHash,
      replaced: plan.replace,
    };
  }

  async artifactWrite(args) {
    safeSegment(args.project_slug, 'project_slug');
    safeSegment(args.task_slug, 'task_slug');
    relativePath(args.relative_path, 'relative_path', false);
    const decoded = this.decodeContent(args);
    const task = await this.taskRoot(args.project_slug, args.task_slug, args.replace !== true);
    const result = await this.commitPlan(await this.planWrite(task, args, decoded));
    return { value: result, audit: { path: result.relative_path, size: result.size, sha256: result.sha256, replaced: result.replaced } };
  }

  async artifactWriteBatch(args) {
    const projectSlug = safeSegment(args.project_slug, 'project_slug');
    const taskSlug = safeSegment(args.task_slug, 'task_slug');
    if (!Array.isArray(args.files) || args.files.length < 1 || args.files.length > this.config.limits.max_batch_files) {
      fail('INVALID_ARGUMENT', 'files');
    }

    const prepared = [];
    const seen = new Set();
    let totalBytes = 0;
    let needsExistingTask = false;
    for (const file of args.files) {
      const rel = relativePath(file.relative_path, 'relative_path', false);
      const key = rel.toLowerCase();
      if (seen.has(key)) fail('DUPLICATE_TARGET', rel);
      seen.add(key);
      const decoded = this.decodeContent(file);
      totalBytes += decoded.buffer.length;
      if (totalBytes > this.config.limits.max_batch_total_bytes) fail('PAYLOAD_TOO_LARGE', 'batch total');
      if (file.replace === true) needsExistingTask = true;
      prepared.push({ file, rel, decoded });
    }

    const task = await this.taskRoot(projectSlug, taskSlug, !needsExistingTask);
    const plans = [];
    for (const item of prepared) plans.push(await this.planWrite(task, item.file, item.decoded));

    // Revalidate every target before the first commit.
    for (const plan of plans) {
      if (plan.replace) {
        const current = await hashFile(plan.target);
        if (current.toLowerCase() !== plan.expected) fail('FILE_CHANGED', plan.rel);
      } else {
        try {
          await fsp.lstat(plan.target);
          fail('FILE_EXISTS', plan.rel);
        } catch (error) {
          if (error instanceof ProviderError) throw error;
          if (error?.code !== 'ENOENT') throw error;
        }
      }
    }

    const results = [];
    for (const plan of plans) results.push(await this.commitPlan(plan));
    const bytes = results.reduce((sum, item) => sum + item.size, 0);
    return {
      value: { project_slug: projectSlug, task_slug: taskSlug, total_files: results.length, total_bytes: bytes, files: results },
      audit: {
        file_count: results.length,
        total_bytes: bytes,
        hashes: results.map((item) => ({ path: item.relative_path, size: item.size, sha256: item.sha256 })),
      },
    };
  }
}

const projectSlug = { type: 'string', pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' };
const taskSlug = { type: 'string', pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' };
const sourceDomainSchema = { type: 'string', enum: ['ONEC', 'CLEVERENCE'] };
const meta = (capability) => ({
  'onecchatworker/contract': CONTRACT_ID,
  'onecchatworker/contract_version': CONTRACT_VERSION,
  'onecchatworker/provider_version': PROVIDER_VERSION,
  'onecchatworker/capability': capability,
});

export const TOOL_DEFINITIONS = [
  {
    name: 'source_list',
    description: 'OneCChatWorker 1.0 SOURCE_ACCESS: bounded metadata list under one admitted project and source domain.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'source_domain'],
      properties: { project_slug: projectSlug, source_domain: sourceDomainSchema, relative_path: { type: 'string', default: '' }, depth: { type: 'integer', minimum: 0, maximum: 4, default: 1 } },
    },
    annotations: { title: 'Source List', readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: meta('SOURCE_ACCESS'),
  },
  {
    name: 'source_read',
    description: 'OneCChatWorker 1.0 SOURCE_ACCESS: bounded UTF-8 line read under one admitted project and source domain.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'source_domain', 'relative_path'],
      properties: { project_slug: projectSlug, source_domain: sourceDomainSchema, relative_path: { type: 'string', minLength: 1 }, offset: { type: 'integer', minimum: 0, default: 0 }, length: { type: 'integer', minimum: 1, maximum: 400, default: 120 } },
    },
    annotations: { title: 'Source Read', readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: meta('SOURCE_ACCESS'),
  },
  {
    name: 'source_search',
    description: 'OneCChatWorker 1.0 SOURCE_ACCESS: literal fixed-string search with bounded context and completeness metadata.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'source_domain', 'pattern'],
      properties: {
        project_slug: projectSlug, source_domain: sourceDomainSchema, relative_scope: { type: 'string', default: '' }, pattern: { type: 'string', minLength: 1, maxLength: 512 }, glob: { type: 'string', minLength: 1, maxLength: 256, default: '*' }, max_matches: { type: 'integer', minimum: 1, maximum: 100, default: 20 }, before: { type: 'integer', minimum: 0, maximum: 20, default: 2 }, after: { type: 'integer', minimum: 0, maximum: 20, default: 2 },
      },
    },
    annotations: { title: 'Source Search', readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: meta('SOURCE_ACCESS'),
  },
  {
    name: 'artifact_list',
    description: 'OneCChatWorker 1.0 ARTIFACT_DELIVERY: bounded metadata list under one project/task Output namespace.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'task_slug'],
      properties: { project_slug: projectSlug, task_slug: taskSlug, relative_path: { type: 'string', default: '' }, depth: { type: 'integer', minimum: 0, maximum: 4, default: 1 } },
    },
    annotations: { title: 'Artifact List', readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: meta('ARTIFACT_DELIVERY'),
  },
  {
    name: 'artifact_read',
    description: 'OneCChatWorker 1.0 ARTIFACT_DELIVERY: bounded artifact read under one project/task Output namespace.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'task_slug', 'relative_path'],
      properties: { project_slug: projectSlug, task_slug: taskSlug, relative_path: { type: 'string', minLength: 1 }, encoding: { type: 'string', enum: ['utf8', 'base64'], default: 'base64' } },
    },
    annotations: { title: 'Artifact Read', readOnlyHint: true, destructiveHint: false, openWorldHint: false },
    _meta: meta('ARTIFACT_DELIVERY'),
  },
  {
    name: 'artifact_write',
    description: 'OneCChatWorker 1.0 ARTIFACT_DELIVERY: create or expected-SHA256 CAS-replace one Output artifact; no delete.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'task_slug', 'relative_path', 'content'],
      properties: { project_slug: projectSlug, task_slug: taskSlug, relative_path: { type: 'string', minLength: 1 }, content: { type: 'string' }, encoding: { type: 'string', enum: ['utf8', 'base64'], default: 'utf8' }, replace: { type: 'boolean', default: false }, expected_sha256: { type: 'string', pattern: '^[A-Fa-f0-9]{64}$' } },
    },
    annotations: { title: 'Artifact Write', readOnlyHint: false, destructiveHint: false, openWorldHint: false },
    _meta: meta('ARTIFACT_DELIVERY'),
  },
  {
    name: 'artifact_write_batch',
    description: 'OneCChatWorker 1.0 ARTIFACT_DELIVERY: validate then write a bounded multi-file batch inside one project/task Output namespace.',
    inputSchema: {
      type: 'object', additionalProperties: false, required: ['project_slug', 'task_slug', 'files'],
      properties: {
        project_slug: projectSlug, task_slug: taskSlug,
        files: { type: 'array', minItems: 1, maxItems: 16, items: { type: 'object', additionalProperties: false, required: ['relative_path', 'content'], properties: { relative_path: { type: 'string', minLength: 1 }, content: { type: 'string' }, encoding: { type: 'string', enum: ['utf8', 'base64'], default: 'utf8' }, replace: { type: 'boolean', default: false }, expected_sha256: { type: 'string', pattern: '^[A-Fa-f0-9]{64}$' } } } },
      },
    },
    annotations: { title: 'Artifact Write Batch', readOnlyHint: false, destructiveHint: false, openWorldHint: false },
    _meta: meta('ARTIFACT_DELIVERY'),
  },
];
