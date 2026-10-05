#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from validate_distribution_snapshot import _path_collision_findings, build_distribution_manifest, validate_snapshot_root


def row(root: Path, rel: str) -> dict:
    data = (root / rel).read_bytes()
    return {"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_manifest(root: Path, rows: list[dict]) -> None:
    payload = build_distribution_manifest(rows)
    (root / "DISTRIBUTION_MANIFEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def types(report: dict) -> set[str]:
    return {item.get("type") for item in report.get("errors", [])}


def require_finding(case: str, report: dict, finding: str) -> None:
    if finding not in types(report):
        raise AssertionError(f"{case}: expected {finding}, got {report!r}")


def case_casefold_collision() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "A.txt").write_text("upper", encoding="utf-8")
        (root / "a.txt").write_text("lower", encoding="utf-8")
        rows = [row(root, "A.txt"), row(root, "a.txt")]
        write_manifest(root, rows)
        require_finding("casefold", validate_snapshot_root(root), "SNAPSHOT_PATH_IDENTITY_COLLISION")


def case_nfc_collision() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nfc = "caf\u00e9.txt"
        nfd = "cafe\u0301.txt"
        assert unicodedata.normalize("NFC", nfc).casefold() == unicodedata.normalize("NFC", nfd).casefold()
        (root / nfc).write_text("nfc", encoding="utf-8")
        (root / nfd).write_text("nfd", encoding="utf-8")
        rows = [row(root, nfc), row(root, nfd)]
        write_manifest(root, rows)
        require_finding("nfc", validate_snapshot_root(root), "SNAPSHOT_PATH_IDENTITY_COLLISION")


def case_file_directory_collision() -> None:
    # A case-insensitive filesystem cannot materialize both a file "Docs" and a
    # directory "docs". Exercise the canonical path-identity contract directly
    # so this regression is portable while still proving the validator rejects
    # that manifest identity.
    findings = _path_collision_findings(["Docs", "docs/readme.txt"], source="manifest")
    report = {"errors": findings}
    require_finding("file-directory", report, "SNAPSHOT_FILE_DIRECTORY_COLLISION")


def main() -> int:
    case_casefold_collision()
    case_nfc_collision()
    case_file_directory_collision()
    print(json.dumps({"result": "PASS", "cases": ["casefold", "nfc", "file-directory"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
