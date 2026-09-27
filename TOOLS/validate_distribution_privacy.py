#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import base64
import binascii
import hashlib
import json
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PREFIXES = (
    "ARCHIVE/",
    "REFERENCE/SOURCES/",
    "REFERENCE/INDEXES/",
    "MAINTENANCE/INTERNAL/",
    "COLLECTOR/",
)
EXCLUDED_EXACT = {
    "manifest.txt",
    ".github/workflows/internal-distribution-equivalence.yml",
    ".github/workflows/skill-validation.yml",
    ".github/workflows/fast-pr.yml",
    ".github/workflows/manual-full-audit.yml",
    ".github/workflows/post-merge-validation.yml",
}
FORBIDDEN_PATH_PARTS = {"DEVELOPER_PACK", "CURRENT_WORK", "PROJECT_SNAPSHOT", "PENDING"}

EMAIL_RE = re.compile(r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9._%+-])")
WINDOWS_USER_PATH_RE = re.compile(r"(?i)[A-Z]:\\Users\\[^\\\s\"']+")
UNIX_USER_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:/Users|/home)/[^/\s\"']+")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
HIGH_CONFIDENCE_TOKEN_RE = re.compile(r"(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})")
PRIVATE_IPV4_RE = re.compile(
    r"(?<![0-9])(?:"
    r"10(?:\.[0-9]{1,3}){3}|"
    r"127(?:\.[0-9]{1,3}){3}|"
    r"169\.254(?:\.[0-9]{1,3}){2}|"
    r"192\.168(?:\.[0-9]{1,3}){2}|"
    r"172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}"
    r")(?![0-9])"
)
PRIVATE_HOST_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9.-])(?:"
    + "local" + "host"
    + r"|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:local|internal|lan)"
    + r")(?![A-Za-z0-9.-])"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:password|pwd|client_secret|api_key|access_token)\s*[:=]\s*"
    r"(?P<value>[^;\s,]+)"
)
BASE64_PART_RE = re.compile(r"^(?P<prefix>.+\.b64)\.part(?P<part>[0-9A-Za-z]+)$")
BINARY_REVIEW_POLICY_REL = "TOOLS/SHAREABLE_BINARY_REVIEW_POLICY.json"
BINARY_REVIEW_POLICY_ID = "shareable-binary-review-v1"
BASE64_MAX_PARTS = 64
BASE64_MAX_ENCODED_BYTES = 1024 * 1024
BASE64_MAX_DECODED_BYTES = 768 * 1024
BINARY_ARCHIVE_SUFFIXES = {
    ".bin", ".zip", ".7z", ".rar", ".gz", ".tgz", ".tar", ".bz2", ".xz",
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".exe", ".dll", ".so", ".dylib", ".epf", ".erf", ".cf", ".cfe", ".dt",
    ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt", ".pyc",
}
KNOWN_STRUCTURED_SUFFIXES = {".json", ".xml", ".yaml", ".yml", ".svg", ".mslx", ".csv"}
ARCHIVE_MAGIC = (
    (b"PK\x03\x04", "archive/zip"),
    (b"7z\xbc\xaf'\x1c", "archive/7z"),
    (b"Rar!\x1a\x07", "archive/rar"),
    (b"\x1f\x8b", "archive/gzip"),
    (b"%PDF-", "document/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"MZ", "executable/pe"),
    (b"\x7fELF", "executable/elf"),
)


def normalize_rel(value: str | Path) -> str:
    rel = str(value).replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _safe_selected_path(root: Path, rel: str) -> tuple[Path | None, str | None]:
    rel = normalize_rel(rel)
    candidate_rel = Path(rel)
    if not rel or rel.startswith("/") or candidate_rel.is_absolute():
        return None, "absolute_or_empty_path"
    if any(part in ("", ".", "..") for part in candidate_rel.parts):
        return None, "path_traversal"
    candidate = root / candidate_rel
    if candidate.is_symlink():
        return None, "symlink_input"
    try:
        root_resolved = root.resolve()
        candidate_resolved = candidate.resolve(strict=False)
    except OSError:
        return None, "path_resolution_failed"
    if candidate_resolved != root_resolved and root_resolved not in candidate_resolved.parents:
        return None, "outside_distribution_root"
    return candidate, None


def is_distribution_excluded(rel: str) -> bool:
    rel = normalize_rel(rel)
    return rel in EXCLUDED_EXACT or any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def _requested_from_manifest(root: Path, manifest: Path | None = None) -> tuple[list[str], str, list[dict]]:
    if manifest is not None:
        source = manifest
    elif (root / "manifest.txt").is_file():
        source = root / "manifest.txt"
    elif (root / "DISTRIBUTION_MANIFEST.json").is_file():
        source = root / "DISTRIBUTION_MANIFEST.json"
    else:
        raise FileNotFoundError("Neither manifest.txt nor DISTRIBUTION_MANIFEST.json is available")

    declared_excluded = []
    if source.name == "DISTRIBUTION_MANIFEST.json":
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        requested = [normalize_rel(row.get("path", "")) for row in payload.get("files", []) if row.get("path")]
        for row in payload.get("excluded_from_internal_manifest", []):
            if not isinstance(row, dict) or not row.get("path"):
                continue
            declared_excluded.append({
                "path": normalize_rel(row["path"]),
                "reason": row.get("reason") or "declared_excluded_from_internal_manifest",
            })
    else:
        requested = []
        for raw in source.read_text(encoding="utf-8-sig").splitlines():
            rel = normalize_rel(raw.strip())
            if rel and not rel.startswith("#"):
                requested.append(rel)
    return requested, source.name, declared_excluded


def select_distribution_files(root: Path = ROOT, manifest: Path | None = None) -> dict:
    requested, manifest_kind, declared_excluded = _requested_from_manifest(root, manifest)
    missing = []
    excluded = list(declared_excluded)
    unsafe = []
    selected = []

    for rel in requested:
        if is_distribution_excluded(rel):
            excluded.append({"path": rel, "reason": "distribution_restricted_surface"})
            continue
        path, unsafe_reason = _safe_selected_path(root, rel)
        if unsafe_reason is not None:
            unsafe.append({"path": normalize_rel(rel), "reason": unsafe_reason})
            continue
        assert path is not None
        if not path.is_file():
            missing.append(normalize_rel(rel))
            continue
        selected.append(normalize_rel(rel))

    return {
        "manifest_kind": manifest_kind,
        "requested": requested,
        "selected": selected,
        "excluded": excluded,
        "unsafe": unsafe,
        "missing": missing,
    }


def _is_text_content(text: str) -> bool:
    for char in text:
        codepoint = ord(char)
        if char in "\t\n\r":
            continue
        if codepoint < 32 or 0x7F <= codepoint <= 0x9F:
            return False
    return True


def _decode_text(data: bytes) -> str | None:
    if b"\0" in data:
        return None
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if _is_text_content(text):
            return text
        return None
    return None


PRIVACY_FINDING_ID_DOMAIN = b"SHAREABLE_CORE_PRIVACY_FINDING_V1\0"


def _redacted_finding(*, finding_type: str, rule_id: str, rel: str, start: int) -> dict:
    identity = "\0".join((rule_id, normalize_rel(rel), finding_type, str(start))).encode("utf-8")
    digest = hashlib.sha256(PRIVACY_FINDING_ID_DOMAIN + identity).hexdigest()[:24]
    return {
        "type": finding_type,
        "path": normalize_rel(rel),
        "rule_id": rule_id,
        "finding_id": f"privacy-finding-v1:{digest}",
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _detect_public_type(rel: str, data: bytes, text: str | None) -> tuple[str, str]:
    suffix = Path(rel).suffix.lower()
    for magic, type_class in ARCHIVE_MAGIC:
        if data.startswith(magic):
            return "binary_archive", type_class

    if suffix == ".bin":
        if text is not None:
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                pass
            else:
                local_name = root.tag.rsplit("}", 1)[-1]
                if local_name == "package":
                    return "binary_archive", "onec-xdto-package-bin"
        return "binary_archive", "binary/octet-stream"

    if suffix in BINARY_ARCHIVE_SUFFIXES or text is None:
        return "binary_archive", "binary/octet-stream"
    if suffix in KNOWN_STRUCTURED_SUFFIXES:
        return "known_structured_format", f"text/{suffix.lstrip('.')}"
    return "text", "text/plain"


def _load_review_policy(root: Path) -> tuple[dict | None, list[dict]]:
    path = root / BINARY_REVIEW_POLICY_REL
    if not path.is_file():
        return None, [{"type": "BINARY_REVIEW_POLICY_MISSING", "path": BINARY_REVIEW_POLICY_REL}]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [{"type": "BINARY_REVIEW_POLICY_INVALID_JSON", "path": BINARY_REVIEW_POLICY_REL, "error": str(exc)}]
    expected_keys = {"schema_version", "policy_id", "reviewed_binary_files", "third_party_attribution_files"}
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        return None, [{"type": "BINARY_REVIEW_POLICY_SCHEMA_MISMATCH", "path": BINARY_REVIEW_POLICY_REL}]
    if payload.get("schema_version") != 1 or payload.get("policy_id") != BINARY_REVIEW_POLICY_ID:
        return None, [{"type": "BINARY_REVIEW_POLICY_ID_MISMATCH", "path": BINARY_REVIEW_POLICY_REL}]
    return payload, []


def _policy_records(payload: dict | None, key: str) -> dict[str, dict]:
    if not isinstance(payload, dict):
        return {}
    records = {}
    for row in payload.get(key, []):
        if not isinstance(row, dict):
            continue
        rel = row.get("path")
        if not isinstance(rel, str) or normalize_rel(rel) != rel or not rel:
            continue
        records[rel] = row
    return records


def _validate_binary_review(
    rel: str,
    data: bytes,
    detected_type_class: str,
    payload: dict | None,
) -> list[dict]:
    records = _policy_records(payload, "reviewed_binary_files")
    row = records.get(rel)
    if row is None:
        return [{"type": "UNKNOWN_BINARY_OR_ARCHIVE", "path": rel, "type_class": detected_type_class}]
    if row.get("policy_id") != BINARY_REVIEW_POLICY_ID:
        return [{"type": "BINARY_REVIEW_RECORD_POLICY_ID_MISMATCH", "path": rel}]
    expected_sha = row.get("sha256")
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        return [{"type": "BINARY_REVIEW_RECORD_SHA256_INVALID", "path": rel}]
    actual_sha = _sha256_bytes(data)
    if actual_sha != expected_sha:
        return [{"type": "BINARY_REVIEW_HASH_MISMATCH", "path": rel, "expected_sha256": expected_sha, "actual_sha256": actual_sha}]
    if row.get("type_class") != detected_type_class:
        return [{"type": "BINARY_REVIEW_TYPE_MISMATCH", "path": rel, "expected_type_class": row.get("type_class"), "actual_type_class": detected_type_class}]
    if not isinstance(row.get("reason"), str) or not row["reason"].strip():
        return [{"type": "BINARY_REVIEW_REASON_MISSING", "path": rel}]
    return []


def _third_party_attribution_status(
    rel: str,
    data: bytes,
    payload: dict | None,
) -> tuple[bool, list[dict]]:
    if not rel.startswith("THIRD_PARTY/"):
        return False, []
    records = _policy_records(payload, "third_party_attribution_files")
    row = records.get(rel)
    if row is None:
        return False, []
    if row.get("policy_id") != BINARY_REVIEW_POLICY_ID:
        return False, [{"type": "THIRD_PARTY_ATTRIBUTION_POLICY_ID_MISMATCH", "path": rel}]
    expected_sha = row.get("sha256")
    actual_sha = _sha256_bytes(data)
    if expected_sha != actual_sha:
        return False, [{"type": "THIRD_PARTY_ATTRIBUTION_HASH_MISMATCH", "path": rel, "expected_sha256": expected_sha, "actual_sha256": actual_sha}]
    if not isinstance(row.get("reason"), str) or not row["reason"].strip():
        return False, [{"type": "THIRD_PARTY_ATTRIBUTION_REASON_MISSING", "path": rel}]
    return True, []


def _is_placeholder_secret(value: str) -> bool:
    cleaned = value.strip().strip("'\\\"")
    lowered = cleaned.lower()
    if not cleaned:
        return True
    if cleaned.startswith("<") and cleaned.endswith(">"):
        return True
    if cleaned.startswith("$" + "{") and cleaned.endswith("}"):
        return True
    if cleaned.startswith("%") and cleaned.endswith("%") and len(cleaned) > 2:
        return True
    if all(ch in "*xX" for ch in cleaned):
        return True
    return lowered in {"redacted", "changeme", "example", "placeholder", "dummy", "test"}


def _high_confidence_content_findings(data: bytes, rel: str) -> tuple[list[dict], str | None]:
    errors = []
    text = _decode_text(data)
    scan_text = text if text is not None else data.decode("latin-1")
    for regex, finding_type, rule_id in (
        (WINDOWS_USER_PATH_RE, "LOCAL_WINDOWS_USER_PATH", "privacy.local-windows-user-path.v1"),
        (UNIX_USER_PATH_RE, "LOCAL_UNIX_USER_PATH", "privacy.local-unix-user-path.v1"),
        (PRIVATE_KEY_RE, "PRIVATE_KEY_MATERIAL", "privacy.private-key-material.v1"),
        (HIGH_CONFIDENCE_TOKEN_RE, "HIGH_CONFIDENCE_ACCESS_TOKEN", "privacy.high-confidence-access-token.v1"),
        (PRIVATE_IPV4_RE, "PRIVATE_NETWORK_IPV4", "privacy.private-network-ipv4.v1"),
        (PRIVATE_HOST_RE, "PRIVATE_NETWORK_HOSTNAME", "privacy.private-network-hostname.v1"),
    ):
        match = regex.search(scan_text)
        if match:
            errors.append(_redacted_finding(
                finding_type=finding_type,
                rule_id=rule_id,
                rel=rel,
                start=match.start(),
            ))

    for match in SECRET_ASSIGNMENT_RE.finditer(scan_text):
        value = match.group("value")
        if not _is_placeholder_secret(value):
            errors.append(_redacted_finding(
                finding_type="CONNECTION_SECRET_ASSIGNMENT",
                rule_id="privacy.connection-secret-assignment.v1",
                rel=rel,
                start=match.start(),
            ))
    return errors, text


def _validate_base64_transport_payloads(root: Path, rel_paths: list[str]) -> tuple[list[dict], int]:
    groups: dict[str, list[str]] = {}
    for raw_rel in rel_paths:
        rel = normalize_rel(raw_rel)
        match = BASE64_PART_RE.fullmatch(rel)
        if not match or is_distribution_excluded(rel) or not (root / rel).is_file():
            continue
        groups.setdefault(match.group("prefix"), []).append(rel)

    errors = []
    checked_payloads = 0
    for prefix, parts in sorted(groups.items()):
        if len(parts) > BASE64_MAX_PARTS:
            errors.append({"type": "BASE64_TRANSPORT_TOO_MANY_PARTS", "path": prefix, "parts": len(parts), "limit": BASE64_MAX_PARTS})
            continue
        encoded_parts = []
        encoded_size = 0
        invalid = False
        for rel in sorted(parts):
            raw = (root / rel).read_bytes()
            encoded_size += len(raw)
            if encoded_size > BASE64_MAX_ENCODED_BYTES:
                errors.append({"type": "BASE64_TRANSPORT_TOO_LARGE", "path": prefix, "encoded_bytes": encoded_size, "limit": BASE64_MAX_ENCODED_BYTES})
                invalid = True
                break
            try:
                chunk = raw.decode("ascii")
            except UnicodeDecodeError:
                errors.append({"type": "BASE64_TRANSPORT_NOT_ASCII", "path": rel})
                invalid = True
                continue
            if chunk != chunk.strip() or any(char.isspace() for char in chunk):
                errors.append({"type": "BASE64_TRANSPORT_WHITESPACE", "path": rel})
                invalid = True
                continue
            encoded_parts.append(chunk)
        if invalid:
            continue
        try:
            decoded = base64.b64decode("".join(encoded_parts), validate=True)
        except (binascii.Error, ValueError) as exc:
            errors.append({
                "type": "BASE64_TRANSPORT_INVALID",
                "path": prefix,
                "error": str(exc),
            })
            continue
        if len(decoded) > BASE64_MAX_DECODED_BYTES:
            errors.append({"type": "BASE64_TRANSPORT_DECODED_TOO_LARGE", "path": prefix, "decoded_bytes": len(decoded), "limit": BASE64_MAX_DECODED_BYTES})
            continue
        checked_payloads += 1
        decoded_path = prefix + "::<decoded>"
        decoded_errors, decoded_text = _high_confidence_content_findings(decoded, decoded_path)
        errors.extend(decoded_errors)
        decoded_category, decoded_type = _detect_public_type(decoded_path, decoded, decoded_text)
        if decoded_category == "binary_archive":
            errors.append({"type": "BASE64_TRANSPORT_BINARY_ARCHIVE_FORBIDDEN", "path": prefix, "type_class": decoded_type})
    return errors, checked_payloads


def validate_distribution_paths(root: Path, rel_paths: list[str]) -> dict:
    errors = []
    warnings = []
    checked = []
    classification_counts = {"text": 0, "known_structured_format": 0, "binary_archive": 0}
    review_policy = None
    review_policy_errors: list[dict] | None = None

    for raw_rel in rel_paths:
        rel = normalize_rel(raw_rel)
        checked.append(rel)
        parts = set(Path(rel).parts)

        if is_distribution_excluded(rel):
            errors.append({"type": "DISTRIBUTION_RESTRICTED_PATH", "path": rel})
            continue
        bad_parts = sorted(parts & FORBIDDEN_PATH_PARTS)
        if bad_parts:
            errors.append({"type": "PROJECT_WORKING_PATH", "path": rel, "parts": bad_parts})

        path = root / rel
        if not path.is_file():
            errors.append({"type": "DISTRIBUTION_FILE_MISSING", "path": rel})
            continue

        data = path.read_bytes()

        # Secret/local-path checks run for every selected file before type-specific policy.
        content_errors, text = _high_confidence_content_findings(data, rel)
        errors.extend(content_errors)

        category, type_class = _detect_public_type(rel, data, text)
        classification_counts[category] += 1

        if category == "binary_archive":
            if review_policy_errors is None:
                review_policy, review_policy_errors = _load_review_policy(root)
                errors.extend(review_policy_errors)
            errors.extend(_validate_binary_review(rel, data, type_class, review_policy))

        attribution_exact = False
        if rel.startswith("THIRD_PARTY/"):
            if review_policy_errors is None:
                review_policy, review_policy_errors = _load_review_policy(root)
                errors.extend(review_policy_errors)
            attribution_exact, attribution_errors = _third_party_attribution_status(rel, data, review_policy)
            errors.extend(attribution_errors)

        if text is None:
            continue

        # Only exact reviewed license/notice bytes receive the attribution-email exception.
        if attribution_exact:
            continue

        for match in EMAIL_RE.finditer(text):
            errors.append(_redacted_finding(
                finding_type="PERSONAL_EMAIL",
                rule_id="privacy.personal-email.v1",
                rel=rel,
                start=match.start(),
            ))

    base64_errors, checked_base64_payloads = _validate_base64_transport_payloads(root, rel_paths)
    errors.extend(base64_errors)

    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "checked_files": len(checked),
        "checked_base64_payloads": checked_base64_payloads,
        "classification_counts": classification_counts,
        "rule": "Every SHAREABLE_CORE file is classified as text, known structured format, or binary/archive. Unknown binary/archive content fails closed; reviewed binary files require exact public path/SHA-256/type/reason/policy identity. Base64 transport decoding is strict and bounded. Third-party attribution email exceptions apply only to exact reviewed license/notice bytes.",
    }


def validate_repository_distribution_state(root: Path = ROOT) -> dict:
    forbidden_present = []
    for rel in (
        "ARCHIVE/DEVELOPER_PACK",
        "ARCHIVE/EXTERNAL_METHODS",
    ):
        if (root / rel).exists():
            forbidden_present.append(rel)
    try:
        selection = select_distribution_files(root)
    except Exception as exc:
        return {"result": "FAIL", "errors": [{"type": "DISTRIBUTION_MANIFEST_UNAVAILABLE", "error": str(exc)}], "warnings": [], "checked_files": 0}

    report = validate_distribution_paths(root, selection["selected"])
    if selection.get("unsafe"):
        report["errors"].append({"type": "MANIFEST_UNSAFE_SELECTED_PATH", "paths": selection["unsafe"]})
        report["result"] = "FAIL"
    if selection["missing"]:
        report["errors"].append({"type": "MANIFEST_SELECTED_FILE_MISSING", "paths": selection["missing"]})
        report["result"] = "FAIL"
    if forbidden_present:
        report["errors"].append({"type": "PRIVATE_ARCHIVE_PRESENT_IN_CURRENT_TREE", "paths": forbidden_present})
        report["result"] = "FAIL"
    report["selection"] = selection
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the shareable 1C+Cleverence skill distribution surface for privacy and restricted content.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--files-json", help="Optional JSON list/object with selected file paths; otherwise use manifest-derived shareable selection.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.files_json:
        payload = json.loads(Path(args.files_json).read_text(encoding="utf-8-sig"))
        paths = payload.get("files", []) if isinstance(payload, dict) else payload
        report = validate_distribution_paths(root, paths)
    else:
        report = validate_repository_distribution_state(root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
