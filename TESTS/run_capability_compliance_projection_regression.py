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

import machine_receipts
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

    original_run = machine_receipts._run
    def forbidden_replay(*args, **kwargs):
        raise AssertionError("P2 projection must not replay a machine receipt")
    machine_receipts._run = forbidden_replay
    try:
        observed_projection = build_projection(plan, observed_ledger, observed_release)
    finally:
        machine_receipts._run = original_run

    observed_row = by_capability(observed_projection)["CAP.ONEC_BSL_ANALYSIS"]
    require(observed_row["USED"] == USED_OBSERVED, "existing receipt must yield observed use", observed_row)
    require(observed_row["VERIFIED"] == VERIFIED_NOT_BOUND, "observed advisory use must not invent verification", observed_row)
    observation = observed_row.get("usage_observations", [None])[0]
    require(observation and observation["receipt_sha256"] == receipt_sha, "usage observation must carry artifact identity", observation)

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

# A stale/mutated verdict cannot be projected as current VERIFIED when it disagrees with the ledger row.
drift_release = copy.deepcopy(release)
drift_target = next((row for row in drift_release.get("resolution_verdicts") or [] if row.get("scope") == "check" and row.get("rule_id") and row.get("id")), None)
require(drift_target is not None, "release report must expose a check verdict")
drift_target["disposition"] = "PASS" if drift_target.get("disposition") != "PASS" else "NOT_APPLICABLE"
drift_projection = build_projection(plan, ledger, drift_release)
drift_rows = by_capability(drift_projection)
drift_gating = next((row for row in drift_rows.values() if row.get("proof_owner") == f"CHECK:{drift_target['rule_id']}:{drift_target['id']}"), None)
if drift_gating is not None:
    require(drift_gating["VERIFIED"] == "UNRESOLVED" and drift_gating.get("reason") == "VERDICT_LEDGER_DRIFT", "verdict/ledger drift must not project VERIFIED", drift_gating)

# Release-verifier identity/protocol drift makes the projection itself invalid, not release-blocking.
bad_release = copy.deepcopy(release)
bad_release["resolution_verifier"]["version"] = int(bad_release["resolution_verifier"]["version"]) + 1
bad_projection = build_projection(plan, ledger, bad_release)
require(bad_projection.get("projection_integrity") == "FAIL", "verifier protocol drift must fail projection integrity", bad_projection)

print(json.dumps({
    "result": "PASS",
    "cases": 9,
    "projection_kind": KIND,
    "policy": projection["policy"],
}, ensure_ascii=False, indent=2))
