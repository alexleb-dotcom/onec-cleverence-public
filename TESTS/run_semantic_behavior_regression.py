#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
DOC = json.loads((ROOT / "TESTS" / "SEMANTIC_BEHAVIOR_CASES.json").read_text(encoding="utf-8"))
results = {}
errors = []


def violates(case, observation):
    oracle = case["oracle"]
    if oracle == "sum_conservation":
        return sum(observation.get("values", [])) != case["expected_total"]
    if oracle == "numeric_expected":
        return observation.get("actual") != case["expected"]
    if oracle == "correlation_pairs":
        allowed = set(case.get("allowed_pairs", []))
        return any(item not in allowed for item in observation.get("pairs", []))
    if oracle == "temporal_alignment":
        states = observation.get("effective_states", [])
        return len(set(states)) > 1 and not observation.get("mismatch_authorized", False)
    if oracle == "snapshot_protection":
        changed = observation.get("start_version") != observation.get("later_version")
        return changed and not observation.get("consistency_proven", False)
    if oracle == "unit_basis":
        bases = observation.get("bases", [])
        return len(set(bases)) > 1 and not observation.get("conversion_proven", False)
    if oracle == "absence_distinct":
        keys = [key for key in observation if key.startswith("explicit_")]
        return bool(keys) and observation.get("absent") == observation.get(keys[0])
    if oracle == "fact_retention":
        return bool(set(case.get("required", [])) - set(observation.get("output", [])))
    if oracle == "interaction_route":
        return (
            observation.get("presentation_affordance", False)
            and observation.get("action_required", False)
            and not observation.get("action_route_proven", False)
        )
    if oracle == "scope_claim":
        return (
            observation.get("local_ui_restriction", False)
            and observation.get("claims_object_restriction", False)
            and not observation.get("object_permission_proven", False)
        )
    if oracle == "snapshot_handoff_contract":
        overbroad = observation.get("narrower_closure_proven_possible", False) and observation.get("whole_configuration_requested_without_reason", False)
        required = observation.get("required_item_count", 0)
        collected = observation.get("collected_required_item_count", 0)
        incomplete_laundered = collected < required and (observation.get("claims_snapshot_sufficient", False) or not observation.get("missing_required_reported", False))
        binding_missing = not observation.get("snapshot_identity_bound", False) or not observation.get("change_package_bound_to_snapshot", False)
        post_transfer_required_missing = observation.get("post_transfer_policy") == "REQUIRED_BY_PROJECT" and not observation.get("post_transfer_snapshot_present", False)
        applied_proof_laundering = observation.get("claims_applied_target_proven", False) and not observation.get("applied_target_observed", False)
        return overbroad or incomplete_laundered or binding_missing or post_transfer_required_missing or applied_proof_laundering
    if oracle == "delivery_result_contract":
        mode = observation.get("mode")
        incomplete_manual = (
            mode == "MANUAL_TRANSFER_INSTRUCTION"
            and (
                observation.get("documented_material_elements", 0) < observation.get("applicable_material_elements", 0)
                or observation.get("human_must_invent_material_details", False)
            )
        )
        proof_laundering = (
            observation.get("claims_applied_target_proven", False)
            and not observation.get("applied_target_proven", False)
        )
        return incomplete_manual or proof_laundering
    if oracle == "lifecycle_ownership":
        if not observation.get("independent_process", False):
            return False
        if not observation.get("reuses_existing_mechanism", False):
            return False
        if observation.get("shared_orchestrator_extension_point_proven", False):
            return False
        return (
            observation.get("inherits_unrelated_trigger_or_schedule", False)
            or not observation.get("process_owns_retry_state_error_policy", False)
            or not observation.get("capability_boundary_explicit", False)
        )
    if oracle == "write_guard_coverage":
        required = set(observation.get("required_channels", []))
        proven = set(observation.get("proven_guard_channels", []))
        missing = required - proven
        fill_laundering = observation.get("fill_check_claimed_universal", False)
        duplicated = observation.get("duplicate_material_predicate", False)
        exchange_gap = observation.get("exchange_required", False) and not observation.get("exchange_bypass_dispositioned", False)
        return bool(missing) or fill_laundering or duplicated or exchange_gap
    if oracle == "preaction_capability":
        if not observation.get("meaningful_preaction", False):
            return False
        if not observation.get("required_capabilities_checked_before", False):
            return True
        return (
            observation.get("server_authorization_required", False)
            and not observation.get("server_authorization_rechecked", False)
        )
    if oracle == "minimal_change_surface":
        helper_bad = observation.get("existing_owner_satisfies_contract", False) and observation.get("new_parallel_helper_count", 0) > 0
        opportunistic = observation.get("unrelated_changed_artifacts", 0) > 0
        code_golf = observation.get("loc_reduced", False) and observation.get("cohesion_lost", False)
        return helper_bad or opportunistic or code_golf
    if oracle == "bsl_layout_semantic":
        limit = int(case.get("line_limit", 120))
        if observation.get("unrelated_baseline_reformatted", False):
            return True
        if not observation.get("changed_or_new", False):
            return False
        length = int(observation.get("compact_line_length", 0))
        wrapped = observation.get("wrapped", False)
        exception = observation.get("documented_exception", False)
        if (
            wrapped
            and observation.get("simple_readable", False)
            and length <= limit
            and not observation.get("readability_justifies_wrap", False)
        ):
            return True
        if length > limit and not exception:
            if not wrapped:
                return True
            if not observation.get("std444_wrap_compliant", False):
                return True
        return False
    if oracle == "cleverence_contract_path":
        return (
            not observation.get("scenario_bound", False)
            or not observation.get("writer_path_bound", False)
            or not observation.get("state_reentry_dispositioned", False)
            or not observation.get("producer_mapping_consumer_complete", False)
        )
    if oracle == "existing_capability_admission":
        disposition = observation.get("disposition")
        if disposition == "EVIDENCE_REQUIRED" and observation.get("mutation_allowed", False):
            return True
        if disposition == "CUSTOM_REQUIRED" and observation.get("provider_miss_only", False):
            return True
        if observation.get("exact_source_contradicts_provider", False) and observation.get("provider_controls_conclusion", False):
            return True
        if disposition == "REUSE_EXISTING" and observation.get("exact_owner_full", False) and observation.get("new_parallel_mechanism", False) and not observation.get("owner_exception", False):
            return True
        if disposition == "EXTEND_EXISTING" and observation.get("change_scope_exceeds_gap", False):
            return True
        return False
    if oracle == "bounded_work_control":
        allowed_repeat_reasons = {
            "CHANGED_QUESTION_OR_PROPERTY",
            "CHANGED_SOURCE_OR_BASELINE",
            "NEWLY_PROVEN_DEPENDENCY_OR_CALL_EDGE",
            "TRUNCATION_PAGINATION_INCOMPLETE_OUTPUT",
            "CONTRADICTION",
        }
        bind_missing = observation.get("additional_exploration", False) and not all(
            observation.get(key, False)
            for key in (
                "obligation_bound",
                "property_bound",
                "smallest_closure_bound",
                "expected_evidence_bound",
                "exit_condition_bound",
            )
        )
        repeat_bad = (
            observation.get("repeated_search_read_test", False)
            and observation.get("repeat_reason") not in allowed_repeat_reasons
            and not observation.get("bounded_discriminating_retrace", False)
        )
        false_progress = observation.get("claims_material_progress", False) and any(
            observation.get(key, False)
            for key in (
                "new_file_symbol_only",
                "repeated_green_unchanged_bytes",
                "rewritten_explanation_only",
                "search_miss_only",
                "novelty_outside_accepted_outcome",
            )
        )
        return (
            bind_missing
            or repeat_bad
            or (
                observation.get("repeated_nonprogress", False)
                and (
                    observation.get("self_extends_without_progress", False)
                    or int(observation.get("discriminating_retrace_count", 0)) > 1
                )
            )
            or (
                observation.get("internal_boundary", False)
                and observation.get("requires_user_confirmation", False)
                and not observation.get("material_user_boundary", False)
            )
            or (
                observation.get("routine_phase_transition", False)
                and observation.get("stops_for_user_confirmation", False)
                and not observation.get("material_user_boundary", False)
            )
            or (
                observation.get("material_user_boundary", False)
                and not observation.get("returns_to_user", False)
            )
            or (
                observation.get("source_budget_extended", False)
                and (
                    not observation.get("necessary_accepted_scope_dependency", False)
                    or not observation.get("finite_exit_condition", False)
                )
            )
            or (
                observation.get("validation_failure", False)
                and observation.get("reopens_unaffected_closures", False)
            )
            or (
                observation.get("material_fix", False)
                and not observation.get("reroutes_dependent_obligations", False)
            )
            or (
                observation.get("delivery_projection", False)
                and observation.get("rediscovery_without_contradiction", False)
            )
            or false_progress
            or (
                observation.get("material_progress", False)
                and observation.get("expands_scope_without_followup", False)
            )
            or (
                observation.get("truncated_or_partial_output", False)
                and observation.get("claims_absence", False)
            )
            or (
                observation.get("focused_question", False)
                and observation.get("drops_required_obligations", False)
            )
            or (
                observation.get("secondary_active_question", False)
                and not observation.get("discriminating_comparison", False)
            )
            or (
                observation.get("batching_or_renaming", False)
                and observation.get("bypasses_work_control", False)
            )
            or (
                observation.get("interrupted_mutation", False)
                and observation.get("retry_before_native_recovery", False)
            )
            or observation.get("claims_platform_reset_or_hard_boundary", False)
        )
    if oracle == "structure_property_boolean_contract":
        uses_out = observation.get("structure_property_out_param", False)
        bare_bool = observation.get("bare_boolean_consumption", False)
        claims_ready = observation.get("claims_ready", False)
        recognizes_absent = observation.get("absent_key_undefined_path_recognized", False)
        presence_as_type = observation.get("presence_used_as_type_proof", False)
        safe_contract = (
            observation.get("boolean_domain_proven", False)
            or observation.get("boolean_normalized", False)
        )
        return bool(
            uses_out
            and bare_bool
            and claims_ready
            and (presence_as_type or not recognizes_absent or not safe_contract)
        )
    raise ValueError(f"unknown oracle: {oracle}")


ids = []
for case in DOC.get("cases", []):
    cid = case.get("id")
    ids.append(cid)
    try:
        bad_rejected = violates(case, case.get("bad", {}))
        good_accepted = not violates(case, case.get("good", {}))
        ok = bool(cid) and bad_rejected and good_accepted
        details = {"oracle": case.get("oracle"), "bad_rejected": bad_rejected, "good_accepted": good_accepted}
    except Exception as exc:
        ok = False
        details = {"error": str(exc)}
    results[f"semantic_behavior:{cid}"] = {"pass": ok, "details": details}
    if not ok:
        errors.append({"case": cid, "details": details})

if len(ids) != len(set(ids)):
    errors.append({"case": "duplicate_ids", "ids": ids})

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results, "cases": len(ids)}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
