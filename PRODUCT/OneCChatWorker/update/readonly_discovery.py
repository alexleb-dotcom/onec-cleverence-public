#!/usr/bin/env python3
"""OneC Orbit S2-L1A: offline, non-mutating release discovery decision engine.

NO GitHub/network access, process controls, product-state traversal or installer calls.
All trust pins are from a caller's separately protected authority. Never treat a
self-consistent release index or mutable main HEAD as authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

APPROVAL_SCHEMA = "ONEC_ORBIT_APPROVED_RELEASE_INDEX_V1"
APPROVED_REPO = "alexleb-dotcom/onec-cleverence-public"
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
GIT_SHA1 = re.compile(r"[a-f0-9]{40}\Z")
REQUIRED_KEYS = frozenset({
    "schema", "repository", "release_commit_sha", "release_counter",
    "gui_exe_sha256", "distribution_snapshot_sha256",
})


@dataclass(frozen=True)
class Discovery:
    state: str
    reason: str
    installed_integrity: str
    approved_release_commit: str | None
    installation_permitted: bool = False
    update_invoked: bool = False
    worker_or_s4_touched: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "ONEC_ORBIT_READONLY_DISCOVERY_V1",
            "state": self.state,
            "reason": self.reason,
            "installed_integrity": self.installed_integrity,
            "approved_release_commit": self.approved_release_commit,
            "installation_permitted": self.installation_permitted,
            "update_invoked": self.update_invoked,
            "worker_or_s4_touched": self.worker_or_s4_touched,
        }


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_sha(value: object) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def _blocked(state: str, reason: str, integrity: str = "UNVERIFIED") -> Discovery:
    return Discovery(state, reason, integrity, None)


def validate_approved_index(index_bytes: bytes | None, authority_digest: str | None) -> tuple[dict | None, str]:
    """Authenticate a pinned exact index byte identity before interpreting any fields.

    A digest passed by an arbitrary network response does NOT confer authority;
    only a separately protected out-of-band pin is acceptable.
    """
    if not _valid_sha(authority_digest):
        return None, "APPROVAL_AUTHORITY_MISSING"
    if index_bytes is None:
        return None, "APPROVED_INDEX_UNAVAILABLE"
    if len(index_bytes) > 65536:
        return None, "APPROVED_INDEX_TOO_LARGE"
    if sha256_bytes(index_bytes) != authority_digest:
        return None, "APPROVED_INDEX_DIGEST_MISMATCH"
    try:
        index = json.loads(index_bytes.decode("utf-8", "strict"))
    except (UnicodeError, json.JSONDecodeError):
        return None, "APPROVED_INDEX_INVALID"
    if not isinstance(index, dict) or frozenset(index) != REQUIRED_KEYS:
        return None, "APPROVED_INDEX_SCHEMA_INVALID"
    if index["schema"] != APPROVAL_SCHEMA or index["repository"] != APPROVED_REPO:
        return None, "APPROVED_INDEX_ORIGIN_INVALID"
    if not (isinstance(index["release_commit_sha"], str)
            and GIT_SHA1.fullmatch(index["release_commit_sha"])
            and _valid_sha(index["gui_exe_sha256"])
            and _valid_sha(index["distribution_snapshot_sha256"])):
        return None, "APPROVED_INDEX_IDENTITY_INVALID"
    if type(index["release_counter"]) is not int or not 0 <= index["release_counter"] <= 2**31 - 1:
        return None, "APPROVED_INDEX_COUNTER_INVALID"
    return index, "PINNED_APPROVED_INDEX_VALID"


def discover(
    *,
    current_exe_bytes: bytes | None,
    installed_trusted_exe_sha: str | None,
    installed_trusted_release_commit: str | None,
    installed_trusted_release_counter: int | None,
    installed_trusted_distribution_snapshot_sha: str | None,
    approved_index_bytes: bytes | None,
    approval_authority_digest: str | None,
    operation_busy: bool = False,
    release_chain_verified: bool = False,
) -> Discovery:
    """Compute status only. No I/O. Refuse any untrusted/missing installed identity.

    Remote branch HEAD, if observed elsewhere, is *never* a release authority.
    """
    if not _valid_sha(installed_trusted_exe_sha) or not (isinstance(installed_trusted_release_commit, str) and GIT_SHA1.fullmatch(installed_trusted_release_commit)):
        return _blocked("HOLD", "INSTALLED_TRUST_ANCHOR_MISSING")
    if type(installed_trusted_release_counter) is not int or not 0 <= installed_trusted_release_counter <= 2**31 - 1:
        return _blocked("HOLD", "INSTALLED_RELEASE_COUNTER_UNVERIFIED")
    if not _valid_sha(installed_trusted_distribution_snapshot_sha):
        return _blocked("HOLD", "INSTALLED_DISTRIBUTION_SNAPSHOT_UNVERIFIED")
    if current_exe_bytes is None:
        return _blocked("HOLD", "INSTALLED_IMAGE_UNAVAILABLE")
    if sha256_bytes(current_exe_bytes) != installed_trusted_exe_sha:
        return _blocked("REPAIR_REQUIRED", "LOCAL_IMAGE_DRIFT", "DRIFT")

    approved, reason = validate_approved_index(approved_index_bytes, approval_authority_digest)
    if approved is None:
        return _blocked("RELEASE_UNKNOWN", reason, "MATCHES_PINNED_INSTALLED_EXE")
    commit = approved["release_commit_sha"]
    if approved["release_counter"] < installed_trusted_release_counter:
        return Discovery("HOLD", "RELEASE_COUNTER_ROLLBACK", "MATCHES_PINNED_INSTALLED_EXE", commit)
    if approved["release_counter"] == installed_trusted_release_counter:
        if (commit != installed_trusted_release_commit
                or approved["gui_exe_sha256"] != installed_trusted_exe_sha
                or approved["distribution_snapshot_sha256"] != installed_trusted_distribution_snapshot_sha):
            return Discovery("HOLD", "SAME_COUNTER_CONFLICT", "MATCHES_PINNED_INSTALLED_EXE", commit)
        return Discovery("CURRENT", "APPROVED_RELEASE_MATCHES_INSTALLATION", "MATCHES_PINNED_INSTALLED_EXE", commit)
    if commit == installed_trusted_release_commit:
        return Discovery("HOLD", "CHANGED_COUNTER_SAME_COMMIT", "MATCHES_PINNED_INSTALLED_EXE", commit)
    if approved["gui_exe_sha256"] == installed_trusted_exe_sha:
        return Discovery("HOLD", "NEW_RELEASE_WITH_UNCHANGED_IMAGE_NEEDS_REVIEW", "MATCHES_PINNED_INSTALLED_EXE", commit)
    if not release_chain_verified:
        return Discovery("HOLD", "IMMUTABLE_RELEASE_CHAIN_NOT_VERIFIED", "MATCHES_PINNED_INSTALLED_EXE", commit)
    if operation_busy:
        return Discovery("DEFERRED", "WORK_OR_ADMISSION_ACTIVE", "MATCHES_PINNED_INSTALLED_EXE", commit)
    return Discovery("UPDATE_DETECTED", "PINNED_APPROVED_RELEASE_DIFFERS", "MATCHES_PINNED_INSTALLED_EXE", commit)
