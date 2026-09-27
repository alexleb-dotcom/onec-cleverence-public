#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys

RECEIPT_SCHEMA_VERSION = 1
RECEIPT_TYPE = "shareable-core-static-validation-v1"
DISTRIBUTION_PROFILE = "SHAREABLE_CORE"
RECEIPT_SCOPE = "SHAREABLE_CORE_STATIC_VALIDATION"
INVENTORY_REL = "TOOLS/PUBLIC_CI_INVENTORY.json"
MANIFEST_REL = "DISTRIBUTION_MANIFEST.json"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SNAPSHOT_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ALLOWED_EVENT_NAMES = {"pull_request", "push", "workflow_dispatch"}
ALLOWED_MODES = {"FAST", "FULL"}
CLAIMS = {
    "shareable_core_static_validation": True,
    "private_full_acceptance": False,
    "runtime_onec_cleverence_proof": False,
    "customer_project_validation": False,
    "redistribution_legal_approval": False,
}
RECEIPT_KEYS = frozenset({
    "schema_version",
    "receipt_type",
    "repository",
    "event_name",
    "pr_number",
    "pr_head_sha",
    "pr_base_sha",
    "checkout_sha",
    "checkout_tree_sha",
    "ordered_checkout_parents",
    "distribution_profile",
    "snapshot_digest",
    "runner_mode",
    "scope",
    "inventory_id",
    "inventory_schema_version",
    "executed_check_ids",
    "result",
    "claims",
})


class ReceiptContractError(ValueError):
    pass


def _load_json(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReceiptContractError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ReceiptContractError(f"{label} must be a JSON object")
    return payload


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ReceiptContractError(f"{label} must be a lowercase 40-hex SHA")
    return value


def _require_snapshot_digest(value: object) -> str:
    if not isinstance(value, str) or not SNAPSHOT_DIGEST_RE.fullmatch(value):
        raise ReceiptContractError("snapshot_digest must be a lowercase 64-hex SHA-256")
    return value


def _git(checkout_root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(checkout_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if process.returncode != 0:
        raise ReceiptContractError(f"git identity command failed: {' '.join(args)}")
    return process.stdout.strip()


def checkout_identity(checkout_root: Path) -> dict:
    checkout_root = checkout_root.resolve()
    checkout_sha = _require_sha(_git(checkout_root, "rev-parse", "HEAD"), "checkout_sha")
    tree_sha = _require_sha(_git(checkout_root, "rev-parse", "HEAD^{tree}"), "checkout_tree_sha")
    parent_text = _git(checkout_root, "show", "-s", "--format=%P", "HEAD")
    parents = [] if not parent_text else [_require_sha(value, "ordered_checkout_parent") for value in parent_text.split()]
    return {
        "checkout_sha": checkout_sha,
        "checkout_tree_sha": tree_sha,
        "ordered_checkout_parents": parents,
    }


def event_context(environ: dict[str, str]) -> tuple[str, str, dict]:
    required = ("GITHUB_REPOSITORY", "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH")
    missing = [name for name in required if not environ.get(name)]
    if missing:
        raise ReceiptContractError("missing required environment variable(s): " + ", ".join(missing))
    repository = environ["GITHUB_REPOSITORY"]
    if not REPOSITORY_RE.fullmatch(repository):
        raise ReceiptContractError("GITHUB_REPOSITORY must be owner/repository")
    event_name = environ["GITHUB_EVENT_NAME"]
    if event_name not in ALLOWED_EVENT_NAMES:
        raise ReceiptContractError("unsupported GITHUB_EVENT_NAME")
    event_path = Path(environ["GITHUB_EVENT_PATH"])
    event = _load_json(event_path, "GitHub event payload")
    event_repository = ((event.get("repository") or {}).get("full_name") if isinstance(event.get("repository"), dict) else None)
    if event_repository is not None and event_repository != repository:
        raise ReceiptContractError("event repository does not match GITHUB_REPOSITORY")
    return repository, event_name, event


def _pr_fields(event_name: str, event: dict) -> dict:
    if event_name != "pull_request":
        return {"pr_number": None, "pr_head_sha": None, "pr_base_sha": None}
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ReceiptContractError("pull_request event is missing pull_request object")
    number = event.get("number", pull_request.get("number"))
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise ReceiptContractError("pull_request number must be a positive integer")
    head = pull_request.get("head")
    base = pull_request.get("base")
    if not isinstance(head, dict) or not isinstance(base, dict):
        raise ReceiptContractError("pull_request head/base identity is missing")
    return {
        "pr_number": number,
        "pr_head_sha": _require_sha(head.get("sha"), "pr_head_sha"),
        "pr_base_sha": _require_sha(base.get("sha"), "pr_base_sha"),
    }


def _expected_check_ids(inventory: dict, mode: str) -> list[str]:
    if mode not in ALLOWED_MODES:
        raise ReceiptContractError("runner_mode must be FAST or FULL")
    if inventory.get("inventory_id") != "public-safe-ci-v1" or inventory.get("schema_version") != 1:
        raise ReceiptContractError("unsupported public CI inventory identity")
    checks = inventory.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ReceiptContractError("public CI inventory checks are missing")
    rows = checks if mode == "FULL" else [row for row in checks if isinstance(row, dict) and row.get("phase") == "FAST"]
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or not all(isinstance(value, str) and value for value in ids):
        raise ReceiptContractError("public CI inventory contains invalid check ids")
    return ids


def _executed_check_ids(run_report: dict, inventory: dict, mode: str) -> list[str]:
    if run_report.get("result") != "PASS":
        raise ReceiptContractError("public CI run report must be PASS before receipt creation")
    if run_report.get("scope") != "PUBLIC_SHAREABLE_CORE_ONLY":
        raise ReceiptContractError("public CI run report scope mismatch")
    if run_report.get("authoritative_private_acceptance") is not False:
        raise ReceiptContractError("public CI run report must not claim private acceptance")
    if run_report.get("mode") != mode:
        raise ReceiptContractError("public CI run report mode mismatch")
    if run_report.get("inventory_id") != inventory.get("inventory_id"):
        raise ReceiptContractError("public CI run report inventory mismatch")
    checks = run_report.get("checks")
    if not isinstance(checks, list):
        raise ReceiptContractError("public CI run report checks are missing")
    ids = []
    for row in checks:
        if not isinstance(row, dict) or row.get("outcome") != "PASS" or not isinstance(row.get("id"), str):
            raise ReceiptContractError("public CI run report contains a non-PASS or malformed check row")
        ids.append(row["id"])
    expected = _expected_check_ids(inventory, mode)
    if ids != expected:
        raise ReceiptContractError("executed check ids do not match canonical inventory for runner mode")
    return ids


def build_receipt(
    *,
    repository: str,
    event_name: str,
    event: dict,
    checkout: dict,
    snapshot_manifest: dict,
    inventory: dict,
    run_report: dict,
    mode: str,
) -> dict:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ReceiptContractError("repository must be owner/repository")
    if event_name not in ALLOWED_EVENT_NAMES:
        raise ReceiptContractError("unsupported event name")
    checkout_sha = _require_sha(checkout.get("checkout_sha"), "checkout_sha")
    tree_sha = _require_sha(checkout.get("checkout_tree_sha"), "checkout_tree_sha")
    parents = checkout.get("ordered_checkout_parents")
    if not isinstance(parents, list):
        raise ReceiptContractError("ordered_checkout_parents must be a list")
    ordered_parents = [_require_sha(value, "ordered_checkout_parent") for value in parents]

    if snapshot_manifest.get("distribution_profile") != DISTRIBUTION_PROFILE:
        raise ReceiptContractError("distribution manifest profile mismatch")
    snapshot_digest = _require_snapshot_digest(snapshot_manifest.get("snapshot_digest"))
    executed_ids = _executed_check_ids(run_report, inventory, mode)

    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "repository": repository,
        "event_name": event_name,
        **_pr_fields(event_name, event),
        "checkout_sha": checkout_sha,
        "checkout_tree_sha": tree_sha,
        "ordered_checkout_parents": ordered_parents,
        "distribution_profile": DISTRIBUTION_PROFILE,
        "snapshot_digest": snapshot_digest,
        "runner_mode": mode,
        "scope": RECEIPT_SCOPE,
        "inventory_id": inventory["inventory_id"],
        "inventory_schema_version": inventory["schema_version"],
        "executed_check_ids": executed_ids,
        "result": "PASS",
        "claims": dict(CLAIMS),
    }
    return receipt


def validate_receipt(receipt: dict, expected: dict) -> dict:
    errors: list[dict] = []
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        return {"result": "FAIL", "errors": [{"type": "PUBLIC_RECEIPT_SCHEMA_MISMATCH"}]}
    if receipt.get("scope") != RECEIPT_SCOPE:
        errors.append({"type": "PUBLIC_RECEIPT_SCOPE_OVERCLAIM"})
    if receipt.get("claims") != CLAIMS:
        errors.append({"type": "PUBLIC_RECEIPT_CLAIMS_OVERCLAIM"})
    if receipt != expected:
        for key in sorted(RECEIPT_KEYS):
            if receipt.get(key) != expected.get(key):
                errors.append({"type": "PUBLIC_RECEIPT_IDENTITY_MISMATCH", "field": key})
    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "scope": RECEIPT_SCOPE,
        "rule": "Receipt proves only SHAREABLE_CORE static validation for the bound event/checkout/snapshot/inventory execution. It never proves private Full acceptance, runtime behavior, customer/project validation, or redistribution/legal approval.",
    }


def _build_expected_from_cli(args: argparse.Namespace) -> dict:
    repository, event_name, event = event_context(os.environ)
    checkout = checkout_identity(Path(args.checkout_root))
    validation_root = Path(args.validation_root).resolve()
    snapshot_manifest = _load_json(validation_root / MANIFEST_REL, "distribution manifest")
    inventory = _load_json(validation_root / INVENTORY_REL, "public CI inventory")
    run_report = _load_json(Path(args.run_report), "public CI run report")
    return build_receipt(
        repository=repository,
        event_name=event_name,
        event=event,
        checkout=checkout,
        snapshot_manifest=snapshot_manifest,
        inventory=inventory,
        run_report=run_report,
        mode=args.mode,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or validate a public-safe SHAREABLE_CORE static execution receipt without privileged API access.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "validate"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--checkout-root", required=True)
        sub.add_argument("--validation-root", required=True)
        sub.add_argument("--run-report", required=True)
        sub.add_argument("--mode", required=True, choices=("FAST", "FULL"))
        if name == "build":
            sub.add_argument("--output", required=True)
        else:
            sub.add_argument("--receipt", required=True)
    args = parser.parse_args()

    try:
        expected = _build_expected_from_cli(args)
        if args.command == "build":
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"result": "PASS", "receipt": str(output), "scope": RECEIPT_SCOPE}, ensure_ascii=False))
            return 0
        receipt = _load_json(Path(args.receipt), "public execution receipt")
        report = validate_receipt(receipt, expected)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["result"] == "PASS" else 2
    except ReceiptContractError as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc), "scope": RECEIPT_SCOPE}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
