#!/usr/bin/env python3
"""Shared helpers for the executable rule registry.

RULES/rule_registry.json is the single source of truth for routing and release coverage.
Generated views are conveniences and must never become an independent registry.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "RULES/rule_registry.json"
RISK_RANK = {"R0_LOCAL":0,"R1_CONTRACT":1,"R2_STATEFUL_RUNTIME":2,"R3_CROSS_SYSTEM":3}


def load_registry(path: Path | None = None) -> dict:
    p = path or REGISTRY_PATH
    return json.loads(p.read_text(encoding="utf-8-sig"))


def rule_map(registry: dict) -> dict[str, dict]:
    return {row["id"]: row for row in registry.get("rules", [])}

def requirements_rule_map(registry: dict) -> dict[str, dict]:
    return {row["id"]: row for row in registry.get("requirements_rules", [])}


def proof_policy_for(rule: dict, registry: dict) -> dict:
    """Resolve explicit rule policy or the registry-owned compatibility migration."""
    policy=rule.get("proof_policy")
    if isinstance(policy,dict):
        return json.loads(json.dumps(policy,ensure_ascii=False))
    contract=registry.get("proof_policy_contract") or {}
    legacy=contract.get("legacy_compatibility")
    if contract.get("missing_policy_behavior")!="EXPLICIT_LEGACY_COMPATIBILITY" or not isinstance(legacy,dict):
        raise ValueError(f"Missing fail-closed proof policy for rule {rule.get('id')}")
    return {
        "claim_class":legacy.get("claim_class","LEGACY_COMPATIBLE"),
        "required_roles":list(legacy.get("required_roles") or []),
        "migration":"REGISTRY_LEGACY_COMPATIBILITY",
    }


def max_risk(*risks: str | None) -> str:
    values=[x for x in risks if x]
    if not values:
        return "R0_LOCAL"
    return max(values, key=lambda x:RISK_RANK[x])


def regex_hits(rule: dict, text: str) -> list[str]:
    hits=[]
    for pattern in rule.get("activation", {}).get("patterns", []):
        try:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                hits.append(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid activation regex for {rule['id']}: {pattern}: {exc}") from exc
    return hits


def generated_profile_index(registry: dict) -> dict:
    profiles={}
    for rule in registry.get("rules", []):
        profile=rule.get("profile")
        if not profile:
            continue
        profiles[profile]={
            "file": f"PROFILES/{profile}.md",
            "detect": rule.get("activation", {}).get("patterns", []),
            "detect_paths": rule.get("activation", {}).get("path_patterns", []),
            "standards": rule.get("standards", []),
            "rule_id": rule["id"],
            "tier": rule["tier"],
            "risk_floor": rule.get("risk_floor","R0_LOCAL"),
            "surface": rule.get("surface","ANY"),
            "proof_policy": proof_policy_for(rule,registry),
            "performance_review": rule.get("performance_review"),
            "generated_from": "RULES/rule_registry.json"
        }
    return {
        "version": 11,
        "generated": True,
        "generated_from": "RULES/rule_registry.json",
        "principle": registry.get("principle", ""),
        "blocking_rule": "Unknown/unrouted mechanism or missing rule evidence => COVERAGE_GAP; generated views are not an independent source of truth.",
        "profiles": profiles,
        "review_levels":["L1_CONSTRUCTION","L2_ROUTINE","L3_MODULE","L4_METADATA_OBJECT","L5_CROSS_OBJECT","L6_BUSINESS_RUNTIME"],
        "reverse_coverage_required": True
    }


def generated_detailed_profiles(registry: dict) -> dict:
    profiles={}
    for rule in registry.get("rules", []):
        profile=rule.get("profile")
        if not profile:
            continue
        profiles[profile]={
            "detect": rule.get("activation", {}).get("patterns", []),
            "detect_paths": rule.get("activation", {}).get("path_patterns", []),
            "standards": rule.get("standards", []),
            "checks": [c["question"] for c in rule.get("checks", [])],
            "rule_id": rule["id"],
            "proof_policy": proof_policy_for(rule,registry),
            "performance_review": rule.get("performance_review"),
            "generated_from": "RULES/rule_registry.json"
        }
    return {
        "version": 8,
        "generated": True,
        "generated_from": "RULES/rule_registry.json",
        "principle": registry.get("principle", ""),
        "statuses": registry.get("status_model",{}).get("rule_statuses",[]),
        "profiles": profiles,
        "blocking_rule": "Every activated profile/rule requires evidence-backed disposition; generated views cannot silently add/remove rules.",
        "review_levels":["L1_CONSTRUCTION","L2_ROUTINE","L3_MODULE","L4_METADATA_OBJECT","L5_CROSS_OBJECT","L6_BUSINESS_RUNTIME"],
        "reverse_coverage_required": True,
        "reverse_coverage_rule": "Expand checks from RULES/rule_registry.json independently from code-driven findings."
    }


def generated_semantic_markdown(registry: dict) -> str:
    rows=[]
    for rule in registry.get("rules", []):
        for check in rule.get("checks", []):
            if check.get("kind") in {"SEMANTIC_REGRESSION","META"}:
                rows.append((check["id"], rule["id"], check["question"]))
    lines=[
        "# Semantic regression classes",
        "",
        "Generated from `RULES/rule_registry.json`. Do not edit this file directly.",
        "",
    ]
    for cid,rid,q in rows:
        lines += [f"## {cid}","",f"Rule: `{rid}`", "", q, ""]
    return "\n".join(lines).rstrip()+"\n"


def generated_requirements_index(registry: dict) -> dict:
    return {
        "version": 2,
        "generated": True,
        "generated_from": "RULES/rule_registry.json",
        "principle": "Requirements rules are executable pre-code contracts. Missing evidence or blocking OPEN fields stop production-ready technical design; requirements artifacts additionally preserve claim provenance and cannot launder proposals into requirements.",
        "claim_contract": registry.get("requirements_claim_contract",{}),
        "rules": {
            rule["id"]: {
                "tier": rule.get("tier"),
                "surface": rule.get("surface","ANY"),
                "risk_floor": rule.get("risk_floor","R0_LOCAL"),
                "activation": rule.get("activation",{}),
                "checks": [c["question"] for c in rule.get("checks",[])],
                "evidence_modes": rule.get("evidence_modes",[]),
            }
            for rule in registry.get("requirements_rules",[])
        },
        "contract_fields": registry.get("requirements_contract_fields",[]),
        "outcomes": registry.get("requirements_status_model",{}).get("outcomes",[]),
    }

def generated_requirements_semantic_markdown(registry: dict) -> str:
    rows=[]
    for rule in registry.get("requirements_rules",[]):
        for check in rule.get("checks",[]):
            if check.get("kind") in {"SEMANTIC_REGRESSION","META"}:
                rows.append((check["id"],rule["id"],check["question"]))
    lines=["# Requirements semantic regression classes","","Generated from `RULES/rule_registry.json`. Do not edit this file directly.",""]
    for cid,rid,q in rows:
        lines += [f"## {cid}","",f"Rule: `{rid}`","",q,""]
    return "\n".join(lines).rstrip()+"\n"


def _compact_rule(rule: dict) -> dict:
    return {
        "id":rule.get("id"),
        "tier":rule.get("tier"),
        "profile":rule.get("profile"),
        "surface":rule.get("surface","ANY"),
        "risk_floor":rule.get("risk_floor","R0_LOCAL"),
        "evidence_modes":rule.get("evidence_modes",[]),
        "proof_policy":rule.get("proof_policy"),
        "performance_review":rule.get("performance_review"),
        "checks":[{"id":c.get("id"),"kind":c.get("kind"),"question":c.get("question")} for c in rule.get("checks",[])],
    }


def generated_proof_policy_index(registry: dict) -> dict:
    contract=registry.get("proof_policy_contract") or {}
    return {
        "version":1,
        "generated":True,
        "generated_from":"RULES/rule_registry.json",
        "contract":contract,
        "rules":{rule["id"]:proof_policy_for(rule,registry) for rule in registry.get("rules",[])},
    }


def main() -> int:
    ap=argparse.ArgumentParser(description="Query the executable rule registry without loading the full registry into LLM context.")
    ap.add_argument("--rule",help="Print one technical rule by exact id.")
    ap.add_argument("--requirements-rule",help="Print one requirements rule by exact id.")
    args=ap.parse_args()
    registry=load_registry()
    if bool(args.rule)==bool(args.requirements_rule):
        ap.error("provide exactly one of --rule or --requirements-rule")
    rows=registry.get("rules",[]) if args.rule else registry.get("requirements_rules",[])
    wanted=args.rule or args.requirements_rule
    row=next((x for x in rows if x.get("id")==wanted),None)
    if row is None:
        print(json.dumps({"result":"NOT_FOUND","id":wanted},ensure_ascii=False,separators=(",",":")))
        return 2
    print(json.dumps({"result":"FOUND","source":"RULES/rule_registry.json","rule":_compact_rule(row)},ensure_ascii=False,separators=(",",":")))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
