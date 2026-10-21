#!/usr/bin/env python3
"""S2-L1B: offline exact Git tree/blob vs signed release index inventory.

Read ONLY a caller-supplied isolated Git object store. Never installed products,
projects, working-tree contents, or source/Main/Incoming.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import unicodedata
from pathlib import Path

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
RULE = ("This public manifest inventories only files present in SHAREABLE_CORE and their content digests. "
        "Private source identity and excluded internal paths are intentionally not published.")
CONSTANTS = {
    "schema_version": 3,
    "distribution_profile": "SHAREABLE_CORE",
    "snapshot_contract_version": 1,
    "snapshot_digest_algorithm": "sha256-canonical-inventory-v1",
    "public_workflows": [".github/workflows/shareable-validation.yml"],
    "rule": RULE,
}
MANIFEST_KEYS = set(CONSTANTS) | {"file_count", "files", "snapshot_digest"}
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{a}{n}" for a in ("COM", "LPT") for n in range(1, 10)}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _safe_path(path):
    if type(path) is not str or not path or "\\" in path or path.startswith("/"):
        return False
    if unicodedata.normalize("NFC", path) != path:
        return False
    for item in path.split("/"):
        if (not item or item in (".", "..") or item.endswith((" ", "."))
                or any(ord(c) < 32 or c in ':*?"<>|' for c in item)
                or item.split(".")[0].upper() in RESERVED):
            return False
    return True


def _git(repo, *args, input_bytes=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", str(repo), *args], input=input_bytes,
                          capture_output=True, timeout=60, check=False, env=env)


def verify_tree(repo: Path, approval: dict | None, index_bytes: bytes | None):
    """Bind an ALREADY independently signed approval to every committed file.

    index and approval MUST originate from verify_approval; never network input
    alone. Git commit/tree SHA1 is structural; SHA256 on EVERY blob is compared
    to the independently signed canonical manifest digest.
    """
    if type(approval) is not dict or type(index_bytes) is not bytes:
        return False, "TREE_AUTHORITY_MISSING"
    try:
        index = json.loads(index_bytes.decode("utf-8", "strict"), object_pairs_hook=_unique)
        if (hashlib.sha256(index_bytes).hexdigest() != approval.get("index_sha256")
                or index["release_commit_sha"] != approval["release_commit_sha"]
                or index["release_counter"] != approval["release_counter"]
                or type(index["distribution_snapshot_sha256"]) is not str
                or not HEX64.fullmatch(index["distribution_snapshot_sha256"])):
            return False, "TREE_APPROVAL_MISMATCH"
        release = approval["release_commit_sha"]
        if type(release) is not str or not HEX40.fullmatch(release):
            return False, "TREE_COMMIT_INVALID"
        # Tree/blob identity can be proven on a shallow clone. The composite
        # verifier separately REQUIRES complete ancestry and rejects shallow.
        git_dir = _git(repo, "rev-parse", "--git-common-dir")
        if git_dir.returncode:
            return False, "TREE_GIT_HISTORY_OVERRIDE"
        common = Path(git_dir.stdout.decode().strip())
        if not common.is_absolute():
            common = repo / common
        if (common / "info" / "grafts").exists():
            return False, "TREE_GIT_HISTORY_OVERRIDE"
        if _git(repo, "for-each-ref", "--format=%(refname)", "refs/replace").stdout.strip():
            return False, "TREE_GIT_HISTORY_OVERRIDE"
        commit = _git(repo, "cat-file", "commit", release)
        if commit.returncode or hashlib.sha1(b"commit " + str(len(commit.stdout)).encode()
                                             + b"\x00" + commit.stdout).hexdigest() != release:
            return False, "TREE_COMMIT_OBJECT_MISMATCH"
        tree_ref = re.search(rb"^tree ([a-f0-9]{40})$", commit.stdout, re.M)
        if tree_ref is None:
            return False, "TREE_ROOT_MISSING"
        listing = _git(repo, "ls-tree", "-rz", "-t", "--full-tree", release)
        if listing.returncode:
            return False, "TREE_UNAVAILABLE"
        files = {}
        folders = {"": tree_ref.group(1).decode("ascii")}
        identities = set()
        for line in listing.stdout.split(b"\x00"):
            if not line:
                continue
            header, raw_name = line.split(b"\t", 1)
            mode, kind, oid = header.split(b" ")
            name = raw_name.decode("utf-8", "strict")
            identity = unicodedata.normalize("NFC", name).casefold()
            if not _safe_path(name) or identity in identities:
                return False, "TREE_UNSAFE_OR_COLLIDING_PATH"
            identities.add(identity)
            if kind == b"tree":
                if mode != b"040000" and mode != b"40000":
                    return False, "TREE_DIRECTORY_MODE_INVALID"
                folders[name] = oid.decode("ascii")
            elif kind == b"blob" and mode in (b"100644", b"100755"):
                if not HEX40.fullmatch(oid.decode("ascii")):
                    return False, "TREE_OBJECT_ID_INVALID"
                files[name] = oid.decode("ascii")
            else:
                return False, "TREE_SYMLINK_SUBMODULE_OR_MODE_FORBIDDEN"
        # Rehash every Git tree object, including nested folders, not only blobs.
        for oid in folders.values():
            if not HEX40.fullmatch(oid):
                return False, "TREE_OBJECT_ID_INVALID"
            obj = _git(repo, "cat-file", "tree", oid)
            if obj.returncode or hashlib.sha1(b"tree " + str(len(obj.stdout)).encode()
                                             + bytes([0]) + obj.stdout).hexdigest() != oid:
                return False, "TREE_OBJECT_ID_MISMATCH"
        if "DISTRIBUTION_MANIFEST.json" not in files:
            return False, "TREE_MANIFEST_MISSING"
        if any("/".join(path.split("/")[:i]) not in folders
               for path in files for i in range(1, len(path.split("/")))):
            return False, "TREE_SUBDIRECTORY_MISSING"
        total_blob_bytes = 0
        def blob(oid):
            nonlocal total_blob_bytes
            size = _git(repo, "cat-file", "-s", oid)
            if (size.returncode or not size.stdout.strip().isdigit()
                    or int(size.stdout.strip()) > 134217728
                    or total_blob_bytes + int(size.stdout.strip()) > 1073741824):
                raise ValueError("Git blob size budget exceeded")
            res = _git(repo, "cat-file", "blob", oid)
            if res.returncode:
                raise ValueError("blob unavailable")
            data = res.stdout
            if len(data) != int(size.stdout.strip()):
                raise ValueError("blob size mismatch")
            total_blob_bytes += len(data)
            if hashlib.sha1(b"blob " + str(len(data)).encode()
                             + bytes([0]) + data).hexdigest() != oid:
                raise ValueError("blob Git identity mismatch")
            return data
        manifest_raw = blob(files["DISTRIBUTION_MANIFEST.json"])
        if len(manifest_raw) > 262144:
            return False, "TREE_MANIFEST_TOO_LARGE"
        manifest = json.loads(manifest_raw.decode("utf-8", "strict"), object_pairs_hook=_unique)
        if type(manifest) is not dict or set(manifest) != MANIFEST_KEYS:
            return False, "TREE_MANIFEST_SCHEMA_INVALID"
        if any(manifest.get(key) != value for key, value in CONSTANTS.items()):
            return False, "TREE_MANIFEST_CONTRACT_INVALID"
        rows = manifest["files"]
        if (type(rows) is not list or type(manifest["file_count"]) is not int
                or len(rows) != manifest["file_count"] or len(rows) > 10000):
            return False, "TREE_MANIFEST_COUNT_INVALID"
        expected = {}
        normalized = set()
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "size", "sha256"}:
                return False, "TREE_MANIFEST_ROW_INVALID"
            name, size, digest = row["path"], row["size"], row["sha256"]
            if (not _safe_path(name) or name == "DISTRIBUTION_MANIFEST.json"
                    or type(size) is not int or size < 0 or size > 134217728
                    or type(digest) is not str or not HEX64.fullmatch(digest)
                    or name.casefold() in normalized):
                return False, "TREE_MANIFEST_ROW_INVALID"
            normalized.add(name.casefold())
            expected[name] = row
        if set(files) != set(expected) | {"DISTRIBUTION_MANIFEST.json"}:
            return False, "TREE_FILE_SET_MISMATCH"
        for name, item in expected.items():
            data = blob(files[name])
            if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                return False, "TREE_BLOB_CONTENT_MISMATCH"
        canonical = {**CONSTANTS, "file_count": len(rows),
                     "files": sorted(rows, key=lambda row: row["path"])}
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(b"SHAREABLE_CORE_SNAPSHOT_V1\x00" + encoded).hexdigest()
        if (manifest["snapshot_digest"] != digest
                or index["distribution_snapshot_sha256"] != digest):
            return False, "TREE_SIGNED_DISTRIBUTION_MISMATCH"
        return True, "SIGNED_INDEX_MATCHES_COMPLETE_GIT_TREE"
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.TimeoutExpired):
        return False, "TREE_INVALID_OR_UNAVAILABLE"


def verify_complete_release(repo: Path, index_bytes: bytes | None, envelope_bytes: bytes | None,
                            *, trusted_modulus: int | None, trusted_exponent: int | None,
                            protected_minimum_counter: int):
    """All-or-nothing authority -> ancestry -> complete Git distribution proof.

    Both public key and monotonically protected counter MUST come from separately
    provisioned operator/OS authorities. Never from release metadata or repo.
    Does no installation and cannot authorize INSTALL/UPDATE.
    """
    import importlib.util
    source = Path(__file__).with_name("release_authority.py")
    spec = importlib.util.spec_from_file_location("orbit_signed_authority", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    approval, reason = module.verify_approval(
        index_bytes, envelope_bytes, trusted_modulus=trusted_modulus,
        trusted_exponent=trusted_exponent, minimum_counter=protected_minimum_counter)
    if approval is None:
        return None, reason
    valid, reason = module.verify_git_ancestry(repo, approval)
    if not valid:
        return None, reason
    valid, reason = verify_tree(repo, approval, index_bytes)
    if not valid:
        return None, reason
    return approval, "COMPLETE_SIGNED_RELEASE_PROVENANCE_VERIFIED"
