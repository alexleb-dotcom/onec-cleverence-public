#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from build_review_plan import build_plan
from build_validation_ledger import build_ledger
from performance_review import validate as validate_performance_review
from release_gate_core import evaluate as release_evaluate
from rule_registry import load_registry
from validation_work_queue import build_work_queue

results = {}


def record(case_id: str, ok: bool, details=None):
    results[case_id] = {"pass": bool(ok)}
    if details is not None:
        results[case_id]["details"] = details


def algorithm(label: str, *, rows: int = 100_000, primary_passes: int = 1, nested: int = 0, db: int = 0, server: int = 0, external: int = 0, time: str = "O(N)", memory: str = "O(N)", copies: int = 1):
    return {
        "passes_over_primary_data": {"count": primary_passes, "notes": f"{label}: bounded primary passes"},
        "nested_searches": {"count": nested, "notes": f"{label}: nested search count per primary item"},
        "io_inside_iterations": {
            "db_calls_per_primary_row": db,
            "server_calls_per_primary_row": server,
            "external_calls_per_primary_row": external,
            "notes": f"{label}: transitive I/O inspected",
        },
        "asymptotic_time": {"notation": time, "derivation": f"{label}: derived from pass/search structure"},
        "memory_and_copies": {"notation": memory, "materialized_copies": copies, "notes": f"{label}: materializations accounted"},
        "data_ownership": {"owner": "server procedure", "lifetime": "one call"},
        "client_server_db_topology": {"execution_tiers": ["SERVER", "DB"], "round_trips": f"{label}: bounded round trips"},
        "scale_boundary": {"review_rows": rows, "reason": f"{label}: reasonable upper-bound review volume"},
    }


def preservation():
    return {
        field: {"status": "PRESERVED", "reason": f"{field} explicitly compared between current and proposed algorithms"}
        for field in ("result", "ordering", "rounding", "side_effects", "error_retry_semantics")
    }


def complete_review(ledger: dict):
    row = ledger["performance_review"]
    row["status"] = "PASS"
    row["reason"] = "candidate-bound structured performance review complete"
    row["current_algorithm"] = algorithm("current", primary_passes=1, nested=1, time="O(N^2)", memory="O(N)")
    row["proposed_algorithm"] = algorithm("proposed", primary_passes=1, nested=0, time="O(N)", memory="O(N)")
    row["preservation"] = preservation()
    row["runtime_profiling"] = {"mode": "STRUCTURAL_ONLY", "measured_speedup_claim": None, "runtime_case_id": None}
    return row


def error_types(report: dict):
    return {row.get("type") for row in report.get("errors") or [] if isinstance(row, dict)}


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    active_source = td / "active.bsl"
    active_source.write_text(
        "Процедура Тест()\nДля Каждого Элемент Из Массив Цикл\nСообщить(Элемент);\nКонецЦикла;\nКонецПроцедуры\n",
        encoding="utf-8",
    )
    inactive_source = td / "inactive.bsl"
    inactive_source.write_text("Процедура Тест()\nСообщить(\"ok\");\nКонецПроцедуры\n", encoding="utf-8")

    registry = load_registry()
    active_plan = build_plan([active_source], analysis_only=True)
    active_ledger = build_ledger(active_plan, registry)
    inactive_plan = build_plan([inactive_source], analysis_only=True)
    inactive_ledger = build_ledger(inactive_plan, registry)

    active_contract = active_plan.get("performance_review") or {}
    record(
        "performance:active_route_creates_candidate_bound_obligation",
        active_contract.get("required") is True
        and active_contract.get("owner_rule_id") == "COLLECTION_ALGORITHM"
        and bool(active_contract.get("candidate_fingerprint_sha256"))
        and active_ledger.get("performance_review", {}).get("status") == "EVIDENCE_REQUIRED",
        {"plan": active_contract, "ledger_status": active_ledger.get("performance_review", {}).get("status")},
    )

    missing = copy.deepcopy(active_ledger)
    missing.pop("performance_review", None)
    report = validate_performance_review(active_plan, missing, registry=registry)
    record("performance:missing_review_blocks", report["readiness_outcome"] == "BLOCKED" and "PERFORMANCE_REVIEW_MISSING" in error_types(report), report)

    generic = copy.deepcopy(active_ledger)
    generic["performance_review"]["status"] = "PASS"
    generic["performance_review"]["reason"] = "looks good"
    report = validate_performance_review(active_plan, generic, registry=registry)
    record(
        "performance:generic_pass_without_structure_blocks",
        report["readiness_outcome"] == "BLOCKED" and any(x.startswith("PERFORMANCE_REVIEW_ALGORITHM_") for x in error_types(report)),
        report,
    )

    stale = copy.deepcopy(active_ledger)
    complete_review(stale)
    stale["performance_review"]["candidate_fingerprint_sha256"] = "0" * 64
    report = validate_performance_review(active_plan, stale, registry=registry)
    record("performance:stale_candidate_binding_blocks", "PERFORMANCE_REVIEW_BINDING_DRIFT" in error_types(report), report)

    na = copy.deepcopy(active_ledger)
    na["performance_review"]["status"] = "NOT_APPLICABLE"
    na["performance_review"]["reason"] = "synthetic attempt to waive active review"
    report = validate_performance_review(active_plan, na, registry=registry)
    record("performance:active_not_applicable_laundering_blocks", "PERFORMANCE_REVIEW_REQUIRED_NOT_PASS" in error_types(report), report)

    oversized = copy.deepcopy(active_ledger)
    complete_review(oversized)
    oversized["performance_review"]["proposed_algorithm"]["scale_boundary"]["review_rows"] = 100_001
    report = validate_performance_review(active_plan, oversized, registry=registry)
    record("performance:scale_over_100k_blocks", "PERFORMANCE_REVIEW_SCALE_OUT_OF_RANGE" in error_types(report), report)

    measured_without_runtime = copy.deepcopy(active_ledger)
    complete_review(measured_without_runtime)
    measured_without_runtime["performance_review"]["runtime_profiling"] = {
        "mode": "STRUCTURAL_ONLY",
        "measured_speedup_claim": "2.0x faster",
        "runtime_case_id": None,
    }
    report = validate_performance_review(active_plan, measured_without_runtime, registry=registry)
    record("performance:measured_speedup_without_runtime_blocks", "PERFORMANCE_REVIEW_MEASURED_CLAIM_WITHOUT_RUNTIME" in error_types(report), report)

    trusted_manual = copy.deepcopy(active_ledger)
    complete_review(trusted_manual)
    property_id = active_contract["runtime_property_id"]
    trusted_manual["performance_review"]["runtime_profiling"] = {
        "mode": "MEASURED",
        "measured_speedup_claim": "2.0x faster",
        "runtime_case_id": "perf-1",
    }
    fake_runtime = {"perf-1": {"status": "PASS", "_verified_property": property_id, "_observation_kind": "TRUSTED_MANUAL_REVIEW"}}
    report = validate_performance_review(active_plan, trusted_manual, fake_runtime, registry)
    record("performance:manual_runtime_claim_does_not_prove_speedup", "PERFORMANCE_REVIEW_RUNTIME_CASE_NOT_VERIFIED" in error_types(report), report)

    measured_adapter = copy.deepcopy(active_ledger)
    complete_review(measured_adapter)
    measured_adapter["performance_review"]["runtime_profiling"] = {
        "mode": "MEASURED",
        "measured_speedup_claim": "2.0x faster",
        "runtime_case_id": "perf-1",
    }
    adapter_runtime = {"perf-1": {"status": "PASS", "_verified_property": property_id, "_observation_kind": "RUNTIME_ADAPTER"}}
    report = validate_performance_review(active_plan, measured_adapter, adapter_runtime, registry)
    record("performance:runtime_adapter_can_support_measured_claim", report["result"] == "PASS" and report["readiness_outcome"] == "READY_FOR_IMPLEMENTATION", report)

    complete = copy.deepcopy(active_ledger)
    complete_review(complete)
    report = validate_performance_review(active_plan, complete, registry=registry)
    record("performance:complete_structural_review_is_ready", report["result"] == "PASS" and report["readiness_outcome"] == "READY_FOR_IMPLEMENTATION", report)

    report = validate_performance_review(inactive_plan, inactive_ledger, registry=registry)
    record(
        "performance:inactive_exact_route_allows_verifier_na",
        report["result"] == "PASS"
        and report["required"] is False
        and report["readiness_outcome"] == "READY_FOR_IMPLEMENTATION"
        and inactive_plan["performance_review"]["detected_by"] == [],
        report,
    )

    forged_inactive = copy.deepcopy(inactive_ledger)
    forged_inactive["performance_review"]["candidate_fingerprint_sha256"] = "f" * 64
    report = validate_performance_review(inactive_plan, forged_inactive, registry=registry)
    record("performance:inactive_na_still_candidate_bound", "PERFORMANCE_REVIEW_BINDING_DRIFT" in error_types(report), report)

    wrong_candidate = copy.deepcopy(active_ledger)
    complete_review(wrong_candidate)
    wrong_candidate["performance_review"]["candidate_fingerprint_sha256"] = inactive_plan["performance_review"]["candidate_fingerprint_sha256"]
    report = validate_performance_review(active_plan, wrong_candidate, registry=registry)
    record(
        "performance:review_for_different_candidate_blocks",
        report["readiness_outcome"] == "BLOCKED" and "PERFORMANCE_REVIEW_BINDING_DRIFT" in error_types(report),
        report,
    )

    stripped_binding = copy.deepcopy(active_ledger)
    complete_review(stripped_binding)
    stripped_binding["performance_review"].pop("candidate_fingerprint_sha256", None)
    report = validate_performance_review(active_plan, stripped_binding, registry=registry)
    record(
        "performance:stripped_binding_metadata_blocks",
        report["readiness_outcome"] == "BLOCKED" and "PERFORMANCE_REVIEW_BINDING_DRIFT" in error_types(report),
        report,
    )

    manual_ledger_pass = copy.deepcopy(active_ledger)
    manual_ledger_pass["performance_review"]["status"] = "PASS"
    manual_ledger_pass["performance_review"]["reason"] = "manual ledger declaration only"
    release_report = release_evaluate(active_plan, manual_ledger_pass, registry)
    record(
        "performance:manual_ledger_pass_without_review_blocks",
        release_report.get("implementation_readiness", {}).get("readiness_outcome") == "BLOCKED"
        and any(str(x).startswith("PERFORMANCE_REVIEW_ALGORITHM_") for x in error_types(release_report)),
        {"implementation_readiness": release_report.get("implementation_readiness")},
    )

    generic_receipt = copy.deepcopy(active_ledger)
    generic_receipt["performance_review"] = {
        "status": "PASS",
        "reason": "generic receipt claims success",
        "evidence": [{"kind": "SEMANTIC", "status": "PASS", "reason": "generic prose receipt"}],
    }
    release_report = release_evaluate(active_plan, generic_receipt, registry)
    record(
        "performance:generic_receipt_does_not_close_obligation",
        release_report.get("implementation_readiness", {}).get("readiness_outcome") == "BLOCKED"
        and "PERFORMANCE_REVIEW_BINDING_DRIFT" in error_types(release_report),
        {"implementation_readiness": release_report.get("implementation_readiness")},
    )

    integrated_complete = copy.deepcopy(active_ledger)
    complete_review(integrated_complete)
    release_report = release_evaluate(active_plan, integrated_complete, registry)
    record(
        "performance:canonical_release_gate_exposes_ready_implementation_review",
        release_report.get("implementation_readiness", {}).get("readiness_outcome") == "READY_FOR_IMPLEMENTATION"
        and release_report.get("implementation_readiness", {}).get("result") == "PASS",
        {"implementation_readiness": release_report.get("implementation_readiness"), "release_outcome": release_report.get("release_outcome")},
    )

    original_active_bytes = active_source.read_bytes()
    try:
        active_source.write_text(
            active_source.read_text(encoding="utf-8") + "// candidate changed after performance review\n",
            encoding="utf-8",
        )
        release_report = release_evaluate(active_plan, integrated_complete, registry)
        record(
            "performance:candidate_bytes_changed_after_review_blocks_release",
            release_report.get("release_outcome") == "BLOCKED" and "CANDIDATE_SOURCE_DRIFT" in error_types(release_report),
            {"release_outcome": release_report.get("release_outcome"), "errors": sorted(error_types(release_report))},
        )
    finally:
        active_source.write_bytes(original_active_bytes)

    # Mass-operation coverage: prove the structured review accepts explicit current/proposed
    # algorithm shapes without hard-coding every valid algorithm to O(N).
    mass_nested = copy.deepcopy(active_ledger)
    complete_review(mass_nested)
    mass_nested["performance_review"]["current_algorithm"] = algorithm("nested-current", primary_passes=1, nested=1, time="O(N^2)", memory="O(N)")
    mass_nested["performance_review"]["proposed_algorithm"] = algorithm("nested-proposed", primary_passes=1, nested=0, time="O(N)", memory="O(N)")
    report = validate_performance_review(active_plan, mass_nested, registry=registry)
    record("performance:mass_nested_scan_reviewed", report["result"] == "PASS", report)

    repeated_scans = copy.deepcopy(active_ledger)
    complete_review(repeated_scans)
    repeated_scans["performance_review"]["current_algorithm"] = algorithm("repeated-current", primary_passes=4, nested=0, time="O(N)", memory="O(N)")
    repeated_scans["performance_review"]["proposed_algorithm"] = algorithm("repeated-proposed", primary_passes=1, nested=0, time="O(N)", memory="O(N)")
    report = validate_performance_review(active_plan, repeated_scans, registry=registry)
    record("performance:mass_repeated_full_scans_reviewed", report["result"] == "PASS", report)

    loop_io = copy.deepcopy(active_ledger)
    complete_review(loop_io)
    loop_io["performance_review"]["current_algorithm"] = algorithm("io-current", primary_passes=1, nested=0, db=1, server=1, external=1, time="O(N)", memory="O(1)")
    loop_io["performance_review"]["proposed_algorithm"] = algorithm("io-proposed", primary_passes=1, nested=0, db=0, server=0, external=0, time="O(N)", memory="O(N)")
    report = validate_performance_review(active_plan, loop_io, registry=registry)
    record("performance:mass_loop_io_reviewed", report["result"] == "PASS", report)

    indexed_single_pass = copy.deepcopy(active_ledger)
    complete_review(indexed_single_pass)
    indexed_single_pass["performance_review"]["current_algorithm"] = algorithm("scan-current", primary_passes=1, nested=1, time="O(N^2)", memory="O(1)")
    indexed_single_pass["performance_review"]["proposed_algorithm"] = algorithm("index-proposed", primary_passes=1, nested=0, time="O(N)", memory="O(N)", copies=1)
    report = validate_performance_review(active_plan, indexed_single_pass, registry=registry)
    record("performance:indexed_single_pass_alternative_reviewed", report["result"] == "PASS", report)

    hierarchy = copy.deepcopy(active_ledger)
    complete_review(hierarchy)
    hierarchy["performance_review"]["current_algorithm"] = algorithm("hierarchy-current", primary_passes=1, nested=1, time="O(V*E)", memory="O(V)")
    hierarchy["performance_review"]["proposed_algorithm"] = algorithm("hierarchy-proposed", primary_passes=1, nested=0, time="O(V+E)", memory="O(V)")
    report = validate_performance_review(active_plan, hierarchy, registry=registry)
    record("performance:hierarchy_graph_linear_in_vertices_edges_reviewed", report["result"] == "PASS", report)

    # Canonical release gate must preserve the same blocker even though this deliberately
    # unresolved synthetic ledger has many additional validation errors.
    release_report = release_evaluate(active_plan, active_ledger, registry)
    record(
        "performance:release_gate_enforces_review",
        release_report.get("implementation_readiness", {}).get("readiness_outcome") == "BLOCKED"
        and "PERFORMANCE_REVIEW_REQUIRED_NOT_PASS" in error_types(release_report),
        {"implementation_readiness": release_report.get("implementation_readiness"), "performance_errors": sorted(x for x in error_types(release_report) if str(x).startswith("PERFORMANCE_REVIEW_"))},
    )

    queue = build_work_queue(active_ledger)
    record(
        "performance:work_queue_surfaces_review_blocker",
        "performance_review" in (queue.get("work_queue") or {})
        and (queue.get("implementation_readiness") or {}).get("readiness_outcome") == "BLOCKED",
        {"performance_review": (queue.get("work_queue") or {}).get("performance_review"), "implementation_readiness": queue.get("implementation_readiness")},
    )

failed = [case_id for case_id, row in results.items() if not row["pass"]]
report = {"result": "PASS" if not failed else "FAIL", "cases": len(results), "failed": failed, "results": results}
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if not failed else 2)
