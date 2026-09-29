#!/usr/bin/env python3
"""Fail-closed release gate for a completed validation ledger.

This gate validates proof integrity, not only status labels. A clean deterministic
report is never semantic coverage. MACHINE/RUNTIME evidence must point to named
reports/cases; reverse standards coverage must be independently present; exact
baseline/routing/context dependencies may not drift between plan and ledger.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, re, sys, zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from rule_registry import ROOT, load_registry, rule_map, RISK_RANK, proof_policy_for
from release_gate_hardening import validate_trust_boundary, is_substantive_reason
from release_intake import validate_plan_recomputation, load_intake
from release_evidence_receipts import validate_machine_reports as verify_machine_reports, validate_runtime_cases as verify_runtime_cases, validate_evidence_property
from proof_contract import rule_claim_id, check_claim_id, machine_finding_claim_id, validate_row_claim_id, validate_obligation_evidence
from semantic_proof_verifier import validate_independent_reviews, validate_policy_snapshot, validate_claim_policy
from implementation_intent import validate_intent_map
from query_literal_escape_contract import ANALYZER_PROPERTY as QUERY_ESCAPE_PROPERTY, ANALYZER_TOOL as QUERY_ESCAPE_TOOL, FINDING_TYPE as QUERY_ESCAPE_FINDING_TYPE, blocking_row as query_escape_blocking_row
from performance_review import validate as validate_performance_review

BSL_BARE_SYMBOL_TOOL="TOOLS/analyze_onec_bsl.py"
BSL_BARE_SYMBOL_PROPERTY="STATIC:ONEC_BSL_BARE_SYMBOL"

ALLOWED_EVIDENCE_KINDS={"MACHINE","SOURCE_REQUIRED","SEMANTIC","RUNTIME"}
REVIEW_LEVELS=["L1_CONSTRUCTION","L2_ROUTINE","L3_MODULE","L4_METADATA_OBJECT","L5_CROSS_OBJECT","L6_BUSINESS_RUNTIME"]


def _has_text(value):return isinstance(value,str) and bool(value.strip())
def _evidence_kinds(items):return {str(x.get("kind","")).upper() for x in items if isinstance(x,dict)}
def _has_concrete_evidence(items):return bool(items) and all(isinstance(x,dict) and _has_text(x.get('kind')) and _has_text(x.get('ref')) for x in items)
def _canon(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _artifact_fingerprint(value):return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


SOURCE_PROVENANCE_VERIFIER_ID="release_gate_core.source_identity"
SOURCE_PROVENANCE_VERSION=1
RECEIPT_PROVENANCE_VERIFIER_ID="release_gate_core.receipt_provenance"
RECEIPT_PROVENANCE_VERSION=1
KNOWN_RECEIPT_PREDICATE_VERIFIERS=set()
RECEIPT_TRUST_FIELDS={
    "receipt_id","receipt_ref","receipt_sha256","receipt_schema_version","receipt_provenance_id",
    "verification_mode","proof_role","supporting_only","source_sha256","source_fingerprint"
}


def _norm_archive_entry(value):
    parts=[]
    for raw in str(value or "").replace("\\","/").split("/"):
        if raw in {"","."}:continue
        if raw=="..":
            if not parts:return None
            parts.pop();continue
        parts.append(raw)
    return "/".join(parts)


def _canonical_source_ref(ref):
    if not _has_text(ref):return None
    text=str(ref)
    if "!/" in text:
        archive,entry=text.split("!/",1); norm=_norm_archive_entry(entry)
        if norm is None:return None
        try:outer=str(Path(archive).resolve(strict=False))
        except OSError:outer=str(Path(archive).absolute())
        return f"{outer}!/{norm}"
    try:return str(Path(text).resolve(strict=False))
    except OSError:return str(Path(text).absolute())


def _receipt_binding_key(kind,ref,claim_id):
    material={"kind":str(kind or "").upper(),"ref":ref,"claim_id":claim_id}
    return hashlib.sha256(_canon(material).encode("utf-8")).hexdigest()


def _plan_source_index(plan):
    index={}
    def add(ref,sha,kind="CANDIDATE"):
        canon=_canonical_source_ref(ref)
        if canon and _has_text(sha):index[canon]={"sha256":str(sha).lower(),"kind":kind}
    for row in plan.get("candidate_artifacts") or []:
        if isinstance(row,dict):
            add(row.get("origin"),row.get("sha256"),"CANDIDATE")
            add(row.get("portable_origin"),row.get("sha256"),"CANDIDATE")
    baseline=plan.get("baseline") or {}
    if isinstance(baseline,dict) and baseline.get("kind")=="FILE":add(baseline.get("path"),baseline.get("sha256"),"BASELINE")
    for key,label in (("project_context","PROJECT_CONTEXT"),("requirements","REQUIREMENTS")):
        dep=plan.get(key) or {}
        if isinstance(dep,dict):add(dep.get("path"),dep.get("sha256"),label)
    return index


def _receipt_marker_present(item):
    if not isinstance(item,dict):return False
    receipt_specific={"receipt_id","receipt_ref","receipt_sha256","receipt_schema_version","receipt_provenance_id"}
    if any(key in item for key in receipt_specific):return True
    if str(item.get("verification_mode") or "").upper() in {"ATTACH_ONLY","RULE_OWNED_PREDICATE"}:return True
    if str(item.get("proof_role") or "").upper()=="SUPPORTING_ONLY" and _has_text(item.get("source_sha256")):return True
    return False


RESOLUTION_VERIFIER_ID="release_gate_core"
RESOLUTION_VERIFIER_VERSION=1
RESOLUTION_TERMINAL={"PASS","NOT_APPLICABLE"}
RESOLUTION_HYPOTHESIS_TERMINAL={"COVERED_BY_EXISTING_RULE","DISPROVED","NOT_MATERIAL","FIXED_REVALIDATED","PASS","NOT_APPLICABLE"}
RESOLUTION_ARTIFACT_TERMINAL={"PROVIDED","RESOLVED_NOT_NEEDED","NOT_APPLICABLE"}
RESOLUTION_EXTRACTION_TERMINAL={"PROMOTED","PROJECT_ONLY","NO_REUSABLE_KNOWLEDGE"}


def _resolution_error_matches(error,scope,rid,rule_id=None,path_prefix=None):
    """Strictly bind one release error to one ledger identity; unknowns remain global."""
    escope=str(error.get("scope") or "")
    et=str(error.get("type") or "")
    eid=error.get("id")
    erule=error.get("rule")
    if path_prefix and escope.startswith(path_prefix):
        return True
    if scope=="rule":
        if escope=="rule" and eid==rid:return True
        if eid==rid and et.startswith(("RULE_","REQUIRED_RULE_","ROUTED_RULE_","NA_REBUTTAL_","PROOF_","EVIDENCE_","PRIMARY_","CLAIM_","INDEPENDENT_","EXACT_SOURCE_","PLATFORM_RUNTIME_")):return True
        if erule==rid and et.startswith(("NA_RULE_","RULE_","STANDARDS_TO_CODE_")):return True
    elif scope=="check":
        if escope=="check" and eid==f"{rule_id}:{rid}":return True
        if escope==f"check:{rule_id}" and eid==rid:return True
        if erule==rule_id and eid==rid:return True
        if eid==f"{rule_id}:{rid}" and et.startswith(("PROOF_","INDEPENDENT_","EXACT_SOURCE_","PLATFORM_RUNTIME_")):return True
    elif scope=="gate":
        if eid==rid and (escope=="gate" or et.startswith(("GATE_","UNKNOWN_GATE_","PASS_","EVIDENCE_"))):return True
    elif scope=="review_level":
        if eid==rid and (escope=="review_level" or "REVIEW_LEVEL" in et or et.startswith(("PASS_","EVIDENCE_"))):return True
    elif scope=="code_to_standards":
        if eid==rid and (escope=="code_to_standards" or et.startswith(("CODE_TO_STANDARDS","PASS_","EVIDENCE_","NA_"))):return True
    elif scope=="standards_to_code":
        if (erule==rid or (escope=="standards_to_code" and eid==rid)) and et.startswith(("STANDARDS_TO_CODE","NA_","PASS_","EVIDENCE_")):return True
    elif scope=="gap_lens":
        if eid==rid and ("GAP_DISCOVERY_LENS" in et or escope=="gap_discovery_lens" or et.startswith(("PASS_","EVIDENCE_","NA_"))):return True
    elif scope=="hypothesis":
        if eid==rid and et.startswith("GAP_HYPOTHESIS"):return True
    elif scope=="artifact":
        if eid==rid and ("ARTIFACT" in et or escope=="artifact_request" or et.startswith(("PASS_","EVIDENCE_"))):return True
    elif scope=="adversarial":
        if eid==rid and ("ADVERSARIAL" in et or escope=="adversarial_case" or et.startswith(("PASS_","EVIDENCE_","NA_"))):return True
    elif scope=="machine_finding":
        if eid==rid and (escope=="machine_finding" or et.startswith(("MACHINE_FINDING_","PROOF_","INDEPENDENT_","EXACT_SOURCE_","PRIMARY_","EVIDENCE_","ATTACH_ONLY_"))):return True
    elif scope=="knowledge_extraction":
        if et.startswith("KNOWLEDGE_EXTRACTION_"):return True
    return False


def _resolution_protocol(ledger,errors):
    """Emit explicit verifier-owned row verdicts and leave unclaimed errors global."""
    verdicts=[]; claimed=set()

    def add(scope,row,rid,terminal,rule_id=None,path_prefix=None,claim_id=None,status_key="status"):
        if not isinstance(row,dict) or not rid:return
        disposition=row.get(status_key)
        linked=[]
        for index,error in enumerate(errors):
            if _resolution_error_matches(error,scope,rid,rule_id,path_prefix):
                claimed.add(index)
                linked.append({
                    "index":index,
                    "type":error.get("type"),
                    "scope":error.get("scope"),
                    "id":error.get("id"),
                    "rule":error.get("rule"),
                })
        accepted=disposition in terminal and not linked
        verdicts.append({
            "scope":scope,
            "id":rid,
            "rule_id":rule_id,
            "claim_id":claim_id if claim_id is not None else row.get("claim_id"),
            "disposition":disposition,
            "verdict":"ACCEPTED" if accepted else ("REJECTED" if linked else "UNRESOLVED"),
            "verifier":RESOLUTION_VERIFIER_ID,
            "version":RESOLUTION_VERIFIER_VERSION,
            "validator_id":f"{RESOLUTION_VERIFIER_ID}.{scope}",
            "errors":linked,
        })

    for i,row in enumerate(ledger.get("gates") or []):
        add("gate",row,row.get("id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.gates[{i}]")
    for i,row in enumerate(ledger.get("rules") or []):
        rid=row.get("id")
        add("rule",row,rid,RESOLUTION_TERMINAL,path_prefix=f"ledger.rules[{i}]")
        for j,check in enumerate(row.get("checks") or []):
            add("check",check,check.get("id"),RESOLUTION_TERMINAL,rule_id=rid,path_prefix=f"ledger.rules[{i}].checks[{j}]")
    for i,row in enumerate(ledger.get("review_levels") or []):
        add("review_level",row,row.get("id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.review_levels[{i}]")
    for i,row in enumerate(ledger.get("code_to_standards") or []):
        add("code_to_standards",row,row.get("id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.code_to_standards[{i}]")
    for i,row in enumerate(ledger.get("standards_to_code") or []):
        add("standards_to_code",row,row.get("rule_id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.standards_to_code[{i}]")
    discovery=ledger.get("gap_discovery") or {}
    for i,row in enumerate(discovery.get("lenses") or []):
        add("gap_lens",row,row.get("id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.gap_discovery.lenses[{i}]")
    for i,row in enumerate(discovery.get("hypotheses") or []):
        add("hypothesis",row,row.get("id"),RESOLUTION_HYPOTHESIS_TERMINAL,path_prefix=f"ledger.gap_discovery.hypotheses[{i}]")
    for i,row in enumerate(ledger.get("artifact_requests") or []):
        add("artifact",row,row.get("id"),RESOLUTION_ARTIFACT_TERMINAL,path_prefix=f"ledger.artifact_requests[{i}]")
    for i,row in enumerate(ledger.get("adversarial_cases") or []):
        add("adversarial",row,row.get("id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.adversarial_cases[{i}]")
    for i,row in enumerate(ledger.get("machine_findings") or []):
        add("machine_finding",row,row.get("id"),RESOLUTION_TERMINAL,path_prefix=f"ledger.machine_findings[{i}]")
    extraction=ledger.get("knowledge_extraction") or {}
    add("knowledge_extraction",extraction,"KNOWLEDGE_EXTRACTION",RESOLUTION_EXTRACTION_TERMINAL,status_key="outcome",path_prefix="ledger.knowledge_extraction")

    global_errors=[]
    for i,error in enumerate(errors):
        if i in claimed:continue
        item={"index":i,"type":error.get("type"),"scope":error.get("scope"),"id":error.get("id"),"rule":error.get("rule")}
        for key in ("claim_id","artifact","fragment","field","case_id","role"):
            if error.get(key) is not None:item[key]=error.get(key)
        global_errors.append(item)
    return {
        "status":"AVAILABLE",
        "verifier":RESOLUTION_VERIFIER_ID,
        "version":RESOLUTION_VERIFIER_VERSION,
        "verdicts":verdicts,
        "global_errors":global_errors,
        "rule":"Only an explicit ACCEPTED verdict for the exact current row identity can remove a terminal disposition from the validation work queue. Unclaimed/unknown errors are global blockers.",
    }


def _surface_set(surface):
    if surface in {None,'ANALYSIS_ONLY'}:return set()
    if surface=='ONEC_ONLY':return {'ONEC'}
    if surface=='CLEVERENCE_ONLY':return {'CLEVERENCE'}
    if surface=='CROSS_SYSTEM':return {'ONEC','CLEVERENCE'}
    return None


def _index_rows(rows, key, scope, errors):
    result={}
    for index,row in enumerate(rows or []):
        if not isinstance(row,dict):
            errors.append({'type':'ROW_NOT_OBJECT','scope':scope,'index':index}); continue
        rid=row.get(key)
        if not _has_text(rid):
            errors.append({'type':'ROW_WITHOUT_ID','scope':scope,'index':index,'key':key}); continue
        if rid in result:
            errors.append({'type':'DUPLICATE_ROW_ID','scope':scope,'id':rid}); continue
        result[rid]=row
    return result


def _validate_machine_reports(rows, errors):
    return verify_machine_reports(rows,errors)

def _validate_runtime_cases(rows, errors, pending_items, blocking, pending):
    return verify_runtime_cases(rows,errors,pending_items,blocking,pending)

def _verify_direct_source_provenance(item,plan,errors,scope,rid,index):
    provenance=item.get("source_provenance")
    ref=_canonical_source_ref(item.get("ref"))
    source_index=_plan_source_index(plan or {})
    expected=source_index.get(ref)
    ok=True
    if not isinstance(provenance,dict):
        errors.append({"type":"SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED","scope":scope,"id":rid,"index":index,"reason":"SOURCE_PROVENANCE_MISSING"})
        return False
    expected_fields={"type":"CURRENT_CORPUS","verifier":SOURCE_PROVENANCE_VERIFIER_ID,"version":SOURCE_PROVENANCE_VERSION}
    drift={key:{"expected":value,"actual":provenance.get(key)} for key,value in expected_fields.items() if provenance.get(key)!=value}
    if drift:
        errors.append({"type":"SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED","scope":scope,"id":rid,"index":index,"reason":"SOURCE_PROVENANCE_CONTRACT_DRIFT","fields":drift})
        ok=False
    if not expected:
        errors.append({"type":"SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED","scope":scope,"id":rid,"index":index,"reason":"SOURCE_NOT_IN_CURRENT_CORPUS","ref":item.get("ref")})
        return False
    declared=provenance.get("source_sha256")
    if declared!=expected["sha256"]:
        errors.append({"type":"SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED","scope":scope,"id":rid,"index":index,"reason":"SOURCE_PROVENANCE_HASH_MISMATCH","expected":expected["sha256"],"actual":declared})
        ok=False
    current=_current_origin_sha(ref)
    if current is None or current.lower()!=expected["sha256"]:
        errors.append({"type":"SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED","scope":scope,"id":rid,"index":index,"reason":"CURRENT_SOURCE_HASH_MISMATCH","expected":expected["sha256"],"actual":current})
        ok=False
    return ok


def _annotate_evidence_provenance(item,plan,receipt_provenance,errors,scope,rid,index,expected_claim_id):
    annotated=dict(item)
    kind=str(item.get("kind","")).upper()
    key=(kind,item.get("ref"),item.get("claim_id"))
    provenance=(receipt_provenance or {}).get("by_key",{}).get(key)
    if provenance:
        annotated["_verifier_proof_role"]="SUPPORTING_ONLY"
        annotated["_verifier_receipt_predicate_confirmed"]=False
        if provenance.get("_verified") is not True:
            errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_INVALID","scope":scope,"id":rid,"index":index,"claim_id":expected_claim_id,"provenance_id":provenance.get("id"),"details":provenance.get("_verification_errors") or []})
        expected_fields={
            "receipt_id":provenance.get("receipt_id"),
            "receipt_ref":provenance.get("receipt_ref"),
            "receipt_sha256":provenance.get("receipt_sha256"),
            "receipt_schema_version":provenance.get("receipt_schema_version"),
            "receipt_provenance_id":provenance.get("id"),
            "verification_mode":"ATTACH_ONLY",
            "proof_role":"SUPPORTING_ONLY",
            "supporting_only":True,
            "source_sha256":provenance.get("source_sha256"),
        }
        missing=[field for field in expected_fields if field not in item]
        if missing:
            errors.append({"type":"RECEIPT_EVIDENCE_TRUST_FIELDS_MISSING","scope":scope,"id":rid,"index":index,"claim_id":expected_claim_id,"fields":missing,"provenance_id":provenance.get("id")})
        drift={field:{"expected":value,"actual":item.get(field)} for field,value in expected_fields.items() if field in item and item.get(field)!=value}
        fingerprint=item.get("source_fingerprint")
        expected_fingerprint={"algorithm":"SHA-256","sha256":provenance.get("source_sha256"),"type":(provenance.get("source_identity") or {}).get("type")}
        if not isinstance(fingerprint,dict):
            if "source_fingerprint" not in missing:missing.append("source_fingerprint")
            errors.append({"type":"RECEIPT_EVIDENCE_SOURCE_FINGERPRINT_MISSING","scope":scope,"id":rid,"index":index,"claim_id":expected_claim_id,"provenance_id":provenance.get("id")})
        elif fingerprint!=expected_fingerprint:
            drift["source_fingerprint"]={"expected":expected_fingerprint,"actual":fingerprint}
        if drift:
            errors.append({"type":"RECEIPT_EVIDENCE_TRUST_FIELD_DRIFT","scope":scope,"id":rid,"index":index,"claim_id":expected_claim_id,"fields":drift,"provenance_id":provenance.get("id")})
        return annotated

    if _receipt_marker_present(item):
        annotated["_verifier_proof_role"]="SUPPORTING_ONLY"
        annotated["_verifier_receipt_predicate_confirmed"]=False
        errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_MISSING","scope":scope,"id":rid,"index":index,"claim_id":expected_claim_id})
        return annotated

    if kind=="SOURCE_REQUIRED" and expected_claim_id:
        if _verify_direct_source_provenance(item,plan,errors,scope,rid,index):
            annotated["_verifier_proof_role"]="PRIMARY_VERIFIED_SOURCE"
        else:
            annotated["_verifier_proof_role"]="UNVERIFIED"
    return annotated


def _validate_evidence(items, errors, scope, rid, machine_reports=None, runtime_cases=None, required=True, expected_claim_id=None, allowed_kinds=None, require_primary=False, plan=None, receipt_provenance=None, proof_policy=None):
    if not items:
        if required:errors.append({'type':'PASS_WITHOUT_EVIDENCE','scope':scope,'id':rid})
        return []
    if not _has_concrete_evidence(items):
        errors.append({'type':'EVIDENCE_NOT_CONCRETE','scope':scope,'id':rid}); return []
    verified_items=[]
    for index,item in enumerate(items):
        if not isinstance(item,dict):
            continue
        kind=str(item.get('kind','')).upper()
        if kind not in ALLOWED_EVIDENCE_KINDS:
            errors.append({'type':'UNKNOWN_EVIDENCE_KIND','scope':scope,'id':rid,'index':index,'kind':kind}); continue
        annotated=_annotate_evidence_provenance(item,plan,receipt_provenance,errors,scope,rid,index,expected_claim_id)
        if kind in {'MACHINE','RUNTIME'}:
            confirmed=validate_evidence_property(item,scope,rid,machine_reports,runtime_cases,errors,index)
            if kind=='MACHINE':annotated['_verifier_machine_property_confirmed']=confirmed is True
            else:annotated['_verifier_runtime_property_confirmed']=confirmed is True
        verified_items.append(annotated)
    if expected_claim_id:
        validate_obligation_evidence(verified_items,expected_claim_id,allowed_kinds,errors,scope,rid,require_primary=require_primary,proof_policy=proof_policy)
    return verified_items


def _validate_artifact_requests(rows, errors, pending_items, machine_reports=None, runtime_cases=None):
    seen=set()
    for i,row in enumerate(rows or []):
        rid=row.get('id') or f'index:{i}'
        if rid in seen:
            errors.append({'type':'DUPLICATE_ARTIFACT_REQUEST_ID','id':rid}); continue
        seen.add(rid)
        status=row.get('status','REQUEST_REQUIRED'); blocking=bool(row.get('blocking',True))
        artifacts=row.get('artifacts') or []; claim=row.get('claim')
        if status in {'REQUEST_REQUIRED','REQUESTED','UNAVAILABLE','DECLINED'} and (not artifacts or not _has_text(claim)):
            errors.append({'type':'ARTIFACT_REQUEST_INCOMPLETE','id':rid,'status':status})
        if status=='REQUEST_REQUIRED':
            errors.append({'type':'REQUIRED_ARTIFACT_NOT_REQUESTED','id':rid,'claim':claim})
        elif status=='REQUESTED':
            if not _has_text(row.get('request_text')): errors.append({'type':'ARTIFACT_REQUEST_WITHOUT_USER_REQUEST','id':rid})
            if blocking: errors.append({'type':'REQUIRED_ARTIFACT_PENDING','id':rid,'claim':claim})
            else: pending_items.append({'type':'NONBLOCKING_ARTIFACT_PENDING','id':rid,'claim':claim})
        elif status in {'UNAVAILABLE','DECLINED'}:
            if not _has_text(row.get('reason')): errors.append({'type':'ARTIFACT_REQUEST_STATUS_WITHOUT_REASON','id':rid,'status':status})
            if blocking: errors.append({'type':'REQUIRED_ARTIFACT_UNAVAILABLE','id':rid,'status':status,'claim':claim})
            else: pending_items.append({'type':'NONBLOCKING_ARTIFACT_UNAVAILABLE','id':rid,'status':status,'claim':claim})
        elif status=='PROVIDED':
            _validate_evidence(row.get('evidence'),errors,'artifact_request',rid,machine_reports,runtime_cases)
        elif status=='RESOLVED_NOT_NEEDED':
            if not _has_text(row.get('reason')): errors.append({'type':'RESOLVED_NOT_NEEDED_WITHOUT_REASON','id':rid})
        elif status not in {'REQUEST_REQUIRED','REQUESTED','UNAVAILABLE','DECLINED','PROVIDED','RESOLVED_NOT_NEEDED'}:
            errors.append({'type':'UNKNOWN_ARTIFACT_REQUEST_STATUS','id':rid,'status':status})


def _validate_gap_discovery(document, registry, errors, pending_items, ledger_rule_rows=None, runtime_cases=None, machine_reports=None):
    """Validate source-anchored discovery without treating hypotheses as findings."""
    contract=registry.get('gap_discovery_contract') or {}
    expected_lenses=contract.get('lenses') or []
    discovery=document or {}
    lens_rows=discovery.get('lenses') or []
    lenses={}
    for row in lens_rows:
        lid=row.get('id')
        if not lid:errors.append({'type':'GAP_DISCOVERY_LENS_WITHOUT_ID'});continue
        if lid in lenses:errors.append({'type':'GAP_DISCOVERY_LENS_DUPLICATE','id':lid});continue
        lenses[lid]=row
    for lid in expected_lenses:
        row=lenses.get(lid)
        if not row:errors.append({'type':'GAP_DISCOVERY_LENS_MISSING','id':lid});continue
        status=row.get('status')
        if status in {'EVIDENCE_REQUIRED','BLOCKING_DEFECT','NEEDS_REVISION'} or not status:
            errors.append({'type':'GAP_DISCOVERY_LENS_UNRESOLVED','id':lid,'status':status})
        elif status=='PASS':
            _validate_evidence(row.get('evidence'),errors,'gap_discovery_lens',lid,machine_reports,runtime_cases)
        elif status=='NOT_APPLICABLE' and not _has_text(row.get('reason')):
            errors.append({'type':'NA_WITHOUT_REASON','scope':'gap_discovery_lens','id':lid})
        elif status in {'RUNTIME_PENDING','NEEDS_PROFILING'}:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'gap_discovery_lens','id':lid})
            pending_items.append({'type':'GAP_DISCOVERY_LENS_PENDING','id':lid,'status':status})
        elif status not in {'PASS','NOT_APPLICABLE','RUNTIME_PENDING','NEEDS_PROFILING'}:
            errors.append({'type':'UNKNOWN_GAP_DISCOVERY_LENS_STATUS','id':lid,'status':status})
    for lid in sorted(set(lenses)-set(expected_lenses)):
        errors.append({'type':'UNKNOWN_GAP_DISCOVERY_LENS','id':lid})

    resolved=set(contract.get('resolved_hypothesis_statuses') or [])
    blocking=set(contract.get('blocking_hypothesis_statuses') or [])
    pending=set(contract.get('pending_hypothesis_statuses') or [])
    required=contract.get('required_hypothesis_fields') or []
    known_rules=set(rule_map(registry))
    ledger_rule_map={row.get('id'):row for row in (ledger_rule_rows or []) if row.get('id')}
    runtime_case_ids=set(runtime_cases or {})
    seen=set()
    for index,row in enumerate(discovery.get('hypotheses') or []):
        hid=row.get('id') or f'index:{index}'
        if hid in seen:errors.append({'type':'GAP_HYPOTHESIS_DUPLICATE_ID','id':hid});continue
        seen.add(hid)
        missing=[field for field in required if not row.get(field)]
        if missing:errors.append({'type':'GAP_HYPOTHESIS_INCOMPLETE','id':hid,'missing':missing})
        if row.get('lens') not in expected_lenses:
            errors.append({'type':'GAP_HYPOTHESIS_UNKNOWN_LENS','id':hid,'lens':row.get('lens')})
        anchors=row.get('source_anchors')
        if not isinstance(anchors,list) or not anchors or any(not _has_text(x) for x in anchors):
            errors.append({'type':'GAP_HYPOTHESIS_WITHOUT_SOURCE_ANCHORS','id':hid})
        for field in ('statement','counterexample','falsifier'):
            if not _has_text(row.get(field)):errors.append({'type':'GAP_HYPOTHESIS_NON_FALSIFIABLE','id':hid,'field':field})
        status=row.get('status')
        if status in blocking:
            errors.append({'type':'GAP_HYPOTHESIS_BLOCKING','id':hid,'status':status})
            if status=='EVIDENCE_REQUIRED' and not _has_text(row.get('missing_evidence')):
                errors.append({'type':'GAP_HYPOTHESIS_MISSING_EVIDENCE_UNSPECIFIED','id':hid})
            if status in {'CONFIRMED_DEFECT','COVERAGE_GAP'} and not _has_concrete_evidence(row.get('evidence')):
                errors.append({'type':'GAP_HYPOTHESIS_STATUS_WITHOUT_EVIDENCE','id':hid,'status':status})
            if status=='COVERAGE_GAP' and not row.get('existing_rule_search'):
                errors.append({'type':'GAP_HYPOTHESIS_COVERAGE_GAP_WITHOUT_REGISTRY_SEARCH','id':hid})
        elif status in pending:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'gap_hypothesis','id':hid})
            if row.get('runtime_case_id') not in runtime_case_ids:
                errors.append({'type':'GAP_HYPOTHESIS_RUNTIME_CASE_MISSING','id':hid,'runtime_case_id':row.get('runtime_case_id')})
            pending_items.append({'type':'GAP_HYPOTHESIS_PENDING','id':hid,'status':status})
        elif status in resolved:
            _validate_evidence(row.get('evidence'),errors,'gap_hypothesis',hid,machine_reports,runtime_cases)
            if status=='NOT_MATERIAL' and not _has_text(row.get('reason')):
                errors.append({'type':'GAP_HYPOTHESIS_NOT_MATERIAL_WITHOUT_REASON','id':hid})
            if status=='COVERED_BY_EXISTING_RULE' and row.get('existing_rule_id') not in known_rules:
                errors.append({'type':'GAP_HYPOTHESIS_UNKNOWN_RULE_OWNER','id':hid,'rule':row.get('existing_rule_id')})
            elif status=='COVERED_BY_EXISTING_RULE':
                owner=ledger_rule_map.get(row.get('existing_rule_id'))
                if not owner:
                    errors.append({'type':'GAP_HYPOTHESIS_OWNER_NOT_ROUTED','id':hid,'rule':row.get('existing_rule_id')})
                elif owner.get('status')!='PASS':
                    errors.append({'type':'GAP_HYPOTHESIS_OWNER_NOT_PROVEN','id':hid,'rule':row.get('existing_rule_id'),'status':owner.get('status')})
        else:
            errors.append({'type':'UNKNOWN_GAP_HYPOTHESIS_STATUS','id':hid,'status':status})



def _validate_adversarial_cases(rows, errors, pending_items, blocking, pending, machine_reports, runtime_cases, require_one=False):
    cases=_index_rows(rows,'id','adversarial_case',errors)
    if require_one and not cases:errors.append({'type':'ADVERSARIAL_CASES_MISSING'})
    for cid,row in cases.items():
        if not _has_text(row.get('case')):errors.append({'type':'ADVERSARIAL_CASE_WITHOUT_COUNTEREXAMPLE','id':cid})
        status=row.get('status')
        if status in blocking or not status:errors.append({'type':'ADVERSARIAL_CASE_BLOCKING_OR_UNRESOLVED','id':cid,'status':status})
        elif status in pending:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'adversarial_case','id':cid})
            pending_items.append({'type':'ADVERSARIAL_CASE_PENDING','id':cid,'status':status})
        elif status=='PASS':_validate_evidence(row.get('evidence'),errors,'adversarial_case',cid,machine_reports,runtime_cases)
        elif status=='NOT_APPLICABLE':
            if not _has_text(row.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'adversarial_case','id':cid})
        else:errors.append({'type':'UNKNOWN_ADVERSARIAL_CASE_STATUS','id':cid,'status':status})

def _dependency_key(dep):
    if not isinstance(dep,dict):return None
    kind=dep.get('kind'); did=dep.get('id')
    return (str(kind).upper(),str(did)) if _has_text(kind) and _has_text(did) else None


def _validate_evidence_reuse(ledger, errors, plan=None):
    """Validate reusable evidence against explicit dependency identities/fingerprints.

    A dependency name alone is not safe reuse. Each dependency is
    {kind, id, fingerprint}; changed_dependencies invalidates by (kind,id), so a
    new fingerprint cannot accidentally evade invalidation.
    """
    registry_rows=_index_rows(ledger.get('evidence_registry') or [],'id','evidence_registry',errors)
    plan=plan or {}; current_fingerprints={}
    for artifact in plan.get('candidate_artifacts') or []:
        if _has_text(artifact.get('logical_path')) and _has_text(artifact.get('sha256')):
            current_fingerprints[('CANDIDATE',artifact['logical_path'])]=artifact['sha256']
    baseline=plan.get('baseline')
    if isinstance(baseline,dict) and _has_text(baseline.get('path')) and _has_text(baseline.get('sha256')):
        current_fingerprints[('BASELINE',baseline['path'])]=baseline['sha256']
    context=plan.get('project_context') or {}
    if _has_text(context.get('path')) and _has_text(context.get('sha256')):
        current_fingerprints[('PROJECT_CONTEXT',context['path'])]=context['sha256']
    requirements=plan.get('requirements') or {}
    if _has_text(requirements.get('path')) and _has_text(requirements.get('sha256')):
        current_fingerprints[('REQUIREMENTS',requirements['path'])]=requirements['sha256']
    for eid,row in registry_rows.items():
        if not _has_text(row.get('kind')) or not _has_text(row.get('ref')):
            errors.append({'type':'EVIDENCE_REGISTRY_ENTRY_INCOMPLETE','id':eid})
        deps=row.get('dependencies')
        if not isinstance(deps,list) or not deps:
            errors.append({'type':'EVIDENCE_REGISTRY_DEPENDENCIES_MISSING','id':eid}); continue
        seen=set()
        for index,dep in enumerate(deps):
            key=_dependency_key(dep)
            if not key or not _has_text(dep.get('fingerprint')):
                errors.append({'type':'EVIDENCE_DEPENDENCY_NOT_FINGERPRINT_BOUND','id':eid,'index':index}); continue
            if key in seen:errors.append({'type':'EVIDENCE_DEPENDENCY_DUPLICATE','id':eid,'kind':key[0],'dependency_id':key[1]})
            seen.add(key)
            expected=current_fingerprints.get(key)
            if expected is not None and str(dep.get('fingerprint'))!=str(expected):
                errors.append({'type':'EVIDENCE_DEPENDENCY_FINGERPRINT_DRIFT','id':eid,'kind':key[0],'dependency_id':key[1],'expected':expected,'actual':dep.get('fingerprint')})
    reuse=ledger.get('evidence_reuse') or {}
    reused=list(reuse.get('reused_ids') or []); invalidated=list(reuse.get('invalidated_ids') or []); changed=list(reuse.get('changed_dependencies') or [])
    if len(reused)!=len(set(reused)):errors.append({'type':'EVIDENCE_REUSE_DUPLICATE_ID'})
    if len(invalidated)!=len(set(invalidated)):errors.append({'type':'EVIDENCE_INVALIDATION_DUPLICATE_ID'})
    overlap=sorted(set(reused)&set(invalidated))
    if overlap:errors.append({'type':'EVIDENCE_REUSED_AND_INVALIDATED','ids':overlap})
    for eid in reused+invalidated:
        if eid not in registry_rows:errors.append({'type':'EVIDENCE_REUSE_UNKNOWN_ID','id':eid})
    changed_keys=set()
    for index,dep in enumerate(changed):
        key=_dependency_key(dep)
        if not key:
            errors.append({'type':'CHANGED_DEPENDENCY_IDENTITY_INVALID','index':index}); continue
        changed_keys.add(key)
    for eid in reused:
        row=registry_rows.get(eid) or {}; deps=row.get('dependencies') or []
        collided=[dep for dep in deps if _dependency_key(dep) in changed_keys]
        if collided:errors.append({'type':'REUSED_EVIDENCE_DEPENDENCY_CHANGED','id':eid,'dependencies':collided})


def _validate_bidirectional(ledger, expected_rule_ids, expected_checks, errors, pending_items, blocking, pending, machine_reports, runtime_cases, known_rule_ids, require_forward=False):
    c2s=_index_rows(ledger.get('code_to_standards') or [],'id','code_to_standards',errors)
    if not c2s:errors.append({'type':'CODE_TO_STANDARDS_MISSING'})
    for cid,row in c2s.items():
        if row.get('origin')!='SOURCE_CONSTRUCTIONS':errors.append({'type':'CODE_TO_STANDARDS_ORIGIN_INVALID','id':cid,'origin':row.get('origin')})
        anchors=row.get('source_anchors') or []
        if not isinstance(anchors,list) or not anchors or any(not _has_text(x) for x in anchors):errors.append({'type':'CODE_TO_STANDARDS_SOURCE_ANCHORS_MISSING','id':cid})
        discovered=row.get('rule_ids') or []
        if not isinstance(discovered,list):errors.append({'type':'CODE_TO_STANDARDS_RULE_IDS_INVALID','id':cid}); discovered=[]
        unknown=sorted(set(discovered)-known_rule_ids)
        if unknown:errors.append({'type':'CODE_TO_STANDARDS_UNKNOWN_RULE','id':cid,'rules':unknown})
        reroute=sorted(set(discovered)-set(expected_rule_ids))
        if reroute:errors.append({'type':'CODE_TO_STANDARDS_DISCOVERY_REQUIRES_REROUTE','id':cid,'rules':reroute})
        status=row.get('status')
        if status in blocking or not status:errors.append({'type':'CODE_TO_STANDARDS_UNRESOLVED','id':cid,'status':status})
        elif status in pending:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'code_to_standards','id':cid})
            pending_items.append({'type':'CODE_TO_STANDARDS_PENDING','id':cid,'status':status})
        elif status=='PASS':
            if not discovered:errors.append({'type':'CODE_TO_STANDARDS_PASS_WITHOUT_RULE_MAPPING','id':cid})
            _validate_evidence(row.get('evidence'),errors,'code_to_standards',cid,machine_reports,runtime_cases)
        elif status=='NOT_APPLICABLE':
            if require_forward:errors.append({'type':'CODE_TO_STANDARDS_NA_WITH_CODE_SOURCE','id':cid})
            if not _has_text(row.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'code_to_standards','id':cid})
        else:errors.append({'type':'UNKNOWN_CODE_TO_STANDARDS_STATUS','id':cid,'status':status})

    s2c_rows=ledger.get('standards_to_code') or []
    ledger_rule_status={row.get('id'):row.get('status') for row in (ledger.get('rules') or []) if isinstance(row,dict) and _has_text(row.get('id'))}
    by_rule={}
    seen_ids=set()
    for index,row in enumerate(s2c_rows):
        sid=row.get('id')
        if not _has_text(sid):errors.append({'type':'ROW_WITHOUT_ID','scope':'standards_to_code','index':index});continue
        if sid in seen_ids:errors.append({'type':'DUPLICATE_ROW_ID','scope':'standards_to_code','id':sid});continue
        seen_ids.add(sid)
        rid=row.get('rule_id')
        if not _has_text(rid):errors.append({'type':'STANDARDS_TO_CODE_WITHOUT_RULE','id':sid});continue
        if rid in by_rule:errors.append({'type':'STANDARDS_TO_CODE_DUPLICATE_RULE','rule':rid});continue
        by_rule[rid]=row
    missing=sorted(set(expected_rule_ids)-set(by_rule)); extra=sorted(set(by_rule)-set(expected_rule_ids))
    for rid in missing:errors.append({'type':'STANDARDS_TO_CODE_RULE_MISSING','rule':rid})
    for rid in extra:errors.append({'type':'STANDARDS_TO_CODE_UNROUTED_RULE','rule':rid})
    for rid in expected_rule_ids:
        row=by_rule.get(rid)
        if not row:continue
        if row.get('origin')!='REGISTRY_EXPANSION':errors.append({'type':'STANDARDS_TO_CODE_ORIGIN_INVALID','rule':rid,'origin':row.get('origin')})
        actual_checks=row.get('check_ids') or []
        expected=set(expected_checks.get(rid) or [])
        if len(actual_checks)!=len(set(actual_checks)):errors.append({'type':'STANDARDS_TO_CODE_DUPLICATE_CHECK','rule':rid})
        if set(actual_checks)!=expected:errors.append({'type':'STANDARDS_TO_CODE_CHECK_COVERAGE_DRIFT','rule':rid,'missing':sorted(expected-set(actual_checks)),'extra':sorted(set(actual_checks)-expected)})
        status=row.get('status'); owner_status=ledger_rule_status.get(rid)
        if owner_status=='PASS' and status=='NOT_APPLICABLE':errors.append({'type':'STANDARDS_TO_CODE_NA_FOR_PROVEN_RULE','rule':rid})
        if owner_status=='NOT_APPLICABLE' and status=='PASS':errors.append({'type':'STANDARDS_TO_CODE_PASS_FOR_NA_RULE','rule':rid})
        if status in blocking or not status:errors.append({'type':'STANDARDS_TO_CODE_UNRESOLVED','rule':rid,'status':status})
        elif status in pending:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'standards_to_code','id':rid})
            pending_items.append({'type':'STANDARDS_TO_CODE_PENDING','id':rid,'status':status})
        elif status=='PASS':_validate_evidence(row.get('evidence'),errors,'standards_to_code',rid,machine_reports,runtime_cases)
        elif status=='NOT_APPLICABLE':
            if not _has_text(row.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'standards_to_code','id':rid})
        else:errors.append({'type':'UNKNOWN_STANDARDS_TO_CODE_STATUS','rule':rid,'status':status})


def _artifact_map(rows, where, errors):
    result={}
    for index,row in enumerate(rows or []):
        logical=row.get('logical_path'); sha=row.get('sha256')
        if not _has_text(logical) or not _has_text(sha):errors.append({'type':'CANDIDATE_ARTIFACT_INCOMPLETE','where':where,'index':index});continue
        if logical in result:errors.append({'type':'DUPLICATE_CANDIDATE_ARTIFACT','where':where,'logical_path':logical});continue
        if not re.fullmatch(r'[0-9a-fA-F]{64}',sha):errors.append({'type':'CANDIDATE_ARTIFACT_HASH_INVALID','where':where,'logical_path':logical,'sha256':sha})
        result[logical]=sha.lower()
    return result



def _machine_finding_mapping(registry):
    mapping={}
    for rule in registry.get("rules") or []:
        for check in rule.get("checks") or []:
            for finding_type in check.get("machine_finding_types") or []:
                if finding_type in mapping:
                    raise ValueError(f"machine finding type has multiple canonical owners: {finding_type}")
                mapping[finding_type]=(rule["id"],check["id"],proof_policy_for(rule,registry))
    return mapping


def _canonical_finding_sha(finding):
    return hashlib.sha256(_canon(finding).encode("utf-8")).hexdigest()


def _verified_machine_finding_expectations(machine_reports,p_art,registry,errors):
    """Derive exact finding obligations from replay-verified machine stdout."""
    try:
        mapping=_machine_finding_mapping(registry)
    except Exception as exc:
        errors.append({"type":"MACHINE_FINDING_MAPPING_INVALID","error":str(exc)})
        return {}
    expected={}
    for report_id,row in (machine_reports or {}).items():
        if row.get("_receipt_integrity")!="PASS" or row.get("_receipt_result")!="PASS":
            continue
        receipt=row.get("_receipt") or {}; output=receipt.get("output") or {}
        stdout_path=Path(output.get("stdout_path") or "")
        if not stdout_path.is_file():
            errors.append({"type":"MACHINE_FINDING_REPORT_STDOUT_MISSING","report_id":report_id});continue
        try:raw=stdout_path.read_bytes()
        except OSError as exc:
            errors.append({"type":"MACHINE_FINDING_REPORT_STDOUT_UNREADABLE","report_id":report_id,"error":str(exc)});continue
        actual_output_sha=hashlib.sha256(raw).hexdigest()
        if actual_output_sha!=output.get("stdout_sha256"):
            errors.append({"type":"MACHINE_FINDING_REPORT_STDOUT_HASH_DRIFT","report_id":report_id,"expected":output.get("stdout_sha256"),"actual":actual_output_sha});continue
        try:payload=json.loads(raw.decode("utf-8-sig"))
        except Exception as exc:
            errors.append({"type":"MACHINE_FINDING_REPORT_STDOUT_NOT_JSON","report_id":report_id,"error":str(exc)});continue
        input_shas={str(x.get("sha256") or "").lower() for x in receipt.get("inputs") or [] if isinstance(x,dict)}
        candidate_matches=[logical for logical,sha in p_art.items() if sha in input_shas]
        for finding in payload.get("findings") or []:
            if not isinstance(finding,dict):continue
            finding_type=finding.get("type"); owner=mapping.get(finding_type)
            if not owner:continue
            hint=finding.get("file")
            if not _has_text(hint):
                hint=(finding.get("routine") or {}).get("logical_path") if isinstance(finding.get("routine"),dict) else None
            matches=list(candidate_matches)
            if len(matches)>1 and _has_text(hint):
                normalized=str(hint).replace("\\","/")
                narrowed=[x for x in matches if x.replace("\\","/")==normalized or x.replace("\\","/").endswith("/"+normalized) or Path(x).name==Path(normalized).name]
                if len(narrowed)==1:matches=narrowed
            if len(matches)!=1:
                errors.append({"type":"MACHINE_FINDING_CANDIDATE_BINDING_AMBIGUOUS","report_id":report_id,"finding_type":finding_type,"matches":sorted(matches),"hint":hint})
                continue
            artifact=matches[0];candidate_sha=p_art[artifact]
            rule_id,check_id,policy=owner
            finding_sha=_canonical_finding_sha(finding)
            claim_id=machine_finding_claim_id(rule_id,check_id,finding_type,artifact,candidate_sha,finding_sha)
            item={
                "id":claim_id,"claim_id":claim_id,
                "rule_id":rule_id,"check_id":check_id,"finding_type":finding_type,
                "artifact":artifact,"candidate_sha256":candidate_sha,
                "report_id":report_id,"report_output_sha256":actual_output_sha,
                "finding_sha256":finding_sha,"proof_policy":policy,
            }
            if claim_id in expected:
                errors.append({"type":"MACHINE_FINDING_EXPECTED_ID_DUPLICATE","id":claim_id,"report_id":report_id});continue
            expected[claim_id]=item
    return expected


def _validate_machine_findings(rows,expected,rules,errors,pending_items,machine_reports,independent_reviews,plan,receipt_provenance,risk):
    actual=_index_rows(rows or [],"id","machine_finding",errors)
    for rid in sorted(set(actual)-set(expected)):
        errors.append({"type":"MACHINE_FINDING_UNPLANNED_ROW","scope":"machine_finding","id":rid})
    for rid in sorted(set(expected)-set(actual)):
        errors.append({"type":"MACHINE_FINDING_ROW_MISSING","scope":"machine_finding","id":rid,**{k:expected[rid].get(k) for k in ("rule_id","check_id","finding_type","artifact","report_id")}})
    immutable=("claim_id","rule_id","check_id","finding_type","artifact","candidate_sha256","report_id","report_output_sha256","finding_sha256","proof_policy")
    for rid,want in expected.items():
        row=actual.get(rid)
        if not row:continue
        drift={key:{"expected":want.get(key),"actual":row.get(key)} for key in immutable if row.get(key)!=want.get(key)}
        if drift:
            errors.append({"type":"MACHINE_FINDING_BINDING_DRIFT","scope":"machine_finding","id":rid,"fields":drift})
            continue
        rule=rules.get(want["rule_id"])
        check=next((x for x in (rule or {}).get("checks",[]) if x.get("id")==want["check_id"]),None)
        if not rule or not check or want["finding_type"] not in (check.get("machine_finding_types") or []):
            errors.append({"type":"MACHINE_FINDING_CANONICAL_OWNER_INVALID","scope":"machine_finding","id":rid})
            continue
        status=row.get("status")
        if status!="PASS":
            errors.append({"type":"MACHINE_FINDING_BLOCKING_OR_UNRESOLVED","scope":"machine_finding","id":rid,"status":status})
            if status in {"RUNTIME_TEST_REQUIRED","PENDING"}:
                pending_items.append({"type":"MACHINE_FINDING_PENDING","id":rid,"status":status})
            continue
        verified=_validate_evidence(
            row.get("evidence"),errors,"machine_finding",rid,machine_reports,None,
            expected_claim_id=rid,allowed_kinds={"SOURCE_REQUIRED","SEMANTIC"},
            require_primary=True,plan=plan,receipt_provenance=receipt_provenance,
            proof_policy=want["proof_policy"],
        )
        validate_claim_policy(want["proof_policy"],verified,independent_reviews,rid,errors,"machine_finding",rid,risk=risk)


def _current_origin_sha(origin):
    if not _has_text(origin):return None
    if '!/' in origin:
        archive_name,entry=origin.split('!/',1); archive=Path(archive_name)
        if not archive.is_file():return None
        try:
            with zipfile.ZipFile(archive) as z:return hashlib.sha256(z.read(entry)).hexdigest()
        except (KeyError,zipfile.BadZipFile,OSError):return None
    path=Path(origin)
    if not path.is_file():return None
    try:return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:return None


def _current_dependency_snapshot(path):
    p=Path(path)
    if p.is_file():
        data=p.read_bytes(); return {'kind':'FILE','sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
    if p.is_dir():
        digest=hashlib.sha256(); files=0; total=0
        for item in sorted(x for x in p.rglob('*') if x.is_file()):
            rel=item.relative_to(p).as_posix(); data=item.read_bytes(); file_sha=hashlib.sha256(data).hexdigest()
            digest.update(rel.encode('utf-8')); digest.update(b'\0'); digest.update(file_sha.encode('ascii')); digest.update(b'\n')
            files+=1; total+=len(data)
        return {'kind':'DIRECTORY','sha256':digest.hexdigest(),'files':files,'size':total}
    return None


def _validate_current_sources(plan, errors):
    for row in plan.get('candidate_artifacts') or []:
        current=_current_origin_sha(row.get('origin'))
        if current is not None and _has_text(row.get('sha256')) and current.lower()!=row['sha256'].lower():
            errors.append({'type':'CANDIDATE_SOURCE_DRIFT','logical_path':row.get('logical_path'),'origin':row.get('origin'),'expected':row.get('sha256'),'actual':current})
    baseline=plan.get('baseline')
    if isinstance(baseline,dict) and _has_text(baseline.get('path')):
        current=_current_dependency_snapshot(baseline['path'])
        if current is not None and current.get('sha256')!=baseline.get('sha256'):
            errors.append({'type':'BASELINE_SOURCE_DRIFT','path':baseline.get('path'),'expected':baseline.get('sha256'),'actual':current.get('sha256')})
    for scope,key in (('PROJECT_CONTEXT','project_context'),('REQUIREMENTS','requirements')):
        dep=plan.get(key) or {}; path=dep.get('path'); expected=dep.get('sha256')
        if _has_text(path) and _has_text(expected):
            current=_current_origin_sha(path)
            if current is not None and current!=expected:
                errors.append({'type':f'{scope}_SOURCE_DRIFT','path':path,'expected':expected,'actual':current})

def _receipt_current_source_identity(source):
    if not isinstance(source,dict):return None
    stype=source.get("type")
    if stype=="ARCHIVE_ENTRY":
        archive_path=source.get("archive_path"); entry_path=_norm_archive_entry(source.get("entry_path"))
        if not _has_text(archive_path) or not entry_path:return None
        archive=Path(archive_path)
        if not archive.is_file():return None
        try:
            archive_bytes=archive.read_bytes()
            with zipfile.ZipFile(archive) as z:
                matches=[info for info in z.infolist() if not info.is_dir() and _norm_archive_entry(info.filename)==entry_path]
                if len(matches)!=1:return None
                data=z.read(matches[0])
        except (OSError,zipfile.BadZipFile,KeyError):
            return None
        return {
            "type":"ARCHIVE_ENTRY",
            "ref":_canonical_source_ref(f"{archive_path}!/{entry_path}"),
            "archive_path":str(Path(archive_path).resolve(strict=False)),
            "archive_sha256":hashlib.sha256(archive_bytes).hexdigest(),
            "entry_path":entry_path,
            "entry_sha256":hashlib.sha256(data).hexdigest(),
            "sha256":hashlib.sha256(data).hexdigest(),
            "size":len(data),
        }
    if stype=="FILE":
        path=source.get("path") or source.get("ref")
        canon=_canonical_source_ref(path)
        if not canon:return None
        p=Path(canon)
        if not p.is_file():return None
        try:data=p.read_bytes()
        except OSError:return None
        return {"type":"FILE","ref":canon,"path":canon,"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}
    return None


def _validate_receipt_evidence_provenance(ledger,plan,registry,errors):
    rows=ledger.get("receipt_evidence_provenance")
    if rows is None:
        rows=[]
    if not isinstance(rows,list):
        errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_INVALID","reason":"NOT_A_LIST"})
        return {"by_key":{}}

    by_key={}; seen_ids=set(); rules=rule_map(registry); source_index=_plan_source_index(plan)
    for index,row in enumerate(rows):
        if not isinstance(row,dict):
            errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_INVALID","index":index,"reason":"ROW_NOT_OBJECT"})
            continue
        pid=row.get("id")
        if not _has_text(pid):
            errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_INVALID","index":index,"reason":"ID_MISSING"})
            continue
        if pid in seen_ids:
            errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_DUPLICATE","id":pid})
            continue
        seen_ids.add(pid)

        kind=str(row.get("kind") or "").upper(); source_ref=row.get("source_ref"); claim=row.get("claim_id")
        key=(kind,source_ref,claim)
        enriched=dict(row); local=[]

        required_text=("receipt_id","receipt_ref","receipt_sha256","claim_id","rule_id","check_id","kind","source_ref","source_sha256","binding_key_sha256")
        missing=[field for field in required_text if not _has_text(row.get(field))]
        if missing:local.append({"type":"RECEIPT_PROVENANCE_FIELDS_MISSING","fields":missing})

        expected_binding=_receipt_binding_key(kind,source_ref,claim)
        if row.get("binding_key_sha256")!=expected_binding:
            local.append({"type":"RECEIPT_PROVENANCE_BINDING_HASH_DRIFT","expected":expected_binding,"actual":row.get("binding_key_sha256")})

        if row.get("verification_mode")!="ATTACH_ONLY":
            local.append({"type":"RECEIPT_PROVENANCE_MODE_INVALID","actual":row.get("verification_mode")})
        if row.get("proof_role")!="SUPPORTING_ONLY" or row.get("supporting_only") is not True:
            local.append({"type":"RECEIPT_PROVENANCE_ROLE_INVALID","proof_role":row.get("proof_role"),"supporting_only":row.get("supporting_only")})
        if row.get("rule_owned_predicate") is not None:
            local.append({"type":"RECEIPT_PROVENANCE_UNEXPECTED_PREDICATE"})

        rule=rules.get(row.get("rule_id")); spec=None
        if rule:
            spec=next((c for c in rule.get("checks") or [] if c.get("id")==row.get("check_id")),None)
        expected_claim=check_claim_id(row.get("rule_id"),row.get("check_id")) if rule and spec else None
        if not rule or not spec or expected_claim!=claim:
            local.append({"type":"RECEIPT_PROVENANCE_CHECK_IDENTITY_INVALID","expected_claim":expected_claim,"actual_claim":claim})
        else:
            predicate=spec.get("receipt_predicate")
            if predicate is not None:
                verifier_id=predicate.get("verifier_id") if isinstance(predicate,dict) else None
                if verifier_id not in KNOWN_RECEIPT_PREDICATE_VERIFIERS:
                    local.append({"type":"RECEIPT_PREDICATE_VERIFIER_UNKNOWN","verifier_id":verifier_id})
                else:
                    local.append({"type":"RECEIPT_PREDICATE_REPLAY_NOT_IMPLEMENTED","verifier_id":verifier_id})

        canon_ref=_canonical_source_ref(source_ref)
        expected_source=source_index.get(canon_ref)
        if not expected_source:
            local.append({"type":"RECEIPT_PROVENANCE_SOURCE_OUTSIDE_CORPUS","ref":source_ref})
        elif row.get("source_sha256")!=expected_source.get("sha256"):
            local.append({"type":"RECEIPT_PROVENANCE_SOURCE_HASH_DRIFT","expected":expected_source.get("sha256"),"actual":row.get("source_sha256")})

        source_identity=row.get("source_identity")
        current_identity=_receipt_current_source_identity(source_identity)
        if not isinstance(source_identity,dict) or current_identity is None:
            local.append({"type":"RECEIPT_PROVENANCE_SOURCE_IDENTITY_INVALID"})
        else:
            expected_identity={key:source_identity.get(key) for key in ("type","ref","sha256","size","path","archive_path","archive_sha256","entry_path","entry_sha256") if source_identity.get(key) is not None}
            if current_identity!=expected_identity:
                local.append({"type":"RECEIPT_PROVENANCE_CURRENT_SOURCE_DRIFT","expected":expected_identity,"actual":current_identity})

        receipt_path=Path(str(row.get("receipt_ref") or ""))
        receipt_payload=None
        if not receipt_path.is_file():
            local.append({"type":"RECEIPT_PROVENANCE_RECEIPT_MISSING","ref":row.get("receipt_ref")})
        else:
            try:
                receipt_bytes=receipt_path.read_bytes()
                actual_receipt_sha=hashlib.sha256(receipt_bytes).hexdigest()
                if actual_receipt_sha!=row.get("receipt_sha256"):
                    local.append({"type":"RECEIPT_PROVENANCE_RECEIPT_HASH_DRIFT","expected":row.get("receipt_sha256"),"actual":actual_receipt_sha})
                receipt_payload=json.loads(receipt_bytes.decode("utf-8-sig"))
            except (OSError,UnicodeDecodeError,json.JSONDecodeError) as exc:
                local.append({"type":"RECEIPT_PROVENANCE_RECEIPT_INVALID","error":str(exc)})

        if isinstance(receipt_payload,dict):
            if receipt_payload.get("schema_version")!=row.get("receipt_schema_version"):
                local.append({"type":"RECEIPT_PROVENANCE_SCHEMA_DRIFT","expected":row.get("receipt_schema_version"),"actual":receipt_payload.get("schema_version")})
            if receipt_payload.get("id")!=row.get("receipt_id") or str(receipt_payload.get("kind") or "").upper()!=kind:
                local.append({"type":"RECEIPT_PROVENANCE_RECEIPT_IDENTITY_DRIFT"})
            rsource=receipt_payload.get("source") or {}
            receipt_identity={key:rsource.get(key) for key in ("type","ref","sha256","size","path","archive_path","archive_sha256","entry_path","entry_sha256") if rsource.get(key) is not None}
            if isinstance(source_identity,dict) and receipt_identity!=source_identity:
                local.append({"type":"RECEIPT_PROVENANCE_SOURCE_DECLARATION_DRIFT"})
            bindings=[b for b in (receipt_payload.get("bindings") or []) if isinstance(b,dict) and b.get("claim_id")==claim]
            if len(bindings)!=1:
                local.append({"type":"RECEIPT_PROVENANCE_CLAIM_BINDING_INVALID","matches":len(bindings)})
            else:
                binding=bindings[0]
                if binding.get("rule_id")!=row.get("rule_id") or binding.get("check_id")!=row.get("check_id"):
                    local.append({"type":"RECEIPT_PROVENANCE_BINDING_IDENTITY_DRIFT"})
                if binding.get("verification_mode")!="ATTACH_ONLY" or binding.get("rule_owned_predicate") is not None:
                    local.append({"type":"RECEIPT_PROVENANCE_BINDING_ROLE_INVALID"})

        if key in by_key:
            local.append({"type":"RECEIPT_PROVENANCE_BINDING_DUPLICATE"})
        enriched["_verified"]=not local
        enriched["_verification_errors"]=local
        by_key[key]=enriched
        for detail in local:
            errors.append({"type":"RECEIPT_EVIDENCE_PROVENANCE_INVALID","provenance_id":pid,"detail":detail})
    return {"by_key":by_key}


def _query_literal_escape_required(plan):
    route=next((row for row in plan.get("rules") or [] if isinstance(row,dict) and row.get("id")=="QUERY"),None)
    return bool(route and route.get("active"))


def _query_literal_escape_candidates(plan):
    return [
        row for row in plan.get("candidate_artifacts") or []
        if isinstance(row,dict) and str(row.get("logical_path") or "").lower().endswith(".bsl")
    ]


def _query_literal_escape_report_covers(report,candidate):
    if report.get("_receipt_integrity")!="PASS" or report.get("_receipt_result")!="PASS":
        return False
    receipt=report.get("_receipt") or {}
    if receipt.get("tool")!=QUERY_ESCAPE_TOOL or QUERY_ESCAPE_PROPERTY not in (receipt.get("verified_properties") or []):
        return False
    candidate_sha=str(candidate.get("sha256") or "").lower()
    origin=_canonical_source_ref(candidate.get("origin"))
    for row in receipt.get("inputs") or []:
        if not isinstance(row,dict):continue
        if str(row.get("sha256") or "").lower()!=candidate_sha:continue
        if _canonical_source_ref(row.get("path"))==origin:return True
    return False


def _query_literal_escape_payload(report,errors):
    receipt=report.get("_receipt") or {}; output=receipt.get("output") or {}
    path=Path(output.get("stdout_path") or "")
    if not path.is_file():
        errors.append({"type":"QUERY_LITERAL_ESCAPE_REPORT_STDOUT_MISSING","report_id":report.get("id")})
        return None,None
    try:raw=path.read_bytes()
    except OSError as exc:
        errors.append({"type":"QUERY_LITERAL_ESCAPE_REPORT_STDOUT_UNREADABLE","report_id":report.get("id"),"error":str(exc)})
        return None,None
    actual_sha=hashlib.sha256(raw).hexdigest()
    if actual_sha!=output.get("stdout_sha256"):
        errors.append({"type":"QUERY_LITERAL_ESCAPE_REPORT_STDOUT_HASH_DRIFT","report_id":report.get("id"),"expected":output.get("stdout_sha256"),"actual":actual_sha})
        return None,None
    try:payload=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        errors.append({"type":"QUERY_LITERAL_ESCAPE_REPORT_STDOUT_NOT_JSON","report_id":report.get("id"),"error":str(exc)})
        return None,None
    return payload,actual_sha


def _validate_query_literal_escape_gate(plan,ledger,machine_reports,registry,errors):
    """Verifier-owned current-candidate binding for QUERY_LITERAL_ESCAPE_CORRUPTION."""
    if not _query_literal_escape_required(plan):
        return {}
    query_rule=next((row for row in registry.get("rules") or [] if row.get("id")=="QUERY"),None)
    query_check=next((row for row in (query_rule or {}).get("checks") or [] if row.get("id")=="QUERY_LITERAL_ESCAPE_SANITY"),None)
    if not query_check or QUERY_ESCAPE_FINDING_TYPE not in (query_check.get("machine_finding_types") or []):
        errors.append({"type":"QUERY_LITERAL_ESCAPE_CANONICAL_OWNER_INVALID","scope":"check","id":"QUERY_LITERAL_ESCAPE_SANITY","rule":"QUERY"})
        return {}
    actual={
        row.get("id"):row for row in ledger.get("blocking_findings") or []
        if isinstance(row,dict) and row.get("finding_type")==QUERY_ESCAPE_FINDING_TYPE and _has_text(row.get("id"))
    }
    expected={}; expected_report_ids={}
    for candidate in _query_literal_escape_candidates(plan):
        logical=str(candidate.get("logical_path") or "")
        current_reports=[
            row for row in (machine_reports or {}).values()
            if _query_literal_escape_report_covers(row,candidate)
        ]
        if not current_reports:
            errors.append({
                "type":"QUERY_LITERAL_ESCAPE_CURRENT_ANALYZER_REQUIRED",
                "scope":"check","id":"QUERY_LITERAL_ESCAPE_SANITY","rule":"QUERY",
                "artifact":logical,"candidate_sha256":candidate.get("sha256"),
            })
            continue
        # Multiple valid receipts for identical bytes are equivalent; deterministic
        # analyzer replay must produce the same finding identity. Use stable report id
        # order only to choose the provenance row stored in the canonical blocker.
        for report in sorted(current_reports,key=lambda x:str(x.get("id") or "")):
            payload,output_sha=_query_literal_escape_payload(report,errors)
            if payload is None:continue
            for finding in payload.get("findings") or []:
                if not isinstance(finding,dict) or finding.get("type")!=QUERY_ESCAPE_FINDING_TYPE:
                    continue
                row=query_escape_blocking_row(
                    logical,str(candidate.get("sha256") or "").lower(),
                    report.get("id"),output_sha,finding
                )
                expected.setdefault(row["id"],row)
                expected_report_ids.setdefault(row["id"],set()).add(report.get("id"))
    for rid,want in sorted(expected.items()):
        errors.append({
            "type":"QUERY_LITERAL_ESCAPE_CORRUPTION_PRESENT",
            "scope":"blocking_finding","id":rid,"rule":"QUERY",
            "rule_id":want["rule_id"],"check_id":want["check_id"],
            "finding_type":want["finding_type"],"artifact":want["artifact"],
            "candidate_sha256":want["candidate_sha256"],"report_id":want["report_id"],
        })
        got=actual.get(rid)
        if got is None:
            errors.append({
                "type":"BLOCKING_FINDING_ROW_MISSING",
                "scope":"blocking_finding","id":rid,"rule":"QUERY",
                **{key:want.get(key) for key in ("rule_id","check_id","finding_type","artifact","candidate_sha256","report_id","report_output_sha256","finding_sha256")}
            })
            continue
        immutable=("rule_id","check_id","finding_type","artifact","candidate_sha256","report_output_sha256","finding_sha256","severity","status")
        drift={key:{"expected":want.get(key),"actual":got.get(key)} for key in immutable if got.get(key)!=want.get(key)}
        if drift:
            errors.append({"type":"BLOCKING_FINDING_BINDING_DRIFT","scope":"blocking_finding","id":rid,"rule":"QUERY","fields":drift})
        if got.get("report_id") not in expected_report_ids.get(rid,set()):
            errors.append({"type":"BLOCKING_FINDING_REPORT_BINDING_DRIFT","scope":"blocking_finding","id":rid,"rule":"QUERY","actual":got.get("report_id")})
    for rid,row in sorted(actual.items()):
        if rid not in expected:
            errors.append({
                "type":"BLOCKING_FINDING_STALE_OR_UNVERIFIED",
                "scope":"blocking_finding","id":rid,"rule":"QUERY",
                "finding_type":row.get("finding_type"),"artifact":row.get("artifact"),
            })
    return expected


def _bsl_bare_symbol_intent_candidates(plan,ledger,errors):
    if (plan.get("routing") or {}).get("mode")=="ANALYSIS_ONLY":return []
    rows=(ledger.get("implementation_intent_map") or {}).get("rows") or []
    wanted={str(row.get("artifact") or "") for row in rows if isinstance(row,dict) and str(row.get("artifact") or "").lower().endswith((".bsl",".os"))}
    by_logical={str(row.get("logical_path") or ""):row for row in plan.get("candidate_artifacts") or [] if isinstance(row,dict)}
    result=[]
    for artifact in sorted(wanted):
        candidate=by_logical.get(artifact)
        if candidate is None:errors.append({"type":"BSL_BARE_SYMBOL_INTENT_ARTIFACT_NOT_CANDIDATE","artifact":artifact})
        else:result.append(candidate)
    return result

def _bsl_bare_symbol_report_covers(report,candidate):
    if report.get("_receipt_integrity")!="PASS" or report.get("_receipt_result")!="PASS":return False
    receipt=report.get("_receipt") or {}
    if receipt.get("tool")!=BSL_BARE_SYMBOL_TOOL or BSL_BARE_SYMBOL_PROPERTY not in (receipt.get("verified_properties") or []):return False
    candidate_sha=str(candidate.get("sha256") or "").lower();origin=_canonical_source_ref(candidate.get("origin"))
    for row in receipt.get("inputs") or []:
        if isinstance(row,dict) and str(row.get("sha256") or "").lower()==candidate_sha and _canonical_source_ref(row.get("path"))==origin:return True
    return False

def _bsl_bare_symbol_payload_passes(report,candidate,errors):
    receipt=report.get("_receipt") or {};output=receipt.get("output") or {};path=Path(output.get("stdout_path") or "")
    if not path.is_file():errors.append({"type":"BSL_BARE_SYMBOL_REPORT_STDOUT_MISSING","report_id":report.get("id")});return False
    try:raw=path.read_bytes();payload=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:errors.append({"type":"BSL_BARE_SYMBOL_REPORT_STDOUT_INVALID","report_id":report.get("id"),"error":str(exc)});return False
    if hashlib.sha256(raw).hexdigest()!=output.get("stdout_sha256"):errors.append({"type":"BSL_BARE_SYMBOL_REPORT_STDOUT_HASH_DRIFT","report_id":report.get("id")});return False
    if str(payload.get("sha256") or "").lower()!=str(candidate.get("sha256") or "").lower():errors.append({"type":"BSL_BARE_SYMBOL_REPORT_CANDIDATE_DRIFT","report_id":report.get("id"),"artifact":candidate.get("logical_path")});return False
    status=(payload.get("bare_symbol_validation") or {}).get("status")
    if status!="PASS":errors.append({"type":"BSL_BARE_SYMBOL_PROPERTY_NOT_PASS","report_id":report.get("id"),"artifact":candidate.get("logical_path"),"status":status});return False
    return True

def _validate_bsl_bare_symbol_gate(plan,ledger,machine_reports,errors):
    for candidate in _bsl_bare_symbol_intent_candidates(plan,ledger,errors):
        current=[row for row in (machine_reports or {}).values() if _bsl_bare_symbol_report_covers(row,candidate)]
        if not any(_bsl_bare_symbol_payload_passes(row,candidate,errors) for row in current):
            errors.append({"type":"BSL_BARE_SYMBOL_CURRENT_ANALYZER_REQUIRED","artifact":candidate.get("logical_path"),"candidate_sha256":candidate.get("sha256"),"tool":BSL_BARE_SYMBOL_TOOL,"property_id":BSL_BARE_SYMBOL_PROPERTY})

def _active_gating_check_bindings(plan):
    result={}
    for binding in plan.get("active_deliveries") or []:
        if not isinstance(binding,dict) or binding.get("enforcement")!="GATING":continue
        proof=binding.get("proof_binding") or {}; owner=proof.get("owner")
        if _has_text(owner) and owner.startswith("CHECK:"):result[owner]=binding
    return result


def _validate_capability_proof_bindings(plan,ledger_rules,errors):
    """GATING delivery is complete only through its existing canonical check proof."""
    for owner,binding in _active_gating_check_bindings(plan).items():
        capability=binding.get("capability_id"); proof=binding.get("proof_binding") or {}
        parts=owner.split(":",2)
        if len(parts)!=3:
            errors.append({"type":"CAPABILITY_PROOF_BINDING_INVALID","capability_id":capability,"owner":owner});continue
        _,rule_id,check_id=parts
        rule_row=ledger_rules.get(rule_id)
        check=next((x for x in (rule_row or {}).get("checks") or [] if isinstance(x,dict) and x.get("id")==check_id),None)
        if check is None:
            errors.append({"type":"CAPABILITY_PROOF_OWNER_MISSING","scope":"check","id":f"{rule_id}:{check_id}","rule":rule_id,"capability_id":capability});continue
        status=check.get("status")
        if status not in {"PASS","NOT_APPLICABLE"}:
            errors.append({"type":"CAPABILITY_PROOF_BINDING_UNRESOLVED","scope":"check","id":f"{rule_id}:{check_id}","rule":rule_id,"capability_id":capability,"status":status});continue
        accepted=set(proof.get("accepted_evidence") or [])
        actual=_evidence_kinds(check.get("evidence") or [])
        if not accepted or not (actual & accepted):
            errors.append({"type":"CAPABILITY_PROOF_EVIDENCE_NOT_ACCEPTED","scope":"check","id":f"{rule_id}:{check_id}","rule":rule_id,"capability_id":capability,"status":status,"accepted":sorted(accepted),"actual":sorted(actual)})


def evaluate(plan:dict, ledger:dict, registry:dict|None=None, external_intake:dict|None=None)->dict:
    registry=registry or load_registry(); rules=rule_map(registry); sm=registry["status_model"]
    blocking=set(sm["blocking_statuses"]); pending=set(sm["pending_statuses"])
    errors=[]; pending_items=[]; coverage=[]
    recompute=validate_plan_recomputation(plan,external_intake)
    errors.extend(recompute.get("errors") or [])
    if plan.get("release_intake")!=ledger.get("release_intake"):
        errors.append({"type":"RELEASE_INTAKE_DEPENDENCY_DRIFT","plan":plan.get("release_intake"),"ledger":ledger.get("release_intake")})
    trust=validate_trust_boundary(plan,ledger,registry)
    errors.extend(trust["errors"])

    actual_reg_sha=hashlib.sha256((ROOT/'RULES/rule_registry.json').read_bytes()).hexdigest()
    for label,doc in (("plan",plan),("ledger",ledger)):
        sha=(doc.get("registry") or {}).get("sha256")
        if sha != actual_reg_sha:errors.append({"type":"REGISTRY_DEPENDENCY_DRIFT","where":label,"expected":actual_reg_sha,"actual":sha})

    # Plan/ledger dependency identity may not be rewritten while filling proof.
    if plan.get('routing')!=ledger.get('routing'):errors.append({'type':'ROUTING_DEPENDENCY_DRIFT','plan':plan.get('routing'),'ledger':ledger.get('routing')})
    if plan.get('project_context')!=ledger.get('project_context'):errors.append({'type':'PROJECT_CONTEXT_DEPENDENCY_DRIFT','plan':plan.get('project_context'),'ledger':ledger.get('project_context')})
    if plan.get('baseline')!=ledger.get('baseline'):errors.append({'type':'BASELINE_DEPENDENCY_DRIFT','plan':plan.get('baseline'),'ledger':ledger.get('baseline')})
    baseline=plan.get('baseline')
    if baseline and (not isinstance(baseline,dict) or not _has_text(baseline.get('sha256'))):errors.append({'type':'BASELINE_IDENTITY_NOT_HASH_BOUND','baseline':baseline})
    _validate_current_sources(plan,errors)

    preq=plan.get("requirements") or {}; lreq=ledger.get("requirements") or {}
    if preq != lreq:errors.append({"type":"REQUIREMENTS_DEPENDENCY_DRIFT","plan":preq,"ledger":lreq})
    if preq.get("required"):
        if not preq.get("path"):errors.append({"type":"REQUIREMENTS_CONTRACT_MISSING"})
        elif preq.get("gate_result")!="PASS" or preq.get("gate_outcome") not in {"REQUIREMENTS_READY","REQUIREMENTS_READY_WITH_ASSUMPTIONS"}:
            errors.append({"type":"REQUIREMENTS_GATE_NOT_READY","result":preq.get("gate_result"),"outcome":preq.get("gate_outcome"),"errors":preq.get("gate_errors",[])})
        plan_surface=plan.get('routing',{}).get('surface'); plan_risk=plan.get('routing',{}).get('risk')
        req_surface=preq.get('surface'); req_risk=preq.get('risk'); req_set=_surface_set(req_surface); plan_set=_surface_set(plan_surface)
        coverage_ok=bool(req_set is not None and plan_set is not None and req_set.issuperset(plan_set) and req_risk in RISK_RANK and plan_risk in RISK_RANK and RISK_RANK[req_risk]>=RISK_RANK[plan_risk])
        if not coverage_ok:errors.append({'type':'REQUIREMENTS_CONTRACT_SCOPE_INSUFFICIENT','requirements_surface':req_surface,'requirements_risk':req_risk,'plan_surface':plan_surface,'plan_risk':plan_risk})
        if preq.get('coverage_sufficient') is not True:errors.append({'type':'REQUIREMENTS_COVERAGE_FLAG_INVALID','actual':preq.get('coverage_sufficient')})

    p_art=_artifact_map(plan.get('candidate_artifacts',[]),'plan',errors); l_art=_artifact_map(ledger.get('candidate_artifacts',[]),'ledger',errors)
    if p_art!=l_art:errors.append({'type':'CANDIDATE_DEPENDENCY_DRIFT','plan':sorted(p_art.items()),'ledger':sorted(l_art.items())})

    receipt_provenance=_validate_receipt_evidence_provenance(ledger,plan,registry,errors)
    machine_reports=_validate_machine_reports(ledger.get('machine_reports') or [],errors)
    _validate_query_literal_escape_gate(plan,ledger,machine_reports,registry,errors)
    _validate_bsl_bare_symbol_gate(plan,ledger,machine_reports,errors)
    runtime_cases=_validate_runtime_cases(ledger.get('runtime_cases') or [],errors,pending_items,blocking,pending)
    performance_review=validate_performance_review(plan,ledger,runtime_cases,registry)
    errors.extend(performance_review.get("errors") or [])
    independent_reviews=validate_independent_reviews(ledger.get('independent_reviews'),plan,errors)
    if (plan.get('routing') or {}).get('mode')!='ANALYSIS_ONLY':
        intent_result=validate_intent_map(ledger.get('implementation_intent_map'),plan,ledger)
        errors.extend(intent_result.get('errors') or [])
    _validate_evidence_reuse(ledger,errors,plan)
    _validate_artifact_requests(ledger.get("artifact_requests") or [],errors,pending_items,machine_reports,runtime_cases)

    # Plan itself must still represent the full registry. Dict-comprehension collapse is forbidden.
    plan_gate_rows=plan.get('gate_plan') or []
    planned_gates={}
    for index,row in enumerate(plan_gate_rows):
        gid=row.get('gate')
        if not _has_text(gid):errors.append({'type':'PLAN_GATE_WITHOUT_ID','index':index});continue
        if gid in planned_gates:errors.append({'type':'PLAN_GATE_DUPLICATE','id':gid});continue
        planned_gates[gid]=row
    registry_gate_ids={x['id'] for x in registry.get('gates',[])}
    if set(planned_gates)!=registry_gate_ids:errors.append({'type':'PLAN_GATE_COVERAGE_DRIFT','missing':sorted(registry_gate_ids-set(planned_gates)),'extra':sorted(set(planned_gates)-registry_gate_ids)})

    route_rows=plan.get('rules') or []; routes={}
    for index,row in enumerate(route_rows):
        rid=row.get('id')
        if not _has_text(rid):errors.append({'type':'PLAN_RULE_WITHOUT_ID','index':index});continue
        if rid in routes:errors.append({'type':'PLAN_RULE_DUPLICATE','id':rid});continue
        if rid not in rules:errors.append({'type':'PLAN_RULE_UNKNOWN','id':rid});continue
        routes[rid]=row
    if set(routes)!=set(rules):errors.append({'type':'PLAN_RULE_COVERAGE_DRIFT','missing':sorted(set(rules)-set(routes)),'extra':sorted(set(routes)-set(rules))})

    expected=[]
    for rid,route in routes.items():
        rule=rules[rid]
        expected_route_policy=proof_policy_for(rule,registry)
        if route.get('proof_policy')!=expected_route_policy:
            errors.append({'type':'PLAN_PROOF_POLICY_DRIFT','id':rid,'expected':expected_route_policy,'actual':route.get('proof_policy')})
        if rule.get('tier')==0 or route.get('active'):expected.append(rid)
    expected_checks={rid:[x['id'] for x in rules[rid].get('checks',[])] for rid in expected}
    gating_check_bindings=_active_gating_check_bindings(plan)
    risk=(plan.get('routing') or {}).get('risk')

    expected_machine_findings=_verified_machine_finding_expectations(machine_reports,p_art,registry,errors)
    _validate_machine_findings(
        ledger.get("machine_findings") or [],expected_machine_findings,rules,errors,pending_items,
        machine_reports,independent_reviews,plan,receipt_provenance,risk,
    )

    _validate_gap_discovery(ledger.get("gap_discovery"),registry,errors,pending_items,ledger.get("rules"),runtime_cases,machine_reports)

    ledger_gates=_index_rows(ledger.get('gates') or [],'id','gate',errors)
    for gid in sorted(set(ledger_gates)-set(planned_gates)):errors.append({'type':'UNPLANNED_GATE_ROW','id':gid})
    for gid,gp in planned_gates.items():
        row=ledger_gates.get(gid)
        if not row:errors.append({"type":"GATE_MISSING","id":gid});continue
        status=row.get("status")
        if status in blocking or not status:errors.append({"type":"GATE_BLOCKING_OR_UNRESOLVED","id":gid,"status":status});continue
        if status in pending:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'gate','id':gid})
            pending_items.append({"type":"GATE_PENDING","id":gid,"status":status})
        elif status=="PASS":_validate_evidence(row.get('evidence'),errors,'gate',gid,machine_reports,runtime_cases)
        elif status=="NOT_APPLICABLE":
            if gp.get('status')=='REQUIRED':errors.append({'type':'GATE_NA_FOR_REQUIRED_PLAN','id':gid})
            if not is_substantive_reason(row.get("reason")):errors.append({"type":"NA_REASON_NOT_SUBSTANTIVE","scope":"gate","id":gid,"reason":row.get("reason")})
        else:errors.append({'type':'UNKNOWN_GATE_STATUS','id':gid,'status':status})

    adversarial_gate=ledger_gates.get('ADVERSARIAL_VALIDATION') or {}; adversarial_contract=registry.get('adversarial_case_contract') or {}
    min_risk=adversarial_contract.get('min_risk','R1_CONTRACT')
    adversarial_planned=(planned_gates.get('ADVERSARIAL_VALIDATION') or {}).get('status')=='REQUIRED'
    require_adversarial=(adversarial_planned and risk in RISK_RANK and min_risk in RISK_RANK and RISK_RANK[risk]>=RISK_RANK[min_risk] and (plan.get('routing') or {}).get('mode')!='ANALYSIS_ONLY')
    _validate_adversarial_cases(ledger.get('adversarial_cases') or [],errors,pending_items,blocking,pending,machine_reports,runtime_cases,require_adversarial)

    ledger_rules=_index_rows(ledger.get('rules') or [],'id','rule',errors)
    for rid in sorted(set(ledger_rules)-set(expected)):errors.append({'type':'UNROUTED_RULE_ROW','id':rid})
    for rid in expected:
        rule=rules[rid]; route=routes[rid]; row=ledger_rules.get(rid)
        if not row:errors.append({"type":"RULE_MISSING","id":rid});continue
        expected_rule_claim=rule_claim_id(rid)
        expected_policy=proof_policy_for(rule,registry)
        validate_row_claim_id(row,expected_rule_claim,errors,"rule",rid)
        validate_policy_snapshot(row,expected_policy,errors,"rule",rid)

        # Child structure is an independent obligation. Validate it before any
        # parent-status short-circuit so BLOCKING/PENDING/N/A cannot hide a
        # deleted, extra or claim-rebound child check.
        checks=_index_rows(row.get('checks') or [],'id',f'check:{rid}',errors)
        expected_check_ids=set(expected_checks[rid])
        for cid in sorted(set(checks)-expected_check_ids):errors.append({'type':'UNPLANNED_CHECK_ROW','rule':rid,'id':cid})
        for check in rule.get("checks",[]):
            cid=check["id"]; c=checks.get(cid)
            if not c:
                errors.append({"type":"CHECK_MISSING","rule":rid,"id":cid})
                continue
            validate_row_claim_id(c,check_claim_id(rid,cid),errors,"check",f"{rid}:{cid}")
            validate_policy_snapshot(c,expected_policy,errors,"check",f"{rid}:{cid}")

        status=row.get("status")
        parent_terminal=False
        if status in blocking or not status:
            errors.append({"type":"RULE_BLOCKING_OR_UNRESOLVED","id":rid,"status":status})
        elif status=="NOT_APPLICABLE":
            parent_terminal=True
            if not is_substantive_reason(row.get("reason")):
                errors.append({"type":"NA_REASON_NOT_SUBSTANTIVE","scope":"rule","id":rid,"reason":row.get("reason")})
            if route.get("activation_status")=="REQUIRED":
                rebuttal=row.get("applicability_rebuttal") if isinstance(row.get("applicability_rebuttal"),dict) else {}
                na_evidence=row.get("evidence") or rebuttal.get("evidence") or []
                if not na_evidence:
                    errors.append({"type":"REQUIRED_RULE_NA_WITHOUT_PROOF","scope":"rule","id":rid})
                else:
                    verified=_validate_evidence(na_evidence,errors,'rule',rid,machine_reports,runtime_cases,expected_claim_id=expected_rule_claim,allowed_kinds=rule.get('evidence_modes',[]),require_primary=True,plan=plan,receipt_provenance=receipt_provenance,proof_policy=expected_policy)
                    validate_claim_policy(expected_policy,verified,independent_reviews,expected_rule_claim,errors,'rule',rid,risk=risk)
        elif status not in {"PASS",*pending}:
            errors.append({"type":"UNKNOWN_RULE_STATUS","id":rid,"status":status})
        else:
            parent_terminal=True
            if status in pending:
                pending_items.append({"type":"RULE_PENDING","id":rid,"status":status})
                if not _has_text(row.get("reason")):errors.append({"type":"PENDING_WITHOUT_REASON","scope":"rule","id":rid})
            verified=_validate_evidence(row.get('evidence'),errors,'rule',rid,machine_reports,runtime_cases,expected_claim_id=expected_rule_claim,allowed_kinds=rule.get('evidence_modes',[]),require_primary=(status=='PASS'),plan=plan,receipt_provenance=receipt_provenance,proof_policy=expected_policy)
            if status=='PASS':validate_claim_policy(expected_policy,verified,independent_reviews,expected_rule_claim,errors,'rule',rid,risk=risk)
            kinds=_evidence_kinds(row.get("evidence",[]))
            for mode in rule.get("evidence_modes",[]):
                if status in pending and mode=="RUNTIME":continue
                if mode not in kinds:errors.append({"type":"EVIDENCE_MODE_MISSING","id":rid,"mode":mode,"status":status})

        # Child checks are always validated, including when the parent is BLOCKING or N/A.
        child_pending=False
        for check in rule.get("checks",[]):
            cid=check["id"]; c=checks.get(cid)
            if not c:continue
            expected_check_claim=check_claim_id(rid,cid)
            cs=c.get("status")
            if cs in blocking or not cs:
                errors.append({"type":"CHECK_BLOCKING_OR_UNRESOLVED","rule":rid,"id":cid,"status":cs});continue
            if cs in pending:
                child_pending=True; pending_items.append({"type":"CHECK_PENDING","rule":rid,"id":cid,"status":cs})
                if not _has_text(c.get("reason")):errors.append({"type":"PENDING_WITHOUT_REASON","scope":"check","rule":rid,"id":cid})
            elif cs=="PASS":
                verified=_validate_evidence(c.get('evidence'),errors,'check',f'{rid}:{cid}',machine_reports,runtime_cases,expected_claim_id=expected_check_claim,allowed_kinds=rule.get('evidence_modes',[]),require_primary=True,plan=plan,receipt_provenance=receipt_provenance,proof_policy=expected_policy)
                validate_claim_policy(expected_policy,verified,independent_reviews,expected_check_claim,errors,'check',f'{rid}:{cid}',risk=risk)
            elif cs=="NOT_APPLICABLE":
                if not is_substantive_reason(c.get("reason")):
                    errors.append({"type":"NA_REASON_NOT_SUBSTANTIVE","scope":"check","rule":rid,"id":cid,"reason":c.get("reason")})
                gating_binding=gating_check_bindings.get(expected_check_claim)
                if gating_binding is not None:
                    proof=gating_binding.get("proof_binding") or {}
                    allowed_kinds=proof.get("accepted_evidence") or []
                    if not c.get("evidence"):
                        errors.append({"type":"CAPABILITY_BOUND_CHECK_NA_WITHOUT_PROOF","scope":"check","rule":rid,"id":cid,"capability_id":gating_binding.get("capability_id")})
                    else:
                        verified=_validate_evidence(c.get('evidence'),errors,'check',f'{rid}:{cid}',machine_reports,runtime_cases,expected_claim_id=expected_check_claim,allowed_kinds=allowed_kinds,require_primary=True,plan=plan,receipt_provenance=receipt_provenance,proof_policy=expected_policy)
                        validate_claim_policy(expected_policy,verified,independent_reviews,expected_check_claim,errors,'check',f'{rid}:{cid}',risk=risk)
                elif status!="NOT_APPLICABLE":
                    verified=_validate_evidence(c.get('evidence'),errors,'check',f'{rid}:{cid}',machine_reports,runtime_cases,expected_claim_id=expected_check_claim,allowed_kinds=rule.get('evidence_modes',[]),require_primary=True,plan=plan,receipt_provenance=receipt_provenance,proof_policy=expected_policy)
                    validate_claim_policy(expected_policy,verified,independent_reviews,expected_check_claim,errors,'check',f'{rid}:{cid}',risk=risk)
            else:
                errors.append({"type":"UNKNOWN_CHECK_STATUS","rule":rid,"id":cid,"status":cs})
        if status=="NOT_APPLICABLE":
            for cid,c in checks.items():
                if c.get("status")!="NOT_APPLICABLE":
                    errors.append({"type":"RULE_NA_CHILD_STATUS_INCONSISTENT","rule":rid,"id":cid,"status":c.get("status")})
        if status=="PASS" and child_pending:errors.append({"type":"RULE_STATUS_INCONSISTENT","id":rid,"status":"PASS","child":"PENDING"})
        if status in pending and not child_pending and "RUNTIME" not in rule.get("evidence_modes",[]):errors.append({"type":"RULE_STATUS_INCONSISTENT","id":rid,"status":status,"reason":"rule has no pending child and no runtime evidence mode"})
        if parent_terminal:coverage.append(rid)

    _validate_capability_proof_bindings(plan,ledger_rules,errors)

    levels=_index_rows(ledger.get('review_levels') or [],'id','review_level',errors)
    for lid in sorted(set(levels)-set(REVIEW_LEVELS)):errors.append({'type':'UNKNOWN_REVIEW_LEVEL','id':lid})
    level_policies=((registry.get("proof_policy_contract") or {}).get("review_levels") or {})
    for lid in REVIEW_LEVELS:
        row=levels.get(lid)
        if not row:errors.append({"type":"REVIEW_LEVEL_MISSING","id":lid});continue
        st=row.get("status"); level_policy=level_policies.get(lid)
        if level_policy is not None:
            validate_policy_snapshot(row,level_policy,errors,"review_level",lid)
            expected_level_claim=f"REVIEW_LEVEL:{lid}"
            if row.get("claim_id")!=expected_level_claim:
                errors.append({"type":"PROOF_CLAIM_ROW_ID_DRIFT","scope":"review_level","id":lid,"expected":expected_level_claim,"actual":row.get("claim_id")})
        else:expected_level_claim=None
        if st in blocking or not st:errors.append({"type":"REVIEW_LEVEL_UNRESOLVED","id":lid,"status":st})
        elif st=="PASS":
            if level_policy is None:_validate_evidence(row.get('evidence'),errors,'review_level',lid,machine_reports,runtime_cases)
            else:
                verified=_validate_evidence(row.get('evidence'),errors,'review_level',lid,machine_reports,runtime_cases,expected_claim_id=expected_level_claim,allowed_kinds=ALLOWED_EVIDENCE_KINDS,require_primary=True,plan=plan,receipt_provenance=receipt_provenance,proof_policy=level_policy)
                validate_claim_policy(level_policy,verified,independent_reviews,expected_level_claim,errors,'review_level',lid,risk=risk)
        elif st=="NOT_APPLICABLE":
            if not is_substantive_reason(row.get("reason")):errors.append({"type":"NA_REASON_NOT_SUBSTANTIVE","scope":"review_level","id":lid,"reason":row.get("reason")})
            if level_policy is None:_validate_evidence(row.get('evidence'),errors,'review_level',lid,machine_reports,runtime_cases)
            else:
                verified=_validate_evidence(row.get('evidence'),errors,'review_level',lid,machine_reports,runtime_cases,expected_claim_id=expected_level_claim,allowed_kinds=ALLOWED_EVIDENCE_KINDS,require_primary=True,plan=plan,receipt_provenance=receipt_provenance,proof_policy=level_policy)
                validate_claim_policy(level_policy,verified,independent_reviews,expected_level_claim,errors,'review_level',lid,risk=risk)
        elif st in pending:
            if not _has_text(row.get('reason')):errors.append({'type':'PENDING_WITHOUT_REASON','scope':'review_level','id':lid})
            pending_items.append({"type":"REVIEW_LEVEL_PENDING","id":lid,"status":st})
        else:errors.append({'type':'UNKNOWN_REVIEW_LEVEL_STATUS','id':lid,'status':st})

    require_forward=any(bool(x.get('onec') or x.get('cleverence')) for x in plan.get('candidate_artifacts') or [])
    _validate_bidirectional(ledger,expected,expected_checks,errors,pending_items,blocking,pending,machine_reports,runtime_cases,set(rules),require_forward)

    # A section explicitly named blocking_findings may never coexist with PROVEN.
    if ledger.get('blocking_findings'):
        errors.append({'type':'BLOCKING_FINDINGS_PRESENT','count':len(ledger.get('blocking_findings') or [])})

    extraction=ledger.get("knowledge_extraction") or {}; extraction_outcome=extraction.get("outcome")
    allowed_extraction={"PROMOTED","PROJECT_ONLY","NO_REUSABLE_KNOWLEDGE","EVIDENCE_PENDING"}
    if extraction_outcome not in allowed_extraction:errors.append({"type":"KNOWLEDGE_EXTRACTION_OUTCOME_INVALID","actual":extraction_outcome})
    elif extraction_outcome=="EVIDENCE_PENDING":errors.append({"type":"KNOWLEDGE_EXTRACTION_PENDING"})
    elif extraction_outcome=="PROMOTED":
        items=extraction.get("items") or []
        if not items:errors.append({"type":"KNOWLEDGE_EXTRACTION_PROMOTED_WITHOUT_ITEMS"})
        for index,item in enumerate(items):
            for field in ("evidence","universal_statement","owner","coverage","deduplication_decision"):
                if not item.get(field):errors.append({"type":"KNOWLEDGE_EXTRACTION_ITEM_INCOMPLETE","index":index,"field":field})
    elif extraction_outcome=="PROJECT_ONLY":
        if not extraction.get("project_context_updates") and not _has_text(extraction.get("reason")):errors.append({"type":"KNOWLEDGE_EXTRACTION_PROJECT_ONLY_WITHOUT_TARGET"})
    elif extraction_outcome=="NO_REUSABLE_KNOWLEDGE" and not _has_text(extraction.get("reason")):errors.append({"type":"KNOWLEDGE_EXTRACTION_NO_RESULT_WITHOUT_REASON"})

    analysis_only=plan.get("routing",{}).get("mode")=="ANALYSIS_ONLY"
    if errors:outcome="BLOCKED"
    elif pending_items:outcome="READY_FOR_RUNTIME_TEST"
    elif analysis_only:outcome="ANALYSIS_COMPLETE"
    else:outcome="PROVEN"
    resolution=_resolution_protocol(ledger,errors)
    return {"result":"PASS" if not errors else "FAIL","release_outcome":outcome,"implementation_readiness":performance_review,"errors":errors,"pending":pending_items,"covered_rules":coverage,
            "input_identity":{"plan_sha256":_artifact_fingerprint(plan),"ledger_sha256":_artifact_fingerprint(ledger)},
            "evidence_source_policy":trust["evidence_source_policy"],
            "plan_recomputation":recompute.get("result"),
            "resolution_verifier":{k:v for k,v in resolution.items() if k!="verdicts"},
            "resolution_verdicts":resolution["verdicts"],
            "rule":"PROVEN requires recomputed current obligations, exact rule/check claim binding, admissible primary proof, exact dependency identity, verifier-owned machine/runtime leaves, independent bidirectional coverage and no unresolved blocking finding. READY_FOR_RUNTIME_TEST is not PROVEN."}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--plan",required=True); ap.add_argument("--ledger",required=True); ap.add_argument("--intake"); ap.add_argument("--output")
    a=ap.parse_args(); plan=json.loads(Path(a.plan).read_text(encoding="utf-8-sig")); ledger=json.loads(Path(a.ledger).read_text(encoding="utf-8-sig")); intake=load_intake(a.intake) if a.intake else None; result=evaluate(plan,ledger,external_intake=intake)
    out=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    print(out,end=""); raise SystemExit(0 if result["result"]=="PASS" else 2)

if __name__=="__main__":main()
