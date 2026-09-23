#!/usr/bin/env python3
"""Create and verify runtime observation leaves.

Runtime evidence is not allowed to close over a self-referential ledger case. A
PASS case must terminate in a content-bound observation leaf. For release proof,
that leaf must be classified as ``RUNTIME_ADAPTER`` and bound to the adapter/log
bytes it reports. Manual review remains useful evidence but is intentionally too
weak to satisfy a runtime proof obligation.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json

SCHEMA_VERSION=2
OBSERVATION_KINDS={"RUNTIME_ADAPTER","TRUSTED_MANUAL_REVIEW"}


def _has_text(value):return isinstance(value,str) and bool(value.strip())
def _sha(data):return hashlib.sha256(data).hexdigest()


def create_manual_observation(path_value,property_id,observation,observer,result="PASS"):
    if not all(_has_text(x) for x in (property_id,observation,observer)):raise ValueError("property_id, observation and observer are required")
    if result not in {"PASS","FAIL"}:raise ValueError("runtime observation result must be PASS or FAIL")
    payload={
        "schema_version":SCHEMA_VERSION,"kind":"RUNTIME_OBSERVATION","observation_kind":"TRUSTED_MANUAL_REVIEW",
        "property_id":property_id,"observer":observer,"observation":observation,"result":result,
        "limitations":["Manual review is a trusted attestation, not an independently replayed runtime/device observation and cannot satisfy final runtime proof."],
    }
    path=Path(path_value); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return payload


def create_adapter_observation(path_value,property_id,source_ref,producer,environment,observation,result="PASS"):
    source_ref=str(source_ref)
    if not all(_has_text(x) for x in (property_id,source_ref,producer,environment,observation)):raise ValueError("property_id, source_ref, producer, environment and observation are required")
    if result not in {"PASS","FAIL"}:raise ValueError("runtime observation result must be PASS or FAIL")
    source=Path(source_ref)
    if not source.is_file():raise FileNotFoundError(source)
    raw=source.read_bytes()
    payload={
        "schema_version":SCHEMA_VERSION,"kind":"RUNTIME_OBSERVATION","observation_kind":"RUNTIME_ADAPTER",
        "property_id":property_id,"producer":producer,"environment":environment,"observation":observation,"result":result,
        "source":{"ref":str(source),"sha256":_sha(raw),"size":len(raw)},
        "limitations":["The verifier proves identity/integrity of the adapter observation and bound source bytes. Independence still relies on the adapter/runner trust boundary outside model-authored repository state."],
    }
    path=Path(path_value); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return payload


def verify_observation(ref,expected_property=None,expected_sha256=None,require_adapter=False,require_pass=True):
    path=Path(ref); errors=[]
    if not path.is_file():return {"integrity_result":"FAIL","derived_result":None,"errors":[{"type":"RUNTIME_OBSERVATION_MISSING","ref":str(path)}]}
    raw=path.read_bytes(); actual_sha=_sha(raw)
    if expected_sha256 and actual_sha!=expected_sha256:errors.append({"type":"RUNTIME_OBSERVATION_HASH_DRIFT","ref":str(path),"expected":expected_sha256,"actual":actual_sha})
    try:payload=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:return {"integrity_result":"FAIL","derived_result":None,"errors":[{"type":"RUNTIME_OBSERVATION_PARSE_ERROR","ref":str(path),"error":str(exc)}],"sha256":actual_sha}
    if payload.get("schema_version")!=SCHEMA_VERSION:errors.append({"type":"RUNTIME_OBSERVATION_SCHEMA_UNSUPPORTED","actual":payload.get("schema_version")})
    if payload.get("kind")!="RUNTIME_OBSERVATION":errors.append({"type":"RUNTIME_OBSERVATION_KIND_INVALID","actual":payload.get("kind")})
    source_kind=payload.get("observation_kind")
    if source_kind not in OBSERVATION_KINDS:errors.append({"type":"RUNTIME_OBSERVATION_SOURCE_INVALID","actual":source_kind})
    if require_adapter and source_kind!="RUNTIME_ADAPTER":errors.append({"type":"RUNTIME_OBSERVATION_NOT_ADAPTER_EVIDENCE","actual":source_kind})
    property_id=payload.get("property_id")
    if not _has_text(property_id):errors.append({"type":"RUNTIME_OBSERVATION_PROPERTY_MISSING"})
    elif expected_property and property_id!=expected_property:errors.append({"type":"RUNTIME_OBSERVATION_PROPERTY_MISMATCH","expected":expected_property,"actual":property_id})
    result=payload.get("result")
    if result not in {"PASS","FAIL"}:errors.append({"type":"RUNTIME_OBSERVATION_RESULT_INVALID","result":result})
    elif require_pass and result!="PASS":errors.append({"type":"RUNTIME_OBSERVATION_NOT_PASS","result":result})
    if source_kind=="TRUSTED_MANUAL_REVIEW":
        if not _has_text(payload.get("observer")):errors.append({"type":"RUNTIME_OBSERVATION_OBSERVER_MISSING"})
    elif source_kind=="RUNTIME_ADAPTER":
        if not _has_text(payload.get("producer")):errors.append({"type":"RUNTIME_OBSERVATION_PRODUCER_MISSING"})
        if not _has_text(payload.get("environment")):errors.append({"type":"RUNTIME_OBSERVATION_ENVIRONMENT_MISSING"})
        source=payload.get("source") or {}; source_ref=source.get("ref")
        if not _has_text(source_ref) or not _has_text(source.get("sha256")):errors.append({"type":"RUNTIME_OBSERVATION_SOURCE_BINDING_INCOMPLETE"})
        else:
            source_path=Path(source_ref)
            if not source_path.is_file():errors.append({"type":"RUNTIME_OBSERVATION_SOURCE_MISSING","ref":source_ref})
            else:
                source_sha=_sha(source_path.read_bytes())
                if source_sha!=source.get("sha256"):errors.append({"type":"RUNTIME_OBSERVATION_SOURCE_DRIFT","ref":source_ref,"expected":source.get("sha256"),"actual":source_sha})
    if not _has_text(payload.get("observation")):errors.append({"type":"RUNTIME_OBSERVATION_TEXT_MISSING"})
    return {"integrity_result":"PASS" if not errors else "FAIL","derived_result":result,"errors":errors,"payload":payload,"sha256":actual_sha,"property_id":property_id,"observation_kind":source_kind}
