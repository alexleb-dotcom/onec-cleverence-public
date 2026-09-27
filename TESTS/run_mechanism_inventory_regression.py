#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import hashlib
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from mechanism_inventory import (
    build_inventory,
    build_classification_context,
    classify_candidate_path,
    _internal_tool_closure,
    _root_task_entrypoints,
)
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
require(
    report.get("root_task_entrypoints") == _root_task_entrypoints(ROOT),
    "root_entrypoint_set_derived",
    {"report": report.get("root_task_entrypoints"), "derived": _root_task_entrypoints(ROOT)},
)
require(
    report.get("root_task_entrypoints_all_independently_owned") is True,
    "current_root_entrypoints_all_independently_owned",
    {"owners": report.get("root_task_entrypoint_owners"), "errors": report.get("errors")},
)

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

# A regression test must never legitimize the tool it tests.
with tempfile.TemporaryDirectory() as td:
    synthetic_root = Path(td)
    (synthetic_root / "TOOLS").mkdir()
    (synthetic_root / "TESTS").mkdir()
    synthetic_tool = synthetic_root / "TOOLS" / "task_facing_new_analyzer.py"
    synthetic_test = synthetic_root / "TESTS" / "run_task_facing_new_analyzer_regression.py"
    synthetic_tool.write_text("def analyze():\n    return 'task-facing'\n", encoding="utf-8")
    synthetic_test.write_text("import task_facing_new_analyzer\n", encoding="utf-8")

    with_test_internal = _internal_tool_closure(synthetic_root, {})
    with_test_class, _ = classify_candidate_path(
        "TOOLS/task_facing_new_analyzer.py",
        {"support_owners": {}, "internal_tools": with_test_internal},
    )
    require(
        with_test_class == "ORPHAN_UNKNOWN",
        "test_import_only_tool_fails_closed",
        {"classification": with_test_class, "internal_tools": sorted(with_test_internal)},
    )

    synthetic_test.unlink()
    without_test_internal = _internal_tool_closure(synthetic_root, {})
    without_test_class, _ = classify_candidate_path(
        "TOOLS/task_facing_new_analyzer.py",
        {"support_owners": {}, "internal_tools": without_test_internal},
    )
    require(
        without_test_class == "ORPHAN_UNKNOWN",
        "unowned_tool_without_test_fails_closed",
        {"classification": without_test_class, "internal_tools": sorted(without_test_internal)},
    )
    require(
        with_test_class == without_test_class,
        "test_presence_cannot_promote_unowned_tool",
        {"with_test": with_test_class, "without_test": without_test_class},
    )

# Canonical pipeline ownership and transitive pipeline-helper reachability remain intact.
for rel in (
    "TOOLS/capability_compliance_projection.py",
    "TOOLS/skill_freshness.py",
):
    classification, owner = classify_candidate_path(rel, context)
    require(
        classification == "PIPELINE_INTERNAL",
        f"explicit_pipeline_internal_preserved:{rel}",
        {"classification": classification, "owner": owner},
    )

transitive_rel = "TOOLS/validate_public_ci_inventory.py"
transitive_class, transitive_owner = classify_candidate_path(transitive_rel, context)
require(
    transitive_class == "PIPELINE_INTERNAL" and transitive_owner == "PIPELINE_REACHABILITY",
    "canonical_transitive_pipeline_helper_preserved",
    {"path": transitive_rel, "classification": transitive_class, "owner": transitive_owner},
)

# The full inventory itself must fail closed when the test-import-only tool enters the governed surface.
with tempfile.TemporaryDirectory() as td:
    copied_root = Path(td) / "repo"
    shutil.copytree(
        ROOT,
        copied_root,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
    )
    synthetic_tool = copied_root / "TOOLS" / "task_facing_new_analyzer.py"
    synthetic_test = copied_root / "TESTS" / "run_task_facing_new_analyzer_regression.py"
    synthetic_tool.write_text("def analyze():\n    return 'task-facing'\n", encoding="utf-8")
    synthetic_test.write_text("import task_facing_new_analyzer\n", encoding="utf-8")

    manifest_path = copied_root / "DISTRIBUTION_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for path in (synthetic_tool, synthetic_test):
        rel = path.relative_to(copied_root).as_posix()
        raw = path.read_bytes()
        manifest["files"].append({
            "path": rel,
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    manifest["files"] = sorted(manifest["files"], key=lambda row: row["path"])
    manifest["file_count"] = len(manifest["files"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    synthetic_report = build_inventory(copied_root)
    require(
        synthetic_report["result"] == "FAIL",
        "inventory_check_fails_closed_for_test_import_only_tool",
        synthetic_report,
    )
    require(
        "TOOLS/task_facing_new_analyzer.py" in synthetic_report["orphan_unknown_rows"],
        "inventory_reports_test_import_only_tool_as_orphan",
        synthetic_report["orphan_unknown_rows"],
    )

def _manifest_add_file(root: Path, path: Path) -> None:
    manifest_path = root / "DISTRIBUTION_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rel = path.relative_to(root).as_posix()
    raw = path.read_bytes()
    manifest["files"] = [row for row in manifest["files"] if row.get("path") != rel]
    manifest["files"].append({
        "path": rel,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    })
    manifest["files"] = sorted(manifest["files"], key=lambda row: row["path"])
    manifest["file_count"] = len(manifest["files"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _copy_for_root_guard() -> Path:
    holder = Path(tempfile.mkdtemp())
    copied = holder / "repo"
    shutil.copytree(
        ROOT,
        copied,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
    )
    return copied


for rescue in ("NONE", "TEST", "README"):
    copied_root = _copy_for_root_guard()
    try:
        synthetic_tool = copied_root / "TOOLS" / "new_task_route.py"
        synthetic_tool.write_text("def main():\n    return 'task-route'\n", encoding="utf-8")
        _manifest_add_file(copied_root, synthetic_tool)

        skill_path = copied_root / "SKILL.md"
        skill_path.write_text(
            skill_path.read_text(encoding="utf-8") + "\nRun TOOLS/new_task_route.py for the new task route.\n",
            encoding="utf-8",
        )
        _manifest_add_file(copied_root, skill_path)

        if rescue == "TEST":
            synthetic_test = copied_root / "TESTS" / "run_new_task_route_regression.py"
            synthetic_test.write_text("import new_task_route\n", encoding="utf-8")
            _manifest_add_file(copied_root, synthetic_test)
        elif rescue == "README":
            readme_path = copied_root / "README.md"
            readme_path.write_text(
                readme_path.read_text(encoding="utf-8") + "\nSee TOOLS/new_task_route.py.\n",
                encoding="utf-8",
            )
            _manifest_add_file(copied_root, readme_path)

        synthetic_report = build_inventory(copied_root)
        root_errors = [
            row for row in synthetic_report.get("errors", [])
            if row.get("type") == "ROOT_TASK_ENTRYPOINT_WITHOUT_INDEPENDENT_OWNER"
            and row.get("path") == "TOOLS/new_task_route.py"
        ]
        require(
            synthetic_report["result"] == "FAIL" and bool(root_errors),
            f"unowned_root_entrypoint_fails_closed:{rescue.lower()}",
            {"errors": synthetic_report.get("errors"), "owners": synthetic_report.get("root_task_entrypoint_owners")},
        )
    finally:
        shutil.rmtree(copied_root.parent, ignore_errors=True)

copied_root = _copy_for_root_guard()
try:
    synthetic_tool = copied_root / "TOOLS" / "independent_pipeline_route.py"
    synthetic_tool.write_text("def main():\n    return 'pipeline'\n", encoding="utf-8")
    _manifest_add_file(copied_root, synthetic_tool)

    skill_path = copied_root / "SKILL.md"
    skill_path.write_text(
        skill_path.read_text(encoding="utf-8") + "\nRun TOOLS/independent_pipeline_route.py when the pipeline contract requires it.\n",
        encoding="utf-8",
    )
    _manifest_add_file(copied_root, skill_path)

    workflow_path = copied_root / "WORKFLOW" / "DEVELOPMENT_PIPELINE.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["root_entrypoint_guard_fixture"] = "TOOLS/independent_pipeline_route.py"
    workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _manifest_add_file(copied_root, workflow_path)

    owned_report = build_inventory(copied_root)
    require(
        owned_report["result"] == "PASS"
        and owned_report.get("root_task_entrypoint_owners", {}).get("TOOLS/independent_pipeline_route.py") == "PIPELINE:INDEPENDENT_REACHABILITY",
        "independent_pipeline_root_passes",
        {"result": owned_report.get("result"), "owners": owned_report.get("root_task_entrypoint_owners"), "errors": owned_report.get("errors")},
    )

    workflow.pop("root_entrypoint_guard_fixture", None)
    workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _manifest_add_file(copied_root, workflow_path)
    unowned_report = build_inventory(copied_root)
    require(
        unowned_report["result"] == "FAIL"
        and any(
            row.get("type") == "ROOT_TASK_ENTRYPOINT_WITHOUT_INDEPENDENT_OWNER"
            and row.get("path") == "TOOLS/independent_pipeline_route.py"
            for row in unowned_report.get("errors", [])
        ),
        "removing_independent_pipeline_owner_fails_closed",
        {"owners": unowned_report.get("root_task_entrypoint_owners"), "errors": unowned_report.get("errors")},
    )
finally:
    shutil.rmtree(copied_root.parent, ignore_errors=True)

require(
    str(report.get("root_task_entrypoint_owners", {}).get("TOOLS/analyze_onec_bsl.py", "")).startswith("DELIVERY:"),
    "registry_delivery_owned_root_passes",
    report.get("root_task_entrypoint_owners"),
)
require(
    report.get("root_task_entrypoint_owners", {}).get("TOOLS/reference_locator.py") == "SKILL:SOURCE_DISCOVERY",
    "source_support_owned_root_passes",
    report.get("root_task_entrypoint_owners"),
)
require(
    report.get("root_task_entrypoint_owners", {}).get("TOOLS/build_review_plan.py") == "PIPELINE:INDEPENDENT_REACHABILITY",
    "existing_independent_pipeline_root_passes",
    report.get("root_task_entrypoint_owners"),
)

# All-candidate applicability emits exactly one explicit disposition for all nine.
inactive_routes = [
    {"id": rule["id"], "active": False, "tier": rule.get("tier", 1), "detected_by": [], "reason": "test"}
    for rule in registry["rules"]
]
inactive = materialize_delivery_applicability(registry, inactive_routes, "ONEC_ONLY")
require(len(inactive) == 9, "all_candidate_applicability_count", len(inactive))
require(all(row["status"] in {"APPLICABLE", "NOT_APPLICABLE", "NOT_EVALUATED"} for row in inactive), "all_candidate_status_domain")
missing_routes = [row for row in inactive_routes if row["id"] != "CALL_CONTRACT"]
missing = materialize_delivery_applicability(registry, missing_routes, "ONEC_ONLY")
require(any(row["status"] == "NOT_EVALUATED" for row in missing), "missing_owner_route_not_evaluated")
require(all(row["status"] != "APPLICABLE" or row["capability_id"] for row in missing), "no_implicit_applicable")

# Real plan proves applicable set equality and active support reachability.
fixture = ROOT / "TESTS" / "fixtures" / "query_field_good.bsl"
plan = build_plan([str(fixture)], analysis_only=True, surface_override="ONEC_ONLY", risk_override="R1_CONTRACT")
applicable = {row["capability_id"] for row in plan["delivery_applicability"] if row["status"] == "APPLICABLE"}
active = {row["capability_id"] for row in plan["active_deliveries"]}
require(applicable == active, "applicable_equals_active_delivery", {"applicable": sorted(applicable), "active": sorted(active)})
full_support_rows = [
    {k: row.get(k) for k in ("path", "owner_kind", "owner_id")}
    for row in plan.get("active_supporting_artifacts") or []
]
refs = {row["path"] for row in full_support_rows}
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

compact = compact_summary(plan)
compact_references = ((compact.get("context_load_plan") or {}).get("references") or [])
compact_support_refs = {row for row in compact_references if isinstance(row, str)}
require(
    all(row["path"] in compact_support_refs for row in full_support_rows),
    "compact_support_projection_matches_full_plan",
    {"full_support": [row["path"] for row in full_support_rows], "compact_references": compact_references},
)
for rel in (
    "KNOWLEDGE/QUERY_LANGUAGE_GUIDE.md",
    "KNOWLEDGE/QUERY_TOPOLOGY_REVIEW.md",
):
    require(rel in compact_support_refs, f"compact_query_support_visible:{rel}", sorted(compact_support_refs))
for rel in (
    "KNOWLEDGE/DYNAMIC_POST_VALIDATION.md",
    "KNOWLEDGE/OFFICIAL_REFERENCE_NOTES.md",
):
    require(rel in compact_support_refs, f"compact_gate_support_visible:{rel}", sorted(compact_support_refs))
for rel in (
    "KNOWLEDGE/CLEVERENCE_COVERAGE_AUDIT.json",
    "TEMPLATES/PROJECT_SNAPSHOT_MANIFEST.json",
):
    require(rel not in compact_support_refs, f"compact_deprecated_support_absent:{rel}")

def support_reachability_complete(full_rows, compact_projection):
    compact_refs = ((compact_projection.get("context_load_plan") or {}).get("references"))
    expected_paths = [row["path"] for row in full_rows]
    return isinstance(compact_refs, list) and all(path in compact_refs for path in expected_paths)

require(
    support_reachability_complete(full_support_rows, compact),
    "active_support_reachability_contract_derived",
)
broken_compact = json.loads(json.dumps(compact, ensure_ascii=False))
broken_compact["context_load_plan"]["references"] = list((plan.get("context_load_plan") or {}).get("references") or [])
require(
    not support_reachability_complete(full_support_rows, broken_compact),
    "compact_support_removal_breaks_reachability",
)
require(
    not support_reachability_complete(
        full_support_rows,
        {"context_load_plan": {"references": list((plan.get("context_load_plan") or {}).get("references") or [])}},
    ),
    "full_plan_support_alone_not_sufficient",
)

compact_bytes = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
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
