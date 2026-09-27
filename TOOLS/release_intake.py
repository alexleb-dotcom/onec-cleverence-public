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


def _delivery_row_projection(row):
    if not isinstance(row,dict):return None
    return {
        "capability_id":row.get("capability_id"),
        "sequence":row.get("sequence"),
        "owner_rule_id":row.get("owner_rule_id"),
        "enforcement":row.get("enforcement"),
        "executor_payload":row.get("executor_payload"),
        "references":row.get("references") or [],
        "proof_binding":row.get("proof_binding"),
    }


def _derived_delivery_outputs(rows):
    tools=[]; references=[]
    for row in rows:
        payload=row.get("executor_payload") or {}
        if payload.get("kind")=="INSTRUCTION":
            value=payload.get("value")
            if _has_text(value) and value not in tools:tools.append(value)
        for ref in row.get("references") or []:
            if ref not in references:references.append(ref)
    return tools,references


def _validate_delivery_projection(plan, recomputed):
    """Validate exact canonical present subset; ADVISORY omission alone remains nonblocking."""
    errors=[]
    expected_rows=[_delivery_row_projection(x) for x in (recomputed.get("active_deliveries") or [])]
    if any(x is None for x in expected_rows):
        return [{"type":"RELEASE_DELIVERY_RECOMPUTE_INVALID"}]
    expected_by={row["capability_id"]:row for row in expected_rows}
    actual_raw=plan.get("active_deliveries")
    if not isinstance(actual_raw,list):
        return [{"type":"RELEASE_DELIVERY_PROJECTION_INVALID","actual_type":type(actual_raw).__name__}]
    actual_rows=[]
    seen=set()
    for index,raw in enumerate(actual_raw):
        row=_delivery_row_projection(raw)
        if row is None:
            errors.append({"type":"RELEASE_DELIVERY_ROW_INVALID","index":index});continue
        capability=row.get("capability_id")
        if capability in seen:
            errors.append({"type":"RELEASE_DELIVERY_DUPLICATE_CAPABILITY","capability_id":capability,"index":index})
        seen.add(capability)
        expected=expected_by.get(capability)
        if expected is None:
            errors.append({"type":"RELEASE_DELIVERY_UNKNOWN_CAPABILITY","capability_id":capability,"index":index})
        elif row!=expected:
            errors.append({"type":"RELEASE_DELIVERY_BINDING_DRIFT","capability_id":capability,"index":index})
        actual_rows.append(row)

    actual_capabilities={row.get("capability_id") for row in actual_rows}
    for row in expected_rows:
        if row.get("enforcement")=="GATING" and row.get("capability_id") not in actual_capabilities:
            errors.append({"type":"RELEASE_DELIVERY_GATING_MISSING","capability_id":row.get("capability_id")})

    # Canonical expected order is sequence-owned by the registry. The actual plan may
    # omit ADVISORY rows, but every row that remains must preserve that canonical order.
    expected_subset=[row for row in expected_rows if row.get("capability_id") in actual_capabilities]
    if actual_rows!=expected_subset:
        errors.append({
            "type":"RELEASE_DELIVERY_ORDER_OR_SUBSET_DRIFT",
            "expected":[x.get("capability_id") for x in expected_subset],
            "actual":[x.get("capability_id") for x in actual_rows],
        })

    expected_tools,expected_refs=_derived_delivery_outputs(expected_subset)
    actual_tools=plan.get("deterministic_tools")
    if actual_tools!=expected_tools:
        errors.append({"type":"RELEASE_DELIVERY_TOOL_PROJECTION_DRIFT","expected":expected_tools,"actual":actual_tools})
    actual_refs=(plan.get("context_load_plan") or {}).get("references")
    if actual_refs!=expected_refs:
        errors.append({"type":"RELEASE_DELIVERY_REFERENCE_PROJECTION_DRIFT","expected":expected_refs,"actual":actual_refs})
    return errors


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

    delivery_errors=_validate_delivery_projection(plan,recomputed)
    errors.extend(delivery_errors)

    expected=plan_trust_projection(recomputed)
    actual=plan_trust_projection(plan)
    changed=[key for key in expected if actual.get(key)!=expected.get(key)]
    if delivery_errors:
        changed.append("delivery_projection")
    if changed:
        errors.append({"type":"RELEASE_PLAN_RECOMPUTE_DRIFT","changed":list(dict.fromkeys(changed))})
    return {
        "result":"PASS" if not errors else "FAIL",
        "errors":errors,
        "intake_sha256":current_sha,
        "recomputed_projection_sha256":hashlib.sha256(json.dumps(expected,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode("utf-8")).hexdigest(),
    }


def load_intake(path):
    payload=json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return normalize_intake(payload)
