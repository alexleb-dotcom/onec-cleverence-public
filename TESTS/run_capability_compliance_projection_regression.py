#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "TESTS" / "fixtures"
sys.path.insert(0, str(ROOT / "TOOLS"))

import capability_compliance_projection as capability_projection
from build_review_plan import build_plan
from build_validation_ledger import build_ledger
from capability_compliance_projection import (
    KIND,
    USED_NOT_OBSERVABLE,
    USED_OBSERVED,
    VERIFIED_NOT_BOUND,
    build_projection,
)
from machine_receipts import create_receipt
from release_gate_core import evaluate as release_evaluate


def require(condition: bool, message: str, details=None) -> None:
    if not condition:
        raise AssertionError(f"{message}: {details!r}")


scenario_ids: list[str] = []


def by_capability(projection: dict) -> dict[str, dict]:
    return {row["capability_id"]: row for row in projection.get("capabilities") or []}


def derived_outputs(rows: list[dict]) -> tuple[list[str], list[str]]:
    tools: list[str] = []
    refs: list[str] = []
    for row in rows:
        payload = row.get("executor_payload") or {}
        if payload.get("kind") == "INSTRUCTION":
            value = payload.get("value")
            if isinstance(value, str) and value and value not in tools:
                tools.append(value)
        for ref in row.get("references") or []:
            if ref not in refs:
                refs.append(ref)
    return tools, refs


source = FIXTURES / "call_contract_nonexport_caller.bsl"
plan = build_plan([source], analysis_only=True)
ledger = build_ledger(plan)
release = release_evaluate(plan, ledger)
projection = build_projection(plan, ledger, release)

expected_release_identity = {
    "plan_sha256": hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    "ledger_sha256": hashlib.sha256(json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
}
require(release.get("input_identity") == expected_release_identity, "canonical release report must bind exact plan + ledger", release.get("input_identity"))

require(projection.get("projection_integrity") == "PASS", "fresh projection must be structurally valid", projection)
require(projection.get("kind") == KIND, "projection kind", projection.get("kind"))
require(projection["policy"]["authority"] == "NON_AUTHORITATIVE_DERIVED", "projection must be non-authoritative")
require(projection["policy"]["release_gate"] is False, "projection must not be a release gate")
require(projection["policy"]["creates_evidence"] is False and projection["policy"]["creates_telemetry"] is False, "projection must not create proof/telemetry")

rows = by_capability(projection)
require("CAP.ONEC_BSL_ANALYSIS" in rows, "ONEC BSL advisory capability must be expected", rows)
advisory = rows["CAP.ONEC_BSL_ANALYSIS"]
require(advisory["EXPECTED"] is True and advisory["DELIVERED"] is True, "advisory expected/delivered state", advisory)
require(advisory["USED"] == USED_NOT_OBSERVABLE, "no existing receipt means usage is not observable", advisory)
require(advisory["VERIFIED"] == VERIFIED_NOT_BOUND, "advisory verification must remain NOT_BOUND", advisory)

gating_rows = [row for row in rows.values() if row.get("enforcement") == "GATING"]
require(bool(gating_rows), "fixture must route at least one GATING capability", rows)
require(all(row["VERIFIED"] in {"UNRESOLVED", "REJECTED", "ACCEPTED"} for row in gating_rows), "GATING verification must come from verifier verdict vocabulary", gating_rows)
scenario_ids.append("canonical_projection")

# ADVISORY omission is legal delivery behavior: it remains EXPECTED but not DELIVERED.
omitted_plan = copy.deepcopy(plan)
omitted_plan["active_deliveries"] = [
    row for row in omitted_plan.get("active_deliveries") or []
    if row.get("capability_id") != "CAP.ONEC_BSL_ANALYSIS"
]
tools, refs = derived_outputs(omitted_plan["active_deliveries"])
omitted_plan["deterministic_tools"] = tools
omitted_plan.setdefault("context_load_plan", {})["references"] = refs
omitted_ledger = build_ledger(omitted_plan)
omitted_release = release_evaluate(omitted_plan, omitted_ledger)
omitted_projection = build_projection(omitted_plan, omitted_ledger, omitted_release)
require(omitted_projection.get("projection_integrity") == "PASS", "canonical advisory omission must remain projectable", omitted_projection)
omitted_row = by_capability(omitted_projection)["CAP.ONEC_BSL_ANALYSIS"]
require(omitted_row["EXPECTED"] is True and omitted_row["DELIVERED"] is False, "EXPECTED and DELIVERED must stay distinct", omitted_row)
scenario_ids.append("advisory_omission")

# An existing identity-bound machine receipt may observe use. Projection must not replay it.
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    receipt_path = root / "machine.json"
    receipt = create_receipt(
        "TOOLS/analyze_onec_bsl.py",
        [str(source)],
        [str(source)],
        ["STATIC:ONEC_BSL"],
        receipt_path,
    )
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    observed_ledger = copy.deepcopy(ledger)
    observed_ledger["machine_reports"] = [{
        "id": "MACHINE:P2:OBSERVED",
        "tool": "TOOLS/analyze_onec_bsl.py",
        "ref": str(receipt_path),
        "receipt_ref": str(receipt_path),
        "receipt_sha256": receipt_sha,
        "result": receipt["derived_result"],
        "supersedes": [],
    }]
    observed_release = release_evaluate(plan, observed_ledger)

    original_verify_receipt = capability_projection.verify_receipt
    def usage_observation_verify_receipt(path_value, replay=True):
        require(replay is False, "P2 USED observation path must never request machine-receipt replay", {"path": str(path_value), "replay": replay})
        return original_verify_receipt(path_value, replay=replay)
    capability_projection.verify_receipt = usage_observation_verify_receipt
    try:
        observed_projection = build_projection(plan, observed_ledger, observed_release)
    finally:
        capability_projection.verify_receipt = original_verify_receipt

    observed_row = by_capability(observed_projection)["CAP.ONEC_BSL_ANALYSIS"]
    require(observed_row["USED"] == USED_OBSERVED, "existing receipt must yield observed use", observed_row)
    require(observed_row["VERIFIED"] == VERIFIED_NOT_BOUND, "observed advisory use must not invent verification", observed_row)
    observation = observed_row.get("usage_observations", [None])[0]
    require(observation and observation["receipt_sha256"] == receipt_sha, "usage observation must carry artifact identity", observation)
    scenario_ids.append("existing_receipt_usage_observation")

    # A receipt for a different candidate identity is not usage observation for this task.
    other = root / "other.bsl"
    other.write_text(source.read_text(encoding="utf-8") + "\n// different candidate identity\n", encoding="utf-8")
    stale_path = root / "stale.json"
    stale = create_receipt(
        "TOOLS/analyze_onec_bsl.py",
        [str(other)],
        [str(other)],
        ["STATIC:ONEC_BSL"],
        stale_path,
    )
    stale_sha = hashlib.sha256(stale_path.read_bytes()).hexdigest()
    stale_ledger = copy.deepcopy(ledger)
    stale_ledger["machine_reports"] = [{
        "id": "MACHINE:P2:STALE",
        "tool": "TOOLS/analyze_onec_bsl.py",
        "ref": str(stale_path),
        "receipt_ref": str(stale_path),
        "receipt_sha256": stale_sha,
        "result": stale["derived_result"],
        "supersedes": [],
    }]
    stale_release = release_evaluate(plan, stale_ledger)
    stale_projection = build_projection(plan, stale_ledger, stale_release)
    stale_row = by_capability(stale_projection)["CAP.ONEC_BSL_ANALYSIS"]
    require(stale_row["USED"] == USED_NOT_OBSERVABLE, "other candidate receipt cannot observe current task use", stale_row)
    scenario_ids.append("stale_receipt_not_observed")

# A supplied report whose disposition drifts from the canonical Release Gate is rejected.
drift_release = copy.deepcopy(release)
drift_target = next((row for row in drift_release.get("resolution_verdicts") or [] if row.get("scope") == "check" and row.get("rule_id") and row.get("id")), None)
require(drift_target is not None, "release report must expose a check verdict")
drift_target["disposition"] = "PASS" if drift_target.get("disposition") != "PASS" else "NOT_APPLICABLE"
drift_projection = build_projection(plan, ledger, drift_release)
require(
    drift_projection.get("projection_integrity") == "FAIL"
    and any(row.get("type") == "CAPABILITY_PROJECTION_RELEASE_CANONICAL_DRIFT" for row in drift_projection.get("errors") or []),
    "disposition-mutated release report must fail canonical release comparison",
    drift_projection,
)
scenario_ids.append("release_disposition_drift_rejected")

# Review remediation P2-01: mutate only one GATING proof-owner verdict value while
# preserving exact plan/ledger identity, claim, disposition and verifier metadata.
gating_owner = next(
    (
        (row.get("proof_binding") or {}).get("owner")
        for row in plan.get("active_deliveries") or []
        if row.get("enforcement") == "GATING" and (row.get("proof_binding") or {}).get("owner")
    ),
    None,
)
require(gating_owner and gating_owner.startswith("CHECK:"), "fixture must expose a GATING check proof owner", gating_owner)
_, bound_rule_id, bound_check_id = gating_owner.split(":", 2)
verdict_only_release = copy.deepcopy(release)
verdict_only_target = next(
    (
        row for row in verdict_only_release.get("resolution_verdicts") or []
        if row.get("scope") == "check" and row.get("rule_id") == bound_rule_id and row.get("id") == bound_check_id
    ),
    None,
)
require(verdict_only_target is not None, "canonical release report must contain the GATING proof-owner verdict", gating_owner)
preserved = {
    "scope": verdict_only_target.get("scope"),
    "rule_id": verdict_only_target.get("rule_id"),
    "id": verdict_only_target.get("id"),
    "claim_id": verdict_only_target.get("claim_id"),
    "disposition": verdict_only_target.get("disposition"),
    "input_identity": copy.deepcopy(verdict_only_release.get("input_identity")),
    "resolution_verifier": copy.deepcopy(verdict_only_release.get("resolution_verifier")),
    "plan_recomputation": verdict_only_release.get("plan_recomputation"),
}
verdict_only_target["verdict"] = "ACCEPTED" if verdict_only_target.get("verdict") != "ACCEPTED" else "REJECTED"
require(
    {
        "scope": verdict_only_target.get("scope"),
        "rule_id": verdict_only_target.get("rule_id"),
        "id": verdict_only_target.get("id"),
        "claim_id": verdict_only_target.get("claim_id"),
        "disposition": verdict_only_target.get("disposition"),
        "input_identity": verdict_only_release.get("input_identity"),
        "resolution_verifier": verdict_only_release.get("resolution_verifier"),
        "plan_recomputation": verdict_only_release.get("plan_recomputation"),
    } == preserved,
    "P2-01 regression must mutate only verdict value",
)
verdict_only_projection = build_projection(plan, ledger, verdict_only_release)
require(
    verdict_only_projection.get("projection_integrity") == "FAIL"
    and any(
        row.get("type") == "CAPABILITY_PROJECTION_RELEASE_CANONICAL_DRIFT"
        and "resolution_verdicts" in (row.get("changed_fields") or [])
        for row in verdict_only_projection.get("errors") or []
    ),
    "verdict-only mutation must fail against recomputed canonical Release Gate verdicts",
    verdict_only_projection,
)
scenario_ids.append("release_verdict_only_drift_rejected")

# A release report for a different ledger cannot supply VERIFIED for the current task.
stale_ledger = copy.deepcopy(ledger)
stale_ledger["knowledge_extraction"]["reason"] = "post-release-report synthetic ledger drift"
stale_report_projection = build_projection(plan, stale_ledger, release)
require(
    stale_report_projection.get("projection_integrity") == "FAIL"
    and any(row.get("type") == "CAPABILITY_PROJECTION_RELEASE_INPUT_IDENTITY_MISMATCH" for row in stale_report_projection.get("errors") or []),
    "release report must be identity-bound to the exact current ledger",
    stale_report_projection,
)
scenario_ids.append("stale_ledger_release_report_rejected")

# Release-verifier identity/protocol drift makes the projection itself invalid, not release-blocking.
bad_release = copy.deepcopy(release)
bad_release["resolution_verifier"]["version"] = int(bad_release["resolution_verifier"]["version"]) + 1
bad_projection = build_projection(plan, ledger, bad_release)
require(bad_projection.get("projection_integrity") == "FAIL", "verifier protocol drift must fail projection integrity", bad_projection)
scenario_ids.append("release_verifier_protocol_drift_rejected")

print(json.dumps({
    "result": "PASS",
    "scenario_count": len(scenario_ids),
    "scenario_ids": scenario_ids,
    "projection_kind": KIND,
    "policy": projection["policy"],
}, ensure_ascii=False, indent=2))
