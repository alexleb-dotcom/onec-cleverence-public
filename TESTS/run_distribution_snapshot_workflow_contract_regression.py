#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from validate_distribution_snapshot import build_distribution_manifest, validate_snapshot_root

REQUIRED = ".github/workflows/shareable-validation.yml"
FORBIDDEN = (
    "MAINTENANCE/INTERNAL/",
    "REFERENCE/SOURCES/",
    "REFERENCE/INDEXES/",
    "COLLECTOR/",
)


def row(root: Path, rel: str) -> dict:
    data = (root / rel).read_bytes()
    return {"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_manifest(root: Path, paths: list[str]) -> None:
    payload = build_distribution_manifest([row(root, rel) for rel in paths])
    (root / "DISTRIBUTION_MANIFEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def types(report: dict) -> set[str]:
    return {item.get("type") for item in report.get("errors", [])}


def require(report: dict, finding: str, case: str) -> None:
    if finding not in types(report):
        raise AssertionError(f"{case}: expected {finding}, got {report!r}")


def case_exact_workflow_set_passes() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        workflow = root / REQUIRED
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: public\n", encoding="utf-8")
        write_manifest(root, [REQUIRED])
        report = validate_snapshot_root(root)
        if report.get("result") != "PASS":
            raise AssertionError(f"exact workflow set should pass: {report!r}")


def case_extra_workflow_blocks() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (root / REQUIRED).write_text("name: public\n", encoding="utf-8")
        extra = ".github/workflows/extra.yml"
        (root / extra).write_text("name: extra\n", encoding="utf-8")
        write_manifest(root, [REQUIRED, extra])
        require(validate_snapshot_root(root), "SNAPSHOT_PUBLIC_WORKFLOW_SET_MISMATCH", "extra-workflow")


def case_missing_required_workflow_blocks() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a.txt").write_text("a", encoding="utf-8")
        write_manifest(root, ["a.txt"])
        require(validate_snapshot_root(root), "SNAPSHOT_PUBLIC_WORKFLOW_SET_MISMATCH", "missing-required-workflow")


def case_forbidden_dependencies_block() -> None:
    for prefix in FORBIDDEN:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workflow = root / REQUIRED
            workflow.parent.mkdir(parents=True)
            workflow.write_text(f"name: public\njobs:\n  x:\n    run: python {prefix}probe.py\n", encoding="utf-8")
            write_manifest(root, [REQUIRED])
            report = validate_snapshot_root(root)
            require(report, "SNAPSHOT_PUBLIC_WORKFLOW_FORBIDDEN_DEPENDENCY", f"forbidden:{prefix}")
            findings = [x for x in report["errors"] if x.get("type") == "SNAPSHOT_PUBLIC_WORKFLOW_FORBIDDEN_DEPENDENCY"]
            if not any(x.get("dependency_prefix") == prefix for x in findings):
                raise AssertionError(f"forbidden prefix identity missing for {prefix}: {findings!r}")


def main() -> int:
    case_exact_workflow_set_passes()
    case_extra_workflow_blocks()
    case_missing_required_workflow_blocks()
    case_forbidden_dependencies_block()
    print(json.dumps({"result": "PASS", "cases": ["exact", "extra", "missing", "forbidden-dependencies"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
