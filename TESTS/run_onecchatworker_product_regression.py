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

forbidden_helper = [
    "source_write",
    "delete_file",
    "start_process",
    "browser",
    "arbitrary_url",
]
rec("helper_has_no_forbidden_model_capability", not any(x in helper for x in forbidden_helper), [x for x in forbidden_helper if x in helper])
rec("helper_project_task_from_admission", "const PROJECT = String(admission.project_id" in helper and "const TASK = String(admission.task_id" in helper, "admission bindings")
rec("helper_proposal_not_applied", "PROPOSAL_NOT_APPLIED" in helper and "_proposal_provenance.json" in helper, "provenance status/path")
rec("helper_recover_first_cas", "existing&&replace&&existing.sha256===hash" in helper and "IDEMPOTENCY_KEY_REUSE" in helper, "CAS/idempotency")
rec("helper_active_manifest_scope", "collectArtifacts(manifest)" in helper and "artifactPrefixes" in helper, "manifest artifact prefixes")

core_tokens = [
    "Participants/$pid/Target/Main",
    "Participants/$pid/Target/Extensions/$eid",
    "catalog_sha256",
    "DRIFT_APPLY_REQUIRED",
    "Detached",
    "Deactivated",
    "PLATFORM_NOT_IMPLEMENTED_1C_FIRST",
    "Output",
    "EXPECTED",
]
rec("core_has_direct_root_and_lifecycle_contract", all(t in core for t in core_tokens[:-1]), [t for t in core_tokens[:-1] if t not in core])
rec("core_no_redundant_wrapper_literal", "Target/Main/Main" not in core and "Target\\Main\\Main" not in core, "no Main/Main")
rec("core_safe_uninstall_retains_evidence", "retain Output proposals/evidence" in core and "recursive project deletion" in core, "uninstall plan")
rec("core_output_acl_separate", "Participants" in core and ":(OI)(CI)(RX)" in core and ":(OI)(CI)(M)" in core, "RX Participants / M Output")

menu_tokens = ["START PROJECT", "STOP", "STATUS", "PROJECTS", "VERIFY/REPAIR", "SETTINGS/DIAGNOSTICS", "UNINSTALL"]
rec("launcher_has_unified_menu", all(t in launcher for t in menu_tokens), [t for t in menu_tokens if t not in launcher])
rec("launcher_cli_has_required_lifecycle_modes", all(t in launcher for t in ["'APPLY'","'VERIFY'","'REPAIR'","'START'","'STOP'","'DEACTIVATE'"]), "CLI modes")
rec("readme_declares_remote_auth_checkpoint", "unavoidable remote-auth checkpoint" in readme and "helper secret" in readme and "/mcp" in readme, "remote auth documented")
rec("readme_declares_cleverence_deferred", "PLATFORM_NOT_IMPLEMENTED_1C_FIRST" in readme and "Cleverence" in readme, "1C-first")

deps = lock.get("dependencies", {})
rec("node_pinned", deps.get("node", {}).get("version") == "26.7.0" and deps.get("node", {}).get("winget_id") == "OpenJS.NodeJS", deps.get("node"))
rec("ripgrep_pinned", deps.get("ripgrep", {}).get("version") == "15.2.0" and deps.get("ripgrep", {}).get("winget_id") == "BurntSushi.ripgrep.MSVC", deps.get("ripgrep"))

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
