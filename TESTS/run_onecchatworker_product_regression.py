#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "PRODUCT" / "OneCChatWorker"
errors: list[dict] = []
results: dict[str, dict] = {}

def rec(name: str, ok: bool, detail) -> None:
    results[name] = {"pass": bool(ok), "detail": detail}
    if not ok:
        errors.append({"case": name, "detail": detail})

required = [
    "OneCChatWorker.ps1",
    "core/OneCChatWorker.Core.psm1",
    "runtime/source-reader-integration.mjs",
    "runtime/hosted-helper.mjs",
    "runtime.lock.json",
    "projects.example.json",
    "README.md",
    "tests/run_local_regression.ps1",
    "tests/run_operator_acl_regression.ps1",
    "tests/run_guided_ui_regression.ps1",
    "tests/run_update_bootstrap_regression.ps1",
    "tests/run_apply_failure_regression.ps1",
    "tests/run_apply_quarantine_regression.ps1",
    "tests/run_guided_progress_regression.ps1",
    "tests/run_snapshot_fast_path_regression.ps1",
]
missing = [p for p in required if not (PRODUCT / p).is_file()]
rec("product_files_exist", not missing, missing)

lock = json.loads((PRODUCT / "runtime.lock.json").read_text(encoding="utf-8"))
expected_surface = ["source_context", "source_search", "source_read", "proposal_write", "proposal_read"]
rec("model_surface_exact_five", lock["hosted_mcp"]["model_surface"] == expected_surface, lock["hosted_mcp"]["model_surface"])

hash_mismatches = []
for rel, expected in lock.get("components", {}).items():
    path = PRODUCT / rel
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if actual != expected:
        hash_mismatches.append({"path": rel, "expected": expected, "actual": actual})
rec("component_hash_lock_matches", not hash_mismatches, hash_mismatches)

helper = (PRODUCT / "runtime/hosted-helper.mjs").read_text(encoding="utf-8")
core = (PRODUCT / "core/OneCChatWorker.Core.psm1").read_text(encoding="utf-8")
launcher = (PRODUCT / "OneCChatWorker.ps1").read_text(encoding="utf-8")
readme = (PRODUCT / "README.md").read_text(encoding="utf-8")
local_regression = (PRODUCT / "tests/run_local_regression.ps1").read_text(encoding="utf-8")
operator_acl_regression = (PRODUCT / "tests/run_operator_acl_regression.ps1").read_text(encoding="utf-8")
guided_ui_regression = (PRODUCT / "tests/run_guided_ui_regression.ps1").read_text(encoding="utf-8")
update_bootstrap_regression = (PRODUCT / "tests/run_update_bootstrap_regression.ps1").read_text(encoding="utf-8")
apply_failure_regression = (PRODUCT / "tests/run_apply_failure_regression.ps1").read_text(encoding="utf-8")
apply_quarantine_regression = (PRODUCT / "tests/run_apply_quarantine_regression.ps1").read_text(encoding="utf-8")
guided_progress_regression = (PRODUCT / "tests/run_guided_progress_regression.ps1").read_text(encoding="utf-8")
snapshot_fast_regression = (PRODUCT / "tests/run_snapshot_fast_path_regression.ps1").read_text(encoding="utf-8")

forbidden_helper = ["source_write", "delete_file", "start_process", "browser", "arbitrary_url"]
rec("helper_has_no_forbidden_model_capability", not any(x in helper for x in forbidden_helper), [x for x in forbidden_helper if x in helper])
rec("helper_project_task_from_admission", "const PROJECT = String(admission.project_id" in helper and "const TASK = String(admission.task_id" in helper, "admission bindings")
rec("helper_proposal_not_applied", "PROPOSAL_NOT_APPLIED" in helper and "_proposal_provenance.json" in helper, "provenance status/path")
rec("helper_recover_first_cas", "existing&&replace&&existing.sha256===hash" in helper and "IDEMPOTENCY_KEY_REUSE" in helper, "CAS/idempotency")
rec("helper_active_manifest_scope", "collectArtifacts(manifest)" in helper and "artifactPrefixes" in helper, "manifest artifact prefixes")
rec("helper_state_is_snapshot_bound", "s.snapshot_id===SNAPSHOT" in helper and "snapshot_id:SNAPSHOT" in helper, "session state bound to source snapshot")
rec("helper_import_matches_installed_layout", "../provider/source-reader-integration.mjs" in helper, "installed helper/provider sibling layout")
machine_user_marker = "c:" + "\\users\\" + "alexl"
rec("helper_has_no_machine_specific_project", not any(t.lower() in helper.lower() for t in ["nendo", "w1-rp", "w1-ta", machine_user_marker]), "no pilot/user hardcodes")

core_tokens = [
    "Participants/$participantKey/Target/Main",
    "Participants/$participantKey/Target/Extensions/$eid",
    "catalog_sha256",
    "DRIFT_APPLY_REQUIRED",
    "Detached",
    "Deactivated",
    "PLATFORM_NOT_IMPLEMENTED_1C_FIRST",
    "Output",
]
rec("core_has_direct_root_and_lifecycle_contract", all(t in core for t in core_tokens), [t for t in core_tokens if t not in core])
rec("core_no_redundant_wrapper_literal", "Target/Main/Main" not in core and r"Target\Main\Main" not in core, "no Main/Main")
rec("core_output_acl_separate", "Participants" in core and ":(OI)(CI)(RX)" in core and ":(OI)(CI)(M)" in core, "RX Participants / M Output")
rec("core_helper_path_consistent", core.count(r"helper\hosted-helper.mjs") >= 4 and "Destination (Join-Path $ProgramDataRoot 'helper\\hosted-helper.mjs')" in core, "installed integrity/install/start/stop use helper subtree; runtime/hosted-helper is package key only")
rec("core_safe_uninstall_is_runtime_only", "function Invoke-SafeUninstall" in core and "authoritative_external_source_untouched=$true" in core and "reader_identity_retained=$true" in core, "runtime-only uninstall")
rec("core_catalog_manager_edit_remove_surface", all(t in core for t in ["function Edit-WorkerProject", "function Edit-WorkerParticipant", "'PROJECT','PARTICIPANT','MAIN','EXTENSION'", "REPLACED_DETACHED", "DEACTIVATED_DETACHED"]), "edit/deactivate/change summary")
rec("core_incomplete_onec_project_fails_closed", all(t in core for t in ["NO_ACTIVE_ARTIFACTS","SNAPSHOT_ROOT_MISSING","ONEC_CONFIGURATION_XML_MISSING"]), "fast-state/admission fail closed on incomplete ONEC project")
rec("core_start_propagates_parameterized_runtime_root", all(t in core for t in ["New-HelperRunAsCommand", "ONECCHAT_PROGRAM_DATA", "ONECCHAT_ADMISSION_PATH", "EncodedCommand"]), "runas helper binds the admitted ProgramDataRoot and active-admission path")
rec("core_ripgrep_version_parser_canonical", "function Get-RipgrepSemanticVersion" in core and core.count("Get-RipgrepSemanticVersion") >= 5 and "RG_VERSION_OUTPUT_INVALID" in core and "-replace '^ripgrep\\s+'" not in core, "one fail-closed parser owns ripgrep version extraction")
rec("local_regression_covers_ripgrep_version_parser", all(t in local_regression for t in ["rg_semver_parser_revision_form", "ripgrep 15.2.0 (rev e89fff89ac)", "rg_semver_parser_rejects_incomplete", "rg_semver_parser_rejects_trailing_junk"]), "exact rev form plus malformed-output negatives")
pid_assignment = re.compile(r"(?i)\$pid\s*=")
rec("powershell_has_no_pid_local_assignments", not pid_assignment.search(launcher) and not pid_assignment.search(core), "no case-insensitive local assignment may collide with readonly automatic $PID")
rec("local_regression_executes_launcher_lifecycle_ps51", all(t in local_regression for t in ["launcher_add_project_ps51", "launcher_add_participant_ps51", "launcher_set_main_ps51", "launcher_add_extension_ps51", "launcher_apply_ps51", "launcher_verify_ps51"]), "launcher lifecycle is exercised through powershell.exe, not only direct core calls")
rec("operator_acl_owner_is_explicit", all(t in launcher for t in ["[string]$OperatorIdentity", "-OperatorIdentity", "OperatorIdentity=[Security.Principal.WindowsIdentity]::GetCurrent().Name"]) and "Resolve-WorkerOperatorIdentity" in core and "operator_identity=$operatorAcl.operator_identity" in core, "normal operator identity is captured before elevation and persisted")
rec("operator_acl_mutable_surfaces_bounded", all(t in core for t in ["function Set-WorkerOperatorAcl", "'operations'", "'provider'", "'runtime'", "$operatorM", "Protect-WorkerRuntimeFile"]), "operator Modify is limited to required mutable surfaces with protected runtime files")
rec("operator_acl_restricted_surfaces_preserved", all(t in core for t in ["$operatorRx", "'helper'", "'product'", "'secrets'", "-Secret"]) and "operator_secret_read" in operator_acl_regression and "operator_binary_write_" in operator_acl_regression, "helper/product remain RX and helper secret is unreadable to operator")
rec("repair_reconciles_operator_acl_before_journal", "Require-AdminOrRelaunch 'REPAIR'" in launcher and launcher.index("Set-WorkerOperatorAcl -WorkerRoot $WorkerRoot") < launcher.index("Invoke-ObservedAction -OperationType REPAIR"), "REPAIR repairs ACL drift before operation journaling")
rec("operator_acl_regression_runs_nonadmin_lifecycle", all(t in operator_acl_regression for t in ["RUN_PHASE_EXPECTS_NON_ADMIN","OPERATOR_PHASE_MUST_BE_NON_ADMIN","ADD_PROJECT","ADD_PARTICIPANT","SET_MAIN","ADD_EXTENSION","APPLY","VERIFY","Invoke-PostVerifyAclProof","OPERATION_JOURNAL_MISSING","READER_SOURCE_WRITE_RIGHT_PRESENT"]), "actual Windows PS5.1 regression covers elevated setup then non-admin operator lifecycle and negative ACL assertions")
rec("operator_acl_regression_deterministic_start_write_gate", all(t in operator_acl_regression for t in ["New-Admission -ProjectId 'AclRegression' -TaskId 'acl-regression-task'","START_PROVIDER_CONFIG_WRITE_FAILED","START_ADMISSION_WRITE_FAILED","START_ADMISSION_CLEANUP_FAILED","RECOVER_POST_VERIFY"]) and "if($IncludeStart)" in operator_acl_regression, "deterministic gate proves non-admin START provider/runtime writes while interactive runas remains explicit opt-in")
rec("install_bootstrap_prefers_package_core", "$Mode -eq 'INSTALL' -and $PackageCoreAvailable" in launcher and "$PackageCore" in launcher and "$InstalledCore" in launcher, "package INSTALL bootstraps from package core when available; normal runtime may still use installed core")
rec("update_bootstrap_regression_reconstructs_version_skew", all(t in update_bootstrap_regression for t in ["New-StaleInstalledCore","STALE_CORE_RECONSTRUCTION_FAILED","PACKAGE_INSTALL_FAILED","installed_core_refreshed","installed_launcher_refreshed","installed_runtime_lock_refreshed"]), "Windows PS5.1 update regression makes installed core incompatible with -OperatorIdentity and proves package bootstrap refreshes exact package bytes")
rec("update_bootstrap_regression_preserves_data_and_acl", all(t in update_bootstrap_regression for t in ["catalog_preserved","source_preserved","output_preserved","secret_preserved","worker_root_acl","operations_acl","provider_acl","runtime_acl","product_acl","helper_acl","secret_acl","idempotent_core"]), "version-skew update preserves data and #74 ACL ownership on isolated roots")
rec("guided_update_failure_is_human_safe", all(t in launcher for t in ["The install/update package could not be verified.","Run INSTALL again from the complete current OneCChatWorker package; existing projects and data are retained.","PACKAGE_COMPONENT_HASH_MISMATCH|RUNTIME_LOCK_|INSTALLED_COMPONENT_HASH_MISMATCH"]), "guided install/update integrity failures map to actionable user-safe guidance")
rec("apply_copy_is_failure_atomic", all(t in core for t in ["function Get-ApplyStageRoot","function Write-ApplyStageState","'CREATED','COPYING','VERIFIED','COMMITTED'","function Copy-ArtifactSafely","function Remove-ApplyStageTree","function Move-ApplyStageToQuarantine"]), "APPLY copy uses explicit stage lifecycle, bounded staging root and cleanup/quarantine")
rec("apply_residue_is_recover_first", all(t in core for t in ["function Get-ApplyStageResidue","INCOMPLETE_APPLY_RESIDUE","ORPHAN_STAGE_PRESENT","APPLY_RESIDUE_REPAIR_REQUIRED","function Resolve-ApplyStageResidue","function Repair-WorkerProject"]), "VERIFY/APPLY/REPAIR classify and resolve incomplete APPLY residue before replay")
rec("apply_failure_receipt_has_bounded_truth", all(t in core for t in ["error_message=$ErrorMessage","error_phase=$ErrorPhase","error_path=$ErrorPath","cleanup_status=$CleanupStatus","ConvertTo-BoundedDiagnosticText","[UTC]"]), "durable receipt keeps stable class plus bounded safe cause/phase/path/cleanup and labels human log UTC")
rec("apply_failure_regression_covers_required_atomicity", all(t in apply_failure_regression for t in ["injected_apply_fails","failed_stage_cleaned","canonical_target_unchanged_after_midcopy_failure","manifest_unchanged_after_midcopy_failure","durable_error_class_stable","guided_ru_failure_localized","guided_english_fallback_actionable","verify_classifies_incomplete_apply_residue","repair_recover_first_reaches_ready","secret_not_in_operation_evidence","bounded_stage_root_avoids_guid_suffix_path_inflation"]), "Windows PS5.1 failure regression covers cleanup, immutable source/canonical state, diagnostics, localization, recover-first and long-path shape")
rec("apply_cleanup_failure_routes_to_quarantine", all(t in core for t in ["if($cleanup.status -in @('CLEANED','CLEANED_LONG_PATH','ALREADY_ABSENT'))","Move-ApplyStageToQuarantine -Residue $residue -ProjectRoot $projectRoot","action=$q.status","quarantine_path=$q.quarantine_path"]), "cleanup failure deterministically routes to quarantine/classification rather than leaving residue beside canonical Target")
rec("apply_quarantine_regression_covers_fallback_move", all(t in apply_quarantine_regression for t in ["quarantine_move_reports_quarantined","quarantine_under_project_recovery","quarantined_metadata_present","canonical_target_preserved","detached_evidence_preserved","authoritative_source_preserved"]), "separate bounded regression exercises the real quarantine move and preservation boundaries")
rec("guided_apply_failure_is_localized_and_actionable", all(t in launcher for t in ["The managed project copy could not be created.","Incomplete temporary copy was cleaned.","Original XML export was not changed.","Reason: {0}","Stage: {0}","Cleanup: {0}","APPLY_RESIDUE_REPAIR_REQUIRED"]), "default guided APPLY failure replaces raw lifecycle output with localized FAIL/Reason/Stage/Cleanup/Next/Details guidance")
rec("guided_progress_reuses_durable_apply_and_fast_state", all(t in launcher for t in ["function Start-GuidedLifecycleProcess","function Wait-GuidedLifecycleProcess","Get-CurrentWorkerOperation","Invoke-GuidedManagedProjectProgress","Get-FastProjectState","Invoke-GuidedAction -ShowOutput {Invoke-GuidedManagedProjectProgress"]), "guided presentation runs existing APPLY owner, polls its durable receipt, then uses FAST_STATE_CHECK_V1 without implicit deep VERIFY")
rec("guided_progress_has_honest_stage_and_elapsed_liveness", all(t in launcher for t in ["[{0}/5]","Work continues... elapsed {0}","Checking project structure and current state...","Building the managed project copy...","Confirming the managed copy result...","Checking accepted snapshot state...","Done."]) and "%" not in launcher[launcher.index("function Write-GuidedProgressStage"):launcher.index("function Complete-GuidedProject")], "guided completion exposes five human stages plus elapsed heartbeat without percent")
progress_block = launcher[launcher.index("function Start-GuidedLifecycleProcess"):launcher.index("function Complete-GuidedProject")]
rec("guided_progress_adds_no_tree_scan", "Get-CurrentWorkerOperation" in progress_block and not any(t in progress_block for t in ["Get-TreeDigest","Get-ChildItem -Recurse","Measure-Object Length"]), "progress presentation polls receipt/process state only; no duplicate source-tree traversal")
rec("guided_progress_localization_keys_complete", all(t in launcher for t in ["'Checking project structure and current state...'=","'Building the managed project copy...'=","'This may take some time for large configurations.'=","'Confirming the managed copy result...'=","'Checking accepted snapshot state...'=","'Done.'=","'Work continues... elapsed {0}'="]), "ru-* resource covers all current progress labels; canonical English remains fallback")
rec("guided_progress_regression_covers_acceptance", all(t in guided_progress_regression for t in ["Assert-OrderedStages 'ru_order'","Assert-Heartbeat 'ru_liveness_heartbeat'","Assert-OrderedStages 'en_order'","Assert-Heartbeat 'en_liveness_heartbeat'","durable_apply_semantics_unchanged","guided_does_not_run_deep_verify","progress_reuses_cli_apply_then_fast_state","progress_polls_receipt_not_source_tree","progress_failure_uses_guided_failure_boundary","accepted_apply_failure_contract_retained"]), "Windows PS5.1 regression proves RU/EN ordering, liveness, APPLY durability, no implicit deep VERIFY, no UI-only scan and #79 failure boundary")

fast_state_block = core[core.index("function Get-FastProjectState {"):core.index("function Test-LegacyManifestShape {")]
status_block = core[core.index("function Get-WorkerStatus {"):core.index("function Get-WorkerDiagnostics {")]
admission_block = core[core.index("function New-Admission {"):core.index("function Test-IsAdministrator {")]
one_pass_block = core[core.index("function New-SourceCopyPlan {"):core.index("function Write-FingerprintInventory {")]
start_block = launcher[launcher.index("function Run-Start {"):launcher.index("function Run-Stop {")]
rec("snapshot_fast_state_is_bounded", all(t in fast_state_block for t in ["ACCEPTED","APPLY_REQUIRED","CATALOG_DRIFT","INCOMPLETE_APPLY_RESIDUE","DEEP_VERIFY_REQUIRED","SNAPSHOT_MANIFEST_INVALID","SNAPSHOT_ROOT_MISSING"]) and not any(t in fast_state_block for t in ["Get-TreeDigest","Get-ChildItem -Recurse","rg.exe","Copy-Item"]), "FAST_STATE_CHECK_V1 is bounded by catalog/manifest/artifact roots")
rec("snapshot_status_is_fast", "Get-FastProjectState" in status_block and not any(t in status_block for t in ["Verify-WorkerProject","Get-TreeDigest"]), "STATUS uses fast state only")
rec("snapshot_start_is_single_fast_check", start_block.count("Get-FastProjectState") == 1 and "Verify-WorkerProject" not in start_block, "START performs exactly one fast-state check")
rec("snapshot_admission_consumes_accepted_state", "AcceptedState" in admission_block and not any(t in admission_block for t in ["Verify-WorkerProject","Get-TreeDigest"]), "New-Admission binds accepted snapshot without deep verify")
rec("snapshot_manifest_v2_contract", all(t in core for t in ["ACCEPTED_SNAPSHOT_V1","source_snapshot_id","publication_generation","fingerprint_inventory_state","LEGACY_DEEP_VERIFIED","ABSENT_LEGACY"]), "manifest v2 accepted snapshot + legacy adoption contract")
rec("snapshot_one_pass_bootstrap_contract", all(t in one_pass_block for t in ["New-SourceCopyPlan","Invoke-OnePassCopyHash","SOURCE_CHANGED_DURING_SYNC","[IO.File]::Open","TransformBlock","Assert-SourceCopyPlanStable"]) and "Get-TreeDigest" not in one_pass_block, "future bootstrap hashes while copying and metadata-rechecks Source without rereading stage")
rec("snapshot_helper_exact_binding", all(t in helper for t in ["ADMISSION_MANIFEST_HASH_MISMATCH","ADMISSION_SOURCE_SNAPSHOT_MISMATCH","manifest.accepted_snapshot.source_snapshot_id","admission.manifest_sha256","admission.source_snapshot_id"]), "helper fails closed on exact manifest/snapshot mismatch")
rec("snapshot_regression_covers_required_fast_path", all(t in snapshot_fast_regression for t in ["SNAPSHOT_FAST_REGRESSION_PASS","one_pass_digest_equals_legacy","fast_accepted_with_external_source_offline","second_task_reuses_snapshot","helper_manifest_hash_mismatch","helper_snapshot_mismatch","missing_root_fast_reject","missing_config_fast_reject","catalog_drift_fast_reject","residue_fast_recover_first","legacy_insufficient_evidence_rejects","deep_verify_detects_seeded_drift","source_metadata_drift_aborts","start_exactly_one_fast_no_deep","status_no_deep_or_tree_digest","admission_no_deep_or_tree_digest","helper_five_ops_exact"]), "Windows PS5.1 #83 regression covers warm path, fail-closed negatives, deep verify and exact five-tool surface")

operation_tokens = [
    "Start-WorkerOperation",
    "Update-WorkerOperation",
    "Complete-WorkerOperation",
    "Get-CurrentWorkerOperation",
    "Get-RecentWorkerOperations",
    "Get-WorkerOperationLog",
    "Get-OperationRecoveryClassification",
    "events.jsonl",
    "operations.log",
    "history.jsonl",
    "RUNNING','PASS','FAIL','WAITING_FOR_USER','CANCELLED','RECOVERED",
]
rec("rp035_shared_operation_event_model", all(t in core for t in operation_tokens), [t for t in operation_tokens if t not in core])
rec("rp035_status_diagnostics_surface", all(t in core for t in ["Get-WorkerDependencyHealth", "Get-HelperConnectionState", "Get-OutputProposalSummary", "Get-WorkerDiagnostics", "Export-WorkerDiagnosticBundle", "secret_material_included=$false"]), "status/diagnostics")
rec("rp035_logs_are_bounded", "OperationLogMaxBytes" in core and "Rotate-WorkerLog" in core, "bounded rotation")
rec("package_integrity_is_hash_locked", all(t in core for t in ["Read-RuntimeLock", "Test-ProductPackageIntegrity", "Copy-ProductComponent", "Test-InstalledProductIntegrity", "NODE_HASH_MISMATCH", "RG_HASH_MISMATCH"]), "package/dependency hashes")
rec("python_cloudflare_not_product_dependencies", "python=[pscustomobject]@{action='SKIPPED_NOT_REQUIRED'}" in core and "cloudflare_cli=[pscustomobject]@{action='SKIPPED_NOT_REQUIRED'}" in core, "engineering-only dependencies excluded")

guided_tokens = ["function Get-GuidedContext", "function Guided-MainMenu", "Recommended:", "Add local project", "Complete project setup", "Start work", "Advanced", "FAIL:", "Next:", "Details:"]
rec("launcher_has_guided_state_aware_default", all(t in launcher for t in guided_tokens), [t for t in guided_tokens if t not in launcher])
rec("launcher_guided_state_contract", all(t in launcher for t in ["NOT_INSTALLED","REMOTE_AUTH_MISSING","NO_PROJECTS","PROJECT_DRAFT","PROJECT_NEEDS_APPLY","PROJECT_NEEDS_VERIFY","PROJECT_READY","RUNNING","STARTING","START_INCOMPLETE","RECOVERY_REQUIRED"]), "authoritative guided states")
rec("launcher_field_help_contract", all(t in launcher for t in ["What:", "Why :", "Form:", "Example:", "Required:", "Type ? or help", "press Enter to accept"]), "every guided field explains itself and supports help/default")
rec("launcher_guided_ids_are_derived", all(t in launcher for t in ["ConvertTo-SafeTechnicalId","Get-UniqueProjectId","Get-UniqueParticipantId","Get-UniqueTaskId"]), "technical ids are derived in default UX")
rec("launcher_guided_setup_summary_and_resume", all(t in launcher for t in ["Setup summary","Confirm, [B] Back/Edit","Existing valid setup is kept","Complete-GuidedProject"]), "summary/edit/confirm plus resume path")
rec("launcher_guided_expected_errors_are_human", all(t in launcher for t in ["Get-GuidedErrorInfo","Show-GuidedFailure","FAIL: {0}","Next: {0}","Advanced > Diagnostics"]), "default expected errors are concise and diagnostic details remain advanced")
rec("guided_ui_regression_covers_required_states", all(t in guided_ui_regression for t in ["fresh_state_not_installed","installed_auth_missing_state","no_projects_guides_add_project","field_help_contract_visible","invalid_path_reprompts_in_place","interrupted_setup_resumes_to_ready","existing_ready_state","orphan_admission_is_start_incomplete","running_state_requires_helper","advanced_invalid_is_handled","first_project_expected_error_no_stack"]), "Windows PS5.1 guided UI regression coverage")
rec("guided_ui_regression_checks_internal_terms_hidden", "guided_hides_internal_lifecycle_terms" in guided_ui_regression and "participant_id|artifact_id|APPLY CATALOG" in guided_ui_regression, "default UI hides technical lifecycle terms")
rec("launcher_guided_localizes_by_windows_ui_culture", all(t in launcher for t in ["function Get-GuidedLanguage", "CurrentUICulture", "$script:GuidedRu", "^(?i:ru)"]), "ru-* follows Windows UI culture; all other cultures fall back to canonical English")
rec("guided_ui_regression_covers_ru_and_english_fallback", all(t in guided_ui_regression for t in ["'ru-RU'", "'de-DE'", "ru_field_help_localized", "ru_validation_error_localized", "english_fallback_field_help", "english_fallback_validation_error"]), "PS5.1 regression proves Russian guided presentation plus unsupported-culture English fallback")
rec("launcher_cli_has_required_lifecycle_modes", all(t in launcher for t in ["'APPLY'","'VERIFY'","'REPAIR'","'START'","'STOP'","'DEACTIVATE'","'EDIT_PROJECT'","'EDIT_PARTICIPANT'"]), "CLI modes")
rec("launcher_has_human_observability_views", all(t in launcher for t in ["VIEW_CURRENT_OPERATION", "VIEW_RECENT_OPERATIONS", "VIEW_LOGS", "EXPORT_DIAGNOSTICS", "Show-StatusReadable"]), "operator views")
rec("launcher_recover_first_guard", "RECOVERY_REQUIRED: incomplete operation" in launcher and "explicit recover-first path, not blind replay" in launcher, "interrupted operations block blind replay")
rec("launcher_parameterizes_reader_and_relay", "ReaderName='OneCSourceReader'" in launcher and "RelayUrl='wss://onec-g1q1-relay" in launcher and "Set-WorkerReaderIdentity" in launcher, "portable local identity/relay")
rec("launcher_main_deactivation_exposed", "PROJECT/PARTICIPANT/MAIN/EXTENSION" in launcher, "safe MAIN deactivation")
rec("launcher_default_is_human_readable_json_optional", "[switch]$Json" in launcher and "Show-StatusReadable" in launcher, "human default / JSON opt-in")

rec("local_regression_covers_observability", all(t in local_regression for t in ["observability_history", "interrupted_operation_requires_recovery", "diagnostic_bundle_created"]), "RP-035 cases")
rec("local_regression_covers_safe_removal", all(t in local_regression for t in ["deactivate_detaches_extension", "deactivate_main_materializes_but_not_ready", "safe_uninstall_retains_project_data"]), "safe removal cases")

deps = lock.get("dependencies", {})
rec("node_pinned", deps.get("node", {}).get("version") == "26.7.0" and deps.get("node", {}).get("winget_id") == "OpenJS.NodeJS" and len(deps.get("node", {}).get("reference_sha256", "")) == 64, deps.get("node"))
rec("ripgrep_pinned", deps.get("ripgrep", {}).get("version") == "15.2.0" and deps.get("ripgrep", {}).get("winget_id") == "BurntSushi.ripgrep.MSVC" and len(deps.get("ripgrep", {}).get("reference_sha256", "")) == 64, deps.get("ripgrep"))
rec("no_python_or_cloudflare_dependency_lock", "python" not in deps and "cloudflare" not in " ".join(deps.keys()).lower(), list(deps))

budget = lock.get("remote_call_budget", {})
rec("remote_call_budget_encoded", budget.get("known_path_read_calls") == 1 and budget.get("bounded_search_calls") == 1 and budget.get("ordinary_nontrivial_target_max_calls") == 3, budget)

readme_required = [
    "unavoidable remote-auth checkpoint",
    "helper secret",
    "/mcp",
    "PLATFORM_NOT_IMPLEMENTED_1C_FIRST",
    "RECOVER_FIRST_NOT_REPLAY_FIRST",
    "VIEW CURRENT OPERATION",
    "PROPOSAL_NOT_APPLIED",
    "Python",
    "Cloudflare CLI",
]
rec("readme_product_contract_complete", all(t in readme for t in readme_required), [t for t in readme_required if t not in readme])

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
