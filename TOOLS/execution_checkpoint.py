#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATES = {"NEVER_STARTED", "RUNNING", "PASSED", "FAILED", "LOST_PROCESS", "STALE_IDENTITY"}
TERMINAL_STATES = {"PASSED", "FAILED", "LOST_PROCESS", "STALE_IDENTITY"}
EXECUTION_EVIDENCE_SCOPE = "EXECUTION_ONLY"


class CheckpointError(RuntimeError):
    pass


def _utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _directory_digest(path: Path) -> str:
    rows = []
    for item in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
        rows.append({"path": item.relative_to(path).as_posix(), "sha256": _sha256_file(item), "size": item.stat().st_size})
    return _sha256_bytes(_canonical_json(rows))


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_json(path: Path, value: dict) -> None:
    _atomic_write_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n")


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _read_json(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CheckpointError("manifest root must be an object")
    return raw


def _validate_source_identity(source_identity: dict) -> dict:
    if not isinstance(source_identity, dict):
        raise ValueError("source_identity must be an object")
    kind = source_identity.get("kind")
    if kind == "PR_SOURCE":
        required = ("repository", "base_sha", "head_sha", "tree_sha", "verified_local_tree")
    elif kind == "SNAPSHOT":
        required = ("archive_sha256", "snapshot_digest")
    else:
        raise ValueError("source_identity.kind must be PR_SOURCE or SNAPSHOT")
    missing = [key for key in required if not str(source_identity.get(key) or "").strip()]
    if missing:
        raise ValueError(f"source_identity missing fields: {missing}")
    return json.loads(json.dumps(source_identity, sort_keys=True))


def fingerprint_environment(names: list[str], environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    rows = []
    for name in sorted(set(names)):
        value = env.get(name)
        rows.append({"name": name, "present": value is not None, "value_sha256": _sha256_bytes((value or "").encode("utf-8")) if value is not None else None})
    return _sha256_bytes(_canonical_json(rows))


def build_spec(
    *,
    stage_id: str,
    check_id: str,
    command_argv: list[str],
    cwd: str | Path,
    source_identity: dict,
    environment_fingerprint: str,
    expected_outputs: list[str] | None = None,
    report_path: str | None = None,
) -> dict:
    if not str(stage_id).strip() or not str(check_id).strip():
        raise ValueError("stage_id and check_id are required")
    if not isinstance(command_argv, list) or not command_argv or not all(isinstance(x, str) and x for x in command_argv):
        raise ValueError("command_argv must be a non-empty argv list")
    canonical_cwd = str(Path(cwd).resolve())
    if not str(environment_fingerprint).strip():
        raise ValueError("environment_fingerprint is required")
    source = _validate_source_identity(source_identity)
    core = {
        "stage_id": str(stage_id),
        "check_id": str(check_id),
        "command_argv": list(command_argv),
        "cwd": canonical_cwd,
        "source_identity": source,
        "environment_fingerprint": str(environment_fingerprint),
    }
    command_fingerprint = _sha256_bytes(_canonical_json({"argv": command_argv}))
    source_fingerprint = _sha256_bytes(_canonical_json(source))
    operation_id = _sha256_bytes(_canonical_json(core))
    return {
        **core,
        "operation_id": operation_id,
        "command_fingerprint": command_fingerprint,
        "source_fingerprint": source_fingerprint,
        "expected_outputs": sorted(set(expected_outputs or [])),
        "report_path": report_path,
    }


def operation_dir(state_root: str | Path, spec: dict, attempt_index: int = 1) -> Path:
    return Path(state_root).resolve() / spec["operation_id"] / f"attempt-{attempt_index:04d}"


def _slot_paths(state_root: str | Path, spec: dict, attempt_index: int) -> tuple[Path, Path]:
    slot_key = _sha256_bytes(_canonical_json({
        "stage_id": spec["stage_id"],
        "check_id": spec["check_id"],
        "attempt_index": attempt_index,
    }))
    root = Path(state_root).resolve() / "_bindings"
    return root / f"{slot_key}.json", root / f"{slot_key}.claim"


def _bind_operation_slot(state_root: str | Path, spec: dict, attempt_index: int) -> None:
    binding_path, claim_path = _slot_paths(state_root, spec, attempt_index)

    def check_existing() -> bool:
        if not binding_path.exists():
            return False
        try:
            binding = _read_json(binding_path)
        except Exception as exc:
            raise CheckpointError(f"STALE_IDENTITY:CORRUPT_OPERATION_BINDING:{type(exc).__name__}:{exc}") from exc
        expected = {
            "stage_id": spec["stage_id"],
            "check_id": spec["check_id"],
            "attempt_index": attempt_index,
            "operation_id": spec["operation_id"],
        }
        mismatches = [key for key, value in expected.items() if binding.get(key) != value]
        if mismatches:
            raise CheckpointError(f"STALE_IDENTITY:OPERATION_SLOT_MISMATCH:{mismatches}")
        return True

    if check_existing():
        return
    if _acquire_claim(claim_path):
        if check_existing():
            return
        _atomic_write_json(binding_path, {
            "schema_version": SCHEMA_VERSION,
            "stage_id": spec["stage_id"],
            "check_id": spec["check_id"],
            "attempt_index": attempt_index,
            "operation_id": spec["operation_id"],
            "bound_at": _utc_now(),
        })
        return
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if check_existing():
            return
        time.sleep(0.02)
    raise CheckpointError("LOST_PROCESS:OPERATION_SLOT_CLAIM_WITHOUT_BINDING")


def _paths(op_dir: Path) -> dict[str, Path]:
    return {
        "manifest": op_dir / "operation.json",
        "register_claim": op_dir / "register.claim",
        "launch_claim": op_dir / "launch.claim",
        "rc": op_dir / "rc.txt",
        "stdout": op_dir / "stdout.log",
        "stderr": op_dir / "stderr.log",
        "full_log": op_dir / "full.log",
    }


def _acquire_claim(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    try:
        payload = json.dumps({"pid": os.getpid(), "created_at": _utc_now()}, sort_keys=True).encode("utf-8") + b"\n"
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)
    return True


def _process_start_token_linux(pid: int) -> str | None:
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = stat_text.rfind(")")
        if close < 0:
            return None
        rest = stat_text[close + 2 :].split()
        starttime = rest[19]
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
        return f"linux:{boot_id}:{starttime}"
    except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError, OSError):
        return None


def _process_start_token_windows(pid: int) -> str | None:
    if os.name != "nt":
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        created = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return f"windows:{created}"
    finally:
        kernel32.CloseHandle(handle)


def process_start_token(pid: int) -> str | None:
    if sys.platform.startswith("linux"):
        return _process_start_token_linux(pid)
    if os.name == "nt":
        return _process_start_token_windows(pid)
    return None


def process_identity_matches(pid: int | None, expected_token: str | None) -> bool | None:
    if not isinstance(pid, int) or pid <= 0 or not expected_token:
        return False
    actual = process_start_token(pid)
    if actual is None:
        return None
    return actual == expected_token


def _new_manifest(spec: dict, attempt_index: int, op_dir: Path) -> dict:
    p = _paths(op_dir)
    now = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "operation_id": spec["operation_id"],
        "attempt_index": attempt_index,
        "stage_id": spec["stage_id"],
        "check_id": spec["check_id"],
        "state": "NEVER_STARTED",
        "reason": "REGISTERED",
        "timestamps": {"registered_at": now, "started_at": None, "completed_at": None, "reconciled_at": None},
        "command_argv": spec["command_argv"],
        "command_fingerprint": spec["command_fingerprint"],
        "cwd": spec["cwd"],
        "environment_fingerprint": spec["environment_fingerprint"],
        "source_identity": spec["source_identity"],
        "source_fingerprint": spec["source_fingerprint"],
        "supervisor": {"pid": None, "start_token": None},
        "child": {"pid": None, "start_token": None},
        "expected_outputs": list(spec.get("expected_outputs") or []),
        "observed_outputs": [],
        "stdout_path": str(p["stdout"]),
        "stderr_path": str(p["stderr"]),
        "full_log_path": str(p["full_log"]),
        "rc_path": str(p["rc"]),
        "report_path": spec.get("report_path"),
        "exit_code": None,
        "execution_evidence_scope": EXECUTION_EVIDENCE_SCOPE,
        "semantic_proof_granted": False,
    }


def _manifest_matches_spec(manifest: dict, spec: dict) -> tuple[bool, list[str]]:
    fields = (
        "operation_id",
        "stage_id",
        "check_id",
        "command_argv",
        "command_fingerprint",
        "cwd",
        "environment_fingerprint",
        "source_identity",
        "source_fingerprint",
        "expected_outputs",
        "report_path",
    )
    mismatches = [key for key in fields if manifest.get(key) != spec.get(key)]
    return not mismatches, mismatches


def _safe_load_manifest(manifest_path: Path) -> tuple[dict | None, str | None]:
    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        return None, f"CORRUPT_MANIFEST:{type(exc).__name__}:{exc}"
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("state") not in STATES:
        return None, "CORRUPT_MANIFEST:SCHEMA_OR_STATE"
    return manifest, None


def register(state_root: str | Path, spec: dict, attempt_index: int = 1) -> tuple[Path, dict]:
    _bind_operation_slot(state_root, spec, attempt_index)
    op_dir = operation_dir(state_root, spec, attempt_index)
    p = _paths(op_dir)
    op_dir.mkdir(parents=True, exist_ok=True)
    if p["manifest"].exists():
        manifest, error = _safe_load_manifest(p["manifest"])
        if error:
            raise CheckpointError(error)
        matches, mismatches = _manifest_matches_spec(manifest, spec)
        if not matches:
            raise CheckpointError(f"STALE_IDENTITY:{mismatches}")
        return op_dir, manifest

    if _acquire_claim(p["register_claim"]):
        manifest = _new_manifest(spec, attempt_index, op_dir)
        _atomic_write_json(p["manifest"], manifest)
        return op_dir, manifest

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if p["manifest"].exists():
            manifest, error = _safe_load_manifest(p["manifest"])
            if error:
                raise CheckpointError(error)
            matches, mismatches = _manifest_matches_spec(manifest, spec)
            if not matches:
                raise CheckpointError(f"STALE_IDENTITY:{mismatches}")
            return op_dir, manifest
        time.sleep(0.02)
    raise CheckpointError("LOST_PROCESS:REGISTRATION_CLAIM_WITHOUT_MANIFEST")


def _read_rc(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _persist_transition(manifest_path: Path, manifest: dict, *, state: str, reason: str, exit_code: int | None = None) -> dict:
    manifest = json.loads(json.dumps(manifest))
    manifest["state"] = state
    manifest["reason"] = reason
    manifest["exit_code"] = exit_code
    manifest.setdefault("timestamps", {})["reconciled_at"] = _utc_now()
    if state in {"PASSED", "FAILED", "LOST_PROCESS"} and manifest["timestamps"].get("completed_at") is None:
        manifest["timestamps"]["completed_at"] = _utc_now()
    _atomic_write_json(manifest_path, manifest)
    return manifest


def recover(op_dir: str | Path, expected_spec: dict) -> dict:
    op_dir = Path(op_dir).resolve()
    p = _paths(op_dir)
    if not p["manifest"].exists():
        return {"state": "NEVER_STARTED", "reason": "MANIFEST_ABSENT", "operation_id": expected_spec.get("operation_id")}
    manifest, error = _safe_load_manifest(p["manifest"])
    if error:
        return {"state": "LOST_PROCESS", "reason": error, "operation_id": expected_spec.get("operation_id"), "fail_closed": True}
    matches, mismatches = _manifest_matches_spec(manifest, expected_spec)
    if not matches:
        return {
            "state": "STALE_IDENTITY",
            "reason": "EXPECTED_SPEC_MISMATCH",
            "mismatches": mismatches,
            "operation_id": manifest.get("operation_id"),
            "persisted_state": manifest.get("state"),
        }

    state = manifest["state"]
    if state in {"PASSED", "FAILED", "LOST_PROCESS", "STALE_IDENTITY"}:
        return manifest
    if state == "NEVER_STARTED":
        return manifest

    rc = _read_rc(p["rc"])
    if rc is not None:
        # RC can become visible a few instructions before the supervisor persists its
        # final manifest. Recovery must complete the same terminal evidence atomically
        # instead of laundering a bare exit code into a content-less PASS/FAIL.
        manifest["observed_outputs"] = _observed_outputs(manifest)
        manifest.setdefault("timestamps", {})["completed_at"] = manifest.get("timestamps", {}).get("completed_at") or _utc_now()
        _write_full_log(manifest)
        terminal = "PASSED" if rc == 0 else "FAILED"
        return _persist_transition(p["manifest"], manifest, state=terminal, reason="RECONCILED_FROM_RC", exit_code=rc)

    child = manifest.get("child") or {}
    supervisor = manifest.get("supervisor") or {}
    if child.get("pid"):
        child_match = process_identity_matches(child.get("pid"), child.get("start_token"))
        if child_match is True:
            return manifest
        # The child can exit a few instructions before the live supervisor writes
        # rc.txt, captures expected-output hashes and persists the terminal manifest.
        # In that legitimate finalize window the supervisor is still the exact owner
        # of completion, so recovery must keep polling instead of fabricating
        # LOST_PROCESS from the already-finished child.
        if supervisor.get("pid"):
            supervisor_match = process_identity_matches(supervisor.get("pid"), supervisor.get("start_token"))
            if supervisor_match is True:
                return manifest
        reason = "CHILD_PROCESS_IDENTITY_MISMATCH" if child_match is False else "CHILD_PROCESS_IDENTITY_UNVERIFIABLE"
        return _persist_transition(p["manifest"], manifest, state="LOST_PROCESS", reason=reason)
    if supervisor.get("pid"):
        match = process_identity_matches(supervisor.get("pid"), supervisor.get("start_token"))
        if match is True:
            return manifest
        reason = "SUPERVISOR_PROCESS_IDENTITY_MISMATCH" if match is False else "SUPERVISOR_PROCESS_IDENTITY_UNVERIFIABLE"
        return _persist_transition(p["manifest"], manifest, state="LOST_PROCESS", reason=reason)
    return _persist_transition(p["manifest"], manifest, state="LOST_PROCESS", reason="RUNNING_WITHOUT_PROCESS_IDENTITY")


def _observed_outputs(manifest: dict) -> list[dict]:
    cwd = Path(manifest["cwd"])
    rows = []
    for raw in manifest.get("expected_outputs") or []:
        path = Path(raw)
        absolute = path if path.is_absolute() else cwd / path
        row = {"path": raw, "exists": absolute.exists()}
        if absolute.is_file():
            row.update({"kind": "FILE", "size": absolute.stat().st_size, "sha256": _sha256_file(absolute)})
        elif absolute.is_dir():
            row.update({"kind": "DIRECTORY", "sha256": _directory_digest(absolute)})
        elif absolute.exists():
            row["kind"] = "OTHER"
        else:
            row["kind"] = "MISSING"
        rows.append(row)
    return rows


def _write_full_log(manifest: dict) -> None:
    stdout_path = Path(manifest["stdout_path"])
    stderr_path = Path(manifest["stderr_path"])
    parts = ["=== STDOUT ===\n"]
    if stdout_path.exists():
        parts.append(stdout_path.read_text(encoding="utf-8", errors="replace"))
    parts.append("\n=== STDERR ===\n")
    if stderr_path.exists():
        parts.append(stderr_path.read_text(encoding="utf-8", errors="replace"))
    _atomic_write_text(Path(manifest["full_log_path"]), "".join(parts))


def supervise(manifest_path: str | Path) -> int:
    manifest_path = Path(manifest_path).resolve()
    manifest, error = _safe_load_manifest(manifest_path)
    if error or manifest is None:
        return 111
    op_dir = manifest_path.parent
    p = _paths(op_dir)
    supervisor_token = process_start_token(os.getpid())
    if supervisor_token is None:
        _persist_transition(manifest_path, manifest, state="LOST_PROCESS", reason="SUPERVISOR_IDENTITY_UNVERIFIABLE")
        return 112

    manifest["state"] = "RUNNING"
    manifest["reason"] = "SUPERVISOR_STARTED"
    manifest["supervisor"] = {"pid": os.getpid(), "start_token": supervisor_token}
    manifest.setdefault("timestamps", {})["started_at"] = _utc_now()
    _atomic_write_json(manifest_path, manifest)

    stdout_path = Path(manifest["stdout_path"])
    stderr_path = Path(manifest["stderr_path"])
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with stdout_path.open("wb") as stdout_fh, stderr_path.open("wb") as stderr_fh:
            child = subprocess.Popen(
                list(manifest["command_argv"]),
                cwd=manifest["cwd"],
                stdin=subprocess.DEVNULL,
                stdout=stdout_fh,
                stderr=stderr_fh,
                shell=False,
                close_fds=True,
            )
            child_token = process_start_token(child.pid)
            if child_token is None:
                try:
                    child.terminate()
                except OSError:
                    pass
                _persist_transition(manifest_path, manifest, state="LOST_PROCESS", reason="CHILD_IDENTITY_UNVERIFIABLE")
                return 113
            manifest["child"] = {"pid": child.pid, "start_token": child_token}
            manifest["reason"] = "CHILD_RUNNING"
            _atomic_write_json(manifest_path, manifest)
            rc = child.wait()
    except Exception as exc:
        manifest, _ = _safe_load_manifest(manifest_path)
        if manifest is None:
            return 114
        _atomic_write_text(p["rc"], "127\n")
        manifest["observed_outputs"] = _observed_outputs(manifest)
        manifest["timestamps"]["completed_at"] = _utc_now()
        manifest = _persist_transition(manifest_path, manifest, state="FAILED", reason=f"SUPERVISOR_EXCEPTION:{type(exc).__name__}", exit_code=127)
        _write_full_log(manifest)
        return 127

    _atomic_write_text(p["rc"], f"{rc}\n")
    manifest, error = _safe_load_manifest(manifest_path)
    if error or manifest is None:
        return 115
    manifest["observed_outputs"] = _observed_outputs(manifest)
    manifest["timestamps"]["completed_at"] = _utc_now()
    manifest["state"] = "PASSED" if rc == 0 else "FAILED"
    manifest["reason"] = "CHILD_EXITED"
    manifest["exit_code"] = rc
    _atomic_write_json(manifest_path, manifest)
    _write_full_log(manifest)
    return rc


def launch(state_root: str | Path, spec: dict, attempt_index: int = 1, startup_wait_seconds: float = 2.0) -> dict:
    op_dir, manifest = register(state_root, spec, attempt_index)
    recovered = recover(op_dir, spec)
    if recovered.get("state") != "NEVER_STARTED":
        return recovered
    p = _paths(op_dir)
    if not _acquire_claim(p["launch_claim"]):
        deadline = time.monotonic() + startup_wait_seconds
        while time.monotonic() < deadline:
            recovered = recover(op_dir, spec)
            if recovered.get("state") != "NEVER_STARTED":
                return recovered
            time.sleep(0.02)
        manifest, error = _safe_load_manifest(p["manifest"])
        if error or manifest is None:
            return {"state": "LOST_PROCESS", "reason": error or "LAUNCH_CLAIM_WITHOUT_MANIFEST", "fail_closed": True}
        return _persist_transition(p["manifest"], manifest, state="LOST_PROCESS", reason="LAUNCH_CLAIM_WITHOUT_SUPERVISOR")

    creationflags = 0
    start_new_session = False
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    else:
        start_new_session = True
    try:
        supervisor = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_supervise", str(p["manifest"])],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=start_new_session,
            creationflags=creationflags,
            shell=False,
        )
    except Exception as exc:
        manifest, error = _safe_load_manifest(p["manifest"])
        if error or manifest is None:
            return {"state": "LOST_PROCESS", "reason": error or f"SUPERVISOR_SPAWN_FAILED:{type(exc).__name__}", "fail_closed": True}
        return _persist_transition(p["manifest"], manifest, state="LOST_PROCESS", reason=f"SUPERVISOR_SPAWN_FAILED:{type(exc).__name__}")

    deadline = time.monotonic() + startup_wait_seconds
    while time.monotonic() < deadline:
        recovered = recover(op_dir, spec)
        if recovered.get("state") != "NEVER_STARTED":
            return recovered
        if supervisor.poll() is not None:
            break
        time.sleep(0.02)
    recovered = recover(op_dir, spec)
    if recovered.get("state") == "NEVER_STARTED":
        manifest, error = _safe_load_manifest(p["manifest"])
        if error or manifest is None:
            return {"state": "LOST_PROCESS", "reason": error or "SUPERVISOR_START_NOT_PERSISTED", "fail_closed": True}
        return _persist_transition(p["manifest"], manifest, state="LOST_PROCESS", reason="SUPERVISOR_START_NOT_PERSISTED")
    return recovered


def wait_for_terminal(op_dir: str | Path, spec: dict, timeout_seconds: float = 10.0, poll_seconds: float = 0.02) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = recover(op_dir, spec)
        if state.get("state") in TERMINAL_STATES:
            return state
        time.sleep(poll_seconds)
    return recover(op_dir, spec)


def _load_cli_source_identity(path: str) -> dict:
    return _validate_source_identity(_read_json(Path(path).resolve()))


def _add_cli_spec_arguments(parser: argparse.ArgumentParser, *, include_command: bool = True) -> None:
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--stage-id", required=True)
    parser.add_argument("--check-id", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--source-identity", required=True, help="JSON file containing PR_SOURCE or SNAPSHOT identity")
    parser.add_argument("--env-name", action="append", default=[], help="Environment variable name to fingerprint; values are never persisted")
    parser.add_argument("--expected-output", action="append", default=[])
    parser.add_argument("--report-path")
    parser.add_argument("--attempt-index", type=int, default=1)
    if include_command:
        parser.add_argument("command_argv", nargs=argparse.REMAINDER)


def _spec_from_cli(args: argparse.Namespace) -> dict:
    command = list(args.command_argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise CheckpointError("command argv is required after --")
    return build_spec(
        stage_id=args.stage_id,
        check_id=args.check_id,
        command_argv=command,
        cwd=args.cwd,
        source_identity=_load_cli_source_identity(args.source_identity),
        environment_fingerprint=fingerprint_environment(list(args.env_name or [])),
        expected_outputs=list(args.expected_output or []),
        report_path=args.report_path,
    )


def _cli_result(spec: dict, state_root: str | Path, attempt_index: int, state: dict) -> dict:
    return {
        "state": state.get("state"),
        "reason": state.get("reason"),
        "operation_id": spec["operation_id"],
        "operation_dir": str(operation_dir(state_root, spec, attempt_index)),
        "attempt_index": attempt_index,
        "exit_code": state.get("exit_code"),
        "rc_path": state.get("rc_path"),
        "report_path": state.get("report_path"),
        "full_log_path": state.get("full_log_path"),
        "execution_evidence_scope": state.get("execution_evidence_scope", EXECUTION_EVIDENCE_SCOPE),
        "semantic_proof_granted": bool(state.get("semantic_proof_granted", False)),
    }


def _cli_exit_code(state: str | None) -> int:
    if state in {"PASSED", "RUNNING", "NEVER_STARTED"}:
        return 0
    if state == "FAILED":
        return 2
    return 3


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Canonical persisted local execution checkpoint owner")
    sub = parser.add_subparsers(dest="command", required=True)

    sup = sub.add_parser("_supervise")
    sup.add_argument("manifest")

    run = sub.add_parser("run", help="Launch or recover an exact operation; never duplicate a matching attempt")
    _add_cli_spec_arguments(run)
    run.add_argument("--wait-seconds", type=float, default=0.0)

    rec = sub.add_parser("recover", help="Recover an already registered exact operation without launching it")
    _add_cli_spec_arguments(rec)

    args = parser.parse_args()
    if args.command == "_supervise":
        return supervise(args.manifest)

    try:
        spec = _spec_from_cli(args)
        op_dir = operation_dir(args.state_root, spec, args.attempt_index)
        if args.command == "run":
            state = launch(args.state_root, spec, args.attempt_index)
            if args.wait_seconds > 0 and state.get("state") == "RUNNING":
                state = wait_for_terminal(op_dir, spec, timeout_seconds=args.wait_seconds)
        else:
            # Bind the stage/check/attempt slot before lookup so a changed command/source
            # fails closed instead of silently becoming a different logical operation.
            _bind_operation_slot(args.state_root, spec, args.attempt_index)
            state = recover(op_dir, spec)
    except CheckpointError as exc:
        message = str(exc)
        state_name = "STALE_IDENTITY" if message.startswith("STALE_IDENTITY:") else "LOST_PROCESS"
        state = {"state": state_name, "reason": message, "fail_closed": True}
        try:
            spec
        except UnboundLocalError:
            print(json.dumps(state, ensure_ascii=False, sort_keys=True))
            return 3
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        state = {"state": "LOST_PROCESS", "reason": f"INVALID_OPERATION_SPEC:{type(exc).__name__}:{exc}", "fail_closed": True}
        try:
            spec
        except UnboundLocalError:
            print(json.dumps(state, ensure_ascii=False, sort_keys=True))
            return 3

    result = _cli_result(spec, args.state_root, args.attempt_index, state)
    if state.get("fail_closed"):
        result["fail_closed"] = True
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return _cli_exit_code(result.get("state"))


if __name__ == "__main__":
    raise SystemExit(_cli())
