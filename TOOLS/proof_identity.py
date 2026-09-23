#!/usr/bin/env python3
"""Canonical identities and exact artifact deltas shared by proof verifiers.

These helpers bind semantic review and implementation intent to the exact review
plan and its current candidate/baseline/requirements identities. They prove byte
identity and structural change only; they do not prove business/runtime semantics.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import zipfile

from artifact_corpus import inventory_paths, analyzable_entries


def canonical_json(value)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def sha256_json(value)->str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def candidate_identity(plan:dict)->dict:
    rows=[]
    for item in plan.get("candidate_artifacts") or []:
        if not isinstance(item,dict):
            continue
        rows.append({
            "logical_path":item.get("logical_path"),
            "sha256":item.get("sha256"),
            "size":item.get("size"),
            "onec":bool(item.get("onec")),
            "cleverence":bool(item.get("cleverence")),
        })
    rows.sort(key=lambda x:(str(x.get("logical_path") or ""),str(x.get("sha256") or "")))
    return {"artifacts":rows,"fingerprint_sha256":sha256_json(rows)}


def baseline_identity(plan:dict)->dict:
    baseline=plan.get("baseline")
    if not isinstance(baseline,dict):
        payload={"kind":"NO_BASELINE"}
    else:
        payload={key:baseline.get(key) for key in ("kind","sha256","size","files") if baseline.get(key) is not None}
    return {**payload,"fingerprint_sha256":sha256_json(payload)}


def requirements_identity(plan:dict)->dict:
    req=plan.get("requirements") or {}
    payload={
        "required":bool(req.get("required")),
        "sha256":req.get("sha256") or "NO_REQUIREMENTS_CONTRACT",
        "surface":req.get("surface"),
        "risk":req.get("risk"),
        "gate_outcome":req.get("gate_outcome"),
    }
    return {**payload,"fingerprint_sha256":sha256_json(payload)}


def project_identity(plan:dict)->dict:
    intake=plan.get("release_intake") or {}
    context=plan.get("project_context") or {}
    payload={
        "kind":"PLAN_BOUND_PROJECT",
        "release_intake_sha256":intake.get("sha256"),
        "project_context_sha256":context.get("sha256"),
        "artifact_model":plan.get("artifact_model"),
        "routing":{k:(plan.get("routing") or {}).get(k) for k in ("surface","risk","mode")},
    }
    return {**payload,"fingerprint_sha256":sha256_json(payload)}


def plan_binding(plan:dict)->dict:
    return {
        "project_identity":project_identity(plan),
        "candidate_identity":candidate_identity(plan),
        "baseline_identity":baseline_identity(plan),
        "requirements_identity":requirements_identity(plan),
        "review_plan_sha256":sha256_json(plan),
    }


def candidate_index(plan:dict)->dict:
    return {
        row.get("logical_path"):row
        for row in plan.get("candidate_artifacts") or []
        if isinstance(row,dict) and isinstance(row.get("logical_path"),str)
    }


def _normalized_entry(value:str)->str:
    parts=[]
    for raw in str(value or "").replace("\\","/").split("/"):
        if raw in {"","."}:continue
        if raw=="..":
            if not parts:return ""
            parts.pop()
        else:parts.append(raw)
    return "/".join(parts)


def _decode(raw:bytes)->str:
    for enc in ("utf-8-sig","utf-8","cp1251"):
        try:return raw.decode(enc)
        except UnicodeDecodeError:pass
    return raw.decode("utf-8",errors="replace")


def _surface_flags(logical:str,raw:bytes)->tuple[bool,bool]:
    suffix=Path(logical).suffix.lower(); name=Path(logical).name.lower(); text=_decode(raw)
    cleverence=(
        suffix==".mslx"
        or logical.startswith(("Operations/","Metadata/","DocumentTypes/"))
        or bool(re.search(r"<(?:\w+:)?(?:Operation|\w+Action|ContainerTypesBook|CommonFieldInfoCollection|DocumentType)\b",text,re.I))
    )
    onec=(
        suffix in {".bsl",".os"} or name=="package.bin"
        or bool(re.search(r"https?://v8\.1c\.ru/|<MetaDataObject\b|<Form\b[^>]*xcf/logform|<package\b[^>]*targetNamespace",text,re.I))
    )
    return onec,cleverence


def read_artifact_bytes(artifact:dict)->bytes|None:
    origin=artifact.get("origin")
    if not isinstance(origin,str) or not origin:
        return None
    if "!/" in origin:
        archive,entry=origin.split("!/",1)
        path=Path(archive)
        if not path.is_file():return None
        wanted=_normalized_entry(entry)
        try:
            with zipfile.ZipFile(path) as z:
                matches=[x for x in z.infolist() if not x.is_dir() and _normalized_entry(x.filename)==wanted]
                if len(matches)!=1:return None
                return z.read(matches[0])
        except (OSError,zipfile.BadZipFile,KeyError):
            return None
    path=Path(origin)
    try:return path.read_bytes() if path.is_file() else None
    except OSError:return None


def read_baseline_bytes(plan:dict,artifact:dict)->bytes|None:
    baseline=plan.get("baseline")
    if not isinstance(baseline,dict) or not isinstance(baseline.get("path"),str):
        return None
    root=Path(baseline["path"])
    logical=str(artifact.get("logical_path") or "").replace("\\","/")
    kind=baseline.get("kind")
    if kind=="DIRECTORY":
        candidate=root.joinpath(*[x for x in logical.split("/") if x])
        try:return candidate.read_bytes() if candidate.is_file() else None
        except OSError:return None
    if kind!="FILE" or not root.is_file():
        return None
    if len(plan.get("candidate_artifacts") or [])==1 and not zipfile.is_zipfile(root):
        try:return root.read_bytes()
        except OSError:return None
    if zipfile.is_zipfile(root):
        try:
            corpus=inventory_paths([root])
            matches=[(row,data) for row,data,_,_ in analyzable_entries(corpus) if row==logical]
            if len(matches)==1:return matches[0][1]
        except Exception:
            return None
    return None


def baseline_index(plan:dict)->dict:
    """Return analyzable baseline artifacts, including baseline-only deletion candidates."""
    baseline=plan.get("baseline")
    if not isinstance(baseline,dict) or not isinstance(baseline.get("path"),str):
        return {}
    root=Path(baseline["path"])
    if not root.exists():
        return {}
    candidates=candidate_index(plan)
    if baseline.get("kind")=="FILE" and root.is_file() and not zipfile.is_zipfile(root):
        try:raw=root.read_bytes()
        except OSError:return {}
        logical=next(iter(candidates)) if len(candidates)==1 else root.name
        onec,cleverence=_surface_flags(logical,raw)
        return {logical:{
            "logical_path":logical,"origin":str(root),"sha256":hashlib.sha256(raw).hexdigest(),
            "size":len(raw),"onec":onec,"cleverence":cleverence,"bytes":raw,
        }}
    try:
        corpus=inventory_paths([root])
    except Exception:
        return {}
    result={}
    for logical,data,origin,row in analyzable_entries(corpus):
        onec,cleverence=_surface_flags(logical,data)
        result[logical]={
            "logical_path":logical,"origin":origin,"sha256":hashlib.sha256(data).hexdigest(),
            "size":len(data),"onec":onec,"cleverence":cleverence,"bytes":data,
        }
    return result


def artifact_delta(plan:dict)->dict:
    """Exact analyzable artifact create/modify/delete delta.

    Baseline-only artifacts are retained as delete obligations. This is byte/shape
    evidence only and must not be interpreted as runtime or business proof.
    """
    current=candidate_index(plan); before=baseline_index(plan); result={}
    for logical in sorted(set(current)|set(before)):
        candidate=current.get(logical); baseline=before.get(logical)
        current_bytes=read_artifact_bytes(candidate) if candidate else None
        baseline_bytes=(baseline or {}).get("bytes")
        if candidate and baseline:
            if current_bytes==baseline_bytes:
                continue
            action="modify"
        elif candidate:
            action="create"
        else:
            action="delete"
        candidate_sha=(hashlib.sha256(current_bytes).hexdigest() if current_bytes is not None else (candidate or {}).get("sha256"))
        baseline_sha=(baseline or {}).get("sha256")
        result[logical]={
            "logical_path":logical,
            "action":action,
            "candidate_sha256":candidate_sha,
            "baseline_sha256":baseline_sha,
            "candidate_bytes":current_bytes,
            "baseline_bytes":baseline_bytes,
            "candidate_artifact":candidate,
            "baseline_artifact":baseline,
            "onec":bool((candidate or baseline or {}).get("onec")),
            "cleverence":bool((candidate or baseline or {}).get("cleverence")),
        }
    return result
