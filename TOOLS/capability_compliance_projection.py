#!/usr/bin/env python3
"""Derived, non-authoritative real-task capability compliance projection.

This module does not create evidence, execute delivered capabilities, modify release
readiness, or define semantic ownership. It projects existing Registry delivery,
plan recomputation, release-verifier verdicts, and already-existing machine receipts.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import re

from machine_receipts import verify_receipt
from release_gate_core import RESOLUTION_VERIFIER_ID, RESOLUTION_VERIFIER_VERSION
from release_intake import build_plan_from_intake, validate_plan_recomputation
from rule_registry import load_registry

SCHEMA_VERSION = 1
KIND = "DERIVED_CAPABILITY_COMPLIANCE_PROJECTION"
USED_OBSERVED = "OBSERVED_FROM_EXISTING_ARTIFACT"
USED_NOT_OBSERVABLE = "NOT_OBSERVABLE"
VERIFIED_NOT_BOUND = "NOT_BOUND"
_TOOL_RE = re.compile(r"(?<![A-Za-z0-9_./-])(TOOLS/[A-Za-z0-9_./-]+\.py)(?![A-Za-z0-9_./-])")


def _canon(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _load_json(path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _executor_tool(binding: dict) -> str | None:
    payload = binding.get("executor_payload") or {}
    if payload.get("kind") != "INSTRUCTION":
        return None
    value = payload.get("value")
    if not _has_text(value):
        return None
    matches = list(dict.fromkeys(_TOOL_RE.findall(value)))
    return matches[0] if len(matches) == 1 else None


def _candidate_hashes(plan: dict) -> set[str]:
    return {
        row.get("sha256")
        for row in plan.get("candidate_artifacts") or []
        if isinstance(row, dict) and _has_text(row.get("sha256"))
    }


def _machine_usage_observations(binding: dict, ledger: dict, candidate_hashes: set[str]) -> list[dict]:
    """Observe use only from an already-existing, integrity-valid machine receipt.

    replay=False is deliberate: the projection may inspect evidence that already
    exists, but it must never execute a capability just to manufacture USED.
    """
    tool = _executor_tool(binding)
    if not tool or not candidate_hashes:
        return []

    observations = []
    for row in ledger.get("machine_reports") or []:
        if not isinstance(row, dict) or row.get("tool") != tool:
            continue
        report_id = row.get("id")
        receipt_ref = row.get("receipt_ref") or row.get("ref")
        expected_sha = row.get("receipt_sha256")
        if not _has_text(report_id) or not _has_text(receipt_ref) or not _has_text(expected_sha):
            continue
        verification = verify_receipt(receipt_ref, replay=False)
        if verification.get("integrity_result") != "PASS":
            continue
        if verification.get("receipt_sha256") != expected_sha:
            continue
        receipt = verification.get("receipt") or {}
        if receipt.get("tool") != tool:
            continue
        matched = sorted(
            {
                item.get("sha256")
                for item in receipt.get("inputs") or []
                if isinstance(item, dict) and item.get("sha256") in candidate_hashes
            }
        )
        if not matched:
            continue
        observations.append(
            {
                "kind": "MACHINE_RECEIPT",
                "report_id": report_id,
                "tool": tool,
                "receipt_ref": receipt_ref,
                "receipt_sha256": expected_sha,
                "tool_sha256": receipt.get("tool_sha256"),
                "derived_result": verification.get("derived_result"),
                "matched_candidate_sha256": matched,
            }
        )
    return sorted(observations, key=lambda row: (row["report_id"], row["receipt_sha256"]))


def _proof_verification(binding: dict, ledger: dict, release_report: dict) -> dict:
    proof = binding.get("proof_binding")
    if not isinstance(proof, dict):
        return {"VERIFIED": VERIFIED_NOT_BOUND, "proof_owner": None}

    owner = proof.get("owner")
    if not _has_text(owner) or not owner.startswith("CHECK:"):
        return {"VERIFIED": "UNRESOLVED", "proof_owner": owner, "reason": "INVALID_PROOF_OWNER"}

    parts = owner.split(":", 2)
    if len(parts) != 3:
        return {"VERIFIED": "UNRESOLVED", "proof_owner": owner, "reason": "INVALID_PROOF_OWNER"}
    _, rule_id, check_id = parts

    ledger_rule = next(
        (row for row in ledger.get("rules") or [] if isinstance(row, dict) and row.get("id") == rule_id),
        None,
    )
    ledger_check = next(
        (row for row in (ledger_rule or {}).get("checks") or [] if isinstance(row, dict) and row.get("id") == check_id),
        None,
    )
    if ledger_check is None:
        return {"VERIFIED": "UNRESOLVED", "proof_owner": owner, "reason": "LEDGER_PROOF_OWNER_MISSING"}

    verdict = next(
        (
            row
            for row in release_report.get("resolution_verdicts") or []
            if isinstance(row, dict)
            and row.get("scope") == "check"
            and row.get("rule_id") == rule_id
            and row.get("id") == check_id
        ),
        None,
    )
    if not verdict:
        return {"VERIFIED": "UNRESOLVED", "proof_owner": owner, "reason": "VERDICT_MISSING"}
    if verdict.get("disposition") != ledger_check.get("status") or verdict.get("claim_id") != ledger_check.get("claim_id"):
        return {
            "VERIFIED": "UNRESOLVED",
            "proof_owner": owner,
            "reason": "VERDICT_LEDGER_DRIFT",
            "verification_disposition": verdict.get("disposition"),
            "ledger_disposition": ledger_check.get("status"),
            "verification_claim_id": verdict.get("claim_id"),
            "ledger_claim_id": ledger_check.get("claim_id"),
        }

    return {
        "VERIFIED": verdict.get("verdict") or "UNRESOLVED",
        "proof_owner": owner,
        "verification_disposition": verdict.get("disposition"),
        "verification_claim_id": verdict.get("claim_id"),
        "verifier": verdict.get("verifier"),
        "verifier_version": verdict.get("version"),
        "verification_errors": verdict.get("errors") or [],
    }


def _release_report_integrity(release_report: dict) -> list[dict]:
    errors = []
    protocol = release_report.get("resolution_verifier")
    if not isinstance(protocol, dict):
        return [{"type": "CAPABILITY_PROJECTION_RELEASE_VERIFIER_MISSING"}]
    if protocol.get("status") != "AVAILABLE":
        errors.append({"type": "CAPABILITY_PROJECTION_RELEASE_VERIFIER_UNAVAILABLE", "actual": protocol.get("status")})
    if protocol.get("verifier") != RESOLUTION_VERIFIER_ID or protocol.get("version") != RESOLUTION_VERIFIER_VERSION:
        errors.append(
            {
                "type": "CAPABILITY_PROJECTION_RELEASE_VERIFIER_IDENTITY_MISMATCH",
                "expected": {"verifier": RESOLUTION_VERIFIER_ID, "version": RESOLUTION_VERIFIER_VERSION},
                "actual": {"verifier": protocol.get("verifier"), "version": protocol.get("version")},
            }
        )
    if release_report.get("plan_recomputation") != "PASS":
        errors.append({"type": "CAPABILITY_PROJECTION_RELEASE_PLAN_RECOMPUTATION_NOT_PASS", "actual": release_report.get("plan_recomputation")})
    if not isinstance(release_report.get("resolution_verdicts"), list):
        errors.append({"type": "CAPABILITY_PROJECTION_RELEASE_VERDICTS_INVALID"})
    return errors


def build_projection(plan: dict, ledger: dict, release_report: dict, registry: dict | None = None) -> dict:
    registry = registry or load_registry()
    source_identity = {
        "plan_fingerprint_sha256": _fingerprint(plan),
        "ledger_fingerprint_sha256": _fingerprint(ledger),
        "release_report_fingerprint_sha256": _fingerprint(release_report),
        "registry": plan.get("registry"),
        "release_intake_sha256": (plan.get("release_intake") or {}).get("sha256"),
    }
    policy = {
        "authority": "NON_AUTHORITATIVE_DERIVED",
        "release_gate": False,
        "semantic_authority": False,
        "creates_evidence": False,
        "creates_telemetry": False,
        "VERIFIED_does_not_imply_USED": True,
        "USED_does_not_imply_VERIFIED": True,
        "NOT_OBSERVABLE_does_not_mean_NOT_USED": True,
        "observation_absence_is_not_release_failure": True,
        "used_observation_sources": ["EXISTING_MACHINE_RECEIPT"],
    }

    recompute = validate_plan_recomputation(plan)
    integrity_errors = list(recompute.get("errors") or [])
    integrity_errors.extend(_release_report_integrity(release_report))
    if integrity_errors:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "projection_integrity": "FAIL",
            "errors": integrity_errors,
            "source_identity": source_identity,
            "policy": policy,
            "capabilities": [],
        }

    intake = (plan.get("release_intake") or {}).get("manifest")
    recomputed_plan = build_plan_from_intake(intake)
    expected_rows = [row for row in recomputed_plan.get("active_deliveries") or [] if isinstance(row, dict)]
    actual_by_id = {
        row.get("capability_id"): row
        for row in plan.get("active_deliveries") or []
        if isinstance(row, dict) and _has_text(row.get("capability_id"))
    }
    candidate_hashes = _candidate_hashes(plan)

    capabilities = []
    for binding in expected_rows:
        capability_id = binding.get("capability_id")
        observations = _machine_usage_observations(binding, ledger, candidate_hashes)
        verification = _proof_verification(binding, ledger, release_report)
        row = {
            "capability_id": capability_id,
            "owner_rule_id": binding.get("owner_rule_id"),
            "enforcement": binding.get("enforcement"),
            "EXPECTED": True,
            "DELIVERED": capability_id in actual_by_id,
            "USED": USED_OBSERVED if observations else USED_NOT_OBSERVABLE,
            "VERIFIED": verification.pop("VERIFIED"),
            **verification,
        }
        if observations:
            row["usage_observations"] = observations
        capabilities.append(row)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "projection_integrity": "PASS",
        "source_identity": source_identity,
        "release_context": {
            "result": release_report.get("result"),
            "release_outcome": release_report.get("release_outcome"),
            "resolution_verifier": release_report.get("resolution_verifier"),
        },
        "policy": policy,
        "capabilities": capabilities,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Project non-authoritative EXPECTED/DELIVERED/USED/VERIFIED capability compliance from existing task artifacts.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--release-report", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    projection = build_projection(_load_json(args.plan), _load_json(args.ledger), _load_json(args.release_report))
    text = json.dumps(projection, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if projection.get("projection_integrity") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
