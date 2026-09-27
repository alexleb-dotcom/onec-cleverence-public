#!/usr/bin/env python3
"""Content-bound separated semantic review receipts.

This contract reduces correlated self-review by binding a reviewer disposition to
the exact current plan/change-set and requiring a reviewer execution identity
different from the author execution identity. It does not prove external-system
or cryptographic independence without a separately trusted adapter/root.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from proof_identity import plan_binding, artifact_delta, canonical_json

SCHEMA_VERSION=1
KIND="INDEPENDENT_SEMANTIC_REVIEW"
SEPARATION_STATUS="CONTENT_SESSION_SEPARATED"
EXTERNAL_STATUS_UNVERIFIED="EXTERNAL_REVIEWER_UNVERIFIED"
VERDICTS={"PASS","FAIL"}


def _has_text(value):return isinstance(value,str) and bool(value.strip())
def _sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def _content_sha(payload:dict)->str:
    body={k:v for k,v in payload.items() if k!="content_sha256"}
    return _sha(canonical_json(body).encode("utf-8"))


def _canonical_anchor(row):
    if not isinstance(row,dict):raise ValueError("source anchor must be an object")
    logical=row.get("logical_path"); candidate_sha=row.get("candidate_sha256"); baseline_sha=row.get("baseline_sha256")
    if not _has_text(logical) or (not _has_text(candidate_sha) and not _has_text(baseline_sha)):
        raise ValueError("source anchor requires logical_path and candidate_sha256 and/or baseline_sha256")
    result={"logical_path":logical}
    if _has_text(row.get("action")):result["action"]=row["action"]
    if _has_text(candidate_sha):result["candidate_sha256"]=candidate_sha
    if _has_text(baseline_sha):result["baseline_sha256"]=baseline_sha
    if _has_text(row.get("fragment")):result["fragment"]=row["fragment"]
    return result


def build_review_payload(plan:dict,*,author_execution_id:str,reviewer_execution_id:str,
                         claim_id:str,rule_id:str,check_id:str|None,source_anchors:list,
                         reviewer_verdict:str,defects:list|None=None,limitations:list|None=None,
                         external_reviewer_status:str=EXTERNAL_STATUS_UNVERIFIED)->dict:
    if not all(_has_text(x) for x in (author_execution_id,reviewer_execution_id,claim_id,rule_id)):
        raise ValueError("author/reviewer execution ids, claim_id and rule_id are required")
    if author_execution_id==reviewer_execution_id:
        raise ValueError("author and reviewer execution ids must differ")
    if reviewer_verdict not in VERDICTS:raise ValueError("reviewer_verdict must be PASS or FAIL")
    anchors=[_canonical_anchor(x) for x in (source_anchors or [])]
    if not anchors:raise ValueError("independent semantic review requires source anchors")
    binding=plan_binding(plan)
    payload={
        "schema_version":SCHEMA_VERSION,
        "kind":KIND,
        "separation_status":SEPARATION_STATUS,
        "external_reviewer_status":external_reviewer_status,
        "project_identity":binding["project_identity"],
        "author_execution_id":author_execution_id,
        "reviewer_execution_id":reviewer_execution_id,
        "baseline_identity":binding["baseline_identity"],
        "candidate_identity":binding["candidate_identity"],
        "requirements_identity":binding["requirements_identity"],
        "review_plan_sha256":binding["review_plan_sha256"],
        "claim_id":claim_id,
        "rule_id":rule_id,
        "check_id":check_id,
        "source_anchors":anchors,
        "reviewer_verdict":reviewer_verdict,
        "defects":list(defects or []),
        "limitations":list(limitations or [
            "Content/session separation is procedural evidence. External reviewer provenance is not independently verified without a trusted adapter."
        ]),
    }
    payload["content_sha256"]=_content_sha(payload)
    return payload


def write_review_receipt(path_value,plan:dict,**kwargs)->dict:
    payload=build_review_payload(plan,**kwargs)
    path=Path(path_value); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return payload


def _expected_anchor_map(plan:dict):
    return {
        logical:{
            "action":row.get("action"),
            "candidate_sha256":row.get("candidate_sha256"),
            "baseline_sha256":row.get("baseline_sha256"),
        }
        for logical,row in artifact_delta(plan).items()
    }


def verify_review_receipt(ref,*,expected_sha256:str|None,plan:dict,expected_claim_id:str,
                          expected_rule_id:str,expected_check_id:str|None=None,
                          expected_author_execution_id:str|None=None,
                          require_full_changeset:bool=True)->dict:
    errors=[]; path=Path(str(ref or ""))
    if not path.is_file():
        return {"integrity_result":"FAIL","review_result":None,"errors":[{"type":"INDEPENDENT_REVIEW_RECEIPT_MISSING","ref":str(path)}]}
    raw=path.read_bytes(); receipt_sha=_sha(raw)
    if expected_sha256 and receipt_sha!=expected_sha256:
        errors.append({"type":"INDEPENDENT_REVIEW_RECEIPT_HASH_DRIFT","expected":expected_sha256,"actual":receipt_sha})
    try:payload=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        return {"integrity_result":"FAIL","review_result":None,"errors":[{"type":"INDEPENDENT_REVIEW_RECEIPT_PARSE_ERROR","error":str(exc)}],"receipt_sha256":receipt_sha}
    if payload.get("schema_version")!=SCHEMA_VERSION:errors.append({"type":"INDEPENDENT_REVIEW_SCHEMA_UNSUPPORTED","actual":payload.get("schema_version")})
    if payload.get("kind")!=KIND:errors.append({"type":"INDEPENDENT_REVIEW_KIND_INVALID","actual":payload.get("kind")})
    if payload.get("content_sha256")!=_content_sha(payload):
        errors.append({"type":"INDEPENDENT_REVIEW_CONTENT_HASH_DRIFT"})
    if payload.get("separation_status")!=SEPARATION_STATUS:
        errors.append({"type":"INDEPENDENT_REVIEW_SEPARATION_STATUS_INVALID","actual":payload.get("separation_status")})
    author=payload.get("author_execution_id"); reviewer=payload.get("reviewer_execution_id")
    if not _has_text(author) or not _has_text(reviewer):
        errors.append({"type":"INDEPENDENT_REVIEW_EXECUTION_ID_MISSING"})
    elif author==reviewer:
        errors.append({"type":"INDEPENDENT_REVIEW_AUTHOR_REVIEWER_SAME_EXECUTION","execution_id":author})
    if expected_author_execution_id and author!=expected_author_execution_id:
        errors.append({"type":"INDEPENDENT_REVIEW_AUTHOR_EXECUTION_MISMATCH","expected":expected_author_execution_id,"actual":author})
    binding=plan_binding(plan)
    for field in ("project_identity","baseline_identity","candidate_identity","requirements_identity","review_plan_sha256"):
        if payload.get(field)!=binding.get(field):
            errors.append({"type":"INDEPENDENT_REVIEW_PLAN_BINDING_MISMATCH","field":field,"expected":binding.get(field),"actual":payload.get(field)})
    if payload.get("claim_id")!=expected_claim_id:
        errors.append({"type":"INDEPENDENT_REVIEW_CLAIM_MISMATCH","expected":expected_claim_id,"actual":payload.get("claim_id")})
    if payload.get("rule_id")!=expected_rule_id:
        errors.append({"type":"INDEPENDENT_REVIEW_RULE_MISMATCH","expected":expected_rule_id,"actual":payload.get("rule_id")})
    if payload.get("check_id")!=expected_check_id:
        errors.append({"type":"INDEPENDENT_REVIEW_CHECK_MISMATCH","expected":expected_check_id,"actual":payload.get("check_id")})
    verdict=payload.get("reviewer_verdict")
    if verdict not in VERDICTS:errors.append({"type":"INDEPENDENT_REVIEW_VERDICT_INVALID","actual":verdict})
    defects=payload.get("defects"); limitations=payload.get("limitations")
    if not isinstance(defects,list):
        errors.append({"type":"INDEPENDENT_REVIEW_DEFECTS_INVALID"})
    elif verdict=="PASS" and defects:
        errors.append({"type":"INDEPENDENT_REVIEW_PASS_WITH_DEFECTS","defect_count":len(defects)})
    if not isinstance(limitations,list) or not limitations:
        errors.append({"type":"INDEPENDENT_REVIEW_LIMITATIONS_MISSING"})
    anchors=payload.get("source_anchors")
    if not isinstance(anchors,list) or not anchors:
        errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHORS_MISSING"}); anchors=[]
    expected=_expected_anchor_map(plan); seen=set()
    for index,row in enumerate(anchors):
        try:anchor=_canonical_anchor(row)
        except ValueError as exc:
            errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_INVALID","index":index,"error":str(exc)});continue
        logical=anchor["logical_path"]; expected_row=expected.get(logical)
        if not expected_row:
            errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_OUTSIDE_CHANGESET","index":index,"logical_path":logical});continue
        expected_action=expected_row.get("action")
        if anchor.get("action") and anchor.get("action")!=expected_action:
            errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_ACTION_MISMATCH","index":index,"logical_path":logical,"expected":expected_action,"actual":anchor.get("action")})
        expected_candidate=expected_row.get("candidate_sha256"); expected_baseline=expected_row.get("baseline_sha256")
        if expected_candidate and anchor.get("candidate_sha256")!=expected_candidate:
            errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_HASH_MISMATCH","index":index,"logical_path":logical,"side":"candidate","expected":expected_candidate,"actual":anchor.get("candidate_sha256")})
        if expected_action=="delete" and anchor.get("baseline_sha256")!=expected_baseline:
            errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_HASH_MISMATCH","index":index,"logical_path":logical,"side":"baseline","expected":expected_baseline,"actual":anchor.get("baseline_sha256")})
        elif anchor.get("baseline_sha256") and expected_baseline and anchor.get("baseline_sha256")!=expected_baseline:
            errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_HASH_MISMATCH","index":index,"logical_path":logical,"side":"baseline","expected":expected_baseline,"actual":anchor.get("baseline_sha256")})
        if logical in seen:errors.append({"type":"INDEPENDENT_REVIEW_SOURCE_ANCHOR_DUPLICATE","logical_path":logical})
        seen.add(logical)
    if require_full_changeset:
        missing=sorted(set(expected)-seen)
        if missing:errors.append({"type":"INDEPENDENT_REVIEW_CHANGESET_COVERAGE_INCOMPLETE","missing":missing})
    external_status=payload.get("external_reviewer_status")
    if external_status!=EXTERNAL_STATUS_UNVERIFIED:
        errors.append({"type":"INDEPENDENT_REVIEW_EXTERNAL_VERIFICATION_UNSUPPORTED","actual":external_status,"required":EXTERNAL_STATUS_UNVERIFIED})
    return {
        "integrity_result":"PASS" if not errors else "FAIL",
        "review_result":verdict,
        "errors":errors,
        "payload":payload,
        "receipt_sha256":receipt_sha,
        "content_sha256":payload.get("content_sha256"),
        "separation_status":payload.get("separation_status"),
        "external_reviewer_status":external_status,
    }


def main()->int:
    ap=argparse.ArgumentParser(description="Verify a content-bound separated semantic review receipt.")
    ap.add_argument("--receipt",required=True); ap.add_argument("--plan",required=True)
    ap.add_argument("--claim-id",required=True); ap.add_argument("--rule-id",required=True); ap.add_argument("--check-id")
    ap.add_argument("--receipt-sha256"); ap.add_argument("--author-execution-id")
    a=ap.parse_args()
    plan=json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    result=verify_review_receipt(a.receipt,expected_sha256=a.receipt_sha256,plan=plan,
        expected_claim_id=a.claim_id,expected_rule_id=a.rule_id,expected_check_id=a.check_id,
        expected_author_execution_id=a.author_execution_id)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["integrity_result"]=="PASS" and result["review_result"]=="PASS" else 2


if __name__=="__main__":raise SystemExit(main())
