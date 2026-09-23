#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from execution_checkpoint import (  # noqa: E402
    EXECUTION_EVIDENCE_SCOPE,
    _atomic_write_json,
    build_spec,
    fingerprint_environment,
    launch,
    operation_dir,
    process_start_token,
    recover,
    wait_for_terminal,
)

results = []


def record(case_id: str, passed: bool, details=None):
    results.append({"id": case_id, "result": "PASS" if passed else "FAIL", "details": details})


def source_identity(head="h" * 40, tree="t" * 40):
    return {
        "kind": "PR_SOURCE",
        "repository": "example/repo",
        "base_sha": "b" * 40,
        "head_sha": head,
        "tree_sha": tree,
        "verified_local_tree": tree,
    }


def spec_for(cwd: Path, code: str, *, stage="P3b1", check="checkpoint", outputs=None, head="h" * 40, tree="t" * 40):
    return build_spec(
        stage_id=stage,
        check_id=check,
        command_argv=[sys.executable, "-c", code],
        cwd=cwd,
        source_identity=source_identity(head=head, tree=tree),
        environment_fingerprint=fingerprint_environment(["PATH", "PYTHONPATH"]),
        expected_outputs=outputs or [],
        report_path="report.json",
    )


def counter_code(exit_code=0, sleep_seconds=0.0, output=False):
    return (
        "from pathlib import Path; import time,sys; "
        "p=Path('counter.txt'); n=int(p.read_text() or '0') if p.exists() else 0; p.write_text(str(n+1)); "
        + (f"time.sleep({sleep_seconds}); " if sleep_seconds else "")
        + ("Path('out.txt').write_text('payload'); Path('report.json').write_text('{\\\"ok\\\":true}'); " if output else "")
        + f"sys.exit({exit_code})"
    )


def counter(cwd: Path) -> int:
    p = cwd / "counter.txt"
    return int(p.read_text()) if p.exists() else 0


with tempfile.TemporaryDirectory() as td:
    base = Path(td)

    # 1-3: fresh launch, duplicate caller while RUNNING, and lost launch response recovery.
    cwd = base / "running"; cwd.mkdir()
    state_root = base / "state-running"
    spec = spec_for(cwd, counter_code(sleep_seconds=0.6, output=True), outputs=["out.txt", "report.json"])
    first = launch(state_root, spec)
    op = operation_dir(state_root, spec)
    second = launch(state_root, spec)
    record("execution:fresh_operation_launches_once", first.get("state") in {"RUNNING", "PASSED"}, first)
    record("execution:second_caller_reuses_running_operation", second.get("operation_id") == spec["operation_id"] and counter(cwd) <= 1, second)
    lost_response_recovery = recover(op, spec)
    record("execution:lost_launch_response_recovers_existing_operation", lost_response_recovery.get("state") in {"RUNNING", "PASSED"}, lost_response_recovery)
    terminal = wait_for_terminal(op, spec)
    record("execution:expected_output_hashes_captured", terminal.get("state") == "PASSED" and all(row.get("sha256") for row in terminal.get("observed_outputs") or []), terminal.get("observed_outputs"))

    # 4-5: completion response lost / PASSED requested again must not rerun.
    before = counter(cwd)
    recovered_terminal = recover(op, spec)
    again = launch(state_root, spec)
    record("execution:completion_response_lost_reads_terminal_rc", recovered_terminal.get("state") == "PASSED" and recovered_terminal.get("exit_code") == 0, recovered_terminal)
    record("execution:passed_requested_again_does_not_rerun", again.get("state") == "PASSED" and counter(cwd) == before == 1, {"state": again.get("state"), "counter": counter(cwd)})

    # 6: FAILED is terminal and not retried automatically.
    fail_cwd = base / "failed"; fail_cwd.mkdir()
    fail_root = base / "state-failed"
    fail_spec = spec_for(fail_cwd, counter_code(exit_code=7), check="failed")
    fail_first = launch(fail_root, fail_spec)
    fail_op = operation_dir(fail_root, fail_spec)
    fail_terminal = wait_for_terminal(fail_op, fail_spec)
    fail_again = launch(fail_root, fail_spec)
    record("execution:failed_requested_again_does_not_rerun", fail_terminal.get("state") == "FAILED" and fail_terminal.get("exit_code") == 7 and fail_again.get("state") == "FAILED" and counter(fail_cwd) == 1, {"terminal": fail_terminal, "counter": counter(fail_cwd)})

    # 7-10: exact spec identity mismatch is stale, not a new interpretation of the old checkpoint.
    for case_id, mutate in [
        ("execution:changed_command_is_stale", lambda s: s.update({"command_argv": [sys.executable, "-c", "print('different')"], "command_fingerprint": "0" * 64, "operation_id": "1" * 64})),
        ("execution:changed_cwd_is_stale", lambda s: s.update({"cwd": str((base / 'other').resolve()), "operation_id": "2" * 64})),
        ("execution:changed_source_identity_is_stale", lambda s: s.update({"source_identity": source_identity(head="x" * 40, tree="y" * 40), "source_fingerprint": "3" * 64, "operation_id": "3" * 64})),
        ("execution:changed_stage_check_is_stale", lambda s: s.update({"stage_id": "P3b2", "check_id": "other", "operation_id": "4" * 64})),
    ]:
        changed = copy.deepcopy(spec); mutate(changed)
        stale = recover(op, changed)
        record(case_id, stale.get("state") == "STALE_IDENTITY", stale)

    # 11: dead PID with no RC => LOST_PROCESS.
    dead_cwd = base / "dead"; dead_cwd.mkdir()
    dead_root = base / "state-dead"
    dead_spec = spec_for(dead_cwd, counter_code(), check="dead")
    dead_op = operation_dir(dead_root, dead_spec); dead_op.mkdir(parents=True)
    dead_manifest = {
        "schema_version": 1, "operation_id": dead_spec["operation_id"], "attempt_index": 1,
        "stage_id": dead_spec["stage_id"], "check_id": dead_spec["check_id"], "state": "RUNNING", "reason": "TEST",
        "timestamps": {"registered_at":"x","started_at":"x","completed_at":None,"reconciled_at":None},
        "command_argv": dead_spec["command_argv"], "command_fingerprint": dead_spec["command_fingerprint"], "cwd": dead_spec["cwd"],
        "environment_fingerprint": dead_spec["environment_fingerprint"], "source_identity": dead_spec["source_identity"], "source_fingerprint": dead_spec["source_fingerprint"],
        "supervisor": {"pid": 99999999, "start_token": "linux:missing:1"}, "child": {"pid": 99999998, "start_token": "linux:missing:2"},
        "expected_outputs": [], "observed_outputs": [], "stdout_path": str(dead_op/'stdout.log'), "stderr_path": str(dead_op/'stderr.log'),
        "full_log_path": str(dead_op/'full.log'), "rc_path": str(dead_op/'rc.txt'), "report_path":"report.json", "exit_code":None,
        "execution_evidence_scope": EXECUTION_EVIDENCE_SCOPE, "semantic_proof_granted":False,
    }
    _atomic_write_json(dead_op / "operation.json", dead_manifest)
    dead_result = recover(dead_op, dead_spec)
    record("execution:dead_pid_without_rc_is_lost", dead_result.get("state") == "LOST_PROCESS", dead_result)

    # 12: live PID with wrong process-start token => LOST_PROCESS, never false RUNNING.
    reuse_cwd = base / "reuse"; reuse_cwd.mkdir()
    reuse_root = base / "state-reuse"
    reuse_spec = spec_for(reuse_cwd, counter_code(), check="reuse")
    reuse_op = operation_dir(reuse_root, reuse_spec); reuse_op.mkdir(parents=True)
    reuse_manifest = copy.deepcopy(dead_manifest)
    reuse_manifest.update({"operation_id": reuse_spec["operation_id"], "stage_id": reuse_spec["stage_id"], "check_id": reuse_spec["check_id"], "command_argv": reuse_spec["command_argv"], "command_fingerprint": reuse_spec["command_fingerprint"], "cwd": reuse_spec["cwd"], "source_identity": reuse_spec["source_identity"], "source_fingerprint": reuse_spec["source_fingerprint"]})
    reuse_manifest["child"] = {"pid": os.getpid(), "start_token": (process_start_token(os.getpid()) or "token") + ":wrong"}
    reuse_manifest["supervisor"] = {"pid": os.getpid(), "start_token": process_start_token(os.getpid())}
    _atomic_write_json(reuse_op / "operation.json", reuse_manifest)
    reuse_result = recover(reuse_op, reuse_spec)
    record("execution:pid_reuse_token_mismatch_is_lost", reuse_result.get("state") == "LOST_PROCESS" and "IDENTITY_MISMATCH" in str(reuse_result.get("reason")), reuse_result)

    # 13: corrupt manifest is fail-closed, not NEVER_STARTED.
    corrupt_cwd = base / "corrupt"; corrupt_cwd.mkdir()
    corrupt_root = base / "state-corrupt"
    corrupt_spec = spec_for(corrupt_cwd, counter_code(), check="corrupt")
    corrupt_op = operation_dir(corrupt_root, corrupt_spec); corrupt_op.mkdir(parents=True)
    (corrupt_op / "operation.json").write_text("{not-json", encoding="utf-8")
    corrupt_result = recover(corrupt_op, corrupt_spec)
    record("execution:corrupt_manifest_fails_closed", corrupt_result.get("state") == "LOST_PROCESS" and corrupt_result.get("fail_closed") is True, corrupt_result)

    # 14: abandoned temp write cannot damage prior valid manifest.
    atomic_cwd = base / "atomic"; atomic_cwd.mkdir()
    atomic_root = base / "state-atomic"
    atomic_spec = spec_for(atomic_cwd, counter_code(), check="atomic")
    atomic_first = launch(atomic_root, atomic_spec)
    atomic_op = operation_dir(atomic_root, atomic_spec)
    atomic_terminal = wait_for_terminal(atomic_op, atomic_spec)
    (atomic_op / ".operation.json.tmp.interrupted").write_text("{broken", encoding="utf-8")
    atomic_recovered = recover(atomic_op, atomic_spec)
    record("execution:interrupted_temp_write_preserves_valid_manifest", atomic_terminal.get("state") == "PASSED" and atomic_recovered.get("state") == "PASSED", atomic_recovered)

    # 15: concurrent callers must acquire one launch claim and run one child.
    concurrent_cwd = base / "concurrent"; concurrent_cwd.mkdir()
    concurrent_root = base / "state-concurrent"
    concurrent_spec = spec_for(concurrent_cwd, counter_code(sleep_seconds=0.4), check="concurrent")
    barrier = threading.Barrier(3)
    calls = []
    def caller():
        barrier.wait()
        calls.append(launch(concurrent_root, concurrent_spec))
    threads = [threading.Thread(target=caller) for _ in range(2)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join()
    concurrent_op = operation_dir(concurrent_root, concurrent_spec)
    concurrent_terminal = wait_for_terminal(concurrent_op, concurrent_spec)
    record("execution:concurrent_launch_claim_runs_one_supervisor_child", concurrent_terminal.get("state") == "PASSED" and counter(concurrent_cwd) == 1 and len(calls) == 2, {"counter": counter(concurrent_cwd), "calls": calls})

    # 16 already asserted hashes; assert exact digest independently.
    out_row = next((row for row in terminal.get("observed_outputs") or [] if row.get("path") == "out.txt"), {})
    import hashlib
    expected_sha = hashlib.sha256(b"payload").hexdigest()
    record("execution:expected_output_sha256_exact", out_row.get("sha256") == expected_sha, out_row)

    # 17: execution success is explicitly not semantic proof.
    record("execution:rc_zero_is_execution_only_not_semantic_proof", terminal.get("exit_code") == 0 and terminal.get("execution_evidence_scope") == "EXECUTION_ONLY" and terminal.get("semantic_proof_granted") is False, {"exit_code": terminal.get("exit_code"), "scope": terminal.get("execution_evidence_scope"), "semantic_proof_granted": terminal.get("semantic_proof_granted")})

failed = [row for row in results if row["result"] != "PASS"]
report = {"status": "PASS" if not failed else "FAIL", "passed": len(results) - len(failed), "total": len(results), "cases": results}
print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
raise SystemExit(0 if not failed else 2)
