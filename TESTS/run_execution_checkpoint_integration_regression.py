#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "TOOLS/execution_checkpoint.py"
sys.path.insert(0, str(ROOT / "TOOLS"))
from execution_checkpoint import (  # noqa: E402
    EXECUTION_EVIDENCE_SCOPE,
    _atomic_write_json,
    build_spec,
    fingerprint_environment,
    operation_dir,
    process_start_token,
    register,
)

results = []


def record(case_id: str, passed: bool, details=None):
    results.append({"id": case_id, "result": "PASS" if passed else "FAIL", "details": details})


def cli_args(state_root: Path, source_file: Path, cwd: Path, stage: str, check: str, code: str, *, wait=0.0, expected=None):
    args = [
        sys.executable, str(CHECKPOINT), "run",
        "--state-root", str(state_root),
        "--stage-id", stage,
        "--check-id", check,
        "--cwd", str(cwd),
        "--source-identity", str(source_file),
        "--env-name", "EXECUTION_CHECKPOINT_TEST_SECRET",
        "--wait-seconds", str(wait),
    ]
    for item in expected or []:
        args += ["--expected-output", item]
    return args + ["--", sys.executable, "-c", code]


def recover_args(run_args: list[str]):
    args = list(run_args)
    args[args.index("run")] = "recover"
    i = args.index("--wait-seconds")
    del args[i:i+2]
    return args


def call(args, *, env=None):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    payload = json.loads(p.stdout.strip() or "{}")
    return p.returncode, payload, p.stderr


def wait_recover(args, timeout=4.0, env=None):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        rc, last, _ = call(args, env=env)
        if last.get("state") in {"PASSED", "FAILED", "LOST_PROCESS", "STALE_IDENTITY"}:
            return rc, last
        time.sleep(0.03)
    return rc, last


def counter_code(sleep=0.0, exit_code=0, output=False):
    return (
        "from pathlib import Path; import time,sys; "
        "p=Path('counter.txt'); n=int(p.read_text() or '0') if p.exists() else 0; p.write_text(str(n+1)); "
        + (f"time.sleep({sleep}); " if sleep else "")
        + ("Path('result.json').write_text('{\\\"ok\\\":true}'); " if output else "")
        + f"sys.exit({exit_code})"
    )


def counter(cwd: Path) -> int:
    p = cwd / "counter.txt"
    return int(p.read_text()) if p.exists() else 0


with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    state_root = base / "state"
    source_file = base / "snapshot-identity.json"
    source = {"kind": "SNAPSHOT", "archive_sha256": "a" * 64, "snapshot_digest": "d" * 64}
    source_file.write_text(json.dumps(source), encoding="utf-8")
    env = os.environ.copy()
    env["EXECUTION_CHECKPOINT_TEST_SECRET"] = "secret-value-must-not-be-persisted"

    # A: caller loses the launch response. A second caller recovers the live detached operation.
    cwd = base / "lost-launch"; cwd.mkdir()
    run = cli_args(state_root, source_file, cwd, "P3b2a", "lost-launch", counter_code(sleep=0.45, output=True), expected=["result.json"])
    subprocess.run(run, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    rec = recover_args(run)
    rc, recovered, _ = call(rec, env=env)
    record("integration:lost_launch_response_recovers_existing_operation", rc == 0 and recovered.get("state") in {"RUNNING", "PASSED"}, recovered)
    _, terminal = wait_recover(rec, env=env)
    record("integration:lost_launch_response_finishes_original_process", terminal.get("state") == "PASSED" and counter(cwd) == 1, {"terminal": terminal, "counter": counter(cwd)})

    # C: repeated exact caller after completion must not rerun the target.
    rc, repeated, _ = call(run, env=env)
    record("integration:repeated_identical_caller_does_not_rerun", rc == 0 and repeated.get("state") == "PASSED" and counter(cwd) == 1, {"state": repeated, "counter": counter(cwd)})

    # B: completion response can be discarded; recovery reads persisted terminal RC/report.
    cwd2 = base / "lost-completion"; cwd2.mkdir()
    run2 = cli_args(state_root, source_file, cwd2, "P3b2a", "lost-completion", counter_code(output=True), wait=3.0, expected=["result.json"])
    subprocess.run(run2, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    rc, terminal2, _ = call(recover_args(run2), env=env)
    record("integration:lost_completion_response_reads_terminal_state", rc == 0 and terminal2.get("state") == "PASSED" and terminal2.get("exit_code") == 0 and counter(cwd2) == 1, terminal2)

    # D1: same stage/check/attempt with a different command is stale, not a new operation.
    changed_command = cli_args(state_root, source_file, cwd2, "P3b2a", "lost-completion", "print('different')", wait=0.0)
    rc, stale_command, _ = call(changed_command, env=env)
    record("integration:changed_command_same_slot_is_stale", rc == 3 and stale_command.get("state") == "STALE_IDENTITY" and counter(cwd2) == 1, stale_command)

    # D2: same slot with a different snapshot identity is stale.
    changed_source = base / "snapshot-identity-changed.json"
    changed_source.write_text(json.dumps({"kind":"SNAPSHOT","archive_sha256":"b"*64,"snapshot_digest":"e"*64}), encoding="utf-8")
    changed_identity_args = list(run2)
    changed_identity_args[changed_identity_args.index(str(source_file))] = str(changed_source)
    rc, stale_identity, _ = call(changed_identity_args, env=env)
    record("integration:changed_snapshot_identity_same_slot_is_stale", rc == 3 and stale_identity.get("state") == "STALE_IDENTITY" and counter(cwd2) == 1, stale_identity)

    # E: dead/mismatched process without RC is LOST_PROCESS and cannot trigger an implicit rerun.
    cwd3 = base / "lost-process"; cwd3.mkdir()
    source_identity = json.loads(source_file.read_text(encoding="utf-8"))
    spec = build_spec(
        stage_id="P3b2a", check_id="lost-process",
        command_argv=[sys.executable, "-c", counter_code()], cwd=cwd3,
        source_identity=source_identity,
        environment_fingerprint=fingerprint_environment(["EXECUTION_CHECKPOINT_TEST_SECRET"], env),
    )
    op, manifest = register(state_root, spec)
    # Register binds the exact stage/check/attempt without spawning a child. Convert the
    # persisted NEVER_STARTED manifest into a deterministic dead-process/no-RC state.
    lost_args = cli_args(state_root, source_file, cwd3, "P3b2a", "lost-process", counter_code(), wait=0.0)
    manifest["state"] = "RUNNING"; manifest["exit_code"] = None; manifest["reason"] = "TEST_DEAD_PROCESS"
    manifest["child"] = {"pid": 99999998, "start_token": "linux:missing:2"}
    manifest["supervisor"] = {"pid": 99999999, "start_token": "linux:missing:1"}
    _atomic_write_json(op / "operation.json", manifest)
    rc, lost, _ = call(recover_args(lost_args), env=env)
    before = counter(cwd3)
    rc2, lost_again, _ = call(lost_args, env=env)
    record("integration:lost_process_is_fail_closed_without_rerun", rc == 3 and rc2 == 3 and lost.get("state") == "LOST_PROCESS" and lost_again.get("state") == "LOST_PROCESS" and counter(cwd3) == before, {"recover": lost, "run_again": lost_again, "counter": counter(cwd3)})

    # Public-safe boundary: environment values and runtime state are outside the tracked source tree.
    operation_manifest = Path(terminal2["operation_dir"]) / "operation.json"
    manifest_text = operation_manifest.read_text(encoding="utf-8")
    record("integration:environment_secret_value_not_persisted", "secret-value-must-not-be-persisted" not in manifest_text, {"manifest": str(operation_manifest)})
    record("integration:runtime_state_root_is_outside_tracked_source", not str(operation_manifest).startswith(str(ROOT.resolve())), {"operation_manifest": str(operation_manifest), "source_root": str(ROOT.resolve())})
    record("integration:execution_result_is_not_semantic_proof", terminal2.get("execution_evidence_scope") == EXECUTION_EVIDENCE_SCOPE and terminal2.get("semantic_proof_granted") is False, terminal2)

failed = [row for row in results if row["result"] != "PASS"]
report = {"status": "PASS" if not failed else "FAIL", "passed": len(results)-len(failed), "total": len(results), "cases": results}
print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
raise SystemExit(0 if not failed else 2)
