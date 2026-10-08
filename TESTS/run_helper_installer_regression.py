"""Installer import closure plus isolated Windows PS5.1 owner execution.

No live install, helper execution, account creation or production access.
Linux CI checks the exact copy/lock/integrity/ACL plans and links staged imports;
Windows additionally executes the real installer and Windows file ACL functions.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / 'PRODUCT/OneCChatWorker'
core = (PRODUCT / 'core/OneCChatWorker.Core.psm1').read_text(encoding='utf-8')
lock = json.loads((PRODUCT / 'runtime.lock.json').read_text(encoding='utf-8'))
node = shutil.which('node')
assert node, 'Node is required for actual static module linking'


def section(name):
    body = core.split('function ' + name + ' {', 1)[1]
    return body.split('\nfunction ', 1)[0]


copies = re.findall(
    r"Copy-ProductComponent -Source \(Join-Path \$PackageRoot '([^']+)'\) "
    r"-Destination \(Join-Path \$(ProgramDataRoot|WorkerRoot) '([^']+)'\) "
    r"-ExpectedSha256 \(\[string\]\$lock.components.'([^']+)'\)",
    section('Install-OneCChatWorker'))
plan = {rel: (source.replace('\\', '/'), destination.replace('\\', '/'))
        for source, owner, destination, rel in copies if owner == 'ProgramDataRoot'}
integrity = dict(re.findall(r"'([^']+)'=\(Join-Path \$ProgramDataRoot '([^']+)'\)",
                            section('Test-InstalledProductIntegrity')))
acl = set(re.findall(r"Protect-WorkerRuntimeFile -Path \(Join-Path \$ProgramDataRoot '([^']+)'\) -Identity \$identity",
                     section('Set-WorkerOperatorAcl')))
installed_sources = {dest: rel for rel, (source, dest) in plan.items()}
closure = set()


def visit(destination):
    if destination in closure:
        return
    assert destination in installed_sources, 'missing installed static dependency: ' + destination
    closure.add(destination)
    rel = installed_sources[destination]
    source, dest = plan[rel]
    assert source == rel and integrity.get(rel, '').replace('\\', '/') == dest, rel
    data = (PRODUCT / source).read_bytes()
    assert hashlib.sha256(data).hexdigest() == lock['components'][rel], rel
    imports = re.findall(r"\b(?:import|export)\s+(?:[^;]*?\sfrom\s*)?['\"]([^'\"]+)['\"]", data.decode())
    for specifier in imports:
        if specifier.startswith('node:'):
            continue
        assert specifier.startswith('.'), specifier
        import posixpath
        visit(posixpath.normpath(posixpath.join(posixpath.dirname(destination), specifier)))


visit('helper/hosted-helper.mjs')
for rel in ('runtime/helper-https-pull.mjs', 'runtime/https-pull-auth.mjs', 'runtime/task-checkpoint-store.mjs'):
    assert rel in plan and plan[rel][1] in closure, rel
    assert plan[rel][1].replace('/', '\\') in acl, rel
launcher = (PRODUCT / 'OneCChatWorker.ps1').read_text(encoding='utf-8')
for start, end in (('function Run-Install {', 'function Run-Update {'), ('function Run-Update {', '\nfunction ')):
    body = launcher.split(start, 1)[1].split(end, 1)[0]
    assert 'Install-OneCChatWorker -PackageRoot $PackageRoot' in body

with tempfile.TemporaryDirectory(prefix='onec-installer-imports-') as scratch:
    target = Path(scratch)
    for phase in ('clean-install', 'update'):
        if phase == 'update':
            (target / 'helper/helper-https-pull.mjs').unlink()
            (target / 'helper/https-pull-auth.mjs').write_bytes(b'old installation bytes')
        for destination in closure:
            source = plan[installed_sources[destination]][0]
            output = target / destination
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PRODUCT / source, output)
            assert hashlib.sha256(output.read_bytes()).hexdigest() == lock['components'][source]
        subprocess.run([node, '--experimental-vm-modules', str(PRODUCT / 'tests/helper-import-link.mjs'), str(target)], check=True, timeout=30)
        print('PASS SHA-pinned installer copy plan and actual module linking: ' + phase)

if os.name == 'nt':
    powershell = shutil.which('powershell.exe')
    assert powershell, 'Windows PS5.1 is required'
    subprocess.run([powershell, '-NoProfile', '-File', str(PRODUCT / 'tests/run_helper_installer_regression.ps1'),
                    '-PackageRoot', str(PRODUCT)], check=True, timeout=120)
    windows = 'PASS'
else:
    pwsh = shutil.which('pwsh')
    assert pwsh, 'PowerShell is required for executing actual launcher bootstrap'
    with tempfile.TemporaryDirectory(prefix='onec-installer-bootstrap-') as scratch:
        subprocess.run([pwsh, '-NoProfile', '-File', str(PRODUCT / 'tests/run_package_core_bootstrap_regression.ps1'),
                        '-PackageRoot', str(PRODUCT), '-FixtureRoot', scratch], check=True, timeout=90)
    windows = 'WINDOWS_ONLY; Linux executed launcher bootstrap and actual Node linking'
print(json.dumps({'result': 'PASS', 'static_imports': sorted(closure), 'windows_owner_execution': windows,
                  'production': 'UNTOUCHED'}))
