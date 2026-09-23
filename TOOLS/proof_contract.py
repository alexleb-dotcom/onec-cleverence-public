#!/usr/bin/env python3
"""Exact proof-obligation binding for rule/check evidence.

Evidence kind alone is never sufficient to establish primary proof. Supporting
or attach-only evidence stays supporting even when a model changes the row
status to PASS. Release verifiers may add private verifier-owned annotations
after provenance checks; editable ledger fields can only reduce trust, never
raise it.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION=4
PRIMARY_INTRINSIC_KINDS={"SOURCE_REQUIRED"}
LEGACY_PRIMARY_KINDS={"SEMANTIC"}


def _has_text(value):
    return isinstance(value,str) and bool(value.strip())


def rule_claim_id(rule_id):
    if not _has_text(rule_id):
        raise ValueError("rule id is required")
    return f"RULE:{rule_id}"


def check_claim_id(rule_id,check_id):
    if not _has_text(rule_id) or not _has_text(check_id):
        raise ValueError("rule id and check id are required")
    return f"CHECK:{rule_id}:{check_id}"


def machine_finding_claim_id(rule_id,check_id,finding_type,artifact,candidate_sha256,finding_sha256):
    values=(rule_id,check_id,finding_type,artifact,candidate_sha256,finding_sha256)
    if any(not _has_text(x) for x in values):
        raise ValueError("machine finding claim identity fields are required")
    material={
        "rule_id":rule_id,
        "check_id":check_id,
        "finding_type":finding_type,
        "artifact":artifact,
        "candidate_sha256":candidate_sha256,
        "finding_sha256":finding_sha256,
    }
    digest=hashlib.sha256(json.dumps(material,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    return f"MACHINE_FINDING:{rule_id}:{check_id}:{finding_type}:{digest[:20]}"


def validate_row_claim_id(row,expected_claim_id,errors,scope,rid):
    actual=(row or {}).get("claim_id")
    if actual!=expected_claim_id:
        errors.append({
            "type":"PROOF_CLAIM_ROW_ID_DRIFT",
            "scope":scope,
            "id":rid,
            "expected":expected_claim_id,
            "actual":actual,
        })
        return False
    return True


def _supporting_reason(item):
    """Return why this evidence cannot be primary.

    Public ledger fields are fail-closed hints: they can demote evidence but
    cannot promote it. Private _verifier_* fields are added only in-memory by
    the release verifier after independent provenance validation.
    """
    if item.get("_verifier_proof_role")=="SUPPORTING_ONLY":
        return "VERIFIER_PROVENANCE_SUPPORTING_ONLY"
    if item.get("_verifier_proof_role")=="UNVERIFIED":
        return "VERIFIER_PROVENANCE_UNVERIFIED"
    if item.get("supporting_only") is True:
        return "SUPPORTING_ONLY_FLAG"
    if str(item.get("proof_role") or "").upper()=="SUPPORTING_ONLY":
        return "SUPPORTING_ONLY_ROLE"
    if str(item.get("verification_mode") or "").upper()=="ATTACH_ONLY":
        return "ATTACH_ONLY_MODE"
    if _has_text(item.get("receipt_id")) and item.get("_verifier_receipt_predicate_confirmed") is not True:
        return "RECEIPT_WITHOUT_CONFIRMED_RULE_PREDICATE"
    return None


def validate_obligation_evidence(items,expected_claim_id,allowed_kinds,errors,scope,rid,require_primary=False,proof_policy=None):
    """Validate exact claim binding and primary/supporting semantics.

    SEMANTIC is no longer intrinsically primary. Only the explicit
    LEGACY_COMPATIBLE migration policy can retain its pre-Phase-1 admissibility;
    ARCHITECTURE_SEMANTIC always treats self semantic reasoning as supporting.
    """
    policy=proof_policy if isinstance(proof_policy,dict) else {}
    claim_class=policy.get("claim_class")
    legacy_semantic_primary=claim_class=="LEGACY_COMPATIBLE"
    allowed=set(str(x).upper() for x in (allowed_kinds or []))
    primary=0; seen=set(); supporting=[]
    for index,item in enumerate(items or []):
        if not isinstance(item,dict):
            continue
        kind=str(item.get("kind","")).upper()
        seen.add(kind)
        actual_claim=item.get("claim_id")
        claim_ok=True
        if not _has_text(actual_claim):
            errors.append({"type":"PROOF_CLAIM_ID_MISSING","scope":scope,"id":rid,"index":index,"expected":expected_claim_id})
            claim_ok=False
        elif actual_claim!=expected_claim_id:
            errors.append({"type":"PROOF_CLAIM_BINDING_MISMATCH","scope":scope,"id":rid,"index":index,"expected":expected_claim_id,"actual":actual_claim})
            claim_ok=False

        kind_ok=True
        if allowed and kind not in allowed:
            errors.append({"type":"EVIDENCE_KIND_NOT_ALLOWED_FOR_OBLIGATION","scope":scope,"id":rid,"index":index,"kind":kind,"allowed":sorted(allowed)})
            kind_ok=False

        if not claim_ok or not kind_ok:
            continue

        supporting_reason=_supporting_reason(item)
        if supporting_reason:
            supporting.append({"index":index,"kind":kind,"reason":supporting_reason})
            continue

        if kind in PRIMARY_INTRINSIC_KINDS:
            primary+=1
        elif kind in LEGACY_PRIMARY_KINDS:
            if legacy_semantic_primary:
                primary+=1
            else:
                supporting.append({"index":index,"kind":kind,"reason":"SELF_SEMANTIC_REASONING_SUPPORTING_ONLY"})
        elif kind=="RUNTIME":
            property_id=item.get("property_id")
            if property_id!=expected_claim_id:
                errors.append({"type":"RUNTIME_EVIDENCE_CLAIM_PROPERTY_MISMATCH","scope":scope,"id":rid,"index":index,"expected":expected_claim_id,"actual":property_id})
            else:
                primary+=1
        elif kind=="MACHINE":
            property_id=item.get("property_id")
            if property_id==expected_claim_id:
                primary+=1
            elif item.get("supporting_only") is not True:
                errors.append({"type":"GENERIC_MACHINE_PROPERTY_MUST_BE_SUPPORTING","scope":scope,"id":rid,"index":index,"claim_id":expected_claim_id,"property_id":property_id})

    if require_primary and primary==0:
        if supporting:
            errors.append({
                "type":"ATTACH_ONLY_EVIDENCE_CANNOT_CLOSE_CLAIM",
                "scope":scope,"id":rid,"claim_id":expected_claim_id,
                "supporting_evidence":supporting,
            })
        errors.append({"type":"PRIMARY_PROOF_MISSING","scope":scope,"id":rid,"claim_id":expected_claim_id,"evidence_kinds":sorted(seen)})
    return {"primary_count":primary,"evidence_kinds":sorted(seen),"supporting":supporting}
