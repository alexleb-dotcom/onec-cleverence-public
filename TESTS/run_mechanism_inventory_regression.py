#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from mechanism_inventory import build_inventory, build_classification_context, classify_candidate_path
from rule_registry import load_registry, materialize_delivery_applicability, materialize_supporting_artifacts
from build_review_plan import build_plan, compact_summary

errors = []
def require(condition, name, detail=None):
    if not condition:
        errors.append({"test": name, "detail": detail})

report = build_inventory(ROOT)
require(report["result"] == "PASS", "canonical_inventory_pass", report["errors"])
require(report["classification_counts"].get("ORPHAN_UNKNOWN") == 0, "orphan_unknown_zero", report["orphan_unknown_rows"])
require(report["classification_counts"].get("ROUTED_DELIVERY") == 9, "nine_routed_delivery", report["classification_counts"])
require(report["classification_counts"].get("DEPRECATED") == 2, "two_deprecated", report["classification_counts"])
require(report["routed_without_applicability_owner"] == 0, "routed_owner_complete")
require(report["supporting_without_owner"] == 0, "support_owner_complete")
require(report["silent_drop_paths_remaining"] == 0, "silent_drop_zero", report["errors"])

rows = {row.get("path"): row for row in report["rows"] if row.get("path")}
expected = {
    "KNOWLEDGE/CLEVERENCE_COVERAGE_AUDIT.json": ("DEPRECATED", None),
    "KNOWLEDGE/DEVELOPMENT_HANDOFF_WORKFLOW.md": ("SUPPORTING", "WORKFLOW:WORKFLOW/DEVELOPMENT_PIPELINE.json:handoff_contract"),
    "KNOWLEDGE/DYNAMIC_POST_VALIDATION.md": ("SUPPORTING", "GATE:DYNAMIC_POST_VALIDATION"),
    "KNOWLEDGE/KNOWN_RUNTIME_FINDINGS.md": ("SUPPORTING", "RULE:RUNTIME_EVIDENCE"),
    "KNOWLEDGE/OFFICIAL_REFERENCE_NOTES.md": ("SUPPORTING", "GATE:EXTERNAL_ITS_DISCOVERY"),
    "KNOWLEDGE/OFFICIAL_STANDARD_CATALOG.json": ("SUPPORTING", "RULE:BIDIRECTIONAL_STANDARDS"),
    "KNOWLEDGE/QUERY_LANGUAGE_GUIDE.md": ("SUPPORTING", "RULE:QUERY"),
    "KNOWLEDGE/QUERY_TOPOLOGY_REVIEW.md": ("SUPPORTING", "RULE:QUERY"),
    "KNOWLEDGE/STANDARDS_TRIGGER_MAP.json": ("SUPPORTING", "RULE:BIDIRECTIONAL_STANDARDS"),
    "TEMPLATES/FUNCTIONAL_CONTRACT_TEMPLATE.json": ("SUPPORTING", "WORKFLOW:WORKFLOW/DEVELOPMENT_PIPELINE.json:functional_contract_template"),
    "TEMPLATES/PROJECT_SNAPSHOT_COLLECTION_PLAN.json": ("SUPPORTING", "WORKFLOW:WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json:collection_plan_template"),
    "TEMPLATES/PROJECT_SNAPSHOT_MANIFEST.json": ("DEPRECATED", None),
    "TEMPLATES/VALIDATION_LEDGER_TEMPLATE.json": ("SUPPORTING", "WORKFLOW:WORKFLOW/DEVELOPMENT_PIPELINE.json:validation_ledger_template"),
}
for path, (classification, owner) in expected.items():
    row = rows.get(path)
    require(row is not None, f"resolved_row_present:{path}")
    if row:
        require(row.get("classification") == classification, f"resolved_class:{path}", row)
        if owner:
            require(row.get("canonical_owner") == owner, f"resolved_owner:{path}", row)

registry = load_registry()
context = build_classification_context(ROOT, registry)
for path in ("TOOLS/new_unclassified_analyzer.py", "KNOWLEDGE/NEW_TASK_GUIDE.md"):
    classification, _ = classify_candidate_path(path, context)
    require(classification == "ORPHAN_UNKNOWN", f"new_mechanism_fails_closed:{path}", classification)

# All-candidate applicability emits exactly one explicit disposition for all nine.
inactive_routes = [
    {"id": rule["id"], "active": False, "tier": rule.get("tier", 1), "detected_by": [], "reason": "test"}
    for rule in registry["rules"]
]
inactive = materialize_delivery_applicability(registry, inactive_routes, "ONEC_ONLY")
require(len(inactive) == 9, "all_candidate_applicability_count", len(inactive))
require(all(row["status"] in {"APPLICABLE", "NOT_APPLICABLE", "NOT_EVALUATED"} for row in inactive), "all_candidate_status_domain")
missing_routes = inactive_routes[1:]
missing = materialize_delivery_applicability(registry, missing_routes, "ONEC_ONLY")
require(any(row["status"] == "NOT_EVALUATED" for row in missing), "missing_owner_route_not_evaluated")
require(all(row["status"] != "APPLICABLE" or row["capability_id"] for row in missing), "no_implicit_applicable")

# Real plan proves applicable set equality and active support reachability.
fixture = ROOT / "TESTS" / "fixtures" / "query_field_good.bsl"
plan = build_plan([str(fixture)], analysis_only=True, surface_override="ONEC_ONLY", risk_override="R1_CONTRACT")
applicable = {row["capability_id"] for row in plan["delivery_applicability"] if row["status"] == "APPLICABLE"}
active = {row["capability_id"] for row in plan["active_deliveries"]}
require(applicable == active, "applicable_equals_active_delivery", {"applicable": sorted(applicable), "active": sorted(active)})
refs = set((plan.get("context_load_plan") or {}).get("references") or [])
for rel in (
    "KNOWLEDGE/QUERY_LANGUAGE_GUIDE.md",
    "KNOWLEDGE/QUERY_TOPOLOGY_REVIEW.md",
    "KNOWLEDGE/KNOWN_RUNTIME_FINDINGS.md",
    "KNOWLEDGE/DYNAMIC_POST_VALIDATION.md",
    "KNOWLEDGE/OFFICIAL_REFERENCE_NOTES.md",
):
    require(rel in refs, f"active_support_reachable:{rel}", sorted(refs))
for rel in (
    "KNOWLEDGE/CLEVERENCE_COVERAGE_AUDIT.json",
    "TEMPLATES/PROJECT_SNAPSHOT_MANIFEST.json",
):
    require(rel not in refs, f"deprecated_not_reachable:{rel}")

compact_bytes = len(json.dumps(compact_summary(plan), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
require(compact_bytes <= 12 * 1024, "compact_context_12k", compact_bytes)

development = json.loads((ROOT / "WORKFLOW/DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
snapshot = json.loads((ROOT / "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json").read_text(encoding="utf-8"))
require(development.get("handoff_contract") == "KNOWLEDGE/DEVELOPMENT_HANDOFF_WORKFLOW.md", "workflow_handoff_binding")
require(development.get("functional_contract_template") == "TEMPLATES/FUNCTIONAL_CONTRACT_TEMPLATE.json", "workflow_functional_template_binding")
require(development.get("validation_ledger_template") == "TEMPLATES/VALIDATION_LEDGER_TEMPLATE.json", "workflow_ledger_template_binding")
require(snapshot.get("collection_plan_template") == "TEMPLATES/PROJECT_SNAPSHOT_COLLECTION_PLAN.json", "snapshot_collection_plan_binding")

# Registry support metadata is consumed by the same derived projection used by the planner.
gate_plan = plan["gate_plan"]
materialized_support = {row["path"] for row in materialize_supporting_artifacts(registry, plan["rules"], gate_plan)}
require({
    "KNOWLEDGE/QUERY_LANGUAGE_GUIDE.md",
    "KNOWLEDGE/QUERY_TOPOLOGY_REVIEW.md",
}.issubset(materialized_support), "registry_support_materialized")

tool_text = (ROOT / "TOOLS/mechanism_inventory.py").read_text(encoding="utf-8")
require("Workbench" not in tool_text and "GROUPTRADE" not in tool_text.upper(), "no_workbench_grouptrade_dependency")

out = {
    "result": "PASS" if not errors else "FAIL",
    "errors": errors,
    "inventory": {
        "rows": report["discovered_mechanism_rows"],
        "classification_counts": report["classification_counts"],
        "orphan_unknown": len(report["orphan_unknown_rows"]),
    },
    "compact_context_bytes": compact_bytes,
}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
