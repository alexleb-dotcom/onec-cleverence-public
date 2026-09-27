#!/usr/bin/env python3
"""Fail-closed policy for artifacts that may guide discovery/shape but may not prove a claim.

Classification is entity/provenance-oriented rather than spelling-oriented: equivalent
relative/absolute/URL/archive references are normalized, symlinks resolve to their target,
and byte-identical local copies of known non-proof artifacts retain the non-proof role.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse
import argparse
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
NON_PROOF_ROOTS=(
    ("PATTERNS/","ILLUSTRATIVE_PATTERN"),
    ("REFERENCE/CATALOGS/","DISCOVERY_ONLY"),
    ("TESTS/fixtures/","TEST_FIXTURE"),
)


def _norm(value):
    return unquote(str(value or "")).replace("\\","/").strip()


def _segments(value):
    text=_norm(value).replace("!/","/")
    parsed=urlparse(text) if "://" in text else None
    if parsed and parsed.scheme and parsed.netloc:
        text=unquote(parsed.path).replace("\\","/")
    result=[]
    for raw in text.split("/"):
        part=raw.strip().strip("'\"()[]{}<>")
        if not part or part==".":
            continue
        if part=="..":
            if result and result[-1]!="..":result.pop()
            else:result.append(part)
            continue
        result.append(part)
    return result


def _lexical_hit(value):
    parts=[x.upper() for x in _segments(value)]
    for prefix,role in NON_PROOF_ROOTS:
        wanted=[x.upper() for x in prefix.strip("/").split("/")]
        for start in range(0,max(0,len(parts)-len(wanted)+1)):
            if parts[start:start+len(wanted)]==wanted:
                return {"role":role,"prefix":prefix,"matched_by":"CANONICAL_PATH"}
    return None


def _candidate_local_paths(value):
    text=_norm(value)
    if not text or "://" in text:
        return []
    archive=text.split("!/",1)[0] if "!/" in text else text
    path=Path(archive)
    candidates=[path]
    if not path.is_absolute():candidates.append(ROOT/path)
    result=[]; seen=set()
    for candidate in candidates:
        try:resolved=candidate.resolve(strict=False)
        except OSError:resolved=candidate.absolute()
        key=str(resolved)
        if key not in seen:
            seen.add(key); result.append(resolved)
    return result


def _ref_bytes(value):
    text=_norm(value)
    if not text or "://" in text:
        return None
    if "!/" in text:
        _,entry=text.split("!/",1)
        for archive in _candidate_local_paths(text):
            if not archive.is_file():continue
            try:
                with zipfile.ZipFile(archive) as z:return z.read(entry)
            except (KeyError,zipfile.BadZipFile,OSError):
                continue
        return None
    for path in _candidate_local_paths(text):
        if not path.is_file():continue
        try:return path.read_bytes()
        except OSError:continue
    return None


@lru_cache(maxsize=1)
def _non_proof_fingerprints():
    index={}
    for prefix,role in NON_PROOF_ROOTS:
        root=ROOT/prefix.rstrip("/")
        if not root.is_dir():continue
        for path in sorted(x for x in root.rglob("*") if x.is_file()):
            try:digest=hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:continue
            index.setdefault(digest,[]).append({"role":role,"prefix":prefix,"source":str(path.relative_to(ROOT)).replace("\\","/")})
    return index


def classify_non_proof_ref(value):
    text=_norm(value)
    hit=_lexical_hit(text)
    if hit:
        return {**hit,"ref":text}

    data=_ref_bytes(text)
    if data is not None:
        matches=_non_proof_fingerprints().get(hashlib.sha256(data).hexdigest()) or []
        if matches:
            first=matches[0]
            return {
                "role":first["role"],
                "prefix":first["prefix"],
                "ref":text,
                "matched_by":"CONTENT_FINGERPRINT",
                "source":first["source"],
            }
    return None


def validate_evidence_items(items,scope="evidence"):
    errors=[]
    for index,item in enumerate(items or []):
        if not isinstance(item,dict):continue
        hit=classify_non_proof_ref(item.get("ref"))
        if hit:
            errors.append({
                "type":"NON_PROOF_ARTIFACT_USED_AS_EVIDENCE",
                "scope":scope,
                "index":index,
                "role":hit["role"],
                "prefix":hit["prefix"],
                "ref":hit["ref"],
                "matched_by":hit.get("matched_by"),
                "source":hit.get("source"),
            })
    return errors


def validate_ledger(ledger):
    errors=[]

    def walk(value,path="ledger"):
        if isinstance(value,dict):
            if isinstance(value.get("evidence"),list):
                errors.extend(validate_evidence_items(value["evidence"],f"{path}.evidence"))
            if path.startswith("ledger.evidence_registry") and isinstance(value.get("ref"),str):
                hit=classify_non_proof_ref(value.get("ref"))
                if hit:
                    errors.append({
                        "type":"NON_PROOF_ARTIFACT_USED_AS_EVIDENCE",
                        "scope":path,
                        "role":hit["role"],
                        "prefix":hit["prefix"],
                        "ref":hit["ref"],
                        "matched_by":hit.get("matched_by"),
                        "source":hit.get("source"),
                    })
            for key,child in value.items():
                if key=="evidence":continue
                walk(child,f"{path}.{key}")
        elif isinstance(value,list):
            for index,child in enumerate(value):walk(child,f"{path}[{index}]")

    walk(ledger)
    return {
        "result":"PASS" if not errors else "FAIL",
        "errors":errors,
        "rule":"ILLUSTRATIVE_PATTERN, DISCOVERY_ONLY catalogs and TESTS/fixtures may guide shape/discovery/testing but may never close semantic/API/signature/runtime proof. Equivalent path spellings, symlinks and byte-identical local copies retain the non-proof role; use exact target/user-authorized source and linked machine/runtime evidence instead.",
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--ledger",required=True)
    a=ap.parse_args(); ledger=json.loads(Path(a.ledger).read_text(encoding="utf-8-sig")); report=validate_ledger(ledger)
    print(json.dumps(report,ensure_ascii=False,indent=2)); raise SystemExit(0 if report["result"]=="PASS" else 2)

if __name__=="__main__":main()
