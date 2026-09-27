#!/usr/bin/env python3
"""Attach source-bound evidence to exact predeclared validation claims.

Generic SOURCE_REQUIRED and SEMANTIC receipts are evidence transport only. File
existence, hashes, anchors, free-text reasons and editable receipt fields never
produce PASS. Auto-pass is reserved for a future rule-owned deterministic
predicate declared by the canonical rule registry and implemented by a known
verifier; no such predicate is currently enabled.

The admissible source corpus is exact: an inventoried file is one file, and an
archive candidate is one exact archive!/entry. Directory roots and archive
containers do not implicitly authorize siblings.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from evidence_source_policy import classify_non_proof_ref
from rule_registry import load_registry, rule_map
from proof_contract import check_claim_id

SCHEMA_VERSION=3
ALLOWED_KINDS={"SOURCE_REQUIRED","SEMANTIC"}
KNOWN_RULE_PREDICATE_VERIFIERS=set()


def _sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def _has_text(value)->bool:return isinstance(value,str) and bool(value.strip())
def _canon(value)->str:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def _norm_entry(value:str)->str:
    parts=[]
    for raw in str(value or "").replace("\\","/").split("/"):
        if raw in {"","."}:continue
        if raw=="..":
            if not parts:raise ValueError("archive entry escapes archive root")
            parts.pop();continue
        parts.append(raw)
    return "/".join(parts)


def _resolved_path(value:str)->str:
    p=Path(value)
    try:return str(p.resolve(strict=False))
    except OSError:return str(p.absolute())


def _canonical_ref(ref:str)->str:
    text=str(ref or "")
    if "!/" in text:
        archive,entry=text.split("!/",1)
        return f"{_resolved_path(archive)}!/{_norm_entry(entry)}"
    return _resolved_path(text)


def _read_archive_entry(archive_path:str,entry_path:str):
    archive=Path(archive_path)
    if not archive.is_file():raise ValueError(f"receipt source archive does not exist: {archive_path}")
    archive_bytes=archive.read_bytes()
    try:
        with zipfile.ZipFile(archive) as z:
            wanted=_norm_entry(entry_path)
            matches=[info for info in z.infolist() if not info.is_dir() and _norm_entry(info.filename)==wanted]
            if not matches:raise ValueError(f"receipt source archive entry does not exist: {archive_path}!/{wanted}")
            if len(matches)!=1:raise ValueError(f"receipt source archive entry is ambiguous/duplicated: {archive_path}!/{wanted}")
            data=z.read(matches[0])
    except zipfile.BadZipFile as exc:
        raise ValueError(f"receipt source archive is invalid: {archive_path}") from exc
    return archive_bytes,data,wanted


def _add_index(index,ref,descriptor):
    key=_canonical_ref(ref)
    current=index.get(key)
    if current and current!=descriptor:
        raise ValueError(f"ambiguous evidence corpus identity: {key}")
    index[key]=descriptor


def _candidate_source_index(ledger:dict):
    """Exact proof corpus: candidate files/entries plus exact file dependencies."""
    index={}
    for row in ledger.get("candidate_artifacts") or []:
        if not isinstance(row,dict) or not _has_text(row.get("origin")) or not _has_text(row.get("sha256")):continue
        origin=str(row["origin"]); expected=str(row["sha256"]).lower()
        if "!/" in origin:
            archive,entry=origin.split("!/",1)
            _add_index(index,origin,{
                "type":"ARCHIVE_ENTRY","archive_path":_resolved_path(archive),"entry_path":_norm_entry(entry),
                "expected_entry_sha256":expected,"logical_path":row.get("logical_path"),
            })
        else:
            _add_index(index,origin,{"type":"FILE","path":_resolved_path(origin),"expected_sha256":expected,"logical_path":row.get("logical_path")})
        portable=row.get("portable_origin")
        if _has_text(portable):
            if "!/" in str(portable):
                archive,entry=str(portable).split("!/",1)
                _add_index(index,portable,{
                    "type":"ARCHIVE_ENTRY","archive_path":_resolved_path(archive),"entry_path":_norm_entry(entry),
                    "expected_entry_sha256":expected,"logical_path":row.get("logical_path"),"portable":True,
                })
            else:
                _add_index(index,portable,{"type":"FILE","path":_resolved_path(str(portable)),"expected_sha256":expected,"logical_path":row.get("logical_path"),"portable":True})

    for key in ("baseline","project_context","requirements"):
        dep=ledger.get(key) or {}
        if not isinstance(dep,dict) or dep.get("kind")!="FILE" or not _has_text(dep.get("path")) or not _has_text(dep.get("sha256")):continue
        _add_index(index,dep["path"],{"type":"FILE","path":_resolved_path(dep["path"]),"expected_sha256":str(dep["sha256"]).lower(),"dependency":key})
        if _has_text(dep.get("portable_path")):
            _add_index(index,dep["portable_path"],{"type":"FILE","path":_resolved_path(dep["portable_path"]),"expected_sha256":str(dep["sha256"]).lower(),"dependency":key,"portable":True})
    return index


def _source_snapshot(ledger:dict,ref:str,source_type:str|None=None):
    canonical=_canonical_ref(ref)
    descriptor=_candidate_source_index(ledger).get(canonical)
    if not descriptor:raise ValueError(f"receipt source is outside the exact inventoried evidence corpus: {ref}")
    non_proof=classify_non_proof_ref(ref)
    if non_proof:raise ValueError(f"receipt source is non-proof material ({non_proof.get('role')}): {ref}")

    if descriptor["type"]=="ARCHIVE_ENTRY":
        archive_bytes,data,entry=_read_archive_entry(descriptor["archive_path"],descriptor["entry_path"])
        entry_sha=_sha(data)
        if entry_sha!=descriptor["expected_entry_sha256"]:
            raise ValueError(f"receipt archive entry drift from plan: expected {descriptor['expected_entry_sha256']}, actual {entry_sha}")
        source={
            "type":"ARCHIVE_ENTRY","ref":canonical,
            "archive_path":descriptor["archive_path"],"archive_sha256":_sha(archive_bytes),
            "entry_path":entry,"entry_sha256":entry_sha,"sha256":entry_sha,"size":len(data),
        }
        return source,data

    path=Path(descriptor["path"])
    if not path.is_file():raise ValueError(f"receipt source does not exist or is not a file: {descriptor['path']}")
    data=path.read_bytes(); digest=_sha(data)
    if digest!=descriptor["expected_sha256"]:
        raise ValueError(f"receipt source drift from plan: expected {descriptor['expected_sha256']}, actual {digest}")
    return {"type":"FILE","ref":canonical,"path":descriptor["path"],"sha256":digest,"size":len(data)},data


def _check_index(ledger:dict,registry:dict):
    registered=rule_map(registry); result={}
    for rule_row in ledger.get("rules") or []:
        rid=rule_row.get("id"); rule=registered.get(rid)
        if not rule:continue
        allowed={str(x).upper() for x in rule.get("evidence_modes") or []}
        specs={c.get("id"):c for c in rule.get("checks") or []}
        for check in rule_row.get("checks") or []:
            cid=check.get("id"); spec=specs.get(cid)
            if not spec:continue
            expected=check_claim_id(rid,cid)
            if check.get("claim_id")!=expected:raise ValueError(f"ledger claim drift for {rid}:{cid}")
            result[expected]={
                "rule_id":rid,"check_id":cid,"row":check,"allowed_kinds":allowed,
                "check_kind":spec.get("kind","PROFILE"),"question":spec.get("question",""),
                "receipt_predicate":spec.get("receipt_predicate"),
            }
    return result


def _normalize_anchor(anchor,source_sha):
    if not isinstance(anchor,dict):raise ValueError("source anchor must be an object")
    kind=str(anchor.get("type") or "").upper()
    if kind=="TEXT":
        value=anchor.get("value")
        if not _has_text(value):raise ValueError("TEXT anchor requires non-empty value")
        return {"type":"TEXT","value":value}
    if kind=="FILE_SHA256":
        value=anchor.get("sha256") or source_sha
        if value!=source_sha:raise ValueError("FILE_SHA256 anchor does not match receipt source")
        return {"type":"FILE_SHA256","sha256":source_sha}
    raise ValueError(f"unsupported source anchor type: {kind}")


def _verify_anchors(data:bytes,anchors:list[dict],source_sha:str):
    if not isinstance(anchors,list) or not anchors:return False,"SOURCE_ANCHORS_MISSING"
    text=None
    for anchor in anchors:
        kind=anchor.get("type")
        if kind=="FILE_SHA256":
            if anchor.get("sha256")!=source_sha:return False,"SOURCE_ANCHOR_HASH_MISMATCH"
        elif kind=="TEXT":
            if text is None:
                for enc in ("utf-8-sig","utf-8","cp1251"):
                    try:text=data.decode(enc);break
                    except UnicodeDecodeError:pass
                if text is None:text=data.decode("utf-8",errors="replace")
            if anchor.get("value") not in text:return False,"SOURCE_ANCHOR_NOT_FOUND"
        else:return False,"SOURCE_ANCHOR_TYPE_UNSUPPORTED"
    return True,None


def _canonical_observation(data,anchors,source):
    ok,error=_verify_anchors(data,anchors,source["sha256"])
    if not ok:raise ValueError(error)
    material={"source_sha256":source["sha256"],"anchors":anchors}
    return {
        "mode":"ATTACH_ONLY_SOURCE_OBSERVATION",
        "source_sha256":source["sha256"],
        "anchors_sha256":_sha(_canon(material).encode("utf-8")),
        "anchors_verified":True,
    }


def _canonical_predicate(target):
    predicate=target.get("receipt_predicate")
    if predicate is None:return None
    if not isinstance(predicate,dict):raise ValueError(f"invalid rule-owned receipt predicate for {target['rule_id']}:{target['check_id']}")
    verifier_id=predicate.get("verifier_id")
    if verifier_id not in KNOWN_RULE_PREDICATE_VERIFIERS:
        raise ValueError(f"unknown rule-owned receipt predicate verifier: {verifier_id}")
    return predicate


def _source_identity(source):
    keys=("type","ref","sha256","size","path","archive_path","archive_sha256","entry_path","entry_sha256")
    return {key:source.get(key) for key in keys if source.get(key) is not None}


def _receipt_binding_key(kind,ref,claim_id):
    return _sha(_canon({"kind":str(kind).upper(),"ref":ref,"claim_id":claim_id}).encode("utf-8"))


def _provenance_id(receipt_id,kind,ref,claim_id):
    material={"receipt_id":receipt_id,"kind":str(kind).upper(),"ref":ref,"claim_id":claim_id}
    return "RECEIPT_EVIDENCE:"+_sha(_canon(material).encode("utf-8"))


def _prepare_binding(binding,target,data,source,kind):
    claim=target["row"].get("claim_id")
    anchors=binding.get("source_anchors") if isinstance(binding,dict) else None
    normalized=[_normalize_anchor(x,source["sha256"]) for x in (anchors or [{"type":"FILE_SHA256","sha256":source["sha256"]}])]
    observation=_canonical_observation(data,normalized,source)
    predicate=_canonical_predicate(target)
    # No generic predicate is accepted. The receipt merely transports checked source evidence.
    return {
        "claim_id":claim,"rule_id":target["rule_id"],"check_id":target["check_id"],
        "claim_question_sha256":_sha(target["question"].encode("utf-8")),
        "model_observation":binding.get("observation") if isinstance(binding,dict) and binding.get("observation") is not None else "source evidence attached for claim review",
        "source_anchors":normalized,
        "applicability_reason":binding.get("applicability_reason","") if isinstance(binding,dict) else "",
        "verified_observation":observation,
        "verification_mode":"ATTACH_ONLY" if predicate is None else "RULE_OWNED_PREDICATE",
        "rule_owned_predicate":predicate,
    }


def prepare_receipt(ledger_path:Path,receipt_path:Path,receipt_id:str,kind:str,ref:str,claim_ids:list[str]|None=None,bindings:list[dict]|None=None,source_type:str="FILE"):
    raw=ledger_path.read_bytes(); ledger=json.loads(raw.decode("utf-8-sig")); registry=load_registry(); index=_check_index(ledger,registry)
    kind=kind.upper()
    if kind not in ALLOWED_KINDS:raise ValueError("evidence receipt may contain only SOURCE_REQUIRED or SEMANTIC evidence; MACHINE/RUNTIME require verifier-owned receipts/cases")
    if not _has_text(receipt_id) or not _has_text(ref):raise ValueError("receipt id and concrete source ref are required")
    source,data=_source_snapshot(ledger,ref,source_type)

    requested=list(dict.fromkeys(claim_ids or []))
    if bindings:
        requested.extend(x.get("claim_id") for x in bindings if isinstance(x,dict) and _has_text(x.get("claim_id")))
        requested=list(dict.fromkeys(requested))
    if not requested:raise ValueError("at least one exact predeclared claim is required")
    by_claim={x.get("claim_id"):x for x in (bindings or []) if isinstance(x,dict) and _has_text(x.get("claim_id"))}
    prepared=[]
    for claim in requested:
        target=index.get(claim)
        if not target:raise ValueError(f"claim is not an exact registered ledger check: {claim}")
        if target["row"].get("status")!="EVIDENCE_REQUIRED":raise ValueError(f"claim must be EVIDENCE_REQUIRED before receipt preparation: {claim}")
        if kind not in target["allowed_kinds"]:raise ValueError(f"{kind} evidence is not allowed for {claim}")
        prepared.append(_prepare_binding(by_claim.get(claim) or {"claim_id":claim},target,data,source,kind))

    receipt={
        "schema_version":SCHEMA_VERSION,"id":receipt_id,"kind":kind,"ledger_sha256":_sha(raw),
        "source":source,"bindings":prepared,
        "rule":"Generic SOURCE_REQUIRED/SEMANTIC receipts are attach-only. PASS requires a canonical rule-owned deterministic predicate with a known verifier; none are enabled by this tool today. MACHINE/RUNTIME remain separate verifier-owned proof.",
    }
    receipt_path.parent.mkdir(parents=True,exist_ok=True)
    receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return receipt


def _apply_binding(binding,target,data,source,kind,receipt_meta,provenance_rows):
    claim=binding.get("claim_id")
    if binding.get("rule_id")!=target["rule_id"] or binding.get("check_id")!=target["check_id"]:return False,"RECEIPT_BINDING_IDENTITY_DRIFT"
    if binding.get("claim_question_sha256")!=_sha(target["question"].encode("utf-8")):return False,"RECEIPT_CLAIM_QUESTION_DRIFT"

    try:
        anchors=[_normalize_anchor(x,source["sha256"]) for x in (binding.get("source_anchors") or [])]
        current_observation=_canonical_observation(data,anchors,source)
        predicate=_canonical_predicate(target)
    except ValueError as exc:
        return False,str(exc)

    canonical_mode="ATTACH_ONLY" if predicate is None else "RULE_OWNED_PREDICATE"
    if binding.get("verification_mode")!=canonical_mode:return False,"RECEIPT_VERIFICATION_MODE_NOT_CANONICAL"
    if binding.get("rule_owned_predicate")!=predicate:return False,"RECEIPT_RULE_PREDICATE_DRIFT"
    if binding.get("verified_observation")!=current_observation:return False,"RECEIPT_VERIFIED_OBSERVATION_DRIFT"

    if predicate is not None:
        return False,"RULE_OWNED_RECEIPT_PREDICATE_NOT_IMPLEMENTED"

    receipt_id=receipt_meta["id"]
    provenance_id=_provenance_id(receipt_id,kind,source["ref"],claim)
    source_identity=_source_identity(source)
    evidence={
        "kind":kind,"ref":source["ref"],"claim_id":claim,
        "receipt_id":receipt_id,
        "receipt_ref":receipt_meta["ref"],
        "receipt_sha256":receipt_meta["sha256"],
        "receipt_schema_version":receipt_meta["schema_version"],
        "receipt_provenance_id":provenance_id,
        "source_sha256":source["sha256"],
        "source_fingerprint":{"algorithm":"SHA-256","sha256":source["sha256"],"type":source["type"]},
        "source_anchors":anchors,
        "observation":current_observation,
        "applicability_reason":binding.get("applicability_reason") or "",
        "verification_mode":"ATTACH_ONLY",
        "proof_role":"SUPPORTING_ONLY",
        "supporting_only":True,
    }
    if source["type"]=="ARCHIVE_ENTRY":
        evidence.update({
            "archive_path":source["archive_path"],"archive_sha256":source["archive_sha256"],
            "entry_path":source["entry_path"],"entry_sha256":source["entry_sha256"],
        })
    target["row"]["evidence"]=[*(target["row"].get("evidence") or []),evidence]

    provenance={
        "id":provenance_id,
        "receipt_id":receipt_id,
        "receipt_ref":receipt_meta["ref"],
        "receipt_sha256":receipt_meta["sha256"],
        "receipt_schema_version":receipt_meta["schema_version"],
        "claim_id":claim,
        "rule_id":target["rule_id"],
        "check_id":target["check_id"],
        "kind":kind,
        "source_ref":source["ref"],
        "source_sha256":source["sha256"],
        "source_identity":source_identity,
        "binding_key_sha256":_receipt_binding_key(kind,source["ref"],claim),
        "verification_mode":"ATTACH_ONLY",
        "proof_role":"SUPPORTING_ONLY",
        "supporting_only":True,
        "rule_owned_predicate":None,
    }
    existing=next((row for row in provenance_rows if isinstance(row,dict) and row.get("id")==provenance_id),None)
    if existing is not None and existing!=provenance:
        return False,"RECEIPT_EVIDENCE_PROVENANCE_COLLISION"
    if existing is None:
        provenance_rows.append(provenance)
    return None,None


def _same_source_identity(expected,current):
    keys=("type","ref","sha256","size","archive_path","archive_sha256","entry_path","entry_sha256","path")
    return all(expected.get(k)==current.get(k) for k in keys if k in expected or k in current)


def apply_receipt(ledger_path:Path,receipt_path:Path,output_path:Path):
    raw=ledger_path.read_bytes(); ledger=json.loads(raw.decode("utf-8-sig")); receipt=json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if receipt.get("schema_version")!=SCHEMA_VERSION:raise ValueError("unsupported evidence receipt schema")
    if receipt.get("ledger_sha256")!=_sha(raw):raise ValueError("evidence receipt ledger binding mismatch; rebuild receipt for current ledger")
    kind=str(receipt.get("kind") or "").upper()
    if kind not in ALLOWED_KINDS:raise ValueError("evidence receipt kind is not allowed")
    source=receipt.get("source") or {}; ref=source.get("ref")
    if not _has_text(ref):raise ValueError("evidence receipt source is missing")
    current,current_data=_source_snapshot(ledger,ref,source.get("type"))
    if not _same_source_identity(source,current):raise ValueError("evidence receipt source drift: exact source/archive/entry fingerprint changed")

    bindings=receipt.get("bindings")
    if not isinstance(bindings,list) or not bindings:raise ValueError("evidence receipt bindings are required")
    claims=[x.get("claim_id") for x in bindings if isinstance(x,dict)]
    if any(not _has_text(x) for x in claims) or len(claims)!=len(set(claims)):raise ValueError("receipt claim bindings must be unique exact ids")

    receipt_bytes=receipt_path.read_bytes()
    receipt_meta={
        "id":receipt["id"],
        "ref":_resolved_path(str(receipt_path)),
        "sha256":_sha(receipt_bytes),
        "schema_version":receipt["schema_version"],
    }
    provenance_rows=ledger.setdefault("receipt_evidence_provenance",[])
    if not isinstance(provenance_rows,list):
        raise ValueError("receipt_evidence_provenance must be a list")

    index=_check_index(ledger,load_registry()); attached=[]; rejected=[]
    for binding in bindings:
        claim=binding["claim_id"]; target=index.get(claim)
        if not target:rejected.append({"claim_id":claim,"error":"CLAIM_NOT_IN_LEDGER"});continue
        if target["row"].get("status")!="EVIDENCE_REQUIRED":rejected.append({"claim_id":claim,"error":"CLAIM_NOT_EVIDENCE_REQUIRED"});continue
        if kind not in target["allowed_kinds"]:rejected.append({"claim_id":claim,"error":"EVIDENCE_KIND_NOT_ALLOWED"});continue
        result,error=_apply_binding(binding,target,current_data,current,kind,receipt_meta,provenance_rows)
        if result is None:attached.append(claim)
        else:rejected.append({"claim_id":claim,"error":error})

    output_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return {
        "result":"PASS" if not rejected else "PARTIAL","receipt_id":receipt["id"],"kind":kind,
        "passed_claim_ids":[],"attached_claim_ids":attached,"rejected":rejected,"output":str(output_path),
        "rule_owned_auto_pass_predicates_enabled":False,
        "proof_boundary":"Generic SOURCE_REQUIRED/SEMANTIC receipts are SUPPORTING_ONLY. Receipt provenance is recorded separately and replayed by the release gate; no editable receipt field can create primary proof. MACHINE/RUNTIME remain separate verifier-owned proof.",
    }


def main()->int:
    ap=argparse.ArgumentParser(description="Prepare/apply exact-corpus multi-claim evidence receipts.")
    sub=ap.add_subparsers(dest="command",required=True)
    prep=sub.add_parser("prepare")
    prep.add_argument("--ledger",required=True); prep.add_argument("--receipt",required=True); prep.add_argument("--id",required=True)
    prep.add_argument("--kind",required=True,choices=tuple(sorted(ALLOWED_KINDS))); prep.add_argument("--ref",required=True)
    prep.add_argument("--source-type",choices=("FILE","ARCHIVE_ENTRY"),default="FILE")
    prep.add_argument("--claim-id",action="append",default=[])
    prep.add_argument("--binding-json",action="append",default=[],help="Per-claim JSON with claim_id, observation, source_anchors and optional applicability_reason. Assertions never create PASS.")
    apply=sub.add_parser("apply")
    apply.add_argument("--ledger",required=True); apply.add_argument("--receipt",required=True); apply.add_argument("--output",required=True)
    args=ap.parse_args()
    try:
        if args.command=="prepare":
            bindings=[json.loads(x) for x in args.binding_json]
            result=prepare_receipt(Path(args.ledger),Path(args.receipt),args.id,args.kind,args.ref,args.claim_id,bindings,args.source_type)
            shown={"result":"PASS","receipt":str(Path(args.receipt)),"id":result["id"],"kind":result["kind"],"claim_ids":[x["claim_id"] for x in result["bindings"]],"source_sha256":result["source"]["sha256"]}
            code=0
        else:
            shown=apply_receipt(Path(args.ledger),Path(args.receipt),Path(args.output)); code=0 if shown["result"]=="PASS" else 2
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        print(json.dumps({"result":"FAIL","error":str(exc)},ensure_ascii=False,separators=(",",":")));return 2
    print(json.dumps(shown,ensure_ascii=False,separators=(",",":")));return code


if __name__=="__main__":
    raise SystemExit(main())
