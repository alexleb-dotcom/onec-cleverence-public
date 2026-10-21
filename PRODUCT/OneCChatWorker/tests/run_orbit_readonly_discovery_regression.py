#!/usr/bin/env python3
"""Q115 S2-L1A pure fake-byte release decision checks; no Windows/production reads."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "update" / "readonly_discovery.py"
spec = importlib.util.spec_from_file_location("orbit_discovery", MODULE)
mod = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

checks = 0


def require(value, reason: str):
    global checks
    assert value, reason
    checks += 1


old = b"fixture EXE revision approved 1 - fake bytes, not a real executable"
new = b"fixture EXE revision approved 2 - fake bytes, not a real executable"
old_sha = mod.sha256_bytes(old)
new_sha = mod.sha256_bytes(new)
old_commit = "1" * 40
new_commit = "2" * 40
current = {
    "schema": mod.APPROVAL_SCHEMA,
    "repository": mod.APPROVED_REPO,
    "release_commit_sha": old_commit,
    "release_counter": 11,
    "gui_exe_sha256": old_sha,
    "distribution_snapshot_sha256": "e" * 64,
}
latest = {**current, "release_commit_sha": new_commit, "release_counter": 12, "gui_exe_sha256": new_sha}


def index(payload):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return body, hashlib.sha256(body).hexdigest()


def evaluate(
    proposal=current, actual=old, known=old_sha,
    installed_commit=old_commit, installed_counter=11,
    authority=True, tamper=False, operation_busy=False, release_chain_verified=True
):
    raw, valid = index(proposal)
    return mod.discover(
        current_exe_bytes=actual,
        installed_trusted_exe_sha=known,
        installed_trusted_release_commit=installed_commit,
        installed_trusted_release_counter=installed_counter,
        approved_index_bytes=raw + (b"x" if tamper else b""),
        approval_authority_digest=valid if authority else None,
        operation_busy=operation_busy,
        release_chain_verified=release_chain_verified,
    )


def status(actual, want, reason=None):
    require(actual.state == want, f"expected {want}, got {actual.state}: {actual.reason}")
    if reason:
        require(actual.reason == reason, f"expected {reason}, got {actual.reason}")
    for field in ("installation_permitted", "update_invoked", "worker_or_s4_touched"):
        require(getattr(actual, field) is False, "all decisions permanently non-mutating")
    require(actual.to_dict()["schema"] == "ONEC_ORBIT_READONLY_DISCOVERY_V1", "schema exact")


status(evaluate(), "CURRENT")
status(evaluate(latest), "UPDATE_DETECTED")
status(evaluate(latest, release_chain_verified=False), "HOLD", "IMMUTABLE_RELEASE_CHAIN_NOT_VERIFIED")
status(evaluate(latest, operation_busy=True), "DEFERRED", "WORK_OR_ADMISSION_ACTIVE")
status(evaluate(current, actual=b"malicious replacement"), "REPAIR_REQUIRED", "LOCAL_IMAGE_DRIFT")
status(evaluate(latest, actual=b"malicious replacement"), "REPAIR_REQUIRED")
status(evaluate(latest, authority=False), "RELEASE_UNKNOWN", "APPROVAL_AUTHORITY_MISSING")
status(evaluate(latest, tamper=True), "RELEASE_UNKNOWN", "APPROVED_INDEX_DIGEST_MISMATCH")
status(evaluate({**latest, "release_counter": 10}), "HOLD", "RELEASE_COUNTER_ROLLBACK")
status(evaluate({**latest, "release_counter": 11}), "HOLD", "SAME_COUNTER_CONFLICT")
status(evaluate({**latest, "release_commit_sha": old_commit}), "HOLD", "CHANGED_COUNTER_SAME_COMMIT")
status(evaluate({**latest, "gui_exe_sha256": old_sha}), "HOLD", "NEW_RELEASE_WITH_UNCHANGED_IMAGE_NEEDS_REVIEW")
status(evaluate({**current, "unexpected_key": "tamper"}), "RELEASE_UNKNOWN", "APPROVED_INDEX_SCHEMA_INVALID")
status(evaluate({**current, "repository": "evil/other"}), "RELEASE_UNKNOWN", "APPROVED_INDEX_ORIGIN_INVALID")
status(evaluate({**current, "release_commit_sha": "HEAD"}), "RELEASE_UNKNOWN", "APPROVED_INDEX_IDENTITY_INVALID")
status(evaluate({**current, "release_counter": True}), "RELEASE_UNKNOWN", "APPROVED_INDEX_COUNTER_INVALID")
status(evaluate(known=None), "HOLD", "INSTALLED_TRUST_ANCHOR_MISSING")
status(evaluate(installed_commit=None), "HOLD", "INSTALLED_TRUST_ANCHOR_MISSING")
status(evaluate(installed_counter=-1), "HOLD", "INSTALLED_RELEASE_COUNTER_UNVERIFIED")
status(evaluate(actual=None), "HOLD", "INSTALLED_IMAGE_UNAVAILABLE")
status(evaluate(latest, operation_busy=True, actual=b"drift"), "REPAIR_REQUIRED", "LOCAL_IMAGE_DRIFT")

index_raw, pinned = index(current)
bad_json = b'{"broken":'
result, why = mod.validate_approved_index(bad_json, mod.sha256_bytes(bad_json))
require(result is None and why == "APPROVED_INDEX_INVALID", "bad json denied")
result, why = mod.validate_approved_index(b"x" * 65537, mod.sha256_bytes(b"x" * 65537))
require(result is None and why == "APPROVED_INDEX_TOO_LARGE", "oversize denied")
result, why = mod.validate_approved_index(None, pinned)
require(result is None and why == "APPROVED_INDEX_UNAVAILABLE", "offline denied")
result, why = mod.validate_approved_index(index_raw, pinned)
require(result is not None and why == "PINNED_APPROVED_INDEX_VALID", "known exact byte pin passes")
require(all(x is not None for x in (old_sha, new_sha, old_commit)), "synthetic data complete")

print(
    f"ORBIT_READONLY_DISCOVERY_DECISION_PASS checks={checks} "
    "network_calls=0 installed_file_reads=0 worker_s4_access=0 "
    "install_calls=0 status_only=true"
)
