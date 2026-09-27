#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from validate_distribution_privacy import (
    BASE64_MAX_ENCODED_BYTES,
    BINARY_REVIEW_POLICY_ID,
    BINARY_REVIEW_POLICY_REL,
    validate_distribution_paths,
)


def write_policy(root: Path, binary_rows=None, third_party_rows=None) -> None:
    path = root / BINARY_REVIEW_POLICY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "policy_id": BINARY_REVIEW_POLICY_ID,
            "reviewed_binary_files": binary_rows or [],
            "third_party_attribution_files": third_party_rows or [],
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def row(path: str, data: bytes, type_class: str) -> dict:
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "type_class": type_class,
        "reason": "synthetic reviewed fixture",
        "policy_id": BINARY_REVIEW_POLICY_ID,
    }


def types(report: dict) -> set[str]:
    return {item.get("type") for item in report.get("errors", [])}


def require(report: dict, finding: str, case: str) -> None:
    if finding not in types(report):
        raise AssertionError(f"{case}: expected {finding}, got {report!r}")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        unknown = root / "unknown.bin"
        unknown.write_bytes(b"\x00\x01opaque")
        write_policy(root)
        require(validate_distribution_paths(root, ["unknown.bin"]), "UNKNOWN_BINARY_OR_ARCHIVE", "unknown-binary")

        opaque = root / "opaque.dat"
        opaque_bytes = b"\x01\x02\x03opaque-control-bytes"
        opaque.write_bytes(opaque_bytes)
        write_policy(root)
        require(validate_distribution_paths(root, ["opaque.dat"]), "UNKNOWN_BINARY_OR_ARCHIVE", "unknown-extension-opaque")

        utf8_text = root / "normal-utf8.dat"
        utf8_text.write_text("normal UTF-8 text\n", encoding="utf-8")
        write_policy(root)
        utf8_report = validate_distribution_paths(root, ["normal-utf8.dat"])
        if utf8_report["result"] != "PASS" or utf8_report["classification_counts"]["text"] != 1:
            raise AssertionError(f"normal UTF-8 text should pass: {utf8_report!r}")

        cp1251_text = root / "normal-cp1251.dat"
        cp1251_text.write_bytes("Обычный текст\n".encode("cp1251"))
        write_policy(root)
        cp1251_report = validate_distribution_paths(root, ["normal-cp1251.dat"])
        if cp1251_report["result"] != "PASS" or cp1251_report["classification_counts"]["text"] != 1:
            raise AssertionError(f"normal CP1251 text should pass: {cp1251_report!r}")

        reviewed = root / "reviewed.bin"
        reviewed_bytes = b"\x00\x01reviewed"
        reviewed.write_bytes(reviewed_bytes)
        write_policy(root, [row("reviewed.bin", reviewed_bytes, "binary/octet-stream")])
        reviewed_report = validate_distribution_paths(root, ["reviewed.bin"])
        if reviewed_report["result"] != "PASS" or reviewed_report["classification_counts"]["binary_archive"] != 1:
            raise AssertionError(f"reviewed binary should pass: {reviewed_report!r}")

        reviewed.write_bytes(reviewed_bytes + b"-drift")
        require(validate_distribution_paths(root, ["reviewed.bin"]), "BINARY_REVIEW_HASH_MISMATCH", "hash-drift")

        archive = root / "reviewed.zip"
        archive_bytes = b"PK\x03\x04synthetic"
        archive.write_bytes(archive_bytes)
        write_policy(root, [row("reviewed.zip", archive_bytes, "binary/octet-stream")])
        require(validate_distribution_paths(root, ["reviewed.zip"]), "BINARY_REVIEW_TYPE_MISMATCH", "type-drift")

        unknown_zip = root / "unknown.zip"
        unknown_zip.write_bytes(archive_bytes)
        write_policy(root)
        require(validate_distribution_paths(root, ["unknown.zip"]), "UNKNOWN_BINARY_OR_ARCHIVE", "unknown-archive")

        payload_dir = root / "PAYLOAD"
        payload_dir.mkdir(exist_ok=True)
        too_large = payload_dir / "large.bin.b64.part01"
        too_large.write_text("A" * (BASE64_MAX_ENCODED_BYTES + 4), encoding="ascii")
        large_report = validate_distribution_paths(root, ["PAYLOAD/large.bin.b64.part01"])
        require(large_report, "BASE64_TRANSPORT_TOO_LARGE", "base64-size-bound")

        encoded_archive = base64.b64encode(b"PK\x03\x04synthetic-archive").decode("ascii")
        encoded_path = payload_dir / "archive.bin.b64.part01"
        encoded_path.write_text(encoded_archive, encoding="ascii")
        archive_report = validate_distribution_paths(root, ["PAYLOAD/archive.bin.b64.part01"])
        require(archive_report, "BASE64_TRANSPORT_BINARY_ARCHIVE_FORBIDDEN", "base64-binary-archive")

        encoded_opaque = base64.b64encode(opaque_bytes).decode("ascii")
        opaque_transport = payload_dir / "opaque.dat.b64.part01"
        opaque_transport.write_text(encoded_opaque, encoding="ascii")
        opaque_transport_report = validate_distribution_paths(root, ["PAYLOAD/opaque.dat.b64.part01"])
        require(opaque_transport_report, "BASE64_TRANSPORT_BINARY_ARCHIVE_FORBIDDEN", "base64-opaque-binary")

        third_party = root / "THIRD_PARTY" / "vendor" / "NOTICE.md"
        third_party.parent.mkdir(parents=True)
        notice = ("Contact maintainer" + "@" + "example.org\n").encode("ascii")
        third_party.write_bytes(notice)
        write_policy(root)
        unreviewed = validate_distribution_paths(root, ["THIRD_PARTY/vendor/NOTICE.md"])
        require(unreviewed, "PERSONAL_EMAIL", "third-party-unreviewed-email")

        third_row = {
            "path": "THIRD_PARTY/vendor/NOTICE.md",
            "sha256": hashlib.sha256(notice).hexdigest(),
            "reason": "synthetic exact attribution notice",
            "policy_id": BINARY_REVIEW_POLICY_ID,
        }
        write_policy(root, third_party_rows=[third_row])
        reviewed_notice = validate_distribution_paths(root, ["THIRD_PARTY/vendor/NOTICE.md"])
        if reviewed_notice["result"] != "PASS":
            raise AssertionError(f"exact reviewed attribution should pass: {reviewed_notice!r}")

        third_party.write_bytes(notice + b"drift")
        drift_notice = validate_distribution_paths(root, ["THIRD_PARTY/vendor/NOTICE.md"])
        require(drift_notice, "THIRD_PARTY_ATTRIBUTION_HASH_MISMATCH", "third-party-hash-drift")

        collector = root / "COLLECTOR" / "payload.bin"
        collector.parent.mkdir(parents=True)
        collector.write_bytes(b"\x00collector")
        collector_report = validate_distribution_paths(root, ["COLLECTOR/payload.bin"])
        require(collector_report, "DISTRIBUTION_RESTRICTED_PATH", "collector-excluded")

    print(json.dumps({"result": "PASS", "cases": [
        "unknown-binary", "unknown-extension-opaque", "utf8-text", "cp1251-text",
        "reviewed-binary", "hash-drift", "type-drift", "unknown-archive",
        "base64-size-bound", "base64-binary-archive", "base64-opaque-binary",
        "third-party-exact-attribution", "collector-excluded"
    ]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
