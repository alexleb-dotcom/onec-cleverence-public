#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from plan_project_snapshot_collection import build_plan  # noqa: E402

REQUEST_PATH = ROOT / "TESTS/fixtures/project_snapshot_request_collector.json"
MATRIX_PATH = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_CAPABILITIES.json"
RUNTIME_PROFILE_PATH = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_RUNTIME_V1_CAPABILITIES.json"
TOOL_PATH = ROOT / "TOOLS/plan_project_snapshot_collection.py"
SKILL_PATH = ROOT / "SKILL.md"
EVIDENCE_ACQUISITION_PATH = ROOT / "KNOWLEDGE/EVIDENCE_ACQUISITION.md"
CHAT_WORKFLOW_PATH = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md"
COLLECTOR_ARCH_PATH = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR.md"
ORCHESTRATION_PATH = ROOT / "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json"
PIPELINE_PATH = ROOT / "WORKFLOW/DEVELOPMENT_PIPELINE.json"


def _check_chat_orchestration(errors: list[str]) -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    acquisition = EVIDENCE_ACQUISITION_PATH.read_text(encoding="utf-8")
    chat_workflow = CHAT_WORKFLOW_PATH.read_text(encoding="utf-8")
    collector_arch = COLLECTOR_ARCH_PATH.read_text(encoding="utf-8")
    orchestration = json.loads(ORCHESTRATION_PATH.read_text(encoding="utf-8"))
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    if "KNOWLEDGE/EVIDENCE_ACQUISITION.md" not in skill:
        errors.append("skill_must_route_evidence_gaps_through_acquisition_protocol")
    if "KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md" not in acquisition:
        errors.append("evidence_acquisition_must_route_supported_1c_gaps_to_project_snapshot_chat_workflow")
    if "default supported 1C acquisition adapter" not in acquisition:
        errors.append("project_snapshot_must_be_default_supported_1c_acquisition_adapter")

    for anchor in [
        "PROJECT_SNAPSHOT_COLLECTION_PLAN.json",
        "ProjectSnapshotCollector.epf",
        "ProjectSnapshot.zip",
        "TOOLS/plan_project_snapshot_collection.py",
        "TOOLS/validate_project_snapshot_package.py",
        "continue the original task immediately",
        "Do **not** ask the user to repeat the original requirement",
        "source_file",
        "expected_module_paths",
        "found_module_paths",
    ]:
        if anchor not in chat_workflow:
            errors.append(f"chat_workflow_missing:{anchor}")

    if "password" in chat_workflow.lower() and "never ask the developer to paste a password into chat" not in chat_workflow.lower():
        errors.append("chat_workflow_must_forbid_password_paste_into_chat")

    expected_states = {
        "EVIDENCE_SUFFICIENT", "SNAPSHOT_REQUIRED", "PLAN_READY", "PACKAGE_RECEIVED",
        "PACKAGE_REJECTED", "PACKAGE_BOUND_PARTIAL", "PACKAGE_BOUND_READY", "SOURCE_INSPECTED",
        "EVIDENCE_BOUND", "DELTA_REQUIRED", "TASK_RESUMED",
    }
    if orchestration.get("canonical_contract") is not True:
        errors.append("project_snapshot_orchestration_must_be_canonical_machine_contract")

    states = set(orchestration.get("states") or [])
    if states != expected_states:
        errors.append(f"project_snapshot_orchestration_states_drift:{sorted(states)}")

    for key, expected in {
        "normative_knowledge": "KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md",
        "entry_contract": "KNOWLEDGE/EVIDENCE_ACQUISITION.md",
        "request_template": "TEMPLATES/PROJECT_SNAPSHOT_REQUEST.json",
        "planner": "TOOLS/plan_project_snapshot_collection.py",
        "package_validator": "TOOLS/validate_project_snapshot_package.py",
    }.items():
        if orchestration.get(key) != expected:
            errors.append(f"project_snapshot_orchestration_reference_drift:{key}:{orchestration.get(key)}")

    pre_manual = orchestration.get("pre_manual_current_onec_gate") or {}
    if pre_manual.get("required_before_manual_current_onec_request") is not True:
        errors.append("project_snapshot_manual_current_onec_request_must_be_gated")
    expected_dispositions = {
        "EVIDENCE_ALREADY_SUFFICIENT", "PROJECT_SNAPSHOT_REQUIRED", "SPLIT_ACQUISITION",
        "DISCOVERY_BOOTSTRAP", "MANUAL_FALLBACK_UNSUPPORTED", "COLLECTOR_UNAVAILABLE",
        "USER_DECLINED_COLLECTOR",
    }
    if set(pre_manual.get("dispositions") or []) != expected_dispositions:
        errors.append(f"project_snapshot_pre_manual_dispositions_drift:{pre_manual.get('dispositions')}")
    manual_rules = "\n".join(pre_manual.get("rules") or [])
    for required_rule in [
        "a broad audit or review is not by itself a reason to bypass ProjectSnapshot",
        "after DISCOVERY_BOOTSTRAP is inventoried the gate must be re-run before any further current-1C evidence request",
        "do not duplicate acquisition when supplied or bootstrap source already closes the supported claim",
    ]:
        if required_rule not in manual_rules:
            errors.append(f"project_snapshot_pre_manual_rule_missing:{required_rule}")

    responsibilities = set(orchestration.get("chat_responsibilities") or [])
    for expected in [
        "retrieve repository-pinned ProjectSnapshotCollector payload",
        "verify collector artifact manifest, payload Git blob identities, reconstructed binary SHA-256/size/blob identity and build-input Git blob binding before delivery",
        "materialize and provide ProjectSnapshotCollector.epf to the developer when collection is required",
        "provide collector and plan together instead of making the developer build or locate the collector",
        "recognize returned ProjectSnapshot evidence package automatically",
        "inspect concrete SOURCE_EXPORT bytes before closing source claims",
        "issue delta plan instead of broad repeat collection",
        "resume original task automatically",
    ]:
        if expected not in responsibilities:
            errors.append(f"project_snapshot_chat_responsibility_missing:{expected}")

    distribution = orchestration.get("collector_distribution") or {}
    availability_guard = distribution.get("availability_guard") or {}
    if availability_guard.get("required_before_project_snapshot_required") is not True:
        errors.append("project_snapshot_collector_availability_guard_missing")
    if availability_guard.get("unavailable_disposition") != "COLLECTOR_UNAVAILABLE":
        errors.append("project_snapshot_collector_unavailable_disposition_missing")
    availability_rule = str(availability_guard.get("rule") or "")
    for required in [
        "apply only when the repository-pinned manifest/payload are present",
        "do not synthesize/build it",
        "COLLECTOR_UNAVAILABLE",
    ]:
        if required not in availability_rule:
            errors.append(f"project_snapshot_collector_availability_rule_missing:{required}")
    for key, expected in {
        "manifest": "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json",
        "payload_dir": "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD",
            "materialized_filename": "ProjectSnapshotCollector.epf",
        "integrity_tool": "TOOLS/materialize_project_snapshot_collector.py",
        "normal_delivery": "CHAT_PROVIDES_VERIFIED_EPF_WITH_PLAN",
    }.items():
        if distribution.get(key) != expected:
            errors.append(f"project_snapshot_collector_distribution_drift:{key}:{distribution.get(key)}")
    if distribution.get("ordinary_developer_build_required") is not False:
        errors.append("project_snapshot_ordinary_developer_build_must_be_false")

    developer_forbidden = set(orchestration.get("developer_must_not_be_required_to") or [])
    for expected in [
        "clone the skill repository merely to obtain the collector",
        "build ProjectSnapshotCollector.epf for ordinary collection",
        "run build_epf.ps1 for ordinary collection",
        "keep a local collector copy between unrelated tasks",
        "understand or reconstruct repository payload encoding",
        "edit generated CollectionPlan JSON",
        "interpret manifest/runtime JSON statuses",
        "extract individual modules from a valid package",
        "repeat original task context after package upload",
    ]:
        if expected not in developer_forbidden:
            errors.append(f"project_snapshot_developer_ux_regression:{expected}")

    acceptance = orchestration.get("package_acceptance") or {}
    if acceptance.get("validator_required") is not True:
        errors.append("project_snapshot_package_validator_must_be_required")
    if acceptance.get("source_content_inspection_required") is not True:
        errors.append("project_snapshot_source_content_inspection_must_be_required")
    if acceptance.get("partial_package_reuse") is not True:
        errors.append("project_snapshot_valid_partial_evidence_must_be_reusable")

    if pipeline.get("snapshot_collection_planner") != "TOOLS/plan_project_snapshot_collection.py":
        errors.append("development_pipeline_snapshot_planner_reference_missing")
    if pipeline.get("snapshot_collector_capabilities") != "KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_CAPABILITIES.json":
        errors.append("development_pipeline_snapshot_capabilities_reference_missing")
    expected_pipeline_refs = {
        "snapshot_chat_orchestration": "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json",
        "snapshot_package_validator": "TOOLS/validate_project_snapshot_package.py",
        "snapshot_collector_distribution_manifest": "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json",
        "snapshot_collector_materializer": "TOOLS/materialize_project_snapshot_collector.py",
    }
    for key, expected in expected_pipeline_refs.items():
        if pipeline.get(key) != expected:
            errors.append(f"development_pipeline_snapshot_reference_missing:{key}:{pipeline.get(key)}")
    package_acceptance = orchestration.get("package_acceptance") or {}
    if package_acceptance.get("machine_receipt_property") != "EVIDENCE:PROJECT_SNAPSHOT_PACKAGE_BINDING":
        errors.append("project_snapshot_package_binding_machine_receipt_missing")

    if "Source-export package acceptance remains a separate target-runtime check" in collector_arch:
        errors.append("collector_architecture_still_claims_source_export_runtime_pending")
    for anchor in [
        "SOURCE_EXPORT_V1 accepted desktop path",
        "COLLECTED_MODULE_FILES",
        "ConfigDumpInfo.xml` is diagnostic, not a source-proof prerequisite",
        "original task continuation",
    ]:
        if anchor not in collector_arch:
            errors.append(f"collector_architecture_acceptance_missing:{anchor}")


def main() -> int:
    errors: list[str] = []
    _check_chat_orchestration(errors)

    request = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    runtime_profile = json.loads(RUNTIME_PROFILE_PATH.read_text(encoding="utf-8"))

    runtime_plan = build_plan(request, matrix, ["RUNTIME_METADATA"], runtime_profile)
    if runtime_plan.get("result") != "BLOCKED":
        errors.append(f"runtime_only_must_block_full_source:{runtime_plan.get('result')}")
    if runtime_plan.get("runtime_profile") != "RUNTIME_V1":
        errors.append(f"runtime_profile_missing:{runtime_plan.get('runtime_profile')}")
    if runtime_plan.get("baseline_expectation") != request.get("baseline_expectation"):
        errors.append("baseline_expectation_must_propagate_to_collection_plan")
    runtime_rows = {row["id"]: row for row in runtime_plan.get("item_plan", [])}
    if runtime_rows.get("document-test-metadata", {}).get("status") != "READY":
        errors.append("runtime_metadata_partial_should_satisfy_partial_requirement")
    if runtime_rows.get("document-test-metadata", {}).get("logical_target") != "DOCUMENT.Test":
        errors.append("logical_target_not_propagated")
    if runtime_rows.get("document-test-object-module", {}).get("status") != "UNSUPPORTED":
        errors.append("runtime_metadata_must_not_claim_module_source")
    if runtime_rows.get("scheduled-jobs-runtime", {}).get("status") != "READY":
        errors.append("runtime_scheduled_jobs_partial_should_satisfy_partial_requirement")
    if "document-test-object-module" in set(runtime_plan.get("runtime_collector_scope") or []):
        errors.append("unsupported_module_source_leaked_into_runtime_scope")

    source_plan = build_plan(request, matrix, ["SOURCE_EXPORT"], runtime_profile)
    if source_plan.get("result") != "BLOCKED":
        errors.append(f"source_export_v1_must_not_claim_whole_fixture:{source_plan.get('result')}")
    if source_plan.get("source_export_profile") != "SOURCE_EXPORT_V1":
        errors.append(f"source_export_profile_missing:{source_plan.get('source_export_profile')}")
    source_rows = {row["id"]: row for row in source_plan.get("item_plan", [])}
    if source_rows.get("document-test-object-module", {}).get("status") != "READY":
        errors.append("supported_document_object_module_must_be_ready")
    if source_rows.get("document-test-metadata", {}).get("status") != "UNSUPPORTED":
        errors.append("source_export_v1_must_not_claim_metadata_properties")
    if source_rows.get("scheduled-jobs-runtime", {}).get("status") != "UNSUPPORTED":
        errors.append("source_export_v1_must_not_claim_scheduled_jobs")
    if source_plan.get("source_export_scope") != ["document-test-object-module"]:
        errors.append(f"source_export_scope_wrong:{source_plan.get('source_export_scope')}")

    hybrid_plan = build_plan(request, matrix, ["SOURCE_EXPORT", "RUNTIME_METADATA"], runtime_profile)
    if hybrid_plan.get("result") != "READY":
        errors.append(f"one_click_hybrid_should_close_fixture:{hybrid_plan.get('result')}")
    if hybrid_plan.get("collection_mode") != "HYBRID":
        errors.append(f"one_click_hybrid_mode_wrong:{hybrid_plan.get('collection_mode')}")
    hybrid_rows = {row["id"]: row for row in hybrid_plan.get("item_plan", [])}
    if hybrid_rows.get("document-test-object-module", {}).get("selected", {}).get("backend") != "SOURCE_EXPORT":
        errors.append("hybrid_module_must_route_to_source_export")
    if hybrid_rows.get("document-test-metadata", {}).get("selected", {}).get("backend") != "RUNTIME_METADATA":
        errors.append("hybrid_metadata_must_route_to_runtime")
    if hybrid_rows.get("scheduled-jobs-runtime", {}).get("selected", {}).get("backend") != "RUNTIME_METADATA":
        errors.append("hybrid_scheduled_job_must_route_to_runtime")

    unsupported_source_target = json.loads(json.dumps(request))
    unsupported_source_target["evidence_categories"] = ["MODULE_SOURCE"]
    unsupported_source_target["required_items"] = [{
        "id": "form-module-not-yet-implemented", "category": "MODULE_SOURCE",
        "logical_target": "DOCUMENT.Test.Form.Main.Module",
        "required_for_claim": "fixture:source-target-shape", "minimum_fidelity": "FULL",
    }]
    unsupported_source_plan = build_plan(unsupported_source_target, matrix, ["SOURCE_EXPORT"], runtime_profile)
    if unsupported_source_plan.get("result") != "BLOCKED":
        errors.append("source_export_v1_unknown_module_shape_must_block")
    unsupported_source_row = (unsupported_source_plan.get("item_plan") or [{}])[0]
    if unsupported_source_row.get("selected") is not None:
        errors.append("unsupported_source_target_must_not_be_selected")

    common_module_request = json.loads(json.dumps(request))
    common_module_request["evidence_categories"] = ["MODULE_SOURCE"]
    common_module_request["required_items"] = [{
        "id": "common-module", "category": "MODULE_SOURCE", "logical_target": "COMMON_MODULE.TestCommon",
        "required_for_claim": "fixture:common-module-source", "minimum_fidelity": "FULL",
    }]
    common_module_plan = build_plan(common_module_request, matrix, ["SOURCE_EXPORT"], runtime_profile)
    if common_module_plan.get("result") != "READY":
        errors.append("source_export_v1_common_module_must_be_ready")

    restricted = json.loads(json.dumps(request))
    restricted["collector_policy"]["allowed_backends"] = ["RUNTIME_METADATA", "HYBRID"]
    restricted_plan = build_plan(restricted, matrix, ["SOURCE_EXPORT", "RUNTIME_METADATA"], runtime_profile)
    restricted_rows = {row["id"]: row for row in restricted_plan.get("item_plan", [])}
    selected = restricted_rows.get("document-test-object-module", {}).get("selected")
    if selected and selected.get("backend") == "SOURCE_EXPORT":
        errors.append("request_disallowed_backend_was_selected")
    if restricted_plan.get("result") != "BLOCKED":
        errors.append("restricted_runtime_plan_must_remain_blocked")

    bad = json.loads(json.dumps(request))
    bad["evidence_categories"].append("UNKNOWN_EVIDENCE")
    bad_plan = build_plan(bad, matrix, ["RUNTIME_METADATA"], runtime_profile)
    if bad_plan.get("result") != "INVALID_REQUEST":
        errors.append("unknown_category_must_invalidate_request")

    bad_baseline = json.loads(json.dumps(request))
    bad_baseline["baseline_expectation"] = "not-an-object"
    bad_baseline_plan = build_plan(bad_baseline, matrix, ["RUNTIME_METADATA"], runtime_profile)
    if bad_baseline_plan.get("result") != "INVALID_REQUEST":
        errors.append("non_object_baseline_expectation_must_invalidate_request")

    missing_target = json.loads(json.dumps(request))
    missing_target["required_items"][0].pop("logical_target")
    missing_target_plan = build_plan(missing_target, matrix, ["RUNTIME_METADATA"], runtime_profile)
    if missing_target_plan.get("result") != "INVALID_REQUEST":
        errors.append("missing_logical_target_must_invalidate_request")

    unimplemented = json.loads(json.dumps(request))
    unimplemented["evidence_categories"] = ["FORM_DEFINITION"]
    unimplemented["required_items"] = [{
        "id": "form-runtime-v1", "category": "FORM_DEFINITION", "logical_target": "DOCUMENT.Test.Form.Main",
        "required_for_claim": "fixture:form", "minimum_fidelity": "PARTIAL",
    }]
    unimplemented_plan = build_plan(unimplemented, matrix, ["RUNTIME_METADATA"], runtime_profile)
    if unimplemented_plan.get("result") != "BLOCKED":
        errors.append(f"runtime_v1_unimplemented_category_must_block:{unimplemented_plan.get('result')}")
    unimplemented_row = (unimplemented_plan.get("item_plan") or [{}])[0]
    if unimplemented_row.get("selected") is not None:
        errors.append("runtime_v1_unimplemented_category_must_not_be_selected")

    wrong_kind = json.loads(json.dumps(request))
    wrong_kind["evidence_categories"] = ["SCHEDULED_JOBS"]
    wrong_kind["required_items"] = [{
        "id": "wrong-kind", "category": "SCHEDULED_JOBS", "logical_target": "DOCUMENT.Test",
        "required_for_claim": "fixture:scheduled-job-kind", "minimum_fidelity": "PARTIAL",
    }]
    wrong_kind_plan = build_plan(wrong_kind, matrix, ["RUNTIME_METADATA"], runtime_profile)
    if wrong_kind_plan.get("result") != "BLOCKED":
        errors.append("runtime_profile_target_kind_must_be_enforced")

    strict_run = subprocess.run([
        sys.executable, str(TOOL_PATH), str(REQUEST_PATH), "--available-backends", "RUNTIME_METADATA", "--strict",
    ], capture_output=True, text=True, encoding="utf-8")
    if strict_run.returncode != 2:
        errors.append(f"strict_runtime_block_exit:{strict_run.returncode}")

    normal_run = subprocess.run([
        sys.executable, str(TOOL_PATH), str(REQUEST_PATH), "--available-backends", "RUNTIME_METADATA",
    ], capture_output=True, text=True, encoding="utf-8")
    if normal_run.returncode != 0:
        errors.append(f"non_strict_valid_plan_exit:{normal_run.returncode}:{normal_run.stderr}")
    else:
        try:
            cli_plan = json.loads(normal_run.stdout)
            if cli_plan.get("result") != "BLOCKED":
                errors.append(f"non_strict_cli_plan_result:{cli_plan.get('result')}")
            if cli_plan.get("baseline_expectation") != request.get("baseline_expectation"):
                errors.append("cli_plan_baseline_expectation_drift")
        except Exception as exc:
            errors.append(f"non_strict_cli_json:{exc}")

    chat_errors = [
        e for e in errors
        if e.startswith(("project_snapshot_", "chat_", "collector_architecture_", "skill_", "evidence_", "development_pipeline_"))
    ]
    out = {
        "result": "PASS" if not errors else "FAIL", "errors": errors,
        "runtime_only": runtime_plan.get("summary"), "source_export": source_plan.get("summary"),
        "hybrid": hybrid_plan.get("summary"), "runtime_profile": runtime_plan.get("runtime_profile"),
        "source_export_profile": source_plan.get("source_export_profile"),
        "chat_orchestration": "PASS" if not chat_errors else "FAIL",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
