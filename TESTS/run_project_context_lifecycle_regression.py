#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from project_context_lifecycle import validate_lifecycle
from build_project_bootstrap import build as build_bootstrap

cases = json.loads((ROOT / "TESTS/PROJECT_CONTEXT_LIFECYCLE_CASES.json").read_text(encoding="utf-8"))
results = {}
errors = []


def record(case_id: str, ok: bool, details: dict) -> None:
    key = f"project_context_lifecycle:{case_id}"
    results[key] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": key, "details": details})


for case in cases.get("cases", []):
    report = validate_lifecycle(
        {"decisions": case.get("decisions") or []},
        case.get("changed_dependencies") or [],
    )
    error_types = {x.get("type") for x in report.get("errors", [])}
    revalidation = {x.get("decision") for x in report.get("revalidation_required", [])}
    summary = report.get("summary", {})

    mismatches = {}
    if report.get("result") != case.get("expect_result"):
        mismatches["result"] = {"expected": case.get("expect_result"), "actual": report.get("result")}

    required_errors = set(case.get("expect_error_types") or [])
    if not required_errors.issubset(error_types):
        mismatches["missing_error_types"] = sorted(required_errors - error_types)

    expected_revalidation = set(case.get("expect_revalidation") or [])
    if expected_revalidation != revalidation:
        mismatches["revalidation"] = {"expected": sorted(expected_revalidation), "actual": sorted(revalidation)}

    forbidden_revalidation = set(case.get("expect_not_revalidation") or [])
    if forbidden_revalidation & revalidation:
        mismatches["unexpected_revalidation"] = sorted(forbidden_revalidation & revalidation)

    if "expect_active" in case and set(case["expect_active"]) != set(summary.get("active_or_temporary") or []):
        mismatches["active"] = {"expected": sorted(case["expect_active"]), "actual": sorted(summary.get("active_or_temporary") or [])}
    if "expect_stale" in case and set(case["expect_stale"]) != set(summary.get("historical_stale") or []):
        mismatches["stale"] = {"expected": sorted(case["expect_stale"]), "actual": sorted(summary.get("historical_stale") or [])}
    if "expect_revalidation_summary" in case and set(case["expect_revalidation_summary"]) != set(summary.get("revalidation_required") or []):
        mismatches["revalidation_summary"] = {"expected": sorted(case["expect_revalidation_summary"]), "actual": sorted(summary.get("revalidation_required") or [])}

    record(case["id"], not mismatches, {"mismatches": mismatches, "report": report})

knowledge = (ROOT / "KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md").read_text(encoding="utf-8")
template = (ROOT / "TEMPLATES/PROJECT_CONTEXT_TEMPLATE.md").read_text(encoding="utf-8") if (ROOT / "TEMPLATES/PROJECT_CONTEXT_TEMPLATE.md").is_file() else ""
first = (ROOT / "README_FIRST.md").read_text(encoding="utf-8")
bootstrap_knowledge = (ROOT / "KNOWLEDGE/PROJECT_BOOTSTRAP.md").read_text(encoding="utf-8")
required_tokens = [
    "TEMPORARY_COMPROMISE_PROMOTED_TO_INVARIANT",
    "STALE_PROJECT_CONTEXT_REUSE",
    "CONFLICTING_PROJECT_FACT_COEXISTENCE",
    "TECHNICAL_ROUTE_AS_BUSINESS_PREDICATE",
    "CROSS_SYSTEM_PREDICATE_REIMPLEMENTATION",
    "ACTIVE",
    "TEMPORARY",
    "REVALIDATION_REQUIRED",
    "SUPERSEDED",
    "INVALIDATED",
]
missing = [x for x in required_tokens if x not in knowledge]
record("contract_tokens", not missing, {"missing": missing})

# Template integration is deliberately tested here so the lifecycle cannot exist only as detached prose/tooling.
template_tokens = ["## Project decision lifecycle", "decision_key", "TEMPORARY", "SUPERSEDED", "revalidation triggers"]
missing_template = [x for x in template_tokens if x not in template]
record("template_integration", not missing_template, {"missing": missing_template})

# Project context must model Project -> Participants -> Artifacts and direct unpacked 1C artifact roots.
participant_tokens = ["participants:", "artifact identity per participant:", "Target/Main", "Target/Extensions/<extension-id>", "project + participant + artifact"]
missing_participant_template = [x for x in participant_tokens if x not in template]
bootstrap_participant_tokens = ["Participant and artifact identity", "Project → Participant → Artifact", "Target/Main", "Target/Extensions/<extension-id>"]
missing_participant_bootstrap = [x for x in bootstrap_participant_tokens if x not in bootstrap_knowledge]
record(
    "participant_artifact_provenance_integration",
    not missing_participant_template and not missing_participant_bootstrap,
    {"template_missing": missing_participant_template, "bootstrap_missing": missing_participant_bootstrap},
)

# BSP identity cache is baseline/source-root bound.
bsp_tokens = ["## BSP identity", "EXACT | RANGE_ONLY | UNKNOWN | NOT_DETECTED", "baseline_identity:", "source-root/baseline change invalidates"]
missing_bsp = [x for x in bsp_tokens if x not in template]
record("bsp_identity_baseline_binding", not missing_bsp, {"missing": missing_bsp})

# Entrypoint must route long-lived project work into lifecycle validation without polluting URL-only first-turn behavior.
entry_tokens = ["## Project-context freshness for long-lived projects", "KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md", "decision_key", "SUPERSEDED", "technical proxy"]
missing_entry = [x for x in entry_tokens if x not in first]
record("entrypoint_integration", not missing_entry, {"missing": missing_entry})

# Later-task integration must reuse only current relevant durable context rather than restart bootstrap or inherit task-local proposals.
later_task_tokens = [
    "genuinely new task after prior delivery in the same project",
    "build a **new task requirements contract**",
    "Do not inherit previous-task assumptions, proposed solutions or task-local evidence",
    "Revalidate only relevant stale/conflicting decision keys",
    "bind the exact current target/project identity before reusing any prior context or source",
]
missing_later_task = [x for x in later_task_tokens if x not in bootstrap_knowledge]
record("later_task_targeted_reuse_contract", not missing_later_task, {"missing": missing_later_task})

# Cross-system predicate ownership must be executable registry coverage, not Markdown-only advice.
registry = json.loads((ROOT / "RULES/rule_registry.json").read_text(encoding="utf-8-sig"))
integration = next((x for x in registry.get("rules", []) if x.get("id") == "CLEVERENCE_INTEGRATION"), {})
check_ids = {x.get("id") for x in integration.get("checks", [])}
enforcement = set((integration.get("regression") or {}).get("enforcement_cases") or [])
registry_ok = {
    "CLEVERENCE_INTEGRATION_P10",
    "CLEVERENCE_INTEGRATION_P11",
}.issubset(check_ids) and {
    "check:CLEVERENCE_INTEGRATION_P10",
    "check:CLEVERENCE_INTEGRATION_P11",
}.issubset(enforcement)
record("predicate_registry_integration", registry_ok, {"check_ids_present": sorted(check_ids & {"CLEVERENCE_INTEGRATION_P10", "CLEVERENCE_INTEGRATION_P11"}), "enforcement": sorted(enforcement)})

# New project bootstrap must emit a lifecycle ledger entrypoint instead of requiring later ad-hoc reconstruction.
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    source = root / "Module.bsl"
    source.write_text("Процедура Тест()\nКонецПроцедуры\n", encoding="utf-8")
    bootstrap = build_bootstrap([source])
    lifecycle = bootstrap.get("decision_lifecycle") or {}
    bootstrap_ok = (
        bootstrap.get("schema_version") >= 2
        and lifecycle.get("contract") == "KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md"
        and lifecycle.get("validator") == "TOOLS/project_context_lifecycle.py"
        and lifecycle.get("decisions") == []
        and {"ACTIVE", "TEMPORARY", "REVALIDATION_REQUIRED", "SUPERSEDED", "INVALIDATED"}.issubset(set(lifecycle.get("statuses") or []))
        and "record/revalidate/supersede mutable project decisions" in bootstrap.get("next_sequence", [])
    )
    record("bootstrap_integration", bootstrap_ok, {"lifecycle": lifecycle, "next_sequence": bootstrap.get("next_sequence")})

out = {
    "result": "PASS" if not errors else "FAIL",
    "errors": errors,
    "results": results,
    "cases": len(cases.get("cases", [])),
}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
