#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import re
import unicodedata

MANIFEST_NAME = "DISTRIBUTION_MANIFEST.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SNAPSHOT_SCHEMA_VERSION = 3
DISTRIBUTION_PROFILE = "SHAREABLE_CORE"
SNAPSHOT_CONTRACT_VERSION = 1
SNAPSHOT_DIGEST_ALGORITHM = "sha256-canonical-inventory-v1"
SNAPSHOT_DIGEST_DOMAIN = b"SHAREABLE_CORE_SNAPSHOT_V1\0"
PUBLIC_WORKFLOWS = (".github/workflows/shareable-validation.yml",)
FORBIDDEN_PUBLIC_DEPENDENCY_PREFIXES = (
    "MAINTENANCE/INTERNAL/",
    "REFERENCE/SOURCES/",
    "REFERENCE/INDEXES/",
    "COLLECTOR/",
)
MANIFEST_RULE = (
    "This public manifest inventories only files present in SHAREABLE_CORE and their content digests. "
    "Private source identity and excluded internal paths are intentionally not published."
)
SNAPSHOT_MANIFEST_KEYS = frozenset({
    "schema_version",
    "distribution_profile",
    "snapshot_contract_version",
    "snapshot_digest_algorithm",
    "snapshot_digest",
    "public_workflows",
    "file_count",
    "files",
    "rule",
})


def canonical_inventory_rows(rows: list[dict]) -> list[dict]:
    """Project rows to the digest contract and order them by path."""
    return sorted(
        [
            {"path": row["path"], "size": row["size"], "sha256": row["sha256"]}
            for row in rows
        ],
        key=lambda row: row["path"],
    )


def canonical_digest_input(rows: list[dict]) -> dict:
    """Build the versioned digest payload; snapshot_digest is intentionally excluded."""
    ordered = canonical_inventory_rows(rows)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "distribution_profile": DISTRIBUTION_PROFILE,
        "snapshot_contract_version": SNAPSHOT_CONTRACT_VERSION,
        "snapshot_digest_algorithm": SNAPSHOT_DIGEST_ALGORITHM,
        "public_workflows": list(PUBLIC_WORKFLOWS),
        "file_count": len(ordered),
        "files": ordered,
        "rule": MANIFEST_RULE,
    }


def canonical_utf8_json(payload: dict) -> bytes:
    """Serialize canonical JSON as UTF-8 with sorted keys and compact separators."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_snapshot_digest(rows: list[dict]) -> str:
    """sha256-canonical-inventory-v1 over the canonical SHAREABLE_CORE identity."""
    payload = canonical_digest_input(rows)
    return hashlib.sha256(SNAPSHOT_DIGEST_DOMAIN + canonical_utf8_json(payload)).hexdigest()


def build_distribution_manifest(rows: list[dict]) -> dict:
    """Build the public manifest using the same canonical owner the validator uses."""
    payload = canonical_digest_input(rows)
    payload["snapshot_digest"] = compute_snapshot_digest(rows)
    return payload


def _canonical_path_identity(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _path_collision_findings(paths: list[str], *, source: str) -> list[dict]:
    findings: list[dict] = []
    files_by_identity: dict[str, str] = {}
    for rel in sorted(paths):
        identity = _canonical_path_identity(rel)
        previous = files_by_identity.get(identity)
        if previous is not None and previous != rel:
            findings.append({
                "type": "SNAPSHOT_PATH_IDENTITY_COLLISION",
                "source": source,
                "paths": sorted([previous, rel]),
            })
            continue
        files_by_identity[identity] = rel

    emitted_file_directory: set[tuple[str, str]] = set()
    for rel in sorted(paths):
        parts = rel.split("/")
        for index in range(1, len(parts)):
            directory = "/".join(parts[:index])
            file_rel = files_by_identity.get(_canonical_path_identity(directory))
            if file_rel is None:
                continue
            pair = (file_rel, directory)
            if pair in emitted_file_directory:
                continue
            emitted_file_directory.add(pair)
            findings.append({
                "type": "SNAPSHOT_FILE_DIRECTORY_COLLISION",
                "source": source,
                "file": file_rel,
                "directory": directory,
                "path": rel,
            })
    return findings


def _public_workflow_findings(expected: dict[str, dict], actual: dict[str, Path]) -> list[dict]:
    findings: list[dict] = []
    required = sorted(PUBLIC_WORKFLOWS)
    declared = sorted(path for path in expected if path.startswith(".github/workflows/"))
    present = sorted(path for path in actual if path.startswith(".github/workflows/"))
    if declared != required or present != required:
        findings.append({
            "type": "SNAPSHOT_PUBLIC_WORKFLOW_SET_MISMATCH",
            "expected": required,
            "declared": declared,
            "actual": present,
        })

    for rel in present:
        workflow_path = actual[rel]
        try:
            text = workflow_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({
                "type": "SNAPSHOT_PUBLIC_WORKFLOW_NOT_UTF8",
                "path": rel,
            })
            continue
        normalized = text.replace("\\", "/")
        for prefix in FORBIDDEN_PUBLIC_DEPENDENCY_PREFIXES:
            if prefix in normalized:
                findings.append({
                    "type": "SNAPSHOT_PUBLIC_WORKFLOW_FORBIDDEN_DEPENDENCY",
                    "path": rel,
                    "dependency_prefix": prefix,
                })
    return findings


def _safe_manifest_path(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        return None
    parts = value.split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        return None
    return value


def validate_snapshot_root(root: Path) -> dict:
    root = root.resolve()
    errors: list[dict] = []
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {
            "result": "FAIL",
            "errors": [{"type": "SNAPSHOT_MANIFEST_MISSING", "path": MANIFEST_NAME}],
            "checked_files": 0,
        }

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "result": "FAIL",
            "errors": [{"type": "SNAPSHOT_MANIFEST_INVALID_JSON", "error": str(exc)}],
            "checked_files": 0,
        }

    if not isinstance(payload, dict) or set(payload) != SNAPSHOT_MANIFEST_KEYS:
        errors.append({
            "type": "SNAPSHOT_MANIFEST_SCHEMA_MISMATCH",
            "keys": sorted(payload) if isinstance(payload, dict) else None,
        })
        rows = []
    else:
        rows = payload.get("files")
        constant_fields = (
            ("schema_version", SNAPSHOT_SCHEMA_VERSION, "SNAPSHOT_SCHEMA_VERSION_MISMATCH"),
            ("distribution_profile", DISTRIBUTION_PROFILE, "SNAPSHOT_PROFILE_MISMATCH"),
            ("snapshot_contract_version", SNAPSHOT_CONTRACT_VERSION, "SNAPSHOT_CONTRACT_VERSION_MISMATCH"),
            ("snapshot_digest_algorithm", SNAPSHOT_DIGEST_ALGORITHM, "SNAPSHOT_DIGEST_ALGORITHM_MISMATCH"),
            ("public_workflows", list(PUBLIC_WORKFLOWS), "SNAPSHOT_PUBLIC_WORKFLOW_IDENTITY_MISMATCH"),
            ("rule", MANIFEST_RULE, "SNAPSHOT_RULE_IDENTITY_MISMATCH"),
        )
        for field, expected_value, finding_type in constant_fields:
            if payload.get(field) != expected_value:
                errors.append({"type": finding_type, "field": field})
        snapshot_digest = payload.get("snapshot_digest")
        if not isinstance(snapshot_digest, str) or not SHA256_RE.fullmatch(snapshot_digest):
            errors.append({"type": "SNAPSHOT_INVALID_SNAPSHOT_DIGEST"})
        if not isinstance(rows, list):
            errors.append({"type": "SNAPSHOT_FILES_NOT_LIST"})
            rows = []

    expected: dict[str, dict] = {}
    valid_digest_rows = True
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"path", "size", "sha256"}:
            errors.append({"type": "SNAPSHOT_FILE_ROW_SCHEMA_MISMATCH", "index": index})
            valid_digest_rows = False
            continue
        rel = _safe_manifest_path(row.get("path"))
        if rel is None or rel == MANIFEST_NAME:
            errors.append({"type": "SNAPSHOT_UNSAFE_FILE_PATH", "index": index, "path": row.get("path")})
            valid_digest_rows = False
            continue
        if rel in expected:
            errors.append({"type": "SNAPSHOT_DUPLICATE_FILE_PATH", "path": rel})
            valid_digest_rows = False
            continue
        size = row.get("size")
        digest = row.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            errors.append({"type": "SNAPSHOT_INVALID_FILE_SIZE", "path": rel, "size": size})
            valid_digest_rows = False
            continue
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append({"type": "SNAPSHOT_INVALID_FILE_SHA256", "path": rel})
            valid_digest_rows = False
            continue
        expected[rel] = row

    manifest_collision_errors = _path_collision_findings(list(expected), source="manifest")
    if manifest_collision_errors:
        errors.extend(manifest_collision_errors)
        valid_digest_rows = False

    declared_count = payload.get("file_count") if isinstance(payload, dict) else None
    if not isinstance(declared_count, int) or isinstance(declared_count, bool) or declared_count != len(rows):
        errors.append({
            "type": "SNAPSHOT_FILE_COUNT_MISMATCH",
            "declared": declared_count,
            "manifest_rows": len(rows),
        })

    if isinstance(payload, dict) and valid_digest_rows and isinstance(rows, list):
        try:
            canonical_digest = compute_snapshot_digest(rows)
        except (KeyError, TypeError, ValueError):
            errors.append({"type": "SNAPSHOT_DIGEST_INPUT_INVALID"})
        else:
            if payload.get("snapshot_digest") != canonical_digest:
                errors.append({"type": "SNAPSHOT_DIGEST_MISMATCH"})

    actual: dict[str, Path] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if path.is_symlink():
            errors.append({"type": "SNAPSHOT_SYMLINK_FORBIDDEN", "path": rel})
            continue
        if not path.is_file() or rel == MANIFEST_NAME:
            continue
        actual[rel] = path

    errors.extend(_path_collision_findings(list(actual), source="actual"))
    errors.extend(_public_workflow_findings(expected, actual))

    expected_paths = set(expected)
    actual_paths = set(actual)
    missing = sorted(expected_paths - actual_paths)
    extra = sorted(actual_paths - expected_paths)
    if missing:
        errors.append({"type": "SNAPSHOT_DECLARED_FILE_MISSING", "paths": missing})
    if extra:
        errors.append({"type": "SNAPSHOT_UNDECLARED_FILE_PRESENT", "paths": extra})

    checked = 0
    for rel in sorted(expected_paths & actual_paths):
        data = actual[rel].read_bytes()
        checked += 1
        actual_size = len(data)
        actual_sha = hashlib.sha256(data).hexdigest()
        row = expected[rel]
        if actual_size != row["size"]:
            errors.append({
                "type": "SNAPSHOT_FILE_SIZE_MISMATCH",
                "path": rel,
                "expected": row["size"],
                "actual": actual_size,
            })
        if actual_sha != row["sha256"]:
            errors.append({
                "type": "SNAPSHOT_FILE_SHA256_MISMATCH",
                "path": rel,
                "expected": row["sha256"],
                "actual": actual_sha,
            })

    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checked_files": checked,
        "declared_files": len(rows),
        "actual_files": len(actual),
        "snapshot_digest": payload.get("snapshot_digest") if isinstance(payload, dict) else None,
        "snapshot_digest_algorithm": payload.get("snapshot_digest_algorithm") if isinstance(payload, dict) else None,
        "rule": "The SHAREABLE_CORE working tree must contain exactly the manifest-declared public files, with exact byte sizes and SHA-256 digests, a valid canonical snapshot digest, collision-free NFC+casefold path identities, exactly the approved public workflow set, and no workflow dependency on private/internal/Collector surfaces. Root .git metadata is ignored because a checked-out public repository necessarily supplies it outside the snapshot payload.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate exact file set, content hashes and canonical digest of an extracted SHAREABLE_CORE snapshot.")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    report = validate_snapshot_root(Path(args.root))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
