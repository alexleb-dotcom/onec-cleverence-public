#!/usr/bin/env python3
"""Run transport and adjacent S4/helper regressions without a live helper."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
if not NODE:
    raise SystemExit("FAIL: Node is required for relay/helper transport regressions")
rows = []
tests = (
    "relay-helper-lifecycle-regression.mjs",
    "relay-ws-response-retry-regression.mjs",
    "relay-ws-telemetry-regression.mjs",
    "helper-state-race-regression.mjs",
    "helper-persistence-regression.mjs",
    "s4-accounting-regression.mjs",
    "task-checkpoint-regression.mjs",
    "https-pull-security-regression.mjs",
)
with tempfile.TemporaryDirectory(prefix="onec-transport-tests-") as scratch:
    scratch_path = Path(scratch).resolve()
    assert scratch_path.parent == Path(tempfile.gettempdir()).resolve()
    env = {**os.environ, "ONEC_TEST_SCRATCH_ROOT": str(scratch_path / "checkpoint")}
    for name in tests:
        command = [NODE, str(ROOT / "PRODUCT/OneCChatWorker/tests" / name)]
        if name == "helper-state-race-regression.mjs":
            command.append(str(scratch_path / "helper"))
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding="utf-8", timeout=90)
        rows.append({"test": name, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            print(json.dumps({"result": "FAIL", "checks": rows}, indent=2))
            raise SystemExit(1)
print(json.dumps({"result": "PASS", "checks": rows}, indent=2))
