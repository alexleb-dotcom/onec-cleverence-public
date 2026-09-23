#!/usr/bin/env python3
"""Compact verifier-owned projection of unresolved validation obligations.

Terminal labels are declarations, not proof. A row disappears only when the
canonical release verifier returns an explicit ACCEPTED verdict for the exact
row identity. Verifier unavailability, protocol drift and unclaimed/global
errors are fail-closed blockers and keep every terminal row visible.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from release_intake import build_plan_from_intake
from release_gate_core import evaluate as release_evaluate, RESOLUTION_VERIFIER_ID, RESOLUTION_VERIFIER_VERSION
from rule_registry import load_registry

TERMINAL_STATUSES={"PASS","NOT_APPLICABLE"}
RESOLVED_ARTIFACT_STATUSES={"PROVIDED","RESOLVED_NOT_NEEDED","NOT_APPLICABLE"}
RESOLVED_HYPOTHESIS_STATUSES={"COVERED_BY_EXISTING_RULE","DISPROVED","NOT_MATERIAL","FIXED_REVALIDATED","PASS","NOT_APPLICABLE"}
RESOLVED_EXTRACTION_OUTCOMES={"PROMOTED","PROJECT_ONLY","NO_REUSABLE_KNOWLEDGE"}


def _compact_profiles(rows):
    result=[]
    for row in rows or []:
        if not isinstance(row,dict):continue
        item={"name":row.get("name"),"file":row.get("file")}
        result.append({k:v for k,v in item.items() if v})
    return result


def _unavailable(kind,details=None):
    blocker={"type":kind}
    if details is not None:blocker["details"]=details
    return {},[blocker],{"status":"UNAVAILABLE","verifier":RESOLUTION_VERIFIER_ID,"version":RESOLUTION_VERIFIER_VERSION},[],None


def _verifier_snapshot(ledger):
    record=ledger.get("release_intake")
    if not isinstance(record,dict):
        return _unavailable("WORK_QUEUE_RELEASE_INTAKE_MISSING")
    manifest=record.get("manifest")
    if not isinstance(manifest,dict):
        return _unavailable("WORK_QUEUE_RELEASE_INTAKE_MANIFEST_INVALID",{"actual_type":type(manifest).__name__})
    try:
        plan=build_plan_from_intake(manifest)
    except Exception as exc:
        return _unavailable("WORK_QUEUE_PLAN_REBUILD_FAILED",{"error":str(exc)})
    try:
        report=release_evaluate(plan,ledger,load_registry())
    except Exception as exc:
        return _unavailable("WORK_QUEUE_RELEASE_VERIFIER_FAILED",{"error":str(exc)})
    if not isinstance(report,dict):
        return _unavailable("WORK_QUEUE_VERIFIER_REPORT_INVALID",{"actual_type":type(report).__name__})

    protocol=report.get("resolution_verifier")
    verdicts=report.get("resolution_verdicts")
    if not isinstance(protocol,dict) or protocol.get("status")!="AVAILABLE":
        return _unavailable("WORK_QUEUE_VERIFIER_UNAVAILABLE",protocol)
    if protocol.get("verifier")!=RESOLUTION_VERIFIER_ID or protocol.get("version")!=RESOLUTION_VERIFIER_VERSION:
        return _unavailable("WORK_QUEUE_VERIFIER_IDENTITY_MISMATCH",protocol)
    if not isinstance(verdicts,list):
        return _unavailable("WORK_QUEUE_VERDICTS_MISSING")

    index={}; represented=set(); blockers=[]
    for raw in verdicts:
        if not isinstance(raw,dict):
            blockers.append({"type":"WORK_QUEUE_VERDICT_INVALID","details":{"actual_type":type(raw).__name__}})
            continue
        key=(raw.get("scope"),raw.get("rule_id"),raw.get("id"))
        if not all((raw.get("scope"),raw.get("id"))):
            blockers.append({"type":"WORK_QUEUE_VERDICT_IDENTITY_INCOMPLETE","details":raw})
            continue
        if key in index:
            blockers.append({"type":"WORK_QUEUE_VERDICT_DUPLICATE","details":{"scope":key[0],"rule_id":key[1],"id":key[2]}})
            continue
        if raw.get("verifier")!=RESOLUTION_VERIFIER_ID or raw.get("version")!=RESOLUTION_VERIFIER_VERSION:
            blockers.append({"type":"WORK_QUEUE_VERDICT_VERIFIER_MISMATCH","details":{"scope":key[0],"id":key[2]}})
            continue
        if raw.get("verdict") not in {"ACCEPTED","REJECTED","UNRESOLVED"}:
            blockers.append({"type":"WORK_QUEUE_VERDICT_UNKNOWN","details":{"scope":key[0],"id":key[2],"verdict":raw.get("verdict")}})
            continue
        for error in raw.get("errors") or []:
            if isinstance(error,dict) and isinstance(error.get("index"),int):represented.add(error["index"])
        index[key]=raw

    global_errors=protocol.get("global_errors") or []
    if not isinstance(global_errors,list):
        blockers.append({"type":"WORK_QUEUE_GLOBAL_ERRORS_INVALID"})
        global_errors=[]
    for error in global_errors:
        if isinstance(error,dict) and isinstance(error.get("index"),int):represented.add(error["index"])
    if global_errors:
        blockers.append({"type":"WORK_QUEUE_VERIFIER_GLOBAL_ERRORS","details":{"errors":global_errors[:8],"count":len(global_errors)}})

    report_errors=report.get("errors") or []
    if not isinstance(report_errors,list):
        blockers.append({"type":"WORK_QUEUE_VERIFIER_ERRORS_INVALID"})
        report_errors=[]
    unaccounted=[i for i in range(len(report_errors)) if i not in represented]
    if unaccounted:
        blockers.append({
            "type":"WORK_QUEUE_VERIFIER_ERROR_UNACCOUNTED",
            "details":{"indexes":unaccounted[:8],"count":len(unaccounted),"types":[(report_errors[i] or {}).get("type") if isinstance(report_errors[i],dict) else type(report_errors[i]).__name__ for i in unaccounted[:8]]},
        })

    verifier={
        "status":"AVAILABLE" if not blockers else "DEGRADED",
        "verifier":RESOLUTION_VERIFIER_ID,
        "version":RESOLUTION_VERIFIER_VERSION,
        "release_result":report.get("result"),
        "release_outcome":report.get("release_outcome"),
        "global_blocker_count":len(blockers),
    }
    return index,blockers,verifier,report_errors,report.get("implementation_readiness")


def _state(row,verdict_index,blockers,scope,rid,rule_id=None,terminal=TERMINAL_STATUSES,status_key="status"):
    disposition=row.get(status_key)
    if disposition not in terminal:
        return "UNRESOLVED",[]
    if blockers:
        return "RESOLUTION_REVIEW_REQUIRED",blockers
    verdict=verdict_index.get((scope,rule_id,rid))
    if not isinstance(verdict,dict):
        return "RESOLUTION_REVIEW_REQUIRED",[{"type":"VERIFIER_VERDICT_MISSING","scope":scope,"id":rid}]
    local=[]
    if verdict.get("disposition")!=disposition:
        local.append({"type":"VERIFIER_DISPOSITION_MISMATCH","expected":disposition,"actual":verdict.get("disposition")})
    expected_claim=row.get("claim_id")
    if expected_claim is not None and verdict.get("claim_id")!=expected_claim:
        local.append({"type":"VERIFIER_CLAIM_ID_MISMATCH","expected":expected_claim,"actual":verdict.get("claim_id")})
    if verdict.get("verdict")!="ACCEPTED":
        local.extend(verdict.get("errors") or [{"type":"VERIFIER_VERDICT_NOT_ACCEPTED","verdict":verdict.get("verdict")}])
    if local:return "RESOLUTION_REVIEW_REQUIRED",local
    return "VERIFIER_CONFIRMED",[]


def _error_types(errors):
    result=[]
    for error in errors or []:
        if not isinstance(error,dict):name=type(error).__name__
        else:name=error.get("type") or (error.get("details") or {}).get("type") or "VERIFIER_ERROR"
        if name not in result:result.append(str(name))
    return result[:4]


def _compact_item(row,state,hits,id_key="id"):
    rid=row.get(id_key) or row.get("id")
    if state=="UNRESOLVED":return rid
    item={"id":rid,"state":state}
    if row.get("claim_id") is not None:item["claim_id"]=row.get("claim_id")
    item.update({"declared":row.get("status"),"source":row.get("resolution_source") or "MODEL_OR_USER","errors":_error_types(hits)})
    return item


def build_work_queue(ledger:dict,ledger_sha256:str|None=None)->dict:
    verdicts,blockers,verifier,report_errors,implementation_readiness=_verifier_snapshot(ledger)

    rules=[]
    for row in ledger.get("rules") or []:
        if not isinstance(row,dict) or not row.get("id"):continue
        rid=row["id"]; rstate,rhits=_state(row,verdicts,blockers,"rule",rid)
        checks=[]
        for check in row.get("checks") or []:
            if not isinstance(check,dict) or not check.get("id"):continue
            cstate,chits=_state(check,verdicts,blockers,"check",check["id"],rid)
            if cstate!="VERIFIER_CONFIRMED":checks.append(_compact_item(check,cstate,chits))
        if rstate!="VERIFIER_CONFIRMED" or checks:
            policy=row.get("proof_policy") if isinstance(row.get("proof_policy"),dict) else {}
            critical_unresolved=(
                policy.get("claim_class")=="ARCHITECTURE_SEMANTIC"
                and rstate=="UNRESOLVED"
                and all(not isinstance(x,dict) for x in checks)
            )
            if not critical_unresolved:
                item={"id":rid}
                if rstate=="RESOLUTION_REVIEW_REQUIRED":item.update({"state":rstate,"declared":row.get("status"),"errors":_error_types(rhits)})
                elif rstate=="UNRESOLVED" and row.get("status") not in {None,"EVIDENCE_REQUIRED"}:item["status"]=row.get("status")
                if checks:item["checks"]=checks
                rules.append(item)

    def compact_rows(rows,scope,id_key="id",terminal=TERMINAL_STATUSES,status_key="status"):
        result=[]
        for row in rows or []:
            if not isinstance(row,dict) or not row.get(id_key):continue
            rid=row.get(id_key)
            state,hits=_state(row,verdicts,blockers,scope,rid,terminal=terminal,status_key=status_key)
            if state!="VERIFIER_CONFIRMED":result.append(_compact_item(row,state,hits,id_key))
        return result

    gates=compact_rows(ledger.get("gates"),"gate")
    levels=compact_rows(ledger.get("review_levels"),"review_level")
    c2s=compact_rows(ledger.get("code_to_standards"),"code_to_standards")
    s2c=compact_rows(ledger.get("standards_to_code"),"standards_to_code","rule_id")

    discovery=ledger.get("gap_discovery") or {}
    lenses=compact_rows(discovery.get("lenses"),"gap_lens")
    hypotheses=compact_rows(discovery.get("hypotheses"),"hypothesis",terminal=RESOLVED_HYPOTHESIS_STATUSES)
    artifacts=compact_rows(ledger.get("artifact_requests"),"artifact",terminal=RESOLVED_ARTIFACT_STATUSES)
    adversarial=compact_rows(ledger.get("adversarial_cases"),"adversarial")

    machine_findings=[]
    for row in ledger.get("machine_findings") or []:
        if not isinstance(row,dict) or not row.get("id"):continue
        state,hits=_state(row,verdicts,blockers,"machine_finding",row["id"])
        if state=="VERIFIER_CONFIRMED":continue
        item={
            "id":row["id"],
            "claim_id":row.get("claim_id"),
            "finding_type":row.get("finding_type"),
            "rule_id":row.get("rule_id"),
            "check_id":row.get("check_id"),
            "artifact":row.get("artifact"),
        }
        if state!="UNRESOLVED":
            item.update({"state":state,"declared":row.get("status"),"errors":_error_types(hits)})
        machine_findings.append(item)

    blocking_findings_by_id={}
    for row in ledger.get("blocking_findings") or []:
        if not isinstance(row,dict) or not row.get("id"):continue
        blocking_findings_by_id[row["id"]]={
            key:row.get(key) for key in ("id","rule_id","check_id","finding_type","artifact","candidate_sha256","report_id","severity","status","line","sequence")
            if row.get(key) is not None
        }
    # Deleted ledger rows cannot erase verifier-derived literal-escape blockers.
    for error in report_errors:
        if not isinstance(error,dict) or error.get("type")!="QUERY_LITERAL_ESCAPE_CORRUPTION_PRESENT":continue
        rid=error.get("id")
        if not rid:continue
        item=blocking_findings_by_id.setdefault(rid,{"id":rid})
        for key in ("rule_id","check_id","finding_type","artifact","candidate_sha256","report_id"):
            if error.get(key) is not None:item[key]=error.get(key)
        item["state"]="VERIFIER_BLOCKED"
    blocking_findings=list(blocking_findings_by_id.values())

    extraction=ledger.get("knowledge_extraction") or {}
    extraction_state,extraction_errors=_state(
        extraction,verdicts,blockers,"knowledge_extraction","KNOWLEDGE_EXTRACTION",
        terminal=RESOLVED_EXTRACTION_OUTCOMES,status_key="outcome"
    )

    work={
        "rules":rules,"gates":gates,"review_levels":levels,
        "bidirectional":{"code_to_standards":c2s,"standards_to_code":s2c},
        "gap_discovery":{"lenses":lenses,"hypotheses":hypotheses},
        "artifact_requests":artifacts,"adversarial_cases":adversarial,
        "machine_findings":machine_findings,
        "blocking_findings":blocking_findings,
    }
    performance_row=ledger.get("performance_review") if isinstance(ledger.get("performance_review"),dict) else {}
    if not isinstance(implementation_readiness,dict) or implementation_readiness.get("readiness_outcome")!="READY_FOR_IMPLEMENTATION":
        work["performance_review"]={
            "owner_rule_id":performance_row.get("owner_rule_id") or "COLLECTION_ALGORITHM",
            "declared":performance_row.get("status") or "MISSING",
            "state":"UNRESOLVED" if not isinstance(implementation_readiness,dict) else "VERIFIER_BLOCKED",
            "errors":sorted({str(x.get("type")) for x in (implementation_readiness or {}).get("errors",[]) if isinstance(x,dict) and x.get("type")}),
        }
    if extraction_state!="VERIFIER_CONFIRMED":
        work["knowledge_extraction"]={
            "state":extraction_state,
            "declared":extraction.get("outcome") or "EVIDENCE_PENDING",
            "errors":_error_types(extraction_errors),
        }

    all_items=[*gates,*levels,*c2s,*s2c,*lenses,*hypotheses,*artifacts,*adversarial,*machine_findings,*blocking_findings]
    counts={
        "rules":len(rules),"checks":sum(len(row.get("checks") or []) for row in rules),
        "gates":len(gates),"review_levels":len(levels),"code_to_standards":len(c2s),"standards_to_code":len(s2c),
        "gap_lenses":len(lenses),"gap_hypotheses":len(hypotheses),"artifact_requests":len(artifacts),"adversarial_cases":len(adversarial),"machine_findings":len(machine_findings),"blocking_findings":len(blocking_findings),
        "performance_review":1 if "performance_review" in work else 0,
        "resolution_review_required":sum(1 for row in rules if row.get("state")=="RESOLUTION_REVIEW_REQUIRED")
          +sum(1 for row in rules for check in row.get("checks") or [] if isinstance(check,dict) and check.get("state")=="RESOLUTION_REVIEW_REQUIRED")
          +sum(1 for row in all_items if isinstance(row,dict) and row.get("state")=="RESOLUTION_REVIEW_REQUIRED")
          +(1 if extraction_state=="RESOLUTION_REVIEW_REQUIRED" else 0),
    }
    # Proof metadata is grouped once by required-role set instead of repeated on
    # every rule/check row. Fully unresolved architecture rows live only here;
    # rejected/terminal declarations stay in the ordinary queue for review detail.
    proof_groups={}
    for row in ledger.get("rules") or []:
        if not isinstance(row,dict):continue
        policy=row.get("proof_policy") if isinstance(row.get("proof_policy"),dict) else {}
        if policy.get("claim_class")!="ARCHITECTURE_SEMANTIC":continue
        roles=tuple(policy.get("required_roles") or [])
        rstate,_=_state(row,verdicts,blockers,"rule",row.get("id"))
        if rstate!="VERIFIER_CONFIRMED" and row.get("claim_id"):
            proof_groups.setdefault(roles,set()).add(row["claim_id"])
        for check in row.get("checks") or []:
            if not isinstance(check,dict):continue
            cstate,_=_state(check,verdicts,blockers,"check",check.get("id"),row.get("id"))
            if cstate!="VERIFIER_CONFIRMED" and check.get("claim_id"):
                proof_groups.setdefault(roles,set()).add(check["claim_id"])
    for row in ledger.get("machine_findings") or []:
        if not isinstance(row,dict):continue
        policy=row.get("proof_policy") if isinstance(row.get("proof_policy"),dict) else {}
        state,_=_state(row,verdicts,blockers,"machine_finding",row.get("id"))
        if state!="VERIFIER_CONFIRMED" and row.get("claim_id"):
            proof_groups.setdefault(tuple(policy.get("required_roles") or []),set()).add(row["claim_id"])
    for row in ledger.get("review_levels") or []:
        if not isinstance(row,dict):continue
        policy=row.get("proof_policy") if isinstance(row.get("proof_policy"),dict) else {}
        if policy.get("claim_class")!="ARCHITECTURE_SEMANTIC":continue
        state,_=_state(row,verdicts,blockers,"review_level",row.get("id"))
        if state!="VERIFIER_CONFIRMED" and row.get("claim_id"):
            proof_groups.setdefault(tuple(policy.get("required_roles") or []),set()).add(row["claim_id"])
    proof_requirements=[
        {"roles":list(roles),"claims":sorted(claims)}
        for roles,claims in sorted(proof_groups.items(),key=lambda x:x[0])
        if claims
    ]

    requirements=ledger.get("requirements") or {}; routing=ledger.get("routing") or {}
    compact_implementation_readiness=None
    if isinstance(implementation_readiness,dict):
        compact_implementation_readiness={
            "readiness_outcome":implementation_readiness.get("readiness_outcome"),
            "required":implementation_readiness.get("required"),
        }
        readiness_error_types=sorted({str(x.get("type")) for x in implementation_readiness.get("errors") or [] if isinstance(x,dict) and x.get("type")})
        if readiness_error_types:compact_implementation_readiness["errors"]=readiness_error_types
    result={
        "schema_version":3,"projection":"VALIDATION_WORK_QUEUE","ledger_sha256":ledger_sha256,
        "routing":{k:routing.get(k) for k in ("surface","risk","mode") if routing.get(k) is not None},
        "requirements":{k:requirements.get(k) for k in ("required","technical_design_allowed","gate_outcome") if k in requirements},
        "implementation_readiness":compact_implementation_readiness,
        "active_profiles":_compact_profiles(ledger.get("active_profiles")),"work_queue":work,"counts":counts,"verifier":verifier,
        "policy":{"declared_status_is_not_proof":True,"omit_only_on_explicit_accepted_verdict":True,"global_verifier_error_is_fail_closed":True,"system_status_requires_reverification":True,"registry_owner":"RULES/rule_registry.json is read by executable tools, not loaded wholesale into normal LLM context."},
    }
    if proof_requirements:result["proof_requirements"]=proof_requirements
    proof=[]; intent=[]; seen_proof=set(); seen_intent=set()
    for row in report_errors:
        if not isinstance(row,dict):continue
        typ=str(row.get("type") or "")
        if typ.startswith(("INDEPENDENT_","EXACT_SOURCE_","PLATFORM_RUNTIME_","PROOF_")):
            item={k:row.get(k) for k in ("type","claim_id","scope","id","rule") if row.get(k) is not None}
            key=json.dumps(item,ensure_ascii=False,sort_keys=True)
            if key not in seen_proof:seen_proof.add(key);proof.append(item)
        if typ.startswith(("IMPLEMENTATION_INTENT_","MATERIAL_ARTIFACT_","BSL_ROUTINE_","MSLX_ACTION_","CLEVERENCE_FIELD_","CLEVERENCE_MAPPING_","NEW_EXPORT_","NEW_FUNCTION_","CROSS_SYSTEM_ONE_SIDED_")):
            item={k:row.get(k) for k in ("type","artifact","side","kind","identity","normalized_identity","spellings","occurrences","fragment","semantic_identity","field","target_kind","expected","actual","expected_action") if row.get(k) is not None}
            key=json.dumps(item,ensure_ascii=False,sort_keys=True)
            if key not in seen_intent:seen_intent.add(key);intent.append(item)
    if blockers:
        result["global_blocker"]={"state":"VERIFIER_BLOCKED","errors":_error_types(blockers),"count":len(blockers)}
    if proof:result["proof_blockers"]=proof
    if intent:result["intent_blockers"]=intent
    return result


def project_file(path:Path)->dict:
    raw=path.read_bytes(); ledger=json.loads(raw.decode("utf-8-sig"))
    return build_work_queue(ledger,hashlib.sha256(raw).hexdigest())


def main()->int:
    ap=argparse.ArgumentParser(description="Print unresolved and verifier-rejected validation obligations from a full ledger.")
    ap.add_argument("--ledger",required=True); ap.add_argument("--output")
    args=ap.parse_args(); result=project_file(Path(args.ledger)); out=json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n"
    if args.output:Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(out,end=""); return 0


if __name__=="__main__":
    raise SystemExit(main())
