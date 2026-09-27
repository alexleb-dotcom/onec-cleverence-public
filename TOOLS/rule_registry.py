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


CAPABILITY_ID_RE = re.compile(r"^CAP\.[A-Z0-9_]+$")
DELIVERY_ENFORCEMENT = {"ADVISORY","GATING"}
DELIVERY_PAYLOAD_KINDS = {"INSTRUCTION"}


def validate_delivery_bindings(registry: dict) -> list[str]:
    """Validate the narrow rule-owned delivery/proof contract without creating a second registry."""
    errors=[]; seen={}; seen_sequences={}; rules=rule_map(registry); surfaces=set(registry.get("surfaces") or [])
    allowed_modes={"MACHINE","SOURCE_REQUIRED","SEMANTIC","RUNTIME"}
    for rule in registry.get("rules",[]):
        rid=rule.get("id","?"); deliveries=rule.get("delivery",[])
        if not isinstance(deliveries,list):
            errors.append(f"delivery_not_list:{rid}"); continue
        checks={row.get("id") for row in rule.get("checks",[]) if isinstance(row,dict)}
        for index,binding in enumerate(deliveries):
            where=f"{rid}:{index}"
            if not isinstance(binding,dict):errors.append(f"delivery_not_object:{where}");continue
            allowed={"capability_id","sequence","executor_payload","references","enforcement","proof_binding","condition"}
            extra=sorted(set(binding)-allowed)
            if extra:errors.append(f"delivery_unknown_fields:{where}:{extra}")
            capability=binding.get("capability_id")
            if not isinstance(capability,str) or not CAPABILITY_ID_RE.fullmatch(capability):
                errors.append(f"delivery_bad_capability_id:{where}:{capability}")
            elif capability in seen:
                errors.append(f"delivery_duplicate_capability_owner:{capability}:{seen[capability]}:{rid}")
            else:seen[capability]=rid
            sequence=binding.get("sequence")
            if not isinstance(sequence,int) or isinstance(sequence,bool) or sequence<0:
                errors.append(f"delivery_bad_sequence:{where}:{sequence}")
            elif sequence in seen_sequences:
                errors.append(f"delivery_duplicate_sequence:{sequence}:{seen_sequences[sequence]}:{where}")
            else:seen_sequences[sequence]=where
            payload=binding.get("executor_payload")
            if not isinstance(payload,dict) or set(payload)!={"kind","value"}:
                errors.append(f"delivery_bad_executor_payload:{where}")
            else:
                if payload.get("kind") not in DELIVERY_PAYLOAD_KINDS:errors.append(f"delivery_bad_payload_kind:{where}:{payload.get('kind')}")
                if not isinstance(payload.get("value"),str) or not payload.get("value").strip():errors.append(f"delivery_payload_empty:{where}")
            references=binding.get("references")
            if not isinstance(references,list) or any(not isinstance(x,str) or not x.strip() for x in references):errors.append(f"delivery_bad_references:{where}")
            enforcement=binding.get("enforcement")
            if enforcement not in DELIVERY_ENFORCEMENT:errors.append(f"delivery_bad_enforcement:{where}:{enforcement}")
            condition=binding.get("condition")
            if condition is not None:
                if not isinstance(condition,dict) or not condition:
                    errors.append(f"delivery_bad_condition:{where}")
                else:
                    extra_condition=sorted(set(condition)-{"surfaces","any_routed_rule_ids"})
                    if extra_condition:errors.append(f"delivery_condition_unknown_fields:{where}:{extra_condition}")
                    if "surfaces" in condition:
                        values=condition.get("surfaces")
                        if not isinstance(values,list) or not values or any(x not in surfaces for x in values):errors.append(f"delivery_condition_bad_surfaces:{where}:{values}")
                    if "any_routed_rule_ids" in condition:
                        values=condition.get("any_routed_rule_ids")
                        if not isinstance(values,list) or not values or any(x not in rules for x in values):errors.append(f"delivery_condition_bad_rule_ids:{where}:{values}")
            proof=binding.get("proof_binding")
            if enforcement=="GATING" and not isinstance(proof,dict):
                errors.append(f"delivery_gating_proof_binding_missing:{where}")
                continue
            if proof is None:continue
            if not isinstance(proof,dict) or set(proof)!={"owner","accepted_evidence"}:
                errors.append(f"delivery_bad_proof_binding:{where}");continue
            owner=proof.get("owner")
            prefix=f"CHECK:{rid}:"
            if not isinstance(owner,str) or not owner.startswith(prefix) or owner[len(prefix):] not in checks:
                errors.append(f"delivery_proof_owner_invalid:{where}:{owner}")
            accepted=proof.get("accepted_evidence")
            if not isinstance(accepted,list) or not accepted or any(x not in allowed_modes for x in accepted):
                errors.append(f"delivery_proof_evidence_invalid:{where}:{accepted}")
            elif not set(accepted).issubset(set(rule.get("evidence_modes") or [])):
                errors.append(f"delivery_proof_evidence_outside_rule:{where}:{accepted}")
    return errors


def materialize_delivery_bindings(registry: dict, rule_rows: list[dict], surface: str) -> list[dict]:
    """Project only active canonical delivery bindings into the task envelope."""
    errors=validate_delivery_bindings(registry)
    if errors:raise ValueError("Invalid registry delivery bindings: "+"; ".join(errors))
    routes={row.get("id"):row for row in rule_rows if isinstance(row,dict)}
    def routed(row):
        return bool(row and row.get("active") and (row.get("detected_by") or row.get("tier",1)>0 or str(row.get("reason","")).startswith("derived")))
    active=[]
    for rule in registry.get("rules",[]):
        route=routes.get(rule.get("id"))
        if not route or not route.get("active"):continue
        for binding in rule.get("delivery",[]):
            condition=binding.get("condition") or {}
            if condition:
                if condition.get("surfaces") and surface not in condition["surfaces"]:continue
                if condition.get("any_routed_rule_ids") and not any(routed(routes.get(x)) for x in condition["any_routed_rule_ids"]):continue
            elif not routed(route):
                continue
            active.append({
                "capability_id":binding["capability_id"],
                "sequence":binding["sequence"],
                "owner_rule_id":rule["id"],
                "enforcement":binding["enforcement"],
                "executor_payload":json.loads(json.dumps(binding["executor_payload"],ensure_ascii=False)),
                "references":list(binding.get("references") or []),
                "proof_binding":json.loads(json.dumps(binding.get("proof_binding"),ensure_ascii=False)) if binding.get("proof_binding") is not None else None,
            })
    active.sort(key=lambda row:(row["sequence"],row["capability_id"]))
    return active


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
        "delivery":rule.get("delivery",[]),
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
