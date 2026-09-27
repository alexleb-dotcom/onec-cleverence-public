#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import copy
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from public_execution_receipt import (
    CLAIMS,
    RECEIPT_SCOPE,
    ReceiptContractError,
    build_receipt,
    event_context,
    validate_receipt,
)

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
DIGEST = "1" * 64


def inventory() -> dict:
    return {
        "schema_version": 1,
        "inventory_id": "public-safe-ci-v1",
        "checks": [
            {"id": "one", "phase": "FAST"},
            {"id": "two", "phase": "FAST"},
            {"id": "three", "phase": "FULL"},
        ],
    }


def run_report(mode: str) -> dict:
    ids = ["one", "two"] if mode == "FAST" else ["one", "two", "three"]
    return {
        "result": "PASS",
        "scope": "PUBLIC_SHAREABLE_CORE_ONLY",
        "authoritative_private_acceptance": False,
        "mode": mode,
        "inventory_id": "public-safe-ci-v1",
        "checks": [{"id": value, "outcome": "PASS"} for value in ids],
    }


def snapshot_manifest() -> dict:
    return {"distribution_profile": "SHAREABLE_CORE", "snapshot_digest": DIGEST}


def checkout() -> dict:
    return {
        "checkout_sha": SHA_C,
        "checkout_tree_sha": SHA_D,
        "ordered_checkout_parents": [SHA_B, SHA_A],
    }


def pr_event() -> dict:
    return {
        "number": 61,
        "repository": {"full_name": "example/repo"},
        "pull_request": {"head": {"sha": SHA_A}, "base": {"sha": SHA_B}},
    }


def build(event_name: str, event: dict, mode: str = "FAST") -> dict:
    return build_receipt(
        repository="example/repo",
        event_name=event_name,
        event=event,
        checkout=checkout(),
        snapshot_manifest=snapshot_manifest(),
        inventory=inventory(),
        run_report=run_report(mode),
        mode=mode,
    )


def expect_error(case: str, callback) -> None:
    try:
        callback()
    except ReceiptContractError:
        return
    raise AssertionError(f"{case}: expected ReceiptContractError")


def main() -> int:
    pr = build("pull_request", pr_event())
    assert pr["pr_number"] == 61 and pr["pr_head_sha"] == SHA_A and pr["pr_base_sha"] == SHA_B
    assert pr["ordered_checkout_parents"] == [SHA_B, SHA_A]
    assert pr["scope"] == RECEIPT_SCOPE and pr["claims"] == CLAIMS
    assert pr["executed_check_ids"] == ["one", "two"]
    assert validate_receipt(pr, copy.deepcopy(pr))["result"] == "PASS"

    push = build("push", {"repository": {"full_name": "example/repo"}})
    assert push["pr_number"] is None and push["pr_head_sha"] is None and push["pr_base_sha"] is None

    manual = build("workflow_dispatch", {"repository": {"full_name": "example/repo"}}, mode="FULL")
    assert manual["pr_number"] is None and manual["pr_head_sha"] is None and manual["pr_base_sha"] is None
    assert manual["executed_check_ids"] == ["one", "two", "three"]

    with tempfile.TemporaryDirectory() as td:
        event_path = Path(td) / "event.json"
        event_path.write_text(json.dumps(pr_event()), encoding="utf-8")
        expect_error("missing-env", lambda: event_context({"GITHUB_EVENT_PATH": str(event_path)}))

    bad_checkout = checkout()
    bad_checkout["checkout_sha"] = "not-a-sha"
    expect_error(
        "malformed-sha",
        lambda: build_receipt(
            repository="example/repo",
            event_name="push",
            event={},
            checkout=bad_checkout,
            snapshot_manifest=snapshot_manifest(),
            inventory=inventory(),
            run_report=run_report("FAST"),
            mode="FAST",
        ),
    )

    reversed_parents = copy.deepcopy(pr)
    reversed_parents["ordered_checkout_parents"] = list(reversed(reversed_parents["ordered_checkout_parents"]))
    report = validate_receipt(reversed_parents, pr)
    assert report["result"] == "FAIL"
    assert any(row.get("field") == "ordered_checkout_parents" for row in report["errors"])

    overclaim = copy.deepcopy(pr)
    overclaim["scope"] = "INTERNAL_FULL_ACCEPTANCE"
    overclaim["claims"]["private_full_acceptance"] = True
    report = validate_receipt(overclaim, pr)
    kinds = {row.get("type") for row in report["errors"]}
    assert "PUBLIC_RECEIPT_SCOPE_OVERCLAIM" in kinds and "PUBLIC_RECEIPT_CLAIMS_OVERCLAIM" in kinds

    bad_report = run_report("FAST")
    bad_report["checks"] = list(reversed(bad_report["checks"]))
    expect_error(
        "executed-id-order",
        lambda: build_receipt(
            repository="example/repo",
            event_name="push",
            event={},
            checkout=checkout(),
            snapshot_manifest=snapshot_manifest(),
            inventory=inventory(),
            run_report=bad_report,
            mode="FAST",
        ),
    )

    workflow = (ROOT / ".github/workflows/shareable-validation.yml").read_text(encoding="utf-8")
    required_fragments = [
        'python TOOLS/run_public_ci.py --mode FAST | tee "$RUNNER_TEMP/public-fast-report.json"',
        'python TOOLS/run_public_ci.py --mode FULL | tee "$RUNNER_TEMP/public-full-report.json"',
        'public_execution_receipt.py" build',
        'public_execution_receipt.py" validate',
        '--mode FAST',
        '--mode FULL',
        '--checkout-root "$GITHUB_WORKSPACE"',
        '--validation-root "$VALIDATION_ROOT"',
        'cat "$RUNNER_TEMP/public-fast-receipt.json"',
        'cat "$RUNNER_TEMP/public-full-receipt.json"',
    ]
    missing = [fragment for fragment in required_fragments if fragment not in workflow]
    if missing:
        raise AssertionError(f"workflow receipt integration missing: {missing!r}")
    if "actions/upload-artifact" in workflow:
        raise AssertionError("public receipt must remain in job output; artifact upload is not required")
    if "secrets." in workflow:
        raise AssertionError("public receipt workflow must not depend on secrets")
    if "permissions:\n  contents: read" not in workflow:
        raise AssertionError("public workflow permissions must remain read-only")
    for action in ("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"):
        if action not in workflow:
            raise AssertionError(f"workflow action is not pinned to the reviewed full SHA: {action}")

    print(json.dumps({"result": "PASS", "cases": 9}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
