#!/usr/bin/env python3
"""Verifier-owned validation of machine reports and runtime evidence leaves."""
from __future__ import annotations

from pathlib import Path
import hashlib

from machine_receipts import verify_receipt
from runtime_evidence import verify_observation


def _has_text(value):return isinstance(value,str) and bool(value.strip())
def _sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _input_identity(receipt):
    return tuple((x.get("sha256"),x.get("size")) for x in (receipt.get("inputs") or []) if isinstance(x,dict))


def validate_machine_reports(rows,errors):
    reports={}
    for index,row in enumerate(rows or []):
        if not isinstance(row,dict):errors.append({"type":"MACHINE_REPORT_NOT_OBJECT","index":index});continue
        rid=row.get("id")
        if not _has_text(rid):errors.append({"type":"MACHINE_REPORT_WITHOUT_ID","index":index});continue
        if rid in reports:errors.append({"type":"DUPLICATE_ROW_ID","scope":"machine_report","id":rid});continue
        receipt_ref=row.get("receipt_ref") or row.get("ref")
        if not _has_text(receipt_ref):errors.append({"type":"MACHINE_REPORT_WITHOUT_RECEIPT","id":rid});reports[rid]=dict(row);continue
        verification=verify_receipt(receipt_ref,replay=True)
        for item in verification.get("errors") or []:errors.append({"type":"MACHINE_REPORT_RECEIPT_INVALID","id":rid,"detail":item})
        expected_sha=row.get("receipt_sha256")
        actual_sha=verification.get("receipt_sha256")
        if not _has_text(expected_sha):errors.append({"type":"MACHINE_REPORT_RECEIPT_HASH_MISSING","id":rid})
        elif actual_sha!=expected_sha:errors.append({"type":"MACHINE_REPORT_RECEIPT_HASH_DRIFT","id":rid,"expected":expected_sha,"actual":actual_sha})
        receipt=verification.get("receipt") or {}
        derived=verification.get("derived_result")
        if row.get("tool")!=receipt.get("tool"):errors.append({"type":"MACHINE_REPORT_TOOL_DECLARATION_MISMATCH","id":rid,"declared":row.get("tool"),"actual":receipt.get("tool")})
        if row.get("result")!=derived:errors.append({"type":"MACHINE_REPORT_RESULT_DECLARATION_MISMATCH","id":rid,"declared":row.get("result"),"actual":derived})
        enriched=dict(row); enriched["_verified_properties"]=set(verification.get("verified_properties") or []); enriched["_receipt_result"]=derived; enriched["_receipt_integrity"]=verification.get("integrity_result"); enriched["_receipt"]=receipt
        reports[rid]=enriched

    # A failed deterministic run remains a blocking fact until a PASS receipt on the
    # same tool/input identity explicitly supersedes it. Omitting the old report from
    # evidence references is not a supersession mechanism.
    superseded=set()
    for rid,row in reports.items():
        if row.get("_receipt_result")!="PASS" or row.get("_receipt_integrity")!="PASS":continue
        for old_id in row.get("supersedes") or []:
            old=reports.get(old_id)
            if not old:
                errors.append({"type":"MACHINE_REPORT_SUPERSEDES_UNKNOWN","id":rid,"supersedes":old_id});continue
            if old.get("_receipt_result")!="FAIL":
                errors.append({"type":"MACHINE_REPORT_SUPERSEDES_NONFAILURE","id":rid,"supersedes":old_id});continue
            new_receipt=row.get("_receipt") or {}; old_receipt=old.get("_receipt") or {}
            compatible=(new_receipt.get("tool")==old_receipt.get("tool") and _input_identity(new_receipt)==_input_identity(old_receipt) and set(new_receipt.get("verified_properties") or []).issuperset(set(old_receipt.get("verified_properties") or [])))
            if not compatible:
                errors.append({"type":"MACHINE_REPORT_SUPERSESSION_SCOPE_MISMATCH","id":rid,"supersedes":old_id});continue
            superseded.add(old_id)
    for rid,row in reports.items():
        if row.get("_receipt_integrity")=="PASS" and row.get("_receipt_result")=="FAIL" and rid not in superseded:
            errors.append({"type":"UNSUPERSEDED_MACHINE_FAILURE","id":rid})
    return reports


def validate_runtime_cases(rows,errors,pending_items,blocking,pending):
    cases={}
    for index,row in enumerate(rows or []):
        if not isinstance(row,dict):errors.append({"type":"RUNTIME_CASE_NOT_OBJECT","index":index});continue
        cid=row.get("id")
        if not _has_text(cid):errors.append({"type":"ROW_WITHOUT_ID","scope":"runtime_case","index":index,"key":"id"});continue
        if cid in cases:errors.append({"type":"DUPLICATE_ROW_ID","scope":"runtime_case","id":cid});continue
        enriched=dict(row); cases[cid]=enriched
        status=row.get("status")
        if status in blocking or not status:
            errors.append({"type":"RUNTIME_CASE_BLOCKING_OR_UNRESOLVED","id":cid,"status":status});continue
        if status in pending:
            if not _has_text(row.get("reason")):errors.append({"type":"PENDING_WITHOUT_REASON","scope":"runtime_case","id":cid})
            pending_items.append({"type":"RUNTIME_CASE_PENDING","id":cid,"status":status});continue
        if status=="NOT_APPLICABLE":
            if not _has_text(row.get("reason")):errors.append({"type":"NA_WITHOUT_REASON","scope":"runtime_case","id":cid})
            continue
        if status!="PASS":errors.append({"type":"UNKNOWN_RUNTIME_CASE_STATUS","id":cid,"status":status});continue
        property_id=row.get("property_id"); observation_ref=row.get("observation_ref"); observation_sha=row.get("observation_sha256")
        if not _has_text(property_id):errors.append({"type":"RUNTIME_CASE_PROPERTY_MISSING","id":cid})
        if not _has_text(observation_ref):errors.append({"type":"RUNTIME_CASE_OBSERVATION_MISSING","id":cid});continue
        if not _has_text(observation_sha):errors.append({"type":"RUNTIME_CASE_OBSERVATION_HASH_MISSING","id":cid})
        verification=verify_observation(observation_ref,expected_property=property_id,expected_sha256=observation_sha,require_adapter=True,require_pass=True)
        for item in verification.get("errors") or []:errors.append({"type":"RUNTIME_CASE_OBSERVATION_INVALID","id":cid,"detail":item})
        enriched["_verified_property"]=verification.get("property_id") if verification.get("integrity_result")=="PASS" and verification.get("derived_result")=="PASS" else None
        enriched["_observation_kind"]=verification.get("observation_kind")
    return cases


def validate_evidence_property(item,scope,rid,machine_reports,runtime_cases,errors,index):
    kind=str(item.get("kind","")).upper()
    if kind=="MACHINE":
        report_id=item.get("report_id"); report=(machine_reports or {}).get(report_id) if _has_text(report_id) else None
        if not report:
            errors.append({"type":"MACHINE_EVIDENCE_REPORT_MISSING","scope":scope,"id":rid,"index":index,"report_id":report_id});return False
        if report.get("_receipt_integrity")!="PASS" or report.get("_receipt_result")!="PASS":
            errors.append({"type":"MACHINE_EVIDENCE_REPORT_NOT_PASS","scope":scope,"id":rid,"index":index,"report_id":report_id,"result":report.get("_receipt_result")});return False
        property_id=item.get("property_id")
        if not _has_text(property_id):errors.append({"type":"MACHINE_EVIDENCE_PROPERTY_MISSING","scope":scope,"id":rid,"index":index,"report_id":report_id})
        elif property_id not in report.get("_verified_properties",set()):
            errors.append({"type":"MACHINE_EVIDENCE_PROPERTY_UNSUPPORTED","scope":scope,"id":rid,"index":index,"report_id":report_id,"property_id":property_id}); return False
        else:return True
    elif kind=="RUNTIME":
        case_id=item.get("case_id"); case=(runtime_cases or {}).get(case_id) if _has_text(case_id) else None
        if not case:
            errors.append({"type":"RUNTIME_EVIDENCE_CASE_MISSING","scope":scope,"id":rid,"index":index,"case_id":case_id});return False
        if case.get("status")!="PASS" or not case.get("_verified_property"):
            errors.append({"type":"RUNTIME_EVIDENCE_CASE_NOT_PASS","scope":scope,"id":rid,"index":index,"case_id":case_id,"status":case.get("status")});return False
        property_id=item.get("property_id")
        if not _has_text(property_id):errors.append({"type":"RUNTIME_EVIDENCE_PROPERTY_MISSING","scope":scope,"id":rid,"index":index,"case_id":case_id})
        elif property_id!=case.get("_verified_property"):
            errors.append({"type":"RUNTIME_EVIDENCE_PROPERTY_MISMATCH","scope":scope,"id":rid,"index":index,"case_id":case_id,"property_id":property_id,"case_property":case.get("_verified_property")}); return False
        else:return True
    return None
