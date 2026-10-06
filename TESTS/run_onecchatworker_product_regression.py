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
    "runtime/local-quality-adapter.mjs",
    "runtime/task-checkpoint-store.mjs",
    "runtime/quality/cc-1c-skills/meta-info.ps1",
    "runtime/quality/cc-1c-skills/form-info.ps1",
    "runtime/quality/cc-1c-skills/form-validate.ps1",
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
    "tests/local-quality-adapter-regression.mjs",
    "tests/run_local_quality_adapter_regression.ps1",
    "tests/TestScratch.psm1",
    "tests/run_test_scratch_hygiene_regression.ps1",
    "tests/run_s4_admission_regression.ps1",
    "tests/s4-accounting-regression.mjs",
    "tests/run_task_checkpoint_regression.ps1",
    "tests/task-checkpoint-regression.mjs",
    "relay/src/index.js",
    "relay/src/s4-accounting.js",
    "relay/wrangler.jsonc",
    "relay/package.json",
    "relay/package-lock.json",
]
missing = [p for p in required if not (PRODUCT / p).is_file()]
rec("product_files_exist", not missing, missing)

lock = json.loads((PRODUCT / "runtime.lock.json").read_text(encoding="utf-8"))
expected_surface = ["source_context", "source_search", "source_read", "proposal_write", "proposal_read", "task_checkpoint_write"]
rec("model_surface_exact_six", lock["hosted_mcp"]["model_surface"] == expected_surface, lock["hosted_mcp"]["model_surface"])

hash_mismatches = []
for rel, expected in lock.get("components", {}).items():
    path = PRODUCT / rel
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if actual != expected:
        hash_mismatches.append({"path": rel, "expected": expected, "actual": actual})
rec("component_hash_lock_matches", not hash_mismatches, hash_mismatches)

helper = (PRODUCT / "runtime/hosted-helper.mjs").read_text(encoding="utf-8")
quality_adapter = (PRODUCT / "runtime/local-quality-adapter.mjs").read_text(encoding="utf-8")
quality_windows_regression = (PRODUCT / "tests/run_local_quality_adapter_regression.ps1").read_text(encoding="utf-8")
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
test_scratch = (PRODUCT / "tests/TestScratch.psm1").read_text(encoding="utf-8")
test_scratch_hygiene = (PRODUCT / "tests/run_test_scratch_hygiene_regression.ps1").read_text(encoding="utf-8")
s4_accounting = (PRODUCT / "relay/src/s4-accounting.js").read_text(encoding="utf-8")
s4_relay = (PRODUCT / "relay/src/index.js").read_text(encoding="utf-8")
s4_admission_regression = (PRODUCT / "tests/run_s4_admission_regression.ps1").read_text(encoding="utf-8")
s4_accounting_regression = (PRODUCT / "tests/s4-accounting-regression.mjs").read_text(encoding="utf-8")
task_checkpoint_store = (PRODUCT / "runtime/task-checkpoint-store.mjs").read_text(encoding="utf-8")
task_checkpoint_regression = (PRODUCT / "tests/task-checkpoint-regression.mjs").read_text(encoding="utf-8")
task_checkpoint_ps51 = (PRODUCT / "tests/run_task_checkpoint_regression.ps1").read_text(encoding="utf-8")
task_checkpoint_knowledge = (ROOT / "KNOWLEDGE/TASK_CHECKPOINT.md").read_text(encoding="utf-8")
chat_mcp_knowledge = (ROOT / "KNOWLEDGE/CHAT_MCP_EXECUTION.md").read_text(encoding="utf-8")
skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8-sig")

forbidden_helper = ["source_write", "delete_file", "start_process", "browser", "arbitrary_url"]
rec("helper_has_no_forbidden_model_capability", not any(x in helper for x in forbidden_helper), [x for x in forbidden_helper if x in helper])
rec("helper_project_task_from_admission", "const PROJECT = String(admission.project_id" in helper and "const TASK = String(admission.task_id" in helper, "admission bindings")
rec("helper_proposal_not_applied", "PROPOSAL_NOT_APPLIED" in helper and "_proposal_provenance.json" in helper, "provenance status/path")
rec("helper_recover_first_cas", "existing&&replace&&existing.sha256===hash" in helper and "IDEMPOTENCY_KEY_REUSE" in helper, "CAS/idempotency")
rec("helper_active_manifest_scope", "collectArtifacts(manifest)" in helper and "artifactPrefixes" in helper, "manifest artifact prefixes")
rec("helper_state_is_snapshot_bound", "s.snapshot_id===SNAPSHOT" in helper and "snapshot_id:SNAPSHOT" in helper, "session state bound to source snapshot")
rec("helper_import_matches_installed_layout", "../provider/source-reader-integration.mjs" in helper, "installed helper/provider sibling layout")
quality_lock = lock.get("local_quality_adapter", {})
rec("quality_adapter_exact_contract", quality_lock.get("contract") == "LOCAL_QUALITY_ADAPTER_Q0_V1" and quality_lock.get("report_schema") == "LOCAL_QUALITY_REPORT_V1" and quality_lock.get("operations") == ["META_INFO","FORM_INFO","FORM_VALIDATE"], quality_lock)
rec("quality_adapter_exact_upstream_pin", quality_lock.get("upstream_commit") == "1fa205b961f4ed3659f58f4b55d2d9b1d5e4810e" and quality_lock.get("license") == "MIT", quality_lock.get("upstream_commit"))
rec("quality_adapter_shell_false_bounded", quality_lock.get("shell") is False and quality_lock.get("prepared_quality_max_bytes") == 1200 and quality_lock.get("session_cache_targets") == 2 and quality_lock.get("timeouts_ms") == {"META_INFO":15000,"FORM_INFO":15000,"FORM_VALIDATE":30000}, quality_lock)
rec("quality_adapter_selected_scripts_exact", quality_lock.get("selected_scripts",{}).get("meta-info.ps1",{}).get("git_blob") == "cf1a233e7fb270325a91dd8403ca96794d26c7d9" and quality_lock.get("selected_scripts",{}).get("form-info.ps1",{}).get("git_blob") == "0edda69123ce565938bf368ff26039a890ac23d1" and quality_lock.get("selected_scripts",{}).get("form-validate.ps1",{}).get("git_blob") == "208e9ee4c543c7ef85ead5465f1abf5ecff19a3f", quality_lock.get("selected_scripts"))
rec("quality_adapter_internal_only_after_read", helper.count("quality.runConfirmed(rel,v.sha256)") == 1 and helper.index("provider.callClientTool('source_read'") < helper.index("quality.runConfirmed(rel,v.sha256)") and "runConfirmed" not in helper[helper.index("async function sourceSearch"):helper.index("async function qualityPathHash")], "successful source_read precedes the only quality execution site; source_search cannot invoke it")
rec("quality_adapter_no_generic_shell", "shell:false" in quality_adapter and "shell:true" not in quality_adapter and "exec(" not in quality_adapter and "execFile(" not in quality_adapter and "C:\\\\Windows\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe" in quality_adapter, "fixed PS5.1 spawn only")
resolver_block = quality_adapter[quality_adapter.index("async function exactTarget"):quality_adapter.index("function parseValidation")]
rec("quality_adapter_exact_target_binding", all(t in resolver_block for t in ["METADATA_OBJECT","FORM","META_COLLECTIONS","Forms","Form.xml","Module.bsl"]) and "readdir" not in resolver_block and "walk" not in resolver_block.lower(), "direct structural resolver only; no recursive owner search")
rec("quality_adapter_cache_invalidation_contract", all(t in helper+quality_adapter for t in ["reportBindingMatches","source_snapshot_id","manifest_sha256","confirming_read","input_closure","adapter_contract_version","upstream_commit","overlay_sha256","quality_targets","slice(0,2)"]), "bounded cache is exact-binding and closure freshness aware")
rec("quality_adapter_source_drift_contract", "SOURCE_CHANGED_DURING_RUN" in quality_adapter and "state.quality_targets=[]" in helper and "materializeClosure" in quality_adapter, "closure-only sandbox plus post-run source drift discard")
rec("quality_adapter_windows_regression_covers_contract", all(t in quality_windows_regression for t in ["LOCAL_QUALITY_WINDOWS_PS51_REGRESSION_PASS","quality_only_after_successful_source_read","source_search_never_runs_quality","start_fast_path_preserved","status_fast_path_preserved","admission_fast_path_preserved","source_drift_discards_cache"]), "actual Windows PS5.1 regression owner")

s4_lock = lock.get("hosted_mcp", {}).get("s4", {})
relay_lock = lock.get("hosted_mcp", {}).get("relay_source", {})
rec("s4_policy_pending_not_guessed", s4_lock.get("contract") == "S4_DURABLE_TASK_ACCOUNTING_V1" and s4_lock.get("admission_schema") == 3 and s4_lock.get("qualification_status") == "PENDING" and s4_lock.get("candidate") is None and s4_lock.get("epoch_soft_request_limit") == 32 and s4_lock.get("epoch_soft_result_byte_limit") == 36000 and s4_lock.get("max_result_bytes") == 3000, s4_lock)
rec("s4_relay_source_owner_pinned", relay_lock.get("component") == "relay/src/index.js" and relay_lock.get("accepted_pre_s4_deployment") == "5971635f-448e-4ccc-bf48-59709ef95e1a" and relay_lock.get("accepted_pre_s4_source_sha256") == "d57ccecc41fc27940c98908bf1c2e844e78c7f612cfec2de46952209e87dd9b0" and relay_lock.get("current_candidate_source_sha256") == hashlib.sha256((PRODUCT/"relay/src/index.js").read_bytes()).hexdigest() and relay_lock.get("accounting_component_sha256") == hashlib.sha256((PRODUCT/"relay/src/s4-accounting.js").read_bytes()).hexdigest() and relay_lock.get("deployment_status") == "NOT_DEPLOYED_PENDING_CAP_ACCEPTANCE", relay_lock)
relay_tools = re.findall(r"\{name:'(source_context|source_search|source_read|proposal_write|proposal_read|task_checkpoint_write)'", s4_relay)
rec("s4_relay_model_surface_exact_six", relay_tools == expected_surface, relay_tools)
rec("s4_durable_accounting_owner_contract", all(t in s4_accounting for t in ["S4_DURABLE_TASK_ACCOUNTING_V1","task_requests_used","task_result_bytes_used","epoch_requests_used","epoch_result_bytes_used","RECONNECT_WITH_UNRESOLVED_RESERVATION","TASK_SECURITY_BUDGET_EXHAUSTED","SNAPSHOT_MISMATCH"]), "relay durable + epoch accounting and recover-first reservation semantics")
rec("s4_admission_v3_internal_identity", all(t in core for t in ["schema_version=3","task_admission_id=$taskAdmissionId","session_id=$stableSessionId","S4_CAP_QUALIFICATION_REQUIRED","epoch_soft_request_limit","task_result_byte_limit"]) and "task_admission_id" not in core[core.index("function New-Admission {"):core.index("Assert-SafeId $TaskId")], "manager mints task/session identity; unqualified cap fails closed")
rec("s4_helper_stable_task_session", all(t in helper for t in ["admission.schema_version === 3","TASK_ADMISSION_ID","STABLE_SESSION_ID","TASK_EXPIRES_UTC","S4_HELLO_ACK","epoch_soft_request_limit"]) and "epoch_id" not in helper[helper.index("const TASK_ADMISSION_ID"):helper.index("const PROV_PATH")], "helper binds stable task/session; relay owns epoch")
rec("s4_security_regression_required_cases", all(t in s4_accounting_regression for t in ["RECONNECT_PRESERVES_TASK_COUNTERS","HELPER_RESTART_PRESERVES_TASK_COUNTERS","EPOCH_ROTATION_PRESERVES_TASK_COUNTERS","ACCOUNTING_STATE_LOSS_FAILS_CLOSED","AMBIGUOUS_PROPOSAL_WRITE_RECOVERS_BEFORE_REPLAY","UNKNOWN_RESPONSE_SIZE_CANNOT_OVERSHOOT_TASK_CAP","RECONNECT_CHARGES_ORPHAN_RESERVED_BYTES","SNAPSHOT_MISMATCH_CONTEXT_IS_CONTROL_ONLY"]), "focused durable-accounting security regression")
rec("s4_admission_regression_preserves_fast_path", all(t in s4_admission_regression for t in ["S4_ADMISSION_PS51_REGRESSION_PASS","unqualified_default_fails_closed","saved_exact_identity","task_expiry_fixed","no_deep_verify_in_admission"]), "Windows PS5.1 admission v3 regression includes explicit #83 no-deep-verify assertion")
rec("s4_readme_cap_review_boundary", all(t in readme for t in ["task_admission_id","relay-owned durable usage","epoch soft quanta only","cap policy PENDING","fails closed rather than inventing"]), "S4 UX/security contract and unaccepted cap boundary")

checkpoint_lock = lock.get("hosted_mcp", {}).get("task_checkpoint", {})
rec("task_checkpoint_lock_contract", checkpoint_lock.get("checkpoint_schema") == "TASK_CHECKPOINT_V1" and checkpoint_lock.get("head_schema") == "TASK_CHECKPOINT_HEAD_V1" and checkpoint_lock.get("recovery_schema") == "RECOVERY_PACKAGE_V1" and checkpoint_lock.get("activity_cursor_schema") == "S4_ACTIVITY_CURSOR_V1" and checkpoint_lock.get("activity_owner") == "relay task record/request_receipts" and checkpoint_lock.get("checkpoint_max_bytes") == 4096 and checkpoint_lock.get("semantic_max_bytes") == 2048 and checkpoint_lock.get("receipt_max_bytes") == 512 and checkpoint_lock.get("max_committed_versions") == 16 and checkpoint_lock.get("retention_days") == 30 and checkpoint_lock.get("generic_write_capability") is False and checkpoint_lock.get("second_activity_journal") is False, checkpoint_lock)
rec("task_checkpoint_same_s4_activity_owner", all(t in s4_accounting for t in ["request_receipts","activity_seq","activity_sha256","S4_ACTIVITY_CURSOR_V1","S4_ACTIVITY_DELTA_V1"]) and "activity_journal" not in s4_accounting.lower() and "activity:" not in s4_relay, "activity cursor/delta extends existing S4 task record/request_receipts only")
checkpoint_tool = s4_relay[s4_relay.index("{name:'task_checkpoint_write'"):s4_relay.index("];\nconst McpApiHandler")]
rec("task_checkpoint_narrow_model_schema", all(t in checkpoint_tool for t in ["idempotency_key","expected_seq","expected_predecessor_sha256","progress_summary","first_unfinished_step"]) and not any(t in checkpoint_tool for t in ["task_admission_id","session_id","activity_cursor","native_path","project_id","task_id"]), "only bounded semantic fields are model authored")
rec("task_checkpoint_helper_binding", all(t in helper for t in ["createTaskCheckpointStore","checkpointStore.recovery","op==='task_checkpoint_write'","ACTIVITY_CURSOR_UNAVAILABLE","CHECKPOINT_SOURCE_REF_OUTSIDE_ADMISSION","predecessor:admission.predecessor"]), "helper injects active admission/S4 binding and exposes recovery through source_context")
rec("task_checkpoint_store_cas_atomic_bounded", all(t in task_checkpoint_store for t in ["TASK_CHECKPOINT_V1","TASK_CHECKPOINT_HEAD_V1","RECOVERY_PACKAGE_V1","CHECKPOINT_MAX_BYTES=4096","SEMANTIC_MAX_BYTES=2048","MAX_VERSIONS=16","STALE_CHECKPOINT_HEAD","IDEMPOTENCY_KEY_REUSE","CHECKPOINT_STATE_CORRUPT","open(file,'wx'","fsp.rename","CHECKPOINT_RECEIPT_CAP","RECOVERY_PACKAGE_HARD_CAP"]), "immutable CAS/idempotent read-back store with hard byte limits")
rec("task_checkpoint_retention_acl_lifecycle", all(t in core for t in ["function Invoke-TaskStateRetention","RetentionDays=30","Read-TaskCheckpointContinuationHead","Join-Path $ProgramDataRoot 'task-state'","$readerM","Invoke-TaskStateRetention -ProgramDataRoot $ProgramDataRoot"]) and "runtime/task-checkpoint-store.mjs" in core, "existing Worker/Core lifecycle owns task-state ACL/install/retention")
rec("task_checkpoint_explicit_operator_continuation", all(t in core+launcher for t in ["function Continue-WorkerAdmission","TASK_PREDECESSOR_GOAL_MISMATCH","predecessor=$predecessorBinding","CONTINUE_AVAILABLE","recommended='Continue previous task'","Run-Continue"]) and "Predecessor" not in launcher[launcher.index("function Run-Continue {"):launcher.index("function Run-Stop {")], "operator action resolves predecessor; model/operator cannot supply predecessor ids directly")
rec("task_checkpoint_operator_projection", all(t in launcher for t in ["checkpoint=$checkpoint.head","state='CONTINUE_AVAILABLE'","Previous task checkpoint available","A verified semantic checkpoint is available. Continuing creates a new finite S4 admission"]), "guided/operator projection is bounded checkpoint head + explicit continuation action")
rec("task_checkpoint_privacy_no_transcript_or_cot", not any(t in checkpoint_tool.lower() for t in ["transcript","chain_of_thought","chain-of-thought","reasoning","scratchpad","credential","secret","token_trace"]) and not any(t in task_checkpoint_store.lower() for t in ["transcript_text","chain_of_thought","token_trace","logprob"]), "checkpoint schema has no transcript/CoT/credential fields")
rec("task_checkpoint_regression_contract", all(t in task_checkpoint_regression for t in ["TASK_CHECKPOINT_REGRESSION_PASS checks=","FIRST_WRITE_AND_READBACK","CAS_CONCURRENT_WRITERS_NO_LAST_WRITER_WINS","AMBIGUOUS_AFTER_FILE_COMMIT_RECOVERS_HEAD","FRESH_CHAT_ONE_CONTEXT_RECOVERY","HELPER_RESTART_PRESERVES_CHECKPOINT","EPOCH_ROLLOVER_TRANSPARENT","EXPLICIT_CONTINUATION_CROSSES_ADMISSION","ACTIVITY_TRUNCATION_PRESERVES_COUNTS_DIGEST","NO_SOURCE_OUTPUT_MUTATION","EXACT_SIX_TOOL_SURFACE"]) and "TASK_CHECKPOINT_PS51_WRAPPER_PASS" in task_checkpoint_ps51, "focused core regression source declares required cases; durable checkpoint records terminal 18-check PS5.1 PASS")
rec("task_checkpoint_skill_recovery_contract", all(t in task_checkpoint_knowledge+chat_mcp_knowledge+skill_text for t in ["TASK_CHECKPOINT_V1","RECOVERY_PACKAGE_V1","first_unfinished_step","do_not_replay","Continue previous task","task_checkpoint_write"]) and "Do not ask the operator to paste the old conversation" in task_checkpoint_knowledge, "Skill/knowledge consumes current recovery and keeps checkpoint separate from proof/process owners")

scratch_scripts = {
    "local": local_regression,
    "guided_ui": guided_ui_regression,
    "guided_progress": guided_progress_regression,
    "apply_failure": apply_failure_regression,
    "apply_quarantine": apply_quarantine_regression,
    "snapshot_fast": snapshot_fast_regression,
    "operator_acl": operator_acl_regression,
    "update_bootstrap": update_bootstrap_regression,
}
scratch_text = "\\n".join(scratch_scripts.values())
rec("test_scratch_owner_contract", all(t in test_scratch for t in [
    r"Temp\OneCWT",
    "ONEC_TEST_SCRATCH",
    "OneCChatWorker.Tests",
    ".onec-test-scratch.json",
    "creator_process_start_utc",
    "OWNED_STALE",
    "SKIPPED_ACTIVE",
    "SCRATCH_PATH_OUTSIDE_OWNER_ROOT",
    "SCRATCH_MARKER_INVALID_OR_MISSING",
    "Clear-StaleOneCTestScratch",
]), "single marker-bound user-local test scratch owner with liveness + TTL")
rec("test_scratch_owner_ps51_only", "pwsh" not in test_scratch.lower() and "powershell 7" not in test_scratch.lower(), "no PowerShell 7 dependency")
rec("regressions_use_canonical_scratch_owner", all("TestScratch.psm1" in text and "New-OneCTestScratch" in text for text in scratch_scripts.values()), list(scratch_scripts))
rec("regressions_have_no_bare_c_test_roots", r"C:\OneCChatWorker-" not in scratch_text and r"C:\ProgramData\OneCChatWorker-" not in scratch_text, "no persistent regression defaults")
rec("regressions_have_no_adhoc_temp_run_roots", "$env:TEMP" not in scratch_text and "OneCChatWorker-GuidedUI-" not in scratch_text and "OneCChatWorker-ApplyFailure-" not in scratch_text, "run roots are canonical owner paths only")
rec("hygiene_regression_covers_pass_fail_stale_foreign", all(t in test_scratch_hygiene for t in [
    "TEST_SCRATCH_HYGIENE_REGRESSION_PASS",
    "pass_cleanup_leaves_no_created_scratch",
    "injected_fail_cleanup",
    "interrupted_stale_classified",
    "interrupted_stale_ttl_cleaned",
    "active_scratch_not_ttl_deleted",
    "similar_foreign_directory_not_deleted",
    "invalid_marker_directory_not_deleted",
]), "PS5.1 behavioral hygiene coverage")
rec("hygiene_regression_protects_production_and_active_admission", all(t in test_scratch_hygiene for t in [
    "production_worker_delete_rejected",
    "production_programdata_delete_rejected",
    "production_projects_untouched",
    "production_installed_state_untouched",
    "production_helper_file_untouched",
    "production_active_admission_untouched",
    "active_helper_process_untouched",
    "no_new_bare_c_test_roots",
    "no_new_persistent_programdata_test_roots",
]), "production and active helper/admission are observation-only")
rec("durable_task_checkpoints_not_scratch", r"OneCArchitecture\TaskCheckpoints" not in test_scratch and "task_checkpoints_outside_scratch_owner" in test_scratch_hygiene, "durable checkpoints remain outside disposable owner")
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
start_block = launcher[launcher.index("function Run-Start {"):launcher.index("function Run-Continue {")]
rec("snapshot_fast_state_is_bounded", all(t in fast_state_block for t in ["ACCEPTED","APPLY_REQUIRED","CATALOG_DRIFT","INCOMPLETE_APPLY_RESIDUE","DEEP_VERIFY_REQUIRED","SNAPSHOT_MANIFEST_INVALID","SNAPSHOT_ROOT_MISSING"]) and not any(t in fast_state_block for t in ["Get-TreeDigest","Get-ChildItem -Recurse","rg.exe","Copy-Item"]), "FAST_STATE_CHECK_V1 is bounded by catalog/manifest/artifact roots")
rec("snapshot_status_is_fast", "Get-FastProjectState" in status_block and not any(t in status_block for t in ["Verify-WorkerProject","Get-TreeDigest"]), "STATUS uses fast state only")
rec("snapshot_start_is_single_fast_check", start_block.count("Get-FastProjectState") == 1 and "Verify-WorkerProject" not in start_block, "START performs exactly one fast-state check")
rec("snapshot_admission_consumes_accepted_state", "AcceptedState" in admission_block and not any(t in admission_block for t in ["Verify-WorkerProject","Get-TreeDigest"]), "New-Admission binds accepted snapshot without deep verify")
rec("snapshot_manifest_v2_contract", all(t in core for t in ["ACCEPTED_SNAPSHOT_V1","source_snapshot_id","publication_generation","fingerprint_inventory_state","LEGACY_DEEP_VERIFIED","ABSENT_LEGACY"]), "manifest v2 accepted snapshot + legacy adoption contract")
rec("snapshot_one_pass_bootstrap_contract", all(t in one_pass_block for t in ["New-SourceCopyPlan","Invoke-OnePassCopyHash","SOURCE_CHANGED_DURING_SYNC","[IO.File]::Open","TransformBlock","Assert-SourceCopyPlanStable"]) and "Get-TreeDigest" not in one_pass_block, "future bootstrap hashes while copying and metadata-rechecks Source without rereading stage")
rec("snapshot_helper_exact_binding", all(t in helper for t in ["ADMISSION_MANIFEST_HASH_MISMATCH","ADMISSION_SOURCE_SNAPSHOT_MISMATCH","manifest.accepted_snapshot.source_snapshot_id","admission.manifest_sha256","admission.source_snapshot_id"]), "helper fails closed on exact manifest/snapshot mismatch")
rec("snapshot_regression_covers_required_fast_path", all(t in snapshot_fast_regression for t in ["SNAPSHOT_FAST_REGRESSION_PASS","one_pass_digest_equals_legacy","fast_accepted_with_external_source_offline","second_task_reuses_snapshot","helper_manifest_hash_mismatch","helper_snapshot_mismatch","missing_root_fast_reject","missing_config_fast_reject","catalog_drift_fast_reject","residue_fast_recover_first","legacy_insufficient_evidence_rejects","deep_verify_detects_seeded_drift","source_metadata_drift_aborts","start_exactly_one_fast_no_deep","status_no_deep_or_tree_digest","admission_no_deep_or_tree_digest","helper_six_ops_exact"]), "Windows PS5.1 #83 regression covers warm path, fail-closed negatives, deep verify and exact six-tool surface")

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
