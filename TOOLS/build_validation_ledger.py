#!/usr/bin/env python3
"""Create an evidence ledger skeleton from a registry-based review plan.

The generated ledger is intentionally unresolved. It prevents silent omission; it never proves PASS.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, sys, hashlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rule_registry import ROOT, load_registry, rule_map, proof_policy_for
from build_review_plan import build_plan
from proof_contract import SCHEMA_VERSION as PROOF_CONTRACT_SCHEMA_VERSION, rule_claim_id, check_claim_id, machine_finding_claim_id
from machine_receipts import verify_receipt
from query_literal_escape_contract import ANALYZER_PROPERTY, ANALYZER_TOOL, FINDING_TYPE as QUERY_ESCAPE_FINDING_TYPE, blocking_row as query_escape_blocking_row
from implementation_intent import build_skeleton as build_intent_skeleton
from performance_review import build_ledger_skeleton as build_performance_review_ledger

LEVELS=["L1_CONSTRUCTION","L2_ROUTINE","L3_MODULE","L4_METADATA_OBJECT","L5_CROSS_OBJECT","L6_BUSINESS_RUNTIME"]


def _unresolved_check(check,rule_id):
    return {"id":check["id"],"claim_id":check_claim_id(rule_id,check["id"]),"question":check["question"],"status":"EVIDENCE_REQUIRED","evidence":[],"reason":"","kind":check.get("kind","PROFILE")}


def _canonical_sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def machine_finding_mapping(registry):
    mapping={}
    for rule in registry.get("rules") or []:
        for check in rule.get("checks") or []:
            for finding_type in check.get("machine_finding_types") or []:
                if finding_type in mapping:
                    raise ValueError(f"machine finding type has multiple canonical owners: {finding_type}")
                mapping[finding_type]=(rule["id"],check["id"],proof_policy_for(rule,registry))
    return mapping


def bind_machine_findings(ledger,plan,report_id,artifact_logical_path,registry=None):
    """Create exact finding obligations from one replay-verified machine report.

    This does not prove or close a finding.  It snapshots the verified analyzer
    output into a claim bound to the current candidate, parent canonical check and
    exact finding bytes.  Release verification independently replays the receipt.
    """
    registry=registry or load_registry()
    reports=[row for row in ledger.get("machine_reports") or [] if isinstance(row,dict) and row.get("id")==report_id]
    if len(reports)!=1:
        raise ValueError(f"exactly one machine report is required for {report_id}")
    report_row=reports[0]
    receipt_ref=report_row.get("receipt_ref") or report_row.get("ref")
    verification=verify_receipt(receipt_ref,replay=True)
    if verification.get("integrity_result")!="PASS" or verification.get("derived_result")!="PASS":
        raise ValueError(f"machine report receipt is not verifier-PASS: {report_id}")
    receipt=verification.get("receipt") or {}
    output=receipt.get("output") or {}
    stdout_path=Path(output.get("stdout_path") or "")
    if not stdout_path.is_file():
        raise ValueError(f"machine report stdout missing: {report_id}")
    raw=stdout_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=output.get("stdout_sha256"):
        raise ValueError(f"machine report stdout hash drift: {report_id}")
    try:
        payload=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"machine report stdout is not JSON: {report_id}: {exc}") from exc

    logical=str(artifact_logical_path or "").replace("\\","/")
    candidates=[
        row for row in plan.get("candidate_artifacts") or []
        if isinstance(row,dict) and str(row.get("logical_path") or "").replace("\\","/")==logical
    ]
    if len(candidates)!=1:
        raise ValueError(f"exact candidate artifact is required for machine finding binding: {logical}")
    candidate=candidates[0]; candidate_sha=str(candidate.get("sha256") or "").lower()
    input_shas={str(row.get("sha256") or "").lower() for row in receipt.get("inputs") or [] if isinstance(row,dict)}
    if not candidate_sha or candidate_sha not in input_shas:
        raise ValueError(f"machine receipt is not bound to candidate sha256: {logical}")

    mapping=machine_finding_mapping(registry)
    created=[]
    for finding in payload.get("findings") or []:
        if not isinstance(finding,dict):
            continue
        finding_type=finding.get("type")
        owner=mapping.get(finding_type)
        if not owner:
            continue
        rule_id,check_id,policy=owner
        finding_sha=_canonical_sha(finding)
        claim_id=machine_finding_claim_id(
            rule_id,check_id,finding_type,logical,candidate_sha,finding_sha
        )
        row={
            "id":claim_id,
            "claim_id":claim_id,
            "rule_id":rule_id,
            "check_id":check_id,
            "finding_type":finding_type,
            "artifact":logical,
            "candidate_sha256":candidate_sha,
            "report_id":report_id,
            "report_output_sha256":output.get("stdout_sha256"),
            "finding_sha256":finding_sha,
            "status":"EVIDENCE_REQUIRED",
            "reason":"",
            "evidence":[],
            "proof_policy":policy,
        }
        if any(existing.get("id")==claim_id for existing in ledger.get("machine_findings") or [] if isinstance(existing,dict)):
            raise ValueError(f"duplicate machine finding obligation: {claim_id}")
        ledger.setdefault("machine_findings",[]).append(row);created.append(row)
    return created


def bind_query_literal_escape_findings(ledger,plan,report_id,artifact_logical_path):
    """Bind verified QUERY literal-escape findings into canonical blocking_findings."""
    reports=[row for row in ledger.get("machine_reports") or [] if isinstance(row,dict) and row.get("id")==report_id]
    if len(reports)!=1:
        raise ValueError(f"exactly one machine report is required for {report_id}")
    report_row=reports[0]
    receipt_ref=report_row.get("receipt_ref") or report_row.get("ref")
    verification=verify_receipt(receipt_ref,replay=True)
    if verification.get("integrity_result")!="PASS" or verification.get("derived_result")!="PASS":
        raise ValueError(f"machine report receipt is not verifier-PASS: {report_id}")
    receipt=verification.get("receipt") or {}
    if receipt.get("tool")!=ANALYZER_TOOL or ANALYZER_PROPERTY not in (receipt.get("verified_properties") or []):
        raise ValueError(f"machine report does not prove {ANALYZER_PROPERTY}: {report_id}")

    logical=str(artifact_logical_path or "").replace("\\","/")
    candidates=[
        row for row in plan.get("candidate_artifacts") or []
        if isinstance(row,dict) and str(row.get("logical_path") or "").replace("\\","/")==logical
    ]
    if len(candidates)!=1:
        raise ValueError(f"exact candidate artifact is required for query escape binding: {logical}")
    candidate=candidates[0]; candidate_sha=str(candidate.get("sha256") or "").lower()
    origin=Path(candidate.get("origin") or "")
    input_rows=[
        row for row in receipt.get("inputs") or []
        if isinstance(row,dict)
        and str(row.get("sha256") or "").lower()==candidate_sha
        and Path(row.get("path") or "").resolve(strict=False)==origin.resolve(strict=False)
    ]
    if len(input_rows)!=1:
        raise ValueError(f"machine receipt is not bound to exact candidate origin/sha256: {logical}")

    output=receipt.get("output") or {}; stdout_path=Path(output.get("stdout_path") or "")
    if not stdout_path.is_file():
        raise ValueError(f"machine report stdout missing: {report_id}")
    raw=stdout_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=output.get("stdout_sha256"):
        raise ValueError(f"machine report stdout hash drift: {report_id}")
    try:
        payload=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"machine report stdout is not JSON: {report_id}: {exc}") from exc

    created=[]
    for finding in payload.get("findings") or []:
        if not isinstance(finding,dict) or finding.get("type")!=QUERY_ESCAPE_FINDING_TYPE:
            continue
        row=query_escape_blocking_row(logical,candidate_sha,report_id,output.get("stdout_sha256"),finding)
        existing=next((x for x in ledger.get("blocking_findings") or [] if isinstance(x,dict) and x.get("id")==row["id"]),None)
        if existing:
            if existing!=row:
                raise ValueError(f"query escape blocking finding identity drift: {row['id']}")
            continue
        ledger.setdefault("blocking_findings",[]).append(row); created.append(row)
    return created


def _artifact_requests(plan):
    state=plan.get("artifact_delivery_state") or {}; routing=plan.get("routing") or {}; model=plan.get("artifact_model") or {}
    if routing.get("mode")=="ANALYSIS_ONLY" or state.get("exact_delivery_allowed") is not False:return []
    # A 1C source dump/patch can itself be the exact changed-byte delivery surface.
    # The hard request is for unresolved/mixed/runtime-only artifact roles or a
    # Cleverence configuration subset whose target deployment shape is not proven.
    if model.get("family")=="ONEC" and model.get("role")=="SOURCE_DUMP_OR_PATCH":return []
    return [{
        "id":"ARTIFACT_ROLE_AND_DELIVERY",
        "status":"REQUEST_REQUIRED",
        "blocking":True,
        "artifacts":["authoritative deployed/configuration baseline or exact delivery artifact that resolves the current artifact role/layout"],
        "claim":"Exact implementation delivery cannot be proven from the current artifact classification/layout.",
        "request_text":"Provide the smallest authoritative baseline/configuration export that proves the target delivery shape. After it is available, rebuild the review plan; do not merely relabel this request as resolved against the old plan.",
        "reason":f"artifact role={model.get('role')}; layout={model.get('layout')}; blockers={state.get('blockers',[])}"
    }]


def build_ledger(plan:dict, registry:dict|None=None)->dict:
    registry=registry or load_registry(); rules=rule_map(registry)
    rule_rows=[]
    for route in plan.get("rules",[]):
        rule=rules[route["id"]]
        if not route.get("active") and rule.get("tier",1)>0:
            continue
        rule_rows.append({
            "id":rule["id"],"claim_id":rule_claim_id(rule["id"]),"tier":rule["tier"],"profile":rule.get("profile"),"activation_status":route.get("activation_status"),
            "detected_by":route.get("detected_by",[]),"status":"EVIDENCE_REQUIRED","reason":"","evidence":[],
            "required_evidence_modes":rule.get("evidence_modes",[]),
            "proof_policy":proof_policy_for(rule,registry),
            "checks":[{**_unresolved_check(c,rule["id"]),"proof_policy":proof_policy_for(rule,registry)} for c in rule.get("checks",[])],
        })
    gates=[]
    req=plan.get("requirements",{})
    req_ready=req.get("gate_result")=="PASS" and req.get("gate_outcome") in {"REQUIREMENTS_READY","REQUIREMENTS_READY_WITH_ASSUMPTIONS"}
    for row in plan.get("gate_plan",[]):
        if row["status"]=="NOT_APPLICABLE":
            gates.append({"id":row["gate"],"status":"NOT_APPLICABLE","reason":row.get("reason",""),"evidence":[],"resolution_source":"SYSTEM","resolution_basis":"PLANNED_NOT_APPLICABLE"})
        elif row["gate"]=="REQUIREMENTS_AND_SCOPE" and (req_ready or not req.get("required")):
            reason="requirements contract gate passed" if req_ready else "R0/analysis task does not require the full requirements contract"
            evidence=[{"kind":"SEMANTIC","ref":f"requirements:{req.get('sha256')}:{req.get('gate_outcome')}"}] if req_ready else [{"kind":"SEMANTIC","ref":"requirements:R0-or-analysis routing"}]
            gates.append({"id":row["gate"],"status":"PASS","reason":reason,"evidence":evidence,"resolution_source":"SYSTEM","resolution_basis":"REQUIREMENTS_GATE"})
        elif row["gate"]=="PROMOTION":
            gates.append({"id":row["gate"],"status":"NOT_APPLICABLE","reason":"promotion is outside pre-delivery proof unless explicitly requested","evidence":[],"resolution_source":"SYSTEM","resolution_basis":"PRE_DELIVERY_PROMOTION"})
        else:
            gates.append({"id":row["gate"],"status":"EVIDENCE_REQUIRED","reason":"","evidence":[]})
    discovery=registry.get("gap_discovery_contract",{})
    return {
        "schema_version":5,
        "proof_contract":{"schema_version":PROOF_CONTRACT_SCHEMA_VERSION,"rule_check_claim_binding":True,"machine_finding_claim_binding":True,"attach_only_is_supporting_only":True,"source_primary_requires_verifier_provenance":True,"semantic_primary_is_policy_controlled":True,"independent_review_is_verifier_owned":True},
        "resolution_contract":{"schema_version":1,"declared_status_is_not_proof":True,"work_queue_requires_release_verifier":True,"system_resolutions_are_explicit":True},
        "release_intake":plan.get("release_intake"),
        "registry":plan.get("registry"),
        "routing":plan.get("routing"),
        "artifact_model":plan.get("artifact_model"),
        "artifact_delivery_state":plan.get("artifact_delivery_state"),
        "artifact_inventory":plan.get("artifact_inventory"),
        "candidate_artifacts":plan.get("candidate_artifacts",[]),
        "baseline":plan.get("baseline"),
        "project_context":plan.get("project_context",{}),
        "requirements":plan.get("requirements",{}),
        "active_profiles":plan.get("active_profiles",[]),
        "context_load_plan":plan.get("context_load_plan",{}),
        "gates":gates,
        "rules":rule_rows,
        "evidence_registry":[],
        "receipt_evidence_provenance":[],
        "independent_reviews":[],
        "implementation_intent_map":build_intent_skeleton(plan),
        "performance_review":build_performance_review_ledger(plan),
        "artifact_requests":_artifact_requests(plan),
        "evidence_reuse":{"reused_ids":[],"invalidated_ids":[],"changed_dependencies":[]},
        "review_levels":[{
            "id":x,"claim_id":f"REVIEW_LEVEL:{x}","status":"EVIDENCE_REQUIRED","reason":"","evidence":[],
            "proof_policy":((registry.get("proof_policy_contract") or {}).get("review_levels") or {}).get(x)
        } for x in LEVELS],
        "code_to_standards":[{
            "id":"C2S:CHANGESET","origin":"SOURCE_CONSTRUCTIONS","status":"EVIDENCE_REQUIRED","reason":"",
            "source_anchors":[x.get("logical_path") for x in plan.get("candidate_artifacts",[]) if x.get("logical_path")],
            "rule_ids":[],"evidence":[]
        }],
        "standards_to_code":[{
            "id":f"S2C:{row['id']}","origin":"REGISTRY_EXPANSION","rule_id":row["id"],
            "check_ids":[check["id"] for check in row.get("checks",[])],
            "status":"EVIDENCE_REQUIRED","reason":"","evidence":[]
        } for row in rule_rows],
        "adversarial_cases":[],
        "gap_discovery":{
            "method":"KNOWLEDGE/GAP_DISCOVERY_PROTOCOL.md",
            "lenses":[{"id":lens,"status":"EVIDENCE_REQUIRED","reason":"","evidence":[]} for lens in discovery.get("lenses",[])],
            "hypotheses":[],
        },
        "machine_reports":[],
        "machine_findings":[],
        "runtime_cases":[],
        "knowledge_extraction":{"outcome":"EVIDENCE_PENDING","reason":"","project_context_updates":[],"items":[]},
        "blocking_findings":[],
        "completion":{"status":"COVERAGE_GAP","release_outcome":"BLOCKED","note":"Generated skeleton is never PASS. Fill evidence and run TOOLS/release_gate.py. If artifact role/layout changes, rebuild the plan and ledger rather than editing intake dependencies."}
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("paths",nargs="*")
    ap.add_argument("--plan")
    ap.add_argument("--baseline")
    ap.add_argument("--analysis-only",action="store_true")
    ap.add_argument("--surface",choices=("ANALYSIS_ONLY","ONEC_ONLY","CLEVERENCE_ONLY","CROSS_SYSTEM"))
    ap.add_argument("--risk",choices=("R0_LOCAL","R1_CONTRACT","R2_STATEFUL_RUNTIME","R3_CROSS_SYSTEM"))
    ap.add_argument("--project-context")
    ap.add_argument("--requirements-contract")
    ap.add_argument("--output")
    ap.add_argument("--summary",action="store_true",help="Print compact validation work queue instead of the full ledger")
    ap.add_argument("--full-json",action="store_true",help="Print full ledger JSON even when --output is used")
    a=ap.parse_args()
    if a.plan:
        plan=json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    else:
        if not a.paths:ap.error("paths or --plan required")
        plan=build_plan(a.paths,a.baseline,a.analysis_only,a.surface,a.risk,a.project_context,a.requirements_contract)
    ledger=build_ledger(plan)
    out=json.dumps(ledger,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    if a.summary or (a.output and not a.full_json):
        from validation_work_queue import build_work_queue
        shown=build_work_queue(ledger,hashlib.sha256(out.encode("utf-8")).hexdigest())
        print(json.dumps(shown,ensure_ascii=False,separators=(",",":")))
    else:
        print(out,end="")

if __name__=="__main__":main()
