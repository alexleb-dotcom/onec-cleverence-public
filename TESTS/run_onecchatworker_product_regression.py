#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json

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
    "Participants/$pid/Target/Main",
    "Participants/$pid/Target/Extensions/$eid",
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
rec("core_incomplete_onec_project_fails_closed", "ONEC_MAIN_REQUIRED" in core and "NO_ACTIVE_PARTICIPANTS" in core, "verify blocks unusable admission")

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

menu_tokens = ["START PROJECT", "STOP", "STATUS", "PROJECTS", "VERIFY / REPAIR", "SETTINGS / DIAGNOSTICS", "UNINSTALL"]
rec("launcher_has_unified_menu", all(t in launcher for t in menu_tokens), [t for t in menu_tokens if t not in launcher])
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
