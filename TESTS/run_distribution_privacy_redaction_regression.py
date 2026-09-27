#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "TOOLS" / "validate_distribution_privacy.py"


def run_case(root: Path, secret: str, prefix: str = "") -> tuple[dict, subprocess.CompletedProcess[str]]:
    target = root / "secret.txt"
    target.write_text(prefix + secret + "\n", encoding="utf-8")
    files_json = root / "files.json"
    files_json.write_text(json.dumps(["secret.txt"]), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(root), "--files-json", str(files_json)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    report = json.loads(proc.stdout)
    return report, proc


def token_finding(report: dict) -> dict:
    rows = [row for row in report.get("errors", []) if row.get("type") == "HIGH_CONFIDENCE_ACCESS_TOKEN"]
    if len(rows) != 1:
        raise AssertionError(f"expected one token finding, got {rows!r}")
    return rows[0]


def assert_redacted(report: dict, proc: subprocess.CompletedProcess[str], secret: str) -> dict:
    if proc.returncode != 2 or report.get("result") != "FAIL":
        raise AssertionError(f"secret must fail validation: rc={proc.returncode} report={report!r}")
    combined = proc.stdout + proc.stderr
    if secret in combined:
        raise AssertionError("raw synthetic secret leaked to captured stdout/stderr")
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if secret in serialized:
        raise AssertionError("raw synthetic secret leaked to JSON report")
    finding = token_finding(report)
    forbidden_keys = {"value", "match", "prefix", "suffix", "length", "digest", "secret_hash"}
    leaked_keys = sorted(forbidden_keys & set(finding))
    if leaked_keys:
        raise AssertionError(f"finding exposes secret-derived fields: {leaked_keys}")
    if set(finding) != {"type", "path", "rule_id", "finding_id"}:
        raise AssertionError(f"unexpected public finding shape: {finding!r}")
    if not finding["finding_id"].startswith("privacy-finding-v1:"):
        raise AssertionError(f"missing versioned finding id: {finding!r}")
    return finding


def main() -> int:
    secret_a = "ghp_" + ("R" * 24)
    secret_b = "ghp_" + ("S" * 24)
    secret_c = "ghp_" + ("T" * 40)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        report1, proc1 = run_case(root, secret_a)
        finding1 = assert_redacted(report1, proc1, secret_a)

        report2, proc2 = run_case(root, secret_a)
        finding2 = assert_redacted(report2, proc2, secret_a)
        if finding1["finding_id"] != finding2["finding_id"]:
            raise AssertionError("same finding location must have stable id")

        report3, proc3 = run_case(root, secret_b)
        finding3 = assert_redacted(report3, proc3, secret_b)
        if finding1["finding_id"] != finding3["finding_id"]:
            raise AssertionError("changing same-length secret at the same position must not change finding id")

        report_length, proc_length = run_case(root, secret_c)
        finding_length = assert_redacted(report_length, proc_length, secret_c)
        if finding1["finding_id"] != finding_length["finding_id"]:
            raise AssertionError("changing secret length at the same position must not change finding id")

        report4, proc4 = run_case(root, secret_a, prefix="x=")
        finding4 = assert_redacted(report4, proc4, secret_a)
        if finding1["finding_id"] == finding4["finding_id"]:
            raise AssertionError("different finding position must produce a different id")

    print(json.dumps({"result": "PASS", "rule": "privacy findings never expose raw secret material or secret-derived digests"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
