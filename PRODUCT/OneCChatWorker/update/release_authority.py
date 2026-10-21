#!/usr/bin/env python3
"""S2-L1B: offline signed release approval and Git ancestry proof; no installer."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path

HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
REPOSITORY = "alexleb-dotcom/onec-cleverence-public"
SCHEMA = "ONEC_ORBIT_SIGNED_RELEASE_AUTHORITY_V1"
DOMAIN = b"ONEC_ORBIT_RELEASE_AUTHORITY_V1\0"
SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _json(raw: bytes):
    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_pairs)


def verify_rsa_sha256(message: bytes, signature: bytes, modulus: int, exponent: int) -> bool:
    """Strict RSASSA-PKCS1-v1_5 SHA256; key provisioned OUTSIDE downloaded files."""
    if type(modulus) is not int or modulus.bit_length() < 2048 or modulus.bit_length() > 8192:
        return False
    if type(exponent) is not int or exponent < 3 or exponent > 65537 or exponent % 2 != 1:
        return False
    length = (modulus.bit_length() + 7) // 8
    if len(signature) != length:
        return False
    value = int.from_bytes(signature, "big")
    if value >= modulus:
        return False
    encoded = pow(value, exponent, modulus).to_bytes(length, "big")
    tail = SHA256_DER_PREFIX + hashlib.sha256(message).digest()
    padding = length - len(tail) - 3
    return padding >= 8 and encoded == b"\x00\x01" + b"\xff" * padding + b"\x00" + tail


def verify_approval(index_bytes: bytes | None, envelope_bytes: bytes | None,
                    *, trusted_modulus: int | None, trusted_exponent: int | None,
                    minimum_counter: int) -> tuple[dict | None, str]:
    """No source-supplied key or self-digest can grant an approved release."""
    if type(minimum_counter) is not int or minimum_counter < 0:
        return None, "TRUSTED_COUNTER_MISSING"
    if not isinstance(index_bytes, bytes) or not isinstance(envelope_bytes, bytes):
        return None, "AUTHORITY_UNAVAILABLE"
    if len(index_bytes) > 65536 or len(envelope_bytes) > 8192:
        return None, "AUTHORITY_TOO_LARGE"
    try:
        envelope = _json(envelope_bytes)
        if type(envelope) is not dict or set(envelope) != {
                "schema", "repository", "main_commit_sha", "index_sha256",
                "release_counter", "signature_hex"}:
            return None, "AUTHORITY_SCHEMA_INVALID"
        if envelope["schema"] != SCHEMA or envelope["repository"] != REPOSITORY:
            return None, "AUTHORITY_ORIGIN_INVALID"
        main_sha = envelope["main_commit_sha"]
        index_sha = envelope["index_sha256"]
        sig = envelope["signature_hex"]
        counter = envelope["release_counter"]
        if not (type(main_sha) is str and HEX40.fullmatch(main_sha)
                and type(index_sha) is str and HEX64.fullmatch(index_sha)
                and type(sig) is str and len(sig) % 2 == 0
                and re.fullmatch(r"[a-f0-9]+", sig)
                and type(counter) is int and 0 <= counter <= 2**31-1):
            return None, "AUTHORITY_IDENTITY_INVALID"
        if hashlib.sha256(index_bytes).hexdigest() != index_sha:
            return None, "AUTHORITY_INDEX_MISMATCH"
        if counter < minimum_counter:
            return None, "AUTHORITY_ROLLBACK"
        body = {key: envelope[key] for key in (
            "schema", "repository", "main_commit_sha", "index_sha256", "release_counter")}
        signed = DOMAIN + json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not verify_rsa_sha256(signed, bytes.fromhex(sig), trusted_modulus, trusted_exponent):
            return None, "AUTHORITY_SIGNATURE_INVALID"
        from_path = Path(__file__).with_name("readonly_discovery.py")
        # Validate index using the existing accepted exact-byte schema.
        import importlib.util
        spec = importlib.util.spec_from_file_location("orbit_readonly_discovery", from_path)
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        index, reason = module.validate_approved_index(index_bytes, index_sha)
        if index is None or index["release_counter"] != counter:
            return None, "AUTHORITY_INDEX_SEMANTICS_INVALID"
        return {"main_commit_sha": main_sha, "release_commit_sha": index["release_commit_sha"],
                "release_counter": counter, "index_sha256": index_sha}, "SIGNED_APPROVAL_VALID"
    except (UnicodeError, ValueError, TypeError, KeyError, OverflowError):
        return None, "AUTHORITY_MALFORMED"


def verify_git_ancestry(repo: Path, approved: dict | None) -> tuple[bool, str]:
    """Offline full-object Git proof against SIGNED main, never mutable origin/main."""
    if approved is None:
        return False, "APPROVAL_MISSING"
    release = approved.get("release_commit_sha")
    main = approved.get("main_commit_sha")
    if not all(type(x) is str and HEX40.fullmatch(x) for x in (release, main)):
        return False, "COMMIT_INVALID"
    try:
        def run(*args):
            return subprocess.run(["git", "-c", "core.alternateRefsCommand=", "-C", str(repo),
                                   *args], capture_output=True, timeout=10, check=False)
        # Reject shallow repositories, replacement refs, and legacy grafts.
        if run("rev-parse", "--is-shallow-repository").stdout.strip() != b"false":
            return False, "GIT_HISTORY_INCOMPLETE"
        git_dir = run("rev-parse", "--absolute-git-dir")
        if git_dir.returncode:
            return False, "GIT_REPO_UNAVAILABLE"
        if (Path(git_dir.stdout.decode().strip()) / "info" / "grafts").exists():
            return False, "GIT_HISTORY_OVERRIDE"
        if run("for-each-ref", "--format=%(refname)", "refs/replace").stdout.strip():
            return False, "GIT_HISTORY_OVERRIDE"
        for sha in (release, main):
            obj = run("cat-file", "-t", sha)
            if obj.returncode or obj.stdout.strip() != b"commit":
                return False, "GIT_COMMIT_UNAVAILABLE"
        is_ancestor = run("merge-base", "--is-ancestor", release, main)
        if is_ancestor.returncode != 0:
            return False, "GIT_ANCESTRY_UNVERIFIED"
        return True, "SIGNED_MAIN_CONTAINS_RELEASE"
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return False, "GIT_PROOF_UNAVAILABLE"
