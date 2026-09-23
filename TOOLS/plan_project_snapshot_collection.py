#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_CAPABILITIES.json"
DEFAULT_RUNTIME_PROFILE = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_RUNTIME_V1_CAPABILITIES.json"
STATE_RANK = {"UNSUPPORTED": 0, "PARTIAL": 1, "FULL": 2}
SOURCE_EXPORT_PROFILE = "SOURCE_EXPORT_V1"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_backends(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def validate_request(request: dict, matrix: dict, available_backends: list[str]) -> list[str]:
    errors: list[str] = []
    if request.get("schema_version") != 1:
        errors.append("request_schema_version_must_be_1")
    if matrix.get("schema_version") != 1:
        errors.append("matrix_schema_version_must_be_1")

    baseline_expectation = request.get("baseline_expectation")
    if baseline_expectation is not None and not isinstance(baseline_expectation, dict):
        errors.append("baseline_expectation_must_be_object")

    known_categories = set((matrix.get("categories") or {}).keys())
    direct_backends = set((matrix.get("backends") or {}).keys())
    declared_categories = request.get("evidence_categories") or []
    if not declared_categories:
        errors.append("evidence_categories_required")
    if len(declared_categories) != len(set(declared_categories)):
        errors.append("duplicate_evidence_categories")
    for category in declared_categories:
        if category not in known_categories:
            errors.append(f"unknown_evidence_category:{category}")

    policy = request.get("collector_policy") or {}
    allowed_backends = policy.get("allowed_backends") or []
    if not allowed_backends:
        errors.append("collector_policy.allowed_backends_required")
    for backend in allowed_backends:
        if backend != "HYBRID" and backend not in direct_backends:
            errors.append(f"unknown_allowed_backend:{backend}")

    if not available_backends:
        errors.append("available_backends_required")
    for backend in available_backends:
        if backend == "HYBRID":
            errors.append("HYBRID_is_not_a_direct_available_backend")
        elif backend not in direct_backends:
            errors.append(f"unknown_available_backend:{backend}")

    required_items = request.get("required_items") or []
    if not required_items:
        errors.append("required_items_required")
    seen_ids: set[str] = set()
    declared_set = set(declared_categories)
    for index, item in enumerate(required_items):
        item_id = item.get("id")
        category = item.get("category")
        logical_target = item.get("logical_target")
        if not item_id:
            errors.append(f"required_item_missing_id:{index}")
        elif item_id in seen_ids:
            errors.append(f"duplicate_required_item_id:{item_id}")
        else:
            seen_ids.add(item_id)
        if not isinstance(logical_target, str) or not logical_target.strip():
            errors.append(f"required_item_missing_logical_target:{item_id or index}")
        if category not in known_categories:
            errors.append(f"required_item_unknown_category:{item_id or index}:{category}")
        elif category not in declared_set:
            errors.append(f"required_item_category_not_declared:{item_id or index}:{category}")
        minimum = item.get("minimum_fidelity", "FULL")
        if minimum not in {"PARTIAL", "FULL"}:
            errors.append(f"required_item_bad_minimum_fidelity:{item_id or index}:{minimum}")

    return errors


def effective_runtime_contract(
    category: str,
    logical_target: str | None,
    contract: dict,
    runtime_profile: dict | None,
) -> dict | None:
    if not runtime_profile:
        return contract
    implemented = (runtime_profile.get("implemented_categories") or {}).get(category)
    if not implemented:
        return None
    if logical_target:
        target_kind = logical_target.split(".", 1)[0].upper()
        allowed_kinds = set(implemented.get("logical_target_kinds") or [])
        if allowed_kinds and target_kind not in allowed_kinds:
            return None
    matrix_state = contract.get("state", "UNSUPPORTED")
    profile_state = implemented.get("max_fidelity", matrix_state)
    effective_rank = min(STATE_RANK.get(matrix_state, 0), STATE_RANK.get(profile_state, 0))
    state_by_rank = {rank: state for state, rank in STATE_RANK.items()}
    result = dict(contract)
    result["state"] = state_by_rank.get(effective_rank, "UNSUPPORTED")
    result["runtime_profile"] = runtime_profile.get("profile")
    return result


def source_export_v1_supports_target(logical_target: str | None) -> bool:
    if not logical_target:
        return True
    parts = logical_target.split(".")
    kind = parts[0].upper() if parts else ""
    if kind == "COMMON_MODULE":
        return len(parts) == 2 and bool(parts[1])
    if kind in {"DOCUMENT", "CATALOG"}:
        return len(parts) == 3 and bool(parts[1]) and parts[2].upper() in {"OBJECTMODULE", "MANAGERMODULE"}
    return False


def effective_source_export_contract(
    category: str,
    logical_target: str | None,
    contract: dict,
) -> dict | None:
    # The generic matrix describes what an exported source tree can expose.
    # The one-click ProjectSnapshotCollector currently packages only selected
    # module files from a temporary hierarchical Designer dump. Keep planning
    # bounded to that implemented adapter instead of promising generic export.
    if category != "MODULE_SOURCE":
        return None
    if not source_export_v1_supports_target(logical_target):
        return None
    result = dict(contract)
    result["source_export_profile"] = SOURCE_EXPORT_PROFILE
    return result


def choose_backend(
    category: str,
    matrix: dict,
    available: list[str],
    allowed: list[str],
    runtime_profile: dict | None = None,
    logical_target: str | None = None,
) -> dict | None:
    category_contract = matrix["categories"][category]
    backend_contracts = category_contract.get("backends") or {}
    preference = matrix.get("backend_preference") or list(matrix.get("backends") or {})
    preference_rank = {backend: index for index, backend in enumerate(preference)}
    candidates: list[dict] = []
    for backend in available:
        if backend not in allowed:
            continue
        contract = backend_contracts.get(backend)
        if not contract:
            continue
        if backend == "RUNTIME_METADATA":
            contract = effective_runtime_contract(category, logical_target, contract, runtime_profile)
            if contract is None:
                continue
        elif backend == "SOURCE_EXPORT":
            contract = effective_source_export_contract(category, logical_target, contract)
            if contract is None:
                continue
        state = contract.get("state", "UNSUPPORTED")
        candidate = {
            "backend": backend,
            "state": state,
            "method": contract.get("method"),
            "limitations": contract.get("limitations") or [],
            "automatic": bool((matrix.get("backends") or {}).get(backend, {}).get("automatic")),
            "runtime_profile": contract.get("runtime_profile") if backend == "RUNTIME_METADATA" else None,
            "source_export_profile": contract.get("source_export_profile") if backend == "SOURCE_EXPORT" else None,
            "_rank": STATE_RANK.get(state, -1),
            "_preference": preference_rank.get(backend, 9999),
        }
        candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row["_rank"], row["_preference"]))
    selected = candidates[0]
    selected.pop("_rank", None)
    selected.pop("_preference", None)
    if selected.get("runtime_profile") is None:
        selected.pop("runtime_profile", None)
    if selected.get("source_export_profile") is None:
        selected.pop("source_export_profile", None)
    return selected


def build_plan(
    request: dict,
    matrix: dict,
    available_backends: list[str],
    runtime_profile: dict | None = None,
) -> dict:
    errors = validate_request(request, matrix, available_backends)
    if errors:
        return {"schema_version": 1, "result": "INVALID_REQUEST", "errors": errors}
    if runtime_profile is None and DEFAULT_RUNTIME_PROFILE.exists():
        runtime_profile = load_json(DEFAULT_RUNTIME_PROFILE)

    allowed = [
        backend
        for backend in (request.get("collector_policy") or {}).get("allowed_backends", [])
        if backend != "HYBRID"
    ]

    category_plan: list[dict] = []
    for category in request["evidence_categories"]:
        selected = choose_backend(category, matrix, available_backends, allowed, runtime_profile)
        category_plan.append(
            {
                "category": category,
                "selected": selected,
                "status": "UNSUPPORTED" if selected is None or selected["state"] == "UNSUPPORTED" else selected["state"],
            }
        )

    item_plan: list[dict] = []
    selected_backends: set[str] = set()
    runtime_scope: list[str] = []
    source_export_scope: list[str] = []
    for item in request["required_items"]:
        minimum = item.get("minimum_fidelity", "FULL")
        selected = choose_backend(
            item["category"], matrix, available_backends, allowed, runtime_profile, item["logical_target"]
        )
        if selected is None or selected["state"] == "UNSUPPORTED":
            status = "UNSUPPORTED"
        elif STATE_RANK[selected["state"]] >= STATE_RANK[minimum]:
            status = "READY"
        else:
            status = "PARTIAL"

        row = {
            "id": item["id"],
            "category": item["category"],
            "logical_target": item["logical_target"],
            "required_for_claim": item.get("required_for_claim"),
            "minimum_fidelity": minimum,
            "status": status,
            "selected": selected,
        }
        item_plan.append(row)
        if selected and selected["state"] != "UNSUPPORTED":
            selected_backends.add(selected["backend"])
            if selected["backend"] == "RUNTIME_METADATA":
                runtime_scope.append(item["id"])
            elif selected["backend"] == "SOURCE_EXPORT":
                source_export_scope.append(item["id"])

    counts = {
        "ready": sum(1 for row in item_plan if row["status"] == "READY"),
        "partial": sum(1 for row in item_plan if row["status"] == "PARTIAL"),
        "unsupported": sum(1 for row in item_plan if row["status"] == "UNSUPPORTED"),
    }
    if counts["unsupported"]:
        result = "BLOCKED"
    elif counts["partial"]:
        result = "PARTIAL"
    else:
        result = "READY"

    if len(selected_backends) > 1:
        collection_mode = "HYBRID"
    elif len(selected_backends) == 1:
        collection_mode = next(iter(selected_backends))
    else:
        collection_mode = "NONE"

    return {
        "schema_version": 1,
        "result": result,
        "request_id": request.get("request_id"),
        "baseline_expectation": request.get("baseline_expectation"),
        "available_backends": available_backends,
        "allowed_backends": allowed,
        "runtime_profile": runtime_profile.get("profile") if runtime_profile and "RUNTIME_METADATA" in available_backends else None,
        "source_export_profile": SOURCE_EXPORT_PROFILE if "SOURCE_EXPORT" in available_backends else None,
        "collection_mode": collection_mode,
        "selected_backends": sorted(selected_backends),
        "summary": counts,
        "runtime_collector_scope": runtime_scope,
        "source_export_scope": source_export_scope,
        "category_plan": category_plan,
        "item_plan": item_plan,
        "unresolved_items": [row["id"] for row in item_plan if row["status"] != "READY"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan ProjectSnapshot evidence collection for the available customer-contour backends.")
    parser.add_argument("request", type=Path, help="PROJECT_SNAPSHOT_REQUEST.json")
    parser.add_argument(
        "--available-backends",
        default="RUNTIME_METADATA",
        help="Comma-separated direct backends available at the customer contour. HYBRID is derived, not supplied.",
    )
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--runtime-profile", type=Path, default=DEFAULT_RUNTIME_PROFILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict", action="store_true", help="Return exit code 2 unless every required item is READY.")
    args = parser.parse_args()

    request = load_json(args.request)
    matrix = load_json(args.matrix)
    runtime_profile = load_json(args.runtime_profile) if args.runtime_profile.exists() else None
    plan = build_plan(request, matrix, parse_backends(args.available_backends), runtime_profile)
    payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    if plan.get("result") == "INVALID_REQUEST":
        return 2
    if args.strict and plan.get("result") != "READY":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
