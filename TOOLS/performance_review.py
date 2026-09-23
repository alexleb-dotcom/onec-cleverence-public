#!/usr/bin/env python3
"""Candidate-bound Performance Review contract for COLLECTION_ALGORITHM.

The contract is intentionally narrower than the final release gate. It prevents
implementation-readiness laundering when mass-operation triggers are present and
keeps measured acceleration claims behind verifier-owned runtime evidence.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from proof_identity import candidate_identity

OWNER_RULE_ID = "COLLECTION_ALGORITHM"
SCHEMA_VERSION = 1
MAX_REVIEW_ROWS = 100_000
ALGORITHM_FIELDS = (
    "passes_over_primary_data",
    "nested_searches",
    "io_inside_iterations",
    "asymptotic_time",
    "memory_and_copies",
    "data_ownership",
    "client_server_db_topology",
    "scale_boundary",
)
PRESERVATION_FIELDS = (
    "result",
    "ordering",
    "rounding",
    "side_effects",
    "error_retry_semantics",
)
PRESERVATION_STATUSES = {"PRESERVED", "REQUIREMENT_AUTHORIZED_CHANGE", "NOT_APPLICABLE"}
RUNTIME_MODES = {"STRUCTURAL_ONLY", "MEASURED"}
REGISTRY_CONTRACT = {
    "schema_version": SCHEMA_VERSION,
    "required_when_active": True,
    "candidate_bound": True,
    "not_applicable_policy": "VERIFIER_RECOMPUTED_TRIGGER_ABSENCE_ONLY",
    "max_review_rows": MAX_REVIEW_ROWS,
    "measured_acceleration_requires": "RUNTIME_ADAPTER",
}


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _owner_route(plan: dict) -> dict:
    rows = [row for row in plan.get("rules") or [] if isinstance(row, dict) and row.get("id") == OWNER_RULE_ID]
    if len(rows) != 1:
        raise ValueError(f"exactly one {OWNER_RULE_ID} route is required")
    return rows[0]


def performance_property_id(candidate_fingerprint_sha256: str) -> str:
    return f"PERFORMANCE_REVIEW:{candidate_fingerprint_sha256}"


def build_plan_contract(plan: dict) -> dict:
    route = _owner_route(plan)
    fingerprint = candidate_identity(plan)["fingerprint_sha256"]
    return {
        "schema_version": SCHEMA_VERSION,
        "owner_rule_id": OWNER_RULE_ID,
        "required": bool(route.get("active")),
        "activation_status": route.get("activation_status"),
        "detected_by": list(route.get("detected_by") or []),
        "candidate_fingerprint_sha256": fingerprint,
        "max_review_rows": MAX_REVIEW_ROWS,
        "required_algorithm_fields": list(ALGORITHM_FIELDS),
        "required_preservation_fields": list(PRESERVATION_FIELDS),
        "runtime_property_id": performance_property_id(fingerprint),
        "not_applicable_policy": "VERIFIER_RECOMPUTED_TRIGGER_ABSENCE_ONLY",
        "runtime_boundary": "Measured acceleration requires an exact-candidate PASS runtime_case verified from a RUNTIME_ADAPTER observation. Structural/static review may justify complexity/topology but must not claim measured speedup.",
    }


def build_ledger_skeleton(plan: dict) -> dict:
    expected = build_plan_contract(plan)
    if expected["required"]:
        return {
            "schema_version": SCHEMA_VERSION,
            "owner_rule_id": OWNER_RULE_ID,
            "candidate_fingerprint_sha256": expected["candidate_fingerprint_sha256"],
            "activation_status": expected["activation_status"],
            "detected_by": deepcopy(expected["detected_by"]),
            "status": "EVIDENCE_REQUIRED",
            "reason": "",
            "current_algorithm": {},
            "proposed_algorithm": {},
            "preservation": {},
            "runtime_profiling": {
                "mode": "STRUCTURAL_ONLY",
                "measured_speedup_claim": None,
                "runtime_case_id": None,
            },
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "owner_rule_id": OWNER_RULE_ID,
        "candidate_fingerprint_sha256": expected["candidate_fingerprint_sha256"],
        "activation_status": expected["activation_status"],
        "detected_by": deepcopy(expected["detected_by"]),
        "status": "NOT_APPLICABLE",
        "reason": "verifier-derived: COLLECTION_ALGORITHM is inactive for the exact candidate and no activation trigger was detected",
        "current_algorithm": {},
        "proposed_algorithm": {},
        "preservation": {},
        "runtime_profiling": {
            "mode": "STRUCTURAL_ONLY",
            "measured_speedup_claim": None,
            "runtime_case_id": None,
        },
    }


def _validate_pass_metric(value: Any, field: str, errors: list[dict], side: str) -> None:
    if not isinstance(value, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": field, "reason": "object_required"})
        return
    count = value.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": field, "reason": "non_negative_integer_count_required"})
    if not _has_text(value.get("notes")):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": field, "reason": "notes_required"})


def _validate_complexity(value: Any, field: str, errors: list[dict], side: str) -> None:
    if not isinstance(value, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": field, "reason": "object_required"})
        return
    notation = value.get("notation")
    if not _has_text(notation) or not notation.strip().startswith("O("):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": field, "reason": "big_o_notation_required"})
    if not _has_text(value.get("derivation")):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": field, "reason": "derivation_required"})


def _validate_algorithm(row: Any, side: str, errors: list[dict]) -> None:
    if not isinstance(row, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_SECTION_MISSING", "side": side})
        return
    missing = [field for field in ALGORITHM_FIELDS if field not in row]
    if missing:
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELDS_MISSING", "side": side, "fields": missing})
        return

    _validate_pass_metric(row.get("passes_over_primary_data"), "passes_over_primary_data", errors, side)
    _validate_pass_metric(row.get("nested_searches"), "nested_searches", errors, side)

    io = row.get("io_inside_iterations")
    if not isinstance(io, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "io_inside_iterations", "reason": "object_required"})
    else:
        for key in ("db_calls_per_primary_row", "server_calls_per_primary_row", "external_calls_per_primary_row"):
            value = io.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": f"io_inside_iterations.{key}", "reason": "non_negative_integer_required"})
        if not _has_text(io.get("notes")):
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "io_inside_iterations.notes", "reason": "notes_required"})

    _validate_complexity(row.get("asymptotic_time"), "asymptotic_time", errors, side)

    memory = row.get("memory_and_copies")
    if not isinstance(memory, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "memory_and_copies", "reason": "object_required"})
    else:
        notation = memory.get("notation")
        if not _has_text(notation) or not notation.strip().startswith("O("):
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "memory_and_copies.notation", "reason": "big_o_notation_required"})
        copies = memory.get("materialized_copies")
        if not isinstance(copies, int) or isinstance(copies, bool) or copies < 0:
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "memory_and_copies.materialized_copies", "reason": "non_negative_integer_required"})
        if not _has_text(memory.get("notes")):
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "memory_and_copies.notes", "reason": "notes_required"})

    ownership = row.get("data_ownership")
    if not isinstance(ownership, dict) or not _has_text(ownership.get("owner")) or not _has_text(ownership.get("lifetime")):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "data_ownership", "reason": "owner_and_lifetime_required"})

    topology = row.get("client_server_db_topology")
    if not isinstance(topology, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "client_server_db_topology", "reason": "object_required"})
    else:
        tiers = topology.get("execution_tiers")
        if not isinstance(tiers, list) or not tiers or not all(_has_text(x) for x in tiers):
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "client_server_db_topology.execution_tiers", "reason": "non_empty_list_required"})
        if not _has_text(topology.get("round_trips")):
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "client_server_db_topology.round_trips", "reason": "round_trip_description_required"})

    scale = row.get("scale_boundary")
    if not isinstance(scale, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "scale_boundary", "reason": "object_required"})
    else:
        review_rows = scale.get("review_rows")
        if not isinstance(review_rows, int) or isinstance(review_rows, bool) or not (1 <= review_rows <= MAX_REVIEW_ROWS):
            errors.append({"type": "PERFORMANCE_REVIEW_SCALE_OUT_OF_RANGE", "side": side, "actual": review_rows, "max": MAX_REVIEW_ROWS})
        if not _has_text(scale.get("reason")):
            errors.append({"type": "PERFORMANCE_REVIEW_ALGORITHM_FIELD_INVALID", "side": side, "field": "scale_boundary.reason", "reason": "reason_required"})


def _validate_preservation(row: Any, errors: list[dict]) -> None:
    if not isinstance(row, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_PRESERVATION_MISSING"})
        return
    for field in PRESERVATION_FIELDS:
        item = row.get(field)
        if not isinstance(item, dict):
            errors.append({"type": "PERFORMANCE_REVIEW_PRESERVATION_FIELD_MISSING", "field": field})
            continue
        status = item.get("status")
        if status not in PRESERVATION_STATUSES:
            errors.append({"type": "PERFORMANCE_REVIEW_PRESERVATION_STATUS_INVALID", "field": field, "actual": status})
        if not _has_text(item.get("reason")):
            errors.append({"type": "PERFORMANCE_REVIEW_PRESERVATION_REASON_MISSING", "field": field})
        if status == "REQUIREMENT_AUTHORIZED_CHANGE" and not _has_text(item.get("requirement_ref")):
            errors.append({"type": "PERFORMANCE_REVIEW_PRESERVATION_REQUIREMENT_REF_MISSING", "field": field})


def validate(plan: dict, ledger: dict, runtime_cases: dict | None = None, registry: dict | None = None) -> dict:
    errors: list[dict] = []
    if registry is not None:
        owner_rows = [row for row in registry.get("rules") or [] if isinstance(row, dict) and row.get("id") == OWNER_RULE_ID]
        if len(owner_rows) != 1 or owner_rows[0].get("performance_review") != REGISTRY_CONTRACT:
            errors.append({"type": "PERFORMANCE_REVIEW_REGISTRY_CONTRACT_DRIFT", "expected": REGISTRY_CONTRACT, "actual": owner_rows[0].get("performance_review") if len(owner_rows) == 1 else None})
    expected = build_plan_contract(plan)
    planned = plan.get("performance_review")
    if planned != expected:
        errors.append({"type": "PERFORMANCE_REVIEW_PLAN_CONTRACT_DRIFT", "expected": expected, "actual": planned})

    row = ledger.get("performance_review")
    if not isinstance(row, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_MISSING", "owner_rule_id": OWNER_RULE_ID})
        return {"result": "FAIL", "readiness_outcome": "BLOCKED", "required": expected["required"], "errors": errors}

    for key in ("schema_version", "owner_rule_id", "candidate_fingerprint_sha256", "activation_status", "detected_by"):
        if row.get(key) != expected.get(key):
            errors.append({"type": "PERFORMANCE_REVIEW_BINDING_DRIFT", "field": key, "expected": expected.get(key), "actual": row.get(key)})

    if not expected["required"]:
        if expected["detected_by"]:
            errors.append({"type": "PERFORMANCE_REVIEW_NA_TRIGGER_ABSENCE_NOT_PROVEN", "detected_by": expected["detected_by"]})
        if row.get("status") != "NOT_APPLICABLE":
            errors.append({"type": "PERFORMANCE_REVIEW_INACTIVE_STATUS_INVALID", "actual": row.get("status")})
        if not _has_text(row.get("reason")):
            errors.append({"type": "PERFORMANCE_REVIEW_NA_REASON_MISSING"})
        return {
            "result": "PASS" if not errors else "FAIL",
            "readiness_outcome": "READY_FOR_IMPLEMENTATION" if not errors else "BLOCKED",
            "required": False,
            "errors": errors,
            "candidate_fingerprint_sha256": expected["candidate_fingerprint_sha256"],
        }

    if row.get("status") != "PASS":
        errors.append({"type": "PERFORMANCE_REVIEW_REQUIRED_NOT_PASS", "actual": row.get("status")})
    _validate_algorithm(row.get("current_algorithm"), "current_algorithm", errors)
    _validate_algorithm(row.get("proposed_algorithm"), "proposed_algorithm", errors)
    _validate_preservation(row.get("preservation"), errors)

    runtime = row.get("runtime_profiling")
    if not isinstance(runtime, dict):
        errors.append({"type": "PERFORMANCE_REVIEW_RUNTIME_BOUNDARY_MISSING"})
    else:
        mode = runtime.get("mode")
        claim = runtime.get("measured_speedup_claim")
        case_id = runtime.get("runtime_case_id")
        if mode not in RUNTIME_MODES:
            errors.append({"type": "PERFORMANCE_REVIEW_RUNTIME_MODE_INVALID", "actual": mode})
        elif mode == "STRUCTURAL_ONLY":
            if claim not in (None, "") or case_id not in (None, ""):
                errors.append({"type": "PERFORMANCE_REVIEW_MEASURED_CLAIM_WITHOUT_RUNTIME", "claim": claim, "runtime_case_id": case_id})
        elif mode == "MEASURED":
            if not _has_text(claim):
                errors.append({"type": "PERFORMANCE_REVIEW_MEASURED_CLAIM_MISSING"})
            if not _has_text(case_id):
                errors.append({"type": "PERFORMANCE_REVIEW_RUNTIME_CASE_MISSING"})
            else:
                case = (runtime_cases or {}).get(case_id)
                expected_property = expected["runtime_property_id"]
                if not isinstance(case, dict) or case.get("status") != "PASS" or case.get("_verified_property") != expected_property or case.get("_observation_kind") != "RUNTIME_ADAPTER":
                    errors.append({"type": "PERFORMANCE_REVIEW_RUNTIME_CASE_NOT_VERIFIED", "runtime_case_id": case_id, "expected_property": expected_property})

    return {
        "result": "PASS" if not errors else "FAIL",
        "readiness_outcome": "READY_FOR_IMPLEMENTATION" if not errors else "BLOCKED",
        "required": True,
        "errors": errors,
        "candidate_fingerprint_sha256": expected["candidate_fingerprint_sha256"],
        "runtime_property_id": expected["runtime_property_id"],
    }
