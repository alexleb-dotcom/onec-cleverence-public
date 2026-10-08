"""Use native workerd and SQLite in an isolated disposable test environment.

Network fixtures and installed test packages stay outside SHAREABLE_CORE.
This never connects to production, a Windows helper, or a Source provider.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
NPM = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
RG = shutil.which('rg')
if not NODE or not NPM or not RG:
    missing = [name for name, command in (('node', NODE), ('npm', NPM), ('ripgrep', RG)) if not command]
    raise SystemExit('FAIL: native workerd test dependencies missing: ' + ', '.join(missing))
with tempfile.TemporaryDirectory(prefix='onec-pull-native-') as scratch:
    target = Path(scratch)
    fixtures = ROOT / 'PRODUCT/OneCChatWorker/tests/native'
    for name in ('package.json', 'package-lock.json', 'regression.mjs'):
        shutil.copyfile(fixtures / name, target / name)
    install = subprocess.run([NPM, 'ci', '--no-audit', '--no-fund'], cwd=target,
                             capture_output=True, text=True, timeout=180)
    if install.returncode:
        print(install.stdout, install.stderr)
        raise SystemExit(install.returncode)
    result = subprocess.run([NODE, '--expose-gc', str(target / 'regression.mjs'), str(ROOT), RG],
                            cwd=target, timeout=600)
    raise SystemExit(result.returncode)
