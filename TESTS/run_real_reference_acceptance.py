#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from reference_locator import load_catalogs, locate


def norm(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")


def _expectations(payload):
    rows=payload.get("retrieval_expectations")
    if isinstance(rows,list) and rows:
        return rows
    return [{
        "family":payload.get("family") or "CLEVERENCE",
        "query":payload.get("query") or "",
        "expected_public_candidates":payload.get("expected_public_candidates") or [],
        "expected_public_paths_in_target":payload.get("expected_public_paths_in_target") or [],
    }]


def _retrieve(expectation,catalogs,limit,target_paths):
    family=expectation.get("family") or "CLEVERENCE"
    query=expectation.get("query") or ""
    locator=locate(query,catalogs,int(expectation.get("limit") or limit or 50))
    matches=[row for row in locator.get("matches",[]) if row.get("source_family")==family]
    candidates=[]; proof_gate=bool(matches)
    for match in matches:
        if match.get("role")!="DISCOVERY_ONLY" or not match.get("proof_required_after_locator_match"):
            proof_gate=False
        for candidate in match.get("request_candidates",[]):
            row={
                "object_type":candidate.get("object_type") or "UNKNOWN",
                "name":candidate.get("name") or "",
                "suggested_path":norm(candidate.get("suggested_path") or "") or None,
            }
            if row not in candidates:candidates.append(row)

    errors=[]
    expected_names=set(expectation.get("expected_public_candidates") or [])
    returned_names={row["name"] for row in candidates}
    missing_names=sorted(expected_names-returned_names)
    if missing_names:
        errors.append({"type":"EXPECTED_PUBLIC_REFERENCE_NOT_FOUND","family":family,"names":missing_names})

    public_paths={row["suggested_path"] for row in candidates if row.get("suggested_path")}
    expected_paths={norm(value) for value in expectation.get("expected_public_paths_in_target") or []}
    missing_returned=sorted(expected_paths-public_paths)
    missing_in_target=sorted(expected_paths-target_paths)
    if missing_returned:
        errors.append({"type":"EXPECTED_PUBLIC_PATH_NOT_RETURNED","family":family,"paths":missing_returned})
    if missing_in_target:
        errors.append({"type":"EXPECTED_PUBLIC_PATH_NOT_OBSERVED_IN_TARGET","family":family,"paths":missing_in_target})
    if not proof_gate:
        errors.append({"type":"DISCOVERY_PROOF_GATE_MISSING","family":family})

    return {
        "family":family,"query":query,"proof_gate":proof_gate,"returned_candidates":candidates,"errors":errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real-task retrieval acceptance without promoting locator/target-inventory evidence to semantic or runtime proof.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--catalog-root", default=str(ROOT / "REFERENCE/CATALOGS"))
    args = parser.parse_args()

    case_path = Path(args.case).resolve()
    if not case_path.is_file():
        print(json.dumps({"result":"FAIL","errors":[{"type":"CASE_MISSING","path":str(case_path)}]},ensure_ascii=False,indent=2))
        return 2

    payload=json.loads(case_path.read_text(encoding="utf-8-sig"))
    catalogs=load_catalogs(Path(args.catalog_root).resolve())
    target_paths={norm(value) for value in payload.get("observed_target_paths") or []}
    errors=[]

    required_target_paths={norm(value) for value in payload.get("required_target_paths") or []}
    missing_target=sorted(required_target_paths-target_paths)
    if missing_target:
        errors.append({"type":"TARGET_INVENTORY_PATH_MISSING","paths":missing_target})

    retrieval=[]
    for expectation in _expectations(payload):
        report=_retrieve(expectation,catalogs,payload.get("limit") or 50,target_paths)
        retrieval.append(report); errors.extend(report["errors"])

    required_evidence=set(payload.get("required_evidence_before_implementation") or [])
    mandatory=set(payload.get("mandatory_evidence") or [])
    if not mandatory:
        # Backward-compatible strict default for the original Cleverence real acceptance.
        mandatory={"EXACT_TARGET_SOURCE","ACTION_GRAPH","FIELD_CONTRACT","RUNTIME_EVIDENCE"}
    missing_evidence=sorted(mandatory-required_evidence)
    if missing_evidence:
        errors.append({"type":"FAIL_CLOSED_EVIDENCE_GATE_INCOMPLETE","missing":missing_evidence})

    exact_source_available=bool(payload.get("exact_target_source_available"))
    runtime_evidence_available=bool(payload.get("runtime_evidence_available"))
    semantic_ready=exact_source_available
    runtime_ready=exact_source_available and runtime_evidence_available
    decision="EXACT_SOURCE_AVAILABLE" if exact_source_available else "EXACT_SOURCE_REQUIRED"
    expected_decision=payload.get("expected_decision")
    if expected_decision and decision!=expected_decision:
        errors.append({"type":"FAIL_CLOSED_DECISION_MISMATCH","expected":expected_decision,"actual":decision})

    flat=[]
    for row in retrieval:
        for candidate in row["returned_candidates"]:
            tagged=dict(candidate); tagged["family"]=row["family"]
            if tagged not in flat:flat.append(tagged)

    report={
        "result":"PASS" if not errors else "FAIL",
        "acceptance_level":"TARGET_RETRIEVAL_AND_EVIDENCE_GATE",
        "acceptance_surface":payload.get("acceptance_surface") or payload.get("family") or "SINGLE_FAMILY",
        "implementation_ready":semantic_ready,
        "runtime_ready":runtime_ready,
        "decision":decision,
        "proof_gate":all(row["proof_gate"] for row in retrieval),
        "retrieval":retrieval,
        "returned_candidates":flat,
        "target_path_count":len(target_paths),
        "required_evidence_before_implementation":sorted(required_evidence),
        "mandatory_evidence":sorted(mandatory),
        "errors":errors,
        "rule":"A real task can pass retrieval acceptance while remaining correctly blocked for implementation/runtime claims. Each routed discovery family is DISCOVERY_ONLY. Target inventory proves file presence only. Case-specific exact source/dependency/field/semantic/runtime gates remain mandatory before implementation claims.",
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
