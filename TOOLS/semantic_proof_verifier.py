#!/usr/bin/env python3
"""Release-verifier helpers for registry-owned semantic proof policy."""
from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from semantic_review import verify_review_receipt


def _text(v):return isinstance(v,str) and bool(v.strip())


def validate_independent_reviews(rows,plan,errors):
    """Replay every declared review receipt and index only verifier-accepted PASS rows."""
    index={}
    if rows is None:rows=[]
    if not isinstance(rows,list):
        errors.append({"type":"INDEPENDENT_REVIEW_ROWS_INVALID"})
        return index
    for pos,row in enumerate(rows):
        if not isinstance(row,dict):
            errors.append({"type":"INDEPENDENT_REVIEW_ROW_NOT_OBJECT","index":pos});continue
        claim=row.get("claim_id"); rule_id=row.get("rule_id"); check_id=row.get("check_id")
        ref=row.get("receipt_ref") or row.get("ref"); receipt_sha=row.get("receipt_sha256")
        author=row.get("author_execution_id")
        if not all(_text(x) for x in (claim,rule_id,ref,receipt_sha,author)):
            errors.append({"type":"INDEPENDENT_REVIEW_ROW_INCOMPLETE","index":pos});continue
        try:
            result=verify_review_receipt(ref,expected_sha256=receipt_sha,plan=plan,
                expected_claim_id=claim,expected_rule_id=rule_id,expected_check_id=check_id,
                expected_author_execution_id=author,require_full_changeset=True)
        except Exception as exc:
            errors.append({"type":"INDEPENDENT_REVIEW_VERIFIER_UNAVAILABLE","index":pos,"claim_id":claim,"error":str(exc)})
            continue
        for detail in result.get("errors") or []:
            errors.append({"type":"INDEPENDENT_REVIEW_INVALID","index":pos,"claim_id":claim,"detail":detail})
        if result.get("integrity_result")!="PASS":
            continue
        if result.get("review_result")!="PASS":
            errors.append({"type":"INDEPENDENT_REVIEW_REJECTED","index":pos,"claim_id":claim,"defects":(result.get("payload") or {}).get("defects") or []})
            continue
        if claim in index:
            errors.append({"type":"INDEPENDENT_REVIEW_DUPLICATE_FOR_CLAIM","claim_id":claim});continue
        index[claim]={
            "row":row,
            "receipt_sha256":result.get("receipt_sha256"),
            "content_sha256":result.get("content_sha256"),
            "separation_status":result.get("separation_status"),
            "external_reviewer_status":result.get("external_reviewer_status"),
        }
    return index


def validate_policy_snapshot(row,expected_policy,errors,scope,rid):
    actual=(row or {}).get("proof_policy")
    if actual!=expected_policy:
        errors.append({"type":"PROOF_POLICY_SNAPSHOT_DRIFT","scope":scope,"id":rid,"expected":expected_policy,"actual":actual})
        return False
    return True


def validate_claim_policy(policy,verified_evidence,review_index,expected_claim_id,errors,scope,rid,risk=None):
    policy=policy if isinstance(policy,dict) else {}
    claim_class=policy.get("claim_class")
    required=list(policy.get("required_roles") or [])
    satisfied=set()
    if any(isinstance(x,dict) and str(x.get("kind") or "").upper()=="SOURCE_REQUIRED"
           and x.get("_verifier_proof_role")=="PRIMARY_VERIFIED_SOURCE" for x in (verified_evidence or [])):
        satisfied.add("EXACT_SOURCE")
    if expected_claim_id in (review_index or {}):
        satisfied.add("INDEPENDENT_REVIEW")
    if any(isinstance(x,dict) and str(x.get("kind") or "").upper()=="MACHINE"
           and x.get("_verifier_machine_property_confirmed") is True for x in (verified_evidence or [])):
        satisfied.add("MACHINE_EVIDENCE")
    if any(isinstance(x,dict) and str(x.get("kind") or "").upper()=="RUNTIME"
           and x.get("_verifier_runtime_property_confirmed") is True for x in (verified_evidence or [])):
        satisfied.add("PLATFORM_RUNTIME")
    if any(isinstance(x,dict) and str(x.get("kind") or "").upper()=="SEMANTIC" for x in (verified_evidence or [])):
        satisfied.add("SELF_SEMANTIC_REASONING")

    if claim_class=="ARCHITECTURE_SEMANTIC":
        # Self-authored semantic text is explicitly supporting-only for this class.
        for item in verified_evidence or []:
            if isinstance(item,dict) and str(item.get("kind") or "").upper()=="SEMANTIC":
                item["_verifier_proof_role"]="SUPPORTING_ONLY"

    runtime_from=policy.get("runtime_required_from")
    risk_rank={"R0_LOCAL":0,"R1_CONTRACT":1,"R2_STATEFUL_RUNTIME":2,"R3_CROSS_SYSTEM":3}
    if runtime_from in risk_rank and risk in risk_rank and risk_rank[risk]>=risk_rank[runtime_from]:
        if "PLATFORM_RUNTIME" not in required:required.append("PLATFORM_RUNTIME")

    missing=[role for role in required if role not in satisfied]
    for role in missing:
        if role=="INDEPENDENT_REVIEW":
            errors.append({"type":"INDEPENDENT_REVIEW_REQUIRED","scope":scope,"id":rid,"claim_id":expected_claim_id})
        elif role=="EXACT_SOURCE":
            errors.append({"type":"EXACT_SOURCE_REQUIRED","scope":scope,"id":rid,"claim_id":expected_claim_id})
        elif role=="PLATFORM_RUNTIME":
            errors.append({"type":"PLATFORM_RUNTIME_REQUIRED","scope":scope,"id":rid,"claim_id":expected_claim_id})
        else:
            errors.append({"type":"PROOF_ROLE_REQUIRED","scope":scope,"id":rid,"claim_id":expected_claim_id,"role":role})
    return {"required_roles":required,"satisfied_roles":sorted(satisfied),"missing_roles":missing}
