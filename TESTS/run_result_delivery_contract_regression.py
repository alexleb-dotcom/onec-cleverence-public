#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "WORKFLOW/RESULT_DELIVERY_CONTRACT.json"
GUIDE_PATH = ROOT / "KNOWLEDGE/RESULT_DELIVERY.md"
SKILL_PATH = ROOT / "SKILL.md"
PIPELINE_PATH = ROOT / "WORKFLOW/DEVELOPMENT_PIPELINE.json"
CHANGE_PACKAGE_PATH = ROOT / "TEMPLATES/CHANGE_PACKAGE_MANIFEST.json"
REQUIREMENTS_ARTIFACT_TEMPLATE_PATH = ROOT / "TEMPLATES/REQUIREMENTS_ARTIFACT_TEMPLATE.md"
MANUAL_TRANSFER_TEMPLATE_PATH = ROOT / "TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md"
README_PATH = ROOT / "README.md"
PUBLIC_WORKFLOW_PATH = ROOT / ".github/workflows/shareable-validation.yml"
PUBLIC_CI_INVENTORY_PATH = ROOT / "TOOLS/PUBLIC_CI_INVENTORY.json"
FINAL_DOCX_VALIDATOR_PATH = ROOT / "TOOLS/final_docx_set.py"

EXPECTED_SECTIONS = ["OUTCOME", "RESULT", "VERIFICATION", "PROOF_BOUNDARY", "ARTIFACTS", "USER_ACTION"]
EXPECTED_PROFILES = {"ANALYSIS_REPORT", "IMPLEMENTATION_DELIVERY", "REQUIREMENTS_ARTIFACT", "BLOCKED_OR_PARTIAL"}
EXPECTED_FINDING_SHAPE = ["location", "as_is", "problem", "recommendation", "rationale", "evidence_boundary"]
EXPECTED_IMPLEMENTATION_NOTES_HEADER_ORDER = [
    "tz_number",
    "project",
    "task",
    "platform_version",
    "configuration_name_version",
]
EXPECTED_IMPLEMENTATION_NOTES_HEADER_LABELS = {
    "tz_number": "Номер ТЗ",
    "project": "Проект",
    "task": "Задача",
    "platform_version": "Версия платформы",
    "configuration_name_version": "Наименование и версия конфигурации",
}
EXPECTED_IMPLEMENTATION_NOTES_ROW_ORDER = [
    "container",
    "configuration_object",
    "procedure_function",
    "status",
    "change_description",
]
EXPECTED_IMPLEMENTATION_NOTES_LABELS = {
    "container": "Контейнер",
    "configuration_object": "ОбъектКонфигурации",
    "procedure_function": "Процедура/Функция",
    "status": "Статус",
    "change_description": "ОписаниеИзменений",
}



EXPECTED_PERFORMANCE_PROJECTION_FIELDS = [
    "current_algorithm",
    "proposed_algorithm",
    "passes_nested_searches_io",
    "asymptotic_time",
    "memory_and_copies",
    "client_server_db_topology",
    "reviewed_scale",
    "preservation",
    "runtime_status",
]
STRUCTURAL_DISCLOSURE_RU = "Измеренное ускорение не доказано."


def project_performance_review(readiness: dict, review: dict | None, runtime_cases: dict | None, release_outcome: str) -> dict:
    """Test oracle for the presentation boundary; it never mutates canonical readiness/outcome."""
    errors: list[str] = []
    projection = {"release_outcome": release_outcome, "state": "BLOCKED"}
    if not isinstance(readiness, dict) or readiness.get("result") != "PASS" or readiness.get("readiness_outcome") != "READY_FOR_IMPLEMENTATION":
        errors.append("canonical_performance_readiness_not_pass")
        projection["errors"] = errors
        return projection
    if not isinstance(review, dict):
        errors.append("performance_review_missing")
        projection["errors"] = errors
        return projection
    fingerprint = readiness.get("candidate_fingerprint_sha256")
    if not fingerprint or review.get("candidate_fingerprint_sha256") != fingerprint:
        errors.append("performance_review_candidate_binding_stale")
    required = readiness.get("required") is True
    if not required:
        if review.get("status") != "NOT_APPLICABLE" or review.get("detected_by"):
            errors.append("performance_review_na_not_verifier_confirmed")
        if errors:
            projection["errors"] = errors
            return projection
        projection.update({"state": "NOT_APPLICABLE", "message": "Verifier-confirmed: COLLECTION_ALGORITHM is inactive for the exact candidate."})
        return projection
    if review.get("status") != "PASS":
        errors.append("active_performance_review_not_pass")
    for key in ("current_algorithm", "proposed_algorithm", "preservation", "runtime_profiling"):
        if not isinstance(review.get(key), dict) or not review.get(key):
            errors.append(f"performance_review_section_missing:{key}")
    if errors:
        projection["errors"] = errors
        return projection
    runtime = review["runtime_profiling"]
    mode = runtime.get("mode")
    if mode == "STRUCTURAL_ONLY":
        if runtime.get("measured_speedup_claim") not in (None, "") or runtime.get("runtime_case_id") not in (None, ""):
            errors.append("structural_review_contains_measured_claim")
        if not errors:
            projection.update({"state": "STRUCTURAL_ONLY", "runtime_status": STRUCTURAL_DISCLOSURE_RU})
    elif mode == "MEASURED":
        case_id = runtime.get("runtime_case_id")
        case = (runtime_cases or {}).get(case_id) if case_id else None
        if not runtime.get("measured_speedup_claim") or not case_id:
            errors.append("measured_review_claim_or_case_missing")
        elif not isinstance(case, dict) or case.get("status") != "PASS" or case.get("_observation_kind") != "RUNTIME_ADAPTER" or case.get("_verified_property") != readiness.get("runtime_property_id"):
            errors.append("measured_review_runtime_not_verifier_confirmed")
        if not errors:
            projection.update({"state": "MEASURED", "runtime_status": runtime.get("measured_speedup_claim")})
    else:
        errors.append("performance_review_runtime_mode_invalid")
    if errors:
        projection["state"] = "BLOCKED"
        projection["errors"] = errors
    return projection


def validate_contract(contract: dict) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != 2:
        errors.append("result_contract_schema_version")
    if contract.get("owner") != "FINAL_USER_RESULT_PRESENTATION":
        errors.append("result_contract_owner")
    if contract.get("applies_to") != "NON_TRIVIAL_SKILL_TASKS":
        errors.append("result_contract_scope")

    sections = contract.get("common_sections") or []
    ids = [row.get("id") for row in sections if isinstance(row, dict)]
    if ids != EXPECTED_SECTIONS:
        errors.append(f"result_contract_section_order:{ids}")
    if len(ids) != len(set(ids)):
        errors.append("result_contract_duplicate_sections")
    section_map = {row.get("id"): row for row in sections if isinstance(row, dict)}
    if section_map.get("OUTCOME", {}).get("required") is not True:
        errors.append("result_contract_outcome_required")
    if section_map.get("RESULT", {}).get("required") is not True:
        errors.append("result_contract_result_required")
    if "runtime_or_deployment_not_observed" not in set(section_map.get("PROOF_BOUNDARY", {}).get("required_when") or []):
        errors.append("result_contract_proof_boundary_runtime_trigger_missing")
    if "include only when a concrete next action is required" not in str(section_map.get("USER_ACTION", {}).get("conditional") or ""):
        errors.append("result_contract_user_action_must_be_conditional")

    profiles = contract.get("profiles") or {}
    if set(profiles) != EXPECTED_PROFILES:
        errors.append(f"result_contract_profiles:{sorted(profiles)}")
    analysis = profiles.get("ANALYSIS_REPORT") or {}
    if analysis.get("finding_shape") != EXPECTED_FINDING_SHAPE:
        errors.append(f"analysis_finding_shape:{analysis.get('finding_shape')}")
    labels = analysis.get("finding_labels_ru") or {}
    for field in EXPECTED_FINDING_SHAPE:
        if not labels.get(field):
            errors.append(f"analysis_finding_label_missing:{field}")
    if analysis.get("code_comparison", {}).get("when") is None:
        errors.append("analysis_code_comparison_condition_missing")

    implementation = profiles.get("IMPLEMENTATION_DELIVERY") or {}
    implementation_modes = set(implementation.get("primary_result_modes") or [])
    for required in {
        "DIRECT_SOURCE_CHANGESET",
        "MANUAL_TRANSFER_INSTRUCTION",
        "PATCH_DIFF",
        "IMPORTABLE_ARTIFACT",
        "FULL_COMPARE_SET",
    }:
        if required not in implementation_modes:
            errors.append(f"implementation_result_mode_missing:{required}")

    mode_selection = implementation.get("delivery_mode_selection") or {}
    if mode_selection.get("must_precede_final_artifact_construction") is not True:
        errors.append("delivery_mode_must_precede_artifact_construction")
    decision_inputs = set(mode_selection.get("decision_inputs") or [])
    for required in {
        "explicit user request",
        "project modification policy",
        "target/source topology",
        "authorized and actually available direct mutation mechanism",
        "exact import mechanism and validation boundary",
        "whether a human is expected to apply the change",
    }:
        if required not in decision_inputs:
            errors.append(f"delivery_mode_decision_input_missing:{required}")
    if "ability to generate XML is not evidence" not in str(mode_selection.get("xml_capability_rule") or ""):
        errors.append("xml_capability_must_not_imply_importable_delivery")
    if mode_selection.get("manual_transfer_default_result") != "MANUAL_TRANSFER_INSTRUCTION":
        errors.append("manual_transfer_default_result_missing")
    manual_default = "\n".join(mode_selection.get("manual_transfer_default_when") or [])
    for anchor in ["human Configurator/extension", "direct target mutation", "no exact importable artifact route"]:
        if anchor not in manual_default:
            errors.append(f"manual_transfer_default_condition_missing:{anchor}")
    import_requirements = "\n".join(mode_selection.get("importable_artifact_requires") or [])
    for anchor in ["exact import mechanism", "artifact semantics/shape", "validation boundary"]:
        if anchor not in import_requirements:
            errors.append(f"importable_artifact_proof_missing:{anchor}")

    if "implementation_notes" not in (implementation.get("result_shape") or []):
        errors.append("implementation_notes_result_shape_missing")
    notes = implementation.get("implementation_notes") or {}
    if notes.get("title_ru") != "Особенности реализации" or notes.get("required") is not True:
        errors.append("implementation_notes_required_contract_missing")
    if "deterministically applicable" not in str(notes.get("trigger_contract") or ""):
        errors.append("implementation_notes_deterministic_trigger_missing")
    if "incomplete" not in str(notes.get("completion_gate") or ""):
        errors.append("implementation_notes_completion_gate_missing")
    if notes.get("header_order") != EXPECTED_IMPLEMENTATION_NOTES_HEADER_ORDER:
        errors.append(f"implementation_notes_header_order:{notes.get('header_order')}")
    if notes.get("header_labels_ru") != EXPECTED_IMPLEMENTATION_NOTES_HEADER_LABELS:
        errors.append(f"implementation_notes_header_labels_exact:{notes.get('header_labels_ru')}")
    if notes.get("row_order") != EXPECTED_IMPLEMENTATION_NOTES_ROW_ORDER:
        errors.append(f"implementation_notes_row_order:{notes.get('row_order')}")
    labels = notes.get("labels_ru") or {}
    if labels != EXPECTED_IMPLEMENTATION_NOTES_LABELS:
        errors.append(f"implementation_notes_labels_exact:{labels}")
    if notes.get("format") != "SEPARATE_DOCX_HEADER_PLUS_TABLE":
        errors.append("implementation_notes_format_must_be_separate_docx_header_plus_table")
    if notes.get("header_fields_locked") is not True:
        errors.append("implementation_notes_header_fields_must_be_locked")
    if notes.get("base_columns_locked") is not True:
        errors.append("implementation_notes_base_columns_must_be_locked")
    if notes.get("additional_columns_allowed") is not False:
        errors.append("implementation_notes_extra_base_columns_must_be_forbidden")
    if notes.get("additional_information_allowed_outside_base_format") is not True:
        errors.append("implementation_notes_supplementary_information_policy_missing")
    header_field_rules = notes.get("header_field_rules") or {}
    for field in EXPECTED_IMPLEMENTATION_NOTES_HEADER_ORDER:
        if not header_field_rules.get(field):
            errors.append(f"implementation_notes_header_field_rule_missing:{field}")
    field_rules = notes.get("field_rules") or {}
    for field in EXPECTED_IMPLEMENTATION_NOTES_ROW_ORDER:
        if not field_rules.get(field):
            errors.append(f"implementation_notes_field_rule_missing:{field}")
    format_rules = "\n".join(notes.get("format_rules") or [])
    for anchor in [
        "five header fields are mandatory",
        "must not be repeated as table columns",
        "five base table columns are mandatory",
        "do not rename, remove, merge, split or reorder",
        "do not add extra columns to the base table",
        "outside the mandatory header and base table",
    ]:
        if anchor not in format_rules:
            errors.append(f"implementation_notes_format_rule_missing:{anchor}")
    identity_rules = "\n".join(notes.get("identity_rules") or [])
    for anchor in ["Project Context or requirements", "exact evidenced target context", "exact baseline/candidate layout", "same-named objects"]:
        if anchor not in identity_rules:
            errors.append(f"implementation_notes_identity_rule_missing:{anchor}")

    manual_output = implementation.get("manual_transfer_artifact_output") or {}
    if manual_output.get("required") is not True or manual_output.get("separate_file") is not True:
        errors.append("manual_transfer_separate_required_artifact_missing")
    if manual_output.get("chat_only_code_complete") is not False:
        errors.append("manual_transfer_chat_only_must_be_incomplete")
    for key in [
        "purpose_and_boundaries_required",
        "code_anchor_required",
        "ordered_deployment_sequence_required",
        "verification_matrix_required",
        "final_static_control_required",
        "changed_object_map_required",
    ]:
        if manual_output.get(key) is not True:
            errors.append(f"manual_transfer_closure_flag_missing:{key}")
    if manual_output.get("verification_matrix_columns") != ["Действие / сценарий", "Ожидаемый результат"]:
        errors.append("manual_transfer_verification_matrix_columns")
    manual_rules = "\n".join(implementation.get("manual_transfer_template_rules") or [])
    for anchor in [
        "purpose/boundaries",
        "do-not-change/do-not-do",
        "placement anchor",
        "ordered deployment sequence",
        "verification matrix",
        "final static-control checklist",
        "changed-object map",
    ]:
        if anchor not in manual_rules:
            errors.append(f"manual_transfer_rule_missing:{anchor}")

    performance = implementation.get("performance_review_projection") or {}
    if performance.get("title_ru") != "Performance Review":
        errors.append("performance_projection_title")
    if performance.get("owner_rule_id") != "COLLECTION_ALGORITHM" or performance.get("candidate_bound") is not True:
        errors.append("performance_projection_owner_or_binding")
    if performance.get("placement") != "OUTSIDE_IMPLEMENTATION_NOTES_BASE_FORMAT":
        errors.append("performance_projection_must_be_outside_implementation_notes")
    if performance.get("fields") != EXPECTED_PERFORMANCE_PROJECTION_FIELDS:
        errors.append(f"performance_projection_fields:{performance.get('fields')}")
    states = performance.get("runtime_states") or {}
    if states.get("STRUCTURAL_ONLY", {}).get("required_disclosure_ru") != STRUCTURAL_DISCLOSURE_RU:
        errors.append("performance_projection_structural_disclosure_missing")
    if "RUNTIME_ADAPTER" not in str(states.get("MEASURED", {}).get("rule") or ""):
        errors.append("performance_projection_measured_runtime_boundary_missing")
    if "inactive" not in str(states.get("NOT_APPLICABLE", {}).get("rule") or "") or "detected_by" not in str(states.get("NOT_APPLICABLE", {}).get("rule") or ""):
        errors.append("performance_projection_na_verifier_boundary_missing")
    if "missing" not in str(states.get("BLOCKED", {}).get("rule") or "") or "stale" not in str(states.get("BLOCKED", {}).get("rule") or ""):
        errors.append("performance_projection_blocked_visibility_missing")
    performance_rules = "\n".join(performance.get("rules") or [])
    for performance_anchor in [
        "generic prose",
        "STRUCTURAL_ONLY",
        "RUNTIME_ADAPTER",
        "NOT_APPLICABLE",
        "missing, stale, wrong-candidate",
        "cannot change implementation_readiness or final release_outcome",
        "outside the mandatory project/task header and immutable five-column",
    ]:
        if performance_anchor not in performance_rules:
            errors.append(f"performance_projection_rule_missing:{performance_anchor}")

    blocked = profiles.get("BLOCKED_OR_PARTIAL") or {}
    if set(blocked.get("takes_precedence_over") or []) != {
        "ANALYSIS_REPORT",
        "IMPLEMENTATION_DELIVERY",
        "REQUIREMENTS_ARTIFACT",
    }:
        errors.append("blocked_profile_must_take_precedence")
    blocked_rules = "\n".join(blocked.get("rules") or [])
    if "never use ready/proven/completed wording" not in blocked_rules:
        errors.append("blocked_profile_readiness_laundering_guard_missing")
    if "smallest concrete artifact or answer" not in blocked_rules:
        errors.append("blocked_profile_minimal_request_guard_missing")

    readiness = "\n".join((contract.get("readiness_binding") or {}).get("rules") or [])
    for anchor in [
        "BLOCKED must not become ready in prose",
        "READY_FOR_RUNTIME_TEST must not become runtime-proven in prose",
        "ProjectSnapshot package ACCEPTED proves binding/provenance only",
        "delivery artifact validation does not imply applied-target",
    ]:
        if anchor not in readiness:
            errors.append(f"readiness_guard_missing:{anchor}")

    conciseness = contract.get("conciseness") or {}
    for key in ["trivial_tasks_exempt", "omit_empty_sections", "omit_user_action_when_none", "prefer_root_findings_over_repeated_symptoms"]:
        if conciseness.get(key) is not True:
            errors.append(f"conciseness_contract_missing:{key}")
    if conciseness.get("internal_gate_dump_by_default") is not False:
        errors.append("internal_gate_dump_must_be_false_by_default")

    final_docx = contract.get("final_docx_set_validation") or {}
    if final_docx.get("owner") != "RESULT_DELIVERY":
        errors.append("final_docx_owner_must_be_result_delivery")
    if final_docx.get("validator") != "TOOLS/final_docx_set.py":
        errors.append("final_docx_validator_binding_missing")
    if final_docx.get("verification_phase") != "POST_RENDER_POST_PUBLISH_PRE_DELIVERY":
        errors.append("final_docx_verification_phase_invalid")
    derivation = final_docx.get("required_kind_derivation") or {}
    for kind in ["implementation_notes", "manual_transfer", "requirements", "line_by_line", "combined_alternate"]:
        if not derivation.get(kind):
            errors.append(f"final_docx_required_kind_derivation_missing:{kind}")
    if "never substitutes" not in str(derivation.get("combined_alternate") or ""):
        errors.append("final_docx_combined_alternate_must_not_replace_separate_docs")
    binding = final_docx.get("current_binding") or {}
    if binding.get("marker") != "ONEC_RESULT_DELIVERY_BINDING_V1:":
        errors.append("final_docx_binding_marker_invalid")
    expected_binding_fields = [
        "task_id",
        "candidate_sha256",
        "package_binding_sha256",
        "change_items_sha256",
        "result_mode",
        "artifact_kind",
    ]
    if binding.get("fields") != expected_binding_fields:
        errors.append(f"final_docx_binding_fields:{binding.get('fields')}")
    if "circular hashing" not in str(binding.get("package_binding_rule") or ""):
        errors.append("final_docx_package_binding_circularity_rule_missing")
    publication = final_docx.get("publication_binding") or {}
    if "REQUIRES_ROUTE_E2E" not in str(publication.get("platform_attachment") or ""):
        errors.append("final_docx_platform_attachment_route_e2e_missing")
    receipt = final_docx.get("receipt") or {}
    if receipt.get("receipt_kind") != "FINAL_DOCX_SET" or receipt.get("schema_version") != 1:
        errors.append("final_docx_receipt_contract_invalid")
    proof_boundary = "\n".join(final_docx.get("proof_boundary") or [])
    for anchor in [
        "do not prove semantic fidelity",
        "existing delivery semantic review",
        "does not prove applied target",
        "REQUIRES_ROUTE_E2E",
    ]:
        if anchor not in proof_boundary:
            errors.append(f"final_docx_proof_boundary_missing:{anchor}")
    ordering = "\n".join(final_docx.get("ordering_rules") or [])
    for anchor in [
        "render all required separate DOCX",
        "publish/resolve their final references",
        "run final_docx_set validator",
        "only then deliver",
        "pre-render release receipt",
    ]:
        if anchor not in ordering:
            errors.append(f"final_docx_ordering_rule_missing:{anchor}")
    return errors


def contains_key(value: object, target: str) -> bool:
    if isinstance(value, dict):
        return target in value or any(contains_key(v, target) for v in value.values())
    if isinstance(value, list):
        return any(contains_key(v, target) for v in value)
    return False


def main() -> int:
    errors: list[str] = []
    controls: dict[str, dict] = {}

    def control(case_id: str, ok: bool, details=None):
        controls[case_id] = {"pass": bool(ok)}
        if details is not None:
            controls[case_id]["details"] = details
        if not ok:
            errors.append(f"control_failed:{case_id}")
    for path in [CONTRACT_PATH, GUIDE_PATH, SKILL_PATH, PIPELINE_PATH, CHANGE_PACKAGE_PATH, REQUIREMENTS_ARTIFACT_TEMPLATE_PATH, MANUAL_TRANSFER_TEMPLATE_PATH, README_PATH, PUBLIC_WORKFLOW_PATH, PUBLIC_CI_INVENTORY_PATH, FINAL_DOCX_VALIDATOR_PATH]:
        if not path.is_file():
            errors.append(f"missing:{path.relative_to(ROOT)}")
    if errors:
        print(json.dumps({"result": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 2

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors.extend(validate_contract(contract))

    req_profile = (contract.get("profiles") or {}).get("REQUIREMENTS_ARTIFACT") or {}
    impl_profile = (contract.get("profiles") or {}).get("IMPLEMENTATION_DELIVERY") or {}
    if req_profile.get("template") != "TEMPLATES/REQUIREMENTS_ARTIFACT_TEMPLATE.md":
        errors.append("requirements_artifact_template_reference_missing")
    if impl_profile.get("manual_transfer_instruction_template") != "TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md":
        errors.append("manual_transfer_template_reference_missing")
    artifact_format = contract.get("user_artifact_format") or {}
    for token in ["Russian UTF-8", "remain literal", "pseudo-version", "cannot create or upgrade"]:
        if token not in "\n".join(str(v) for v in artifact_format.values()):
            errors.append(f"user_artifact_format_missing:{token}")

    requirements_template = REQUIREMENTS_ARTIFACT_TEMPLATE_PATH.read_text(encoding="utf-8")
    for token in [
        "Функциональная спецификация.docx",
        "Потребность / проблема",
        "Целевой результат",
        "Границы",
        "Функциональное поведение и материальные правила",
        "Приемка",
        "Открытые вопросы / блокеры",
        "Допущения",
        "Предлагаемое решение",
        "Основания и граница доказанности",
        "REQUIREMENTS_BLOCKED",
        "requirements_gate.py",
        "Truly empty conditional sections are omitted",
        "Internal authoring invariants",
    ]:
        if token not in requirements_template:
            errors.append(f"requirements_artifact_template_missing:{token}")

    manual_template = MANUAL_TRANSFER_TEMPLATE_PATH.read_text(encoding="utf-8")
    for token in [
        "Инструкция по внедрению.docx",
        "Целевая база / артефакт",
        "Создаваемые объекты",
        "Изменяемые объекты",
        "Код",
        "Было",
        "Стало",
        "Обоснование",
        "Применимый стандарт/правило",
        "AUTHOR_MARKER",
        "object-first",
        "ChangePackage",
        "Граница доказанности",
        "Назначение и границы",
        "Не изменять / не делать",
        "Якорь / место изменения",
        "Порядок внедрения",
        "Матрица проверки",
        "Ожидаемый результат",
        "Финальный статический контроль",
        "Карта изменённых объектов",
    ]:
        if token not in manual_template:
            errors.append(f"manual_transfer_template_missing:{token}")

    # Negative controls: the validator must reject the two most important output shortcuts.
    no_boundary = copy.deepcopy(contract)
    no_boundary["common_sections"] = [row for row in no_boundary["common_sections"] if row.get("id") != "PROOF_BOUNDARY"]
    if not validate_contract(no_boundary):
        errors.append("negative_control_missing_proof_boundary_not_rejected")
    collapsed_analysis = copy.deepcopy(contract)
    collapsed_analysis["profiles"]["ANALYSIS_REPORT"]["finding_shape"] = ["problem", "recommendation"]
    if not validate_contract(collapsed_analysis):
        errors.append("negative_control_collapsed_analysis_shape_not_rejected")
    no_implementation_notes = copy.deepcopy(contract)
    no_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"].pop("implementation_notes", None)
    if not validate_contract(no_implementation_notes):
        errors.append("negative_control_missing_implementation_notes_not_rejected")
    no_mode_selection = copy.deepcopy(contract)
    no_mode_selection["profiles"]["IMPLEMENTATION_DELIVERY"].pop("delivery_mode_selection", None)
    if not validate_contract(no_mode_selection):
        errors.append("negative_control_missing_delivery_mode_selection_not_rejected")
    chat_only_manual = copy.deepcopy(contract)
    chat_only_manual["profiles"]["IMPLEMENTATION_DELIVERY"]["manual_transfer_artifact_output"]["chat_only_code_complete"] = True
    if not validate_contract(chat_only_manual):
        errors.append("negative_control_chat_only_manual_delivery_not_rejected")
    incomplete_implementation_notes = copy.deepcopy(contract)
    incomplete_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["row_order"].remove("status")
    if not validate_contract(incomplete_implementation_notes):
        errors.append("negative_control_incomplete_implementation_notes_not_rejected")
    missing_header_implementation_notes = copy.deepcopy(contract)
    missing_header_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["header_order"].remove("task")
    if not validate_contract(missing_header_implementation_notes):
        errors.append("negative_control_missing_task_header_not_rejected")
    reordered_header_implementation_notes = copy.deepcopy(contract)
    reordered_header_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["header_order"].reverse()
    if not validate_contract(reordered_header_implementation_notes):
        errors.append("negative_control_reordered_header_not_rejected")
    renamed_header_implementation_notes = copy.deepcopy(contract)
    renamed_header_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["header_labels_ru"]["project"] = "Проект 1С"
    if not validate_contract(renamed_header_implementation_notes):
        errors.append("negative_control_renamed_project_header_not_rejected")
    reordered_implementation_notes = copy.deepcopy(contract)
    reordered_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["row_order"][0:2] = list(reversed(reordered_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["row_order"][0:2]))
    if not validate_contract(reordered_implementation_notes):
        errors.append("negative_control_reordered_implementation_notes_not_rejected")
    renamed_implementation_notes = copy.deepcopy(contract)
    renamed_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["labels_ru"]["container"] = "Контур"
    if not validate_contract(renamed_implementation_notes):
        errors.append("negative_control_renamed_implementation_notes_label_not_rejected")
    repeated_project_column = copy.deepcopy(contract)
    repeated_project_column["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["row_order"].insert(0,"project")
    repeated_project_column["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["labels_ru"]["project"] = "Проект"
    if not validate_contract(repeated_project_column):
        errors.append("negative_control_project_repeated_as_column_not_rejected")
    extra_column_implementation_notes = copy.deepcopy(contract)
    extra_column_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["row_order"].append("evidence")
    extra_column_implementation_notes["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]["labels_ru"]["evidence"] = "Доказательство"
    if not validate_contract(extra_column_implementation_notes):
        errors.append("negative_control_extra_implementation_notes_column_not_rejected")

    # Performance Review projection controls. Canonical readiness remains the owner; projection is read-only.
    fp = "a" * 64
    runtime_property = f"PERFORMANCE_REVIEW:{fp}"
    ready_required = {"result": "PASS", "readiness_outcome": "READY_FOR_IMPLEMENTATION", "required": True, "candidate_fingerprint_sha256": fp, "runtime_property_id": runtime_property}
    structural_review = {
        "status": "PASS", "candidate_fingerprint_sha256": fp, "detected_by": ["Для Каждого"],
        "current_algorithm": {"summary": "nested scan"}, "proposed_algorithm": {"summary": "indexed single pass"},
        "preservation": {"result": "PRESERVED"},
        "runtime_profiling": {"mode": "STRUCTURAL_ONLY", "measured_speedup_claim": None, "runtime_case_id": None},
    }
    projection = project_performance_review(ready_required, structural_review, {}, "PROVEN")
    control("result_delivery:structural_review_does_not_claim_measured_speedup", projection.get("state") == "STRUCTURAL_ONLY" and projection.get("runtime_status") == STRUCTURAL_DISCLOSURE_RU and projection.get("release_outcome") == "PROVEN", projection)

    structural_claim = copy.deepcopy(structural_review)
    structural_claim["runtime_profiling"]["measured_speedup_claim"] = "2x faster"
    projection = project_performance_review(ready_required, structural_claim, {}, "PROVEN")
    control("result_delivery:structural_measured_claim_is_blocked", projection.get("state") == "BLOCKED", projection)

    measured_review = copy.deepcopy(structural_review)
    measured_review["runtime_profiling"] = {"mode": "MEASURED", "measured_speedup_claim": "2x faster", "runtime_case_id": "perf-1"}
    verified_runtime = {"perf-1": {"status": "PASS", "_observation_kind": "RUNTIME_ADAPTER", "_verified_property": runtime_property}}
    projection = project_performance_review(ready_required, measured_review, verified_runtime, "PROVEN")
    control("result_delivery:measured_review_requires_verified_runtime", projection.get("state") == "MEASURED" and projection.get("runtime_status") == "2x faster", projection)

    unverified_runtime = {"perf-1": {"status": "PASS", "_observation_kind": "TRUSTED_MANUAL_REVIEW", "_verified_property": runtime_property}}
    projection = project_performance_review(ready_required, measured_review, unverified_runtime, "PROVEN")
    control("result_delivery:unverified_measured_review_is_blocked", projection.get("state") == "BLOCKED", projection)

    stale_review = copy.deepcopy(structural_review)
    stale_review["candidate_fingerprint_sha256"] = "b" * 64
    projection = project_performance_review(ready_required, stale_review, {}, "BLOCKED")
    control("result_delivery:stale_review_not_rendered_ready", projection.get("state") == "BLOCKED" and projection.get("release_outcome") == "BLOCKED", projection)

    projection = project_performance_review(ready_required, None, {}, "BLOCKED")
    control("result_delivery:missing_active_review_remains_visible_blocker", projection.get("state") == "BLOCKED", projection)

    generic_review = {"status": "PASS", "candidate_fingerprint_sha256": fp, "reason": "looks good", "detected_by": ["Для Каждого"]}
    projection = project_performance_review(ready_required, generic_review, {}, "BLOCKED")
    control("result_delivery:generic_prose_does_not_project_ready_review", projection.get("state") == "BLOCKED", projection)

    active_na = copy.deepcopy(structural_review)
    active_na["status"] = "NOT_APPLICABLE"
    projection = project_performance_review(ready_required, active_na, {}, "BLOCKED")
    control("result_delivery:active_performance_review_cannot_project_na", projection.get("state") == "BLOCKED", projection)

    ready_inactive = {"result": "PASS", "readiness_outcome": "READY_FOR_IMPLEMENTATION", "required": False, "candidate_fingerprint_sha256": fp}
    inactive_review = {"status": "NOT_APPLICABLE", "candidate_fingerprint_sha256": fp, "detected_by": []}
    projection = project_performance_review(ready_inactive, inactive_review, {}, "ANALYSIS_COMPLETE")
    control("result_delivery:inactive_exact_candidate_projects_verifier_na", projection.get("state") == "NOT_APPLICABLE" and projection.get("release_outcome") == "ANALYSIS_COMPLETE", projection)

    locked_notes = contract["profiles"]["IMPLEMENTATION_DELIVERY"]["implementation_notes"]
    perf_contract = contract["profiles"]["IMPLEMENTATION_DELIVERY"]["performance_review_projection"]
    control(
        "result_delivery:performance_projection_cannot_mutate_implementation_notes_columns",
        locked_notes.get("row_order") == EXPECTED_IMPLEMENTATION_NOTES_ROW_ORDER
        and locked_notes.get("labels_ru") == EXPECTED_IMPLEMENTATION_NOTES_LABELS
        and perf_contract.get("placement") == "OUTSIDE_IMPLEMENTATION_NOTES_BASE_FORMAT",
        {"row_order": locked_notes.get("row_order"), "placement": perf_contract.get("placement")},
    )

    skill = SKILL_PATH.read_text(encoding="utf-8-sig")
    for anchor in [
        "WORKFLOW/RESULT_DELIVERY_CONTRACT.json",
        "KNOWLEDGE/RESULT_DELIVERY.md",
        "Как сейчас",
        "Проблема",
        "Рекомендуется",
        "Обоснование",
        "Do not dump the complete validation ledger",
        "Before final presentation, **load and obey**",
        "Presentation never upgrades canonical requirements/evidence/release status.",
        "Особенности реализации.docx",
        "Инструкция по внедрению.docx",
        "ability to generate XML does not by itself justify",
        "default to `MANUAL_TRANSFER_INSTRUCTION`",
    ]:
        if anchor not in skill:
            errors.append(f"skill_result_contract_missing:{anchor}")
    control(
        "result_delivery:skill_defers_exact_format_to_canonical_owner",
        "Exact artifact structure remains owned by the Result Delivery contract and artifact-specific templates" in skill
        and "not duplicated in this Skill body" in skill
        and "KNOWLEDGE/USER_ARTIFACT_DOCX.md" in skill
        and "TOOLS/render_user_artifact_docx.py" in skill,
        {
            "contract": "WORKFLOW/RESULT_DELIVERY_CONTRACT.json",
            "guide": "KNOWLEDGE/RESULT_DELIVERY.md",
        },
    )

    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    if pipeline.get("result_delivery_contract") != "WORKFLOW/RESULT_DELIVERY_CONTRACT.json":
        errors.append("pipeline_result_delivery_contract_reference_missing")
    if pipeline.get("requirements_artifact_template") != "TEMPLATES/REQUIREMENTS_ARTIFACT_TEMPLATE.md":
        errors.append("pipeline_requirements_artifact_template_reference_missing")
    if pipeline.get("manual_transfer_instruction_template") != "TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md":
        errors.append("pipeline_manual_transfer_template_reference_missing")
    requirements_stage = next((row for row in pipeline.get("stages") or [] if row.get("id") == "REQUIREMENTS_AND_SCOPE"), {})
    requirements_actions = "\n".join(requirements_stage.get("actions") or [])
    if "TEMPLATES/REQUIREMENTS_ARTIFACT_TEMPLATE.md" not in requirements_actions or "never upgrade the requirements gate" not in requirements_actions or "Функциональная спецификация.docx" not in requirements_actions:
        errors.append("pipeline_requirements_artifact_rendering_contract_missing")
    implementation_stage = next((row for row in pipeline.get("stages") or [] if row.get("id") == "IMPLEMENTATION"), {})
    implementation_actions = "\n".join(implementation_stage.get("actions") or [])
    for anchor in ["before constructing final implementation artifacts", "technical ability to generate XML does not imply IMPORTABLE_ARTIFACT", "default to MANUAL_TRANSFER_INSTRUCTION"]:
        if anchor not in implementation_actions:
            errors.append(f"pipeline_delivery_mode_selection_missing:{anchor}")
    final_stage = next((row for row in pipeline.get("stages") or [] if row.get("id") == "FINAL_ARTIFACT_VALIDATION"), {})
    final_actions = "\n".join(final_stage.get("actions") or [])
    if "RESULT_DELIVERY_CONTRACT.json" not in final_actions:
        errors.append("pipeline_final_stage_must_apply_result_delivery_contract")
    if "must not upgrade the canonical gate outcome" not in final_actions:
        errors.append("pipeline_final_stage_readiness_guard_missing")
    for anchor in [
        "TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md",
        "separate mandatory Инструкция по внедрению.docx",
        "Создаваемые объекты -> Изменяемые объекты -> Код",
        "ChangePackage remains the machine delivery/proof owner",
        "separate Особенности реализации.docx",
        "verification matrix with expected results",
        "changed-object map",
    ]:
        if anchor not in final_actions:
            errors.append(f"pipeline_manual_transfer_rendering_contract_missing:{anchor}")
    for anchor in ["COLLECTION_ALGORITHM", "Performance Review", "Измеренное ускорение не доказано.", "RUNTIME_ADAPTER", "separate DOCX artifact proof boundary"]:
        if anchor not in final_actions:
            errors.append(f"pipeline_performance_projection_missing:{anchor}")

    change_package = json.loads(CHANGE_PACKAGE_PATH.read_text(encoding="utf-8"))
    if change_package.get("schema_version") != 2:
        errors.append("change_package_schema_must_be_2")
    if contains_key(change_package, "snapshot_id"):
        errors.append("change_package_must_not_require_nonexistent_snapshot_id")
    source_evidence = change_package.get("source_evidence") or {}
    if not isinstance(source_evidence.get("bindings"), list) or not source_evidence.get("bindings"):
        errors.append("change_package_source_evidence_bindings_required")
    binding = (source_evidence.get("bindings") or [{}])[0]
    for key in ["kind", "id", "sha256", "scope"]:
        if key not in binding:
            errors.append(f"change_package_binding_field_missing:{key}")
    proof_boundary = change_package.get("proof_boundary") or {}
    for key in ["delivery_artifact_validated", "applied_target_observed", "deployment_or_import_observed", "runtime_behavior_observed"]:
        if key not in proof_boundary:
            errors.append(f"change_package_proof_boundary_missing:{key}")

    guide = GUIDE_PATH.read_text(encoding="utf-8")
    if "WORKFLOW/RESULT_DELIVERY_CONTRACT.json" not in guide:
        errors.append("result_delivery_guide_must_name_machine_owner")
    if "final response" not in guide.lower():
        errors.append("result_delivery_guide_missing_final_response_scope")
    for anchor in [
        "### Особенности реализации",
        "Особенности реализации.docx",
        "Номер ТЗ",
        "Версия платформы",
        "Наименование и версия конфигурации",
        "| Контейнер | ОбъектКонфигурации | Процедура/Функция | Статус | ОписаниеИзменений |",
        "separate mandatory",
        "### Построчное обоснование изменений",
        "only on explicit user request",
        "### Performance Review",
        "Измеренное ускорение не доказано.",
        "RUNTIME_ADAPTER",
        "The projection cannot change `implementation_readiness` or the final `release_outcome`",
        "### Финальная проверка набора DOCX",
        "TOOLS/final_docx_set.py",
        "POST_RENDER_POST_PUBLISH_PRE_DELIVERY",
        "ONEC_RESULT_DELIVERY_BINDING_V1:",
        "REQUIRES_ROUTE_E2E",
    ]:
        if anchor not in guide:
            errors.append(f"result_delivery_guide_implementation_notes_missing:{anchor}")

    readme = README_PATH.read_text(encoding="utf-8")
    if "KNOWLEDGE/RESULT_DELIVERY.md" not in readme:
        errors.append("readme_result_delivery_reference_missing")

    public_workflow = PUBLIC_WORKFLOW_PATH.read_text(encoding="utf-8")
    public_inventory = json.loads(PUBLIC_CI_INVENTORY_PATH.read_text(encoding="utf-8"))
    result_delivery_inventory_rows = [
        row for row in public_inventory.get("checks", [])
        if row.get("id") == "result_delivery"
        and row.get("phase") == "FAST"
        and row.get("scope") == "PUBLIC_SHAREABLE_CORE_ONLY"
        and row.get("command") == ["{python}", "TESTS/run_result_delivery_contract_regression.py"]
    ]
    if (
        "python TOOLS/run_public_ci.py --mode FAST" not in public_workflow
        or len(result_delivery_inventory_rows) != 1
    ):
        errors.append("result_delivery_regression_not_executed_by_public_fast")

    final_docx_inventory_rows = [
        row for row in public_inventory.get("checks", [])
        if row.get("id") == "final_docx_set"
        and row.get("phase") == "FAST"
        and row.get("scope") == "PUBLIC_SHAREABLE_CORE_ONLY"
        and row.get("command") == ["{python}", "TESTS/run_final_docx_set_regression.py"]
    ]
    if len(final_docx_inventory_rows) != 1:
        errors.append("final_docx_set_regression_not_executed_by_public_fast")

    print(json.dumps({"result": "PASS" if not errors else "FAIL", "errors": errors, "controls": controls}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
