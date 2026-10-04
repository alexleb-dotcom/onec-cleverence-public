#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from skill_freshness import plan_freshness

cases = json.loads((ROOT / "TESTS/SKILL_FRESHNESS_CASES.json").read_text(encoding="utf-8"))
results = {}
errors = []


def record(case_id: str, ok: bool, details: dict) -> None:
    key = f"skill_freshness:{case_id}"
    results[key] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": key, "details": details})


for case in cases.get("cases", []):
    case_id = case["id"]
    out = plan_freshness(
        case.get("loaded_sha"),
        case.get("current_sha"),
        history_comparable=bool(case.get("history_comparable", True)),
        changed_files=case.get("changed_files") or [],
        skill_maintenance=bool(case.get("skill_maintenance", False)),
    )

    mismatches = {}
    for key, expected in (case.get("expected") or {}).items():
        if out.get(key) != expected:
            mismatches[key] = {"expected": expected, "actual": out.get(key)}

    reloads = set(out.get("reload_candidates") or [])
    missing_reload = sorted(set(case.get("reload_contains") or []) - reloads)
    forbidden_reload = sorted(set(case.get("reload_excludes") or []) & reloads)

    ok = not mismatches and not missing_reload and not forbidden_reload
    record(case_id, ok, {
        "mismatches": mismatches,
        "missing_reload": missing_reload,
        "forbidden_reload": forbidden_reload,
        "plan": out,
    })

# The contract itself must retain the long-lived-chat and final-claim guards.
knowledge = (ROOT / "KNOWLEDGE/SKILL_FRESHNESS.md").read_text(encoding="utf-8")
first = (ROOT / "README_FIRST.md").read_text(encoding="utf-8")
contract_tokens = [
    "loaded_sha",
    "REFRESH_REQUIRED",
    "REBOOTSTRAP_REQUIRED",
    "SHA check → diff → task-impact reload",
    "before a final claim",
    "do not claim that the skill is current/latest",
]
missing_contract = [token for token in contract_tokens if token not in knowledge]
record("contract_tokens", not missing_contract, {"missing": missing_contract})

entry_tokens = [
    "KNOWLEDGE/SKILL_FRESHNESS.md",
    "loaded_sha",
    "substantive",
    "diff",
]
missing_entry = [token for token in entry_tokens if token not in first]
record("entrypoint_routes_freshness", not missing_entry, {"missing": missing_entry})

# A shareable/public copy resolves its own canonical repository instead of tracking
# the private maintenance repository embedded in historical documentation.
identity_tokens = [
    "Repository identity is deployment-local",
    "active Git remote or connected repository identity",
    "Never hard-code the private maintenance repository",
    "freshness remains `UNVERIFIED`",
]
missing_identity = [token for token in identity_tokens if token not in knowledge]
hardcoded_private_repository = "alexleb-dotcom/onec-cleverence" in knowledge
record(
    "portable_repository_identity",
    not missing_identity and not hardcoded_private_repository,
    {"missing": missing_identity, "hardcoded_private_repository": hardcoded_private_repository},
)


# Capability-based bounded Chat execution must remain portable and conditional.
chat_exec = (ROOT / "KNOWLEDGE/CHAT_MCP_EXECUTION.md").read_text(encoding="utf-8")
skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
chat_tokens = [
    "source_context",
    "source_search",
    "source_read",
    "proposal_write",
    "proposal_read",
    "PROPOSAL_NOT_APPLIED",
    "MANUAL_SKILL_EXECUTION",
    "semantic capability",
]
missing_chat_tokens = [token for token in chat_tokens if token not in chat_exec]
forbidden_chat_tokens = ["OneC_G1Q1_MCP", "Cloudflare", "OAuth", "relay implementation"]
present_forbidden = [token for token in forbidden_chat_tokens if token in chat_exec or token in skill]
record(
    "chat_mcp_capability_contract_is_portable",
    not missing_chat_tokens and not present_forbidden,
    {"missing": missing_chat_tokens, "forbidden": present_forbidden},
)
record(
    "chat_mcp_trigger_is_conditional_and_small",
    skill.count("KNOWLEDGE/CHAT_MCP_EXECUTION.md") == 1
    and "Route by semantic capability, not connector/namespace name." in skill,
    {"owner_refs": skill.count("KNOWLEDGE/CHAT_MCP_EXECUTION.md")},
)

out = {
    "result": "PASS" if not errors else "FAIL",
    "errors": errors,
    "results": results,
    "cases": len(cases.get("cases", [])),
}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
