#!/usr/bin/env python3
"""Recompute release-relevant planning state from an explicit source intake.

The verifier must not trust editable ``plan.rules[*].active`` or a stale embedded
requirements summary. A controlled runner may provide an intake manifest
separately from the plan; when no external manifest is supplied, the plan's
embedded intake is still replayed against current source bytes so direct core
calls cannot bypass recomputation.

An embedded manifest is not an independent security boundary if the same actor
can rewrite both it and the verifier. The external ``--intake`` path exists for
that stronger runner/repository boundary.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json

SCHEMA_VERSION=1
SURFACES={"ANALYSIS_ONLY","ONEC_ONLY","CLEVERENCE_ONLY","CROSS_SYSTEM"}
RISKS={"R0_LOCAL","R1_CONTRACT","R2_STATEFUL_RUNTIME","R3_CROSS_SYSTEM"}


def _has_text(value):
    return isinstance(value,str) and bool(value.strip())


def normalize_intake(payload):
    if not isinstance(payload,dict):
        raise ValueError("release intake must be an object")
    version=payload.get("schema_version")
    if version!=SCHEMA_VERSION:
        raise ValueError(f"unsupported release intake schema_version: {version}")
    paths=payload.get("source_paths")
    if not isinstance(paths,list) or not paths or any(not _has_text(x) for x in paths):
        raise ValueError("release intake source_paths must be a non-empty list of paths")
    surface=payload.get("surface_override")
    risk=payload.get("risk_override")
    if surface is not None and surface not in SURFACES:
        raise ValueError(f"unsupported release intake surface_override: {surface}")
    if risk is not None and risk not in RISKS:
        raise ValueError(f"unsupported release intake risk_override: {risk}")
    result={
        "schema_version":SCHEMA_VERSION,
        "source_paths":[str(x) for x in paths],
        "baseline":payload.get("baseline"),
        "analysis_only":bool(payload.get("analysis_only",False)),
        "surface_override":surface,
        "risk_override":risk,
        "project_context":payload.get("project_context"),
        "requirements_contract":payload.get("requirements_contract"),
    }
    for key in ("baseline","project_context","requirements_contract"):
        value=result[key]
        if value is not None and not _has_text(value):
            raise ValueError(f"release intake {key} must be a path or null")
    return result


def intake_from_build_args(paths, baseline=None, analysis_only=False, surface_override=None,
                           risk_override=None, project_context=None, requirements_contract=None):
    return normalize_intake({
        "schema_version":SCHEMA_VERSION,
        "source_paths":[str(x) for x in paths],
        "baseline":str(baseline) if baseline is not None else None,
        "analysis_only":bool(analysis_only),
        "surface_override":surface_override,
        "risk_override":risk_override,
        "project_context":str(project_context) if project_context is not None else None,
        "requirements_contract":str(requirements_contract) if requirements_contract is not None else None,
    })


def intake_sha256(payload):
    normalized=normalize_intake(payload)
    raw=json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def intake_record(payload):
    normalized=normalize_intake(payload)
    return {"schema_version":SCHEMA_VERSION,"manifest":normalized,"sha256":intake_sha256(normalized)}


def build_plan_from_intake(payload):
    # Local import avoids a module cycle while build_review_plan emits the intake.
    from build_review_plan import build_plan
    intake=normalize_intake(payload)
    return build_plan(
        intake["source_paths"],
        baseline=intake["baseline"],
        analysis_only=intake["analysis_only"],
        surface_override=intake["surface_override"],
        risk_override=intake["risk_override"],
        project_context=intake["project_context"],
        requirements_contract=intake["requirements_contract"],
    )


def _candidate_projection(rows):
    keep=("logical_path","physical_path","routing_aliases","origin","container_chain","sha256","size","onec","cleverence")
    return [{k:row.get(k) for k in keep} for row in (rows or [])]


def plan_trust_projection(plan):
    """Only fields that can change final obligations belong to this comparison."""
    return {
        "registry":plan.get("registry"),
        "routing":plan.get("routing"),
        "artifact_model":plan.get("artifact_model"),
        "artifact_delivery_state":plan.get("artifact_delivery_state"),
        "candidate_artifacts":_candidate_projection(plan.get("candidate_artifacts")),
        "baseline":plan.get("baseline"),
        "project_context":plan.get("project_context"),
        "requirements":plan.get("requirements"),
        "rules":plan.get("rules"),
        "gate_plan":plan.get("gate_plan"),
    }


def validate_plan_recomputation(plan, external_intake=None):
    errors=[]
    record=plan.get("release_intake")
    if not isinstance(record,dict):
        return {"result":"FAIL","errors":[{"type":"RELEASE_INTAKE_MISSING"}]}
    embedded=record.get("manifest")
    try:
        normalized=normalize_intake(external_intake if external_intake is not None else embedded)
    except Exception as exc:
        return {"result":"FAIL","errors":[{"type":"RELEASE_INTAKE_INVALID","error":str(exc)}]}

    embedded_sha=record.get("sha256")
    try:actual_embedded_sha=intake_sha256(embedded)
    except Exception as exc:
        errors.append({"type":"RELEASE_INTAKE_EMBEDDED_INVALID","error":str(exc)})
        actual_embedded_sha=None
    if embedded_sha!=actual_embedded_sha:
        errors.append({"type":"RELEASE_INTAKE_HASH_DRIFT","expected":embedded_sha,"actual":actual_embedded_sha})

    current_sha=intake_sha256(normalized)
    if external_intake is not None and current_sha!=embedded_sha:
        errors.append({"type":"RELEASE_INTAKE_EXTERNAL_MISMATCH","plan":embedded_sha,"external":current_sha})
    try:
        recomputed=build_plan_from_intake(normalized)
    except Exception as exc:
        errors.append({"type":"RELEASE_PLAN_RECOMPUTE_FAILED","error":str(exc)})
        return {"result":"FAIL","errors":errors,"intake_sha256":current_sha}

    expected=plan_trust_projection(recomputed)
    actual=plan_trust_projection(plan)
    if actual!=expected:
        changed=[key for key in expected if actual.get(key)!=expected.get(key)]
        errors.append({"type":"RELEASE_PLAN_RECOMPUTE_DRIFT","changed":changed})
    return {
        "result":"PASS" if not errors else "FAIL",
        "errors":errors,
        "intake_sha256":current_sha,
        "recomputed_projection_sha256":hashlib.sha256(json.dumps(expected,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")).hexdigest(),
    }


def load_intake(path):
    payload=json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return normalize_intake(payload)
