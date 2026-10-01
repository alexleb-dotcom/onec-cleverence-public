#!/usr/bin/env python3
"""Verifier for the canonical Implementation Intent Map.

The verifier proves exact baseline/candidate delta identity and intent-map
completeness for created, modified and deleted artifacts/fragments. Structural
BSL/XML comparison is not runtime or business-semantic proof; rationale truth
remains owned by separated semantic review.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parent))
from proof_identity import plan_binding,artifact_delta
from proof_contract import rule_claim_id
from semantic_proof_verifier import validate_independent_reviews

SCHEMA_VERSION=3
EXISTING_CAPABILITY_RULE_ID="ANALOG_BEFORE_INVENTION"
STANDARD_CAPABILITY_CHECK_ID="STANDARD_CAPABILITY_BEFORE_CUSTOMIZATION"
SOURCE_DEPENDENT_CHECK_ID="SOURCE_DEPENDENT_IMPLEMENTATION_GATE"
STANDARD_PIPELINE_RULE_ID="STANDARD_PIPELINE_SEMANTIC_PRESERVATION"
SOURCE_DEPENDENCY_STATUSES={"PROVEN","EVIDENCE_REQUIRED"}
SOURCE_DEPENDENCY_FACT_KINDS={"ATTRIBUTE","PARAMETER","SIGNATURE","QUERY_MODE","STANDARD_API_BEHAVIOR","OBJECT_BEHAVIOR","SOURCE_FACT"}
EXISTING_CAPABILITY_DISPOSITIONS={"REUSE_EXISTING","EXTEND_EXISTING","CUSTOM_REQUIRED","EVIDENCE_REQUIRED"}
SOURCE_PROVENANCE_VERIFIER_ID="release_gate_core.source_identity"
SOURCE_PROVENANCE_VERSION=1
ACTIONS={"create","modify","delete"}
TARGET_KINDS={"ARTIFACT","BSL_ROUTINE","MSLX_ACTION","CLEVERENCE_FIELD","XML_FRAGMENT","MAPPING","WRITER"}
ENTRYPOINT_KINDS={"ENTRYPOINT","CALLER","CALLBACK","PUBLIC_API","HELPER_REACHABLE"}
FIELD_TAGS={"field","fieldinfo","commonfieldinfo"}


def _text(v):return isinstance(v,str) and bool(v.strip())
def _decode(raw):
    if raw is None:return ""
    for enc in ("utf-8-sig","utf-8","cp1251"):
        try:return raw.decode(enc)
        except UnicodeDecodeError:pass
    return raw.decode("utf-8",errors="replace")


def _bsl_identity(name):
    """BSL routine identity follows the case-insensitive call-signature contract."""
    return str(name or "").casefold()


def _record_unique_identity(rows,duplicates,identity,spec):
    """Keep only unambiguous semantic identities; never select a last duplicate."""
    if identity in duplicates:
        duplicates[identity].append(spec);return
    if identity in rows:
        first=rows.pop(identity)
        duplicates[identity]=[first,spec];return
    rows[identity]=spec


def _bsl_routines(text):
    starts=list(re.finditer(r"(?im)^\s*(Процедура|Функция)\s+([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\([^\n]*?\)\s*(Экспорт)?\s*$",text))
    rows={};duplicates={}
    for i,m in enumerate(starts):
        end_token="КонецПроцедуры" if m.group(1).lower()=="процедура" else "КонецФункции"
        end=re.search(rf"(?im)^\s*{end_token}\b",text[m.end():])
        stop=m.end()+end.end() if end else (starts[i+1].start() if i+1<len(starts) else len(text))
        body=text[m.start():stop];name=m.group(2);identity=_bsl_identity(name)
        _record_unique_identity(rows,duplicates,identity,{
            "name":name,"semantic_identity":identity,
            "routine_kind":m.group(1).upper(),"export":bool(m.group(3)),
            "sha256":hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "ordinal":i+1,
        })
    return rows,duplicates


def _lname(value)->str:
    return str(value or "").split("}",1)[-1].split(":")[-1]


def _canonical_element(element)->str:
    attrs=sorted((_lname(k),str(v).strip()) for k,v in element.attrib.items())
    payload=[
        _lname(element.tag),
        attrs,
        (element.text or "").strip(),
        [_canonical_element(child) for child in list(element)],
    ]
    return json.dumps(payload,ensure_ascii=False,separators=(",",":"))


def _parse_xml(text):
    if not text.strip():return None,None
    try:return ET.fromstring(text),None
    except ET.ParseError as first:
        stripped=re.sub(r"<\?xml[^>]*\?>","",text,flags=re.I).strip()
        try:return ET.fromstring(f"<IntentRoot>{stripped}</IntentRoot>"),None
        except ET.ParseError:return None,str(first)


def _direct_child_text(element,*names):
    wanted={x.lower() for x in names}
    for child in list(element):
        if _lname(child.tag).lower() in wanted and _text(child.text):
            return child.text.strip()
    return None


def _identity(element,ordinal,kind):
    attrs={_lname(k).lower():str(v).strip() for k,v in element.attrib.items()}
    for key in ("id","name"):
        if _text(attrs.get(key)):return attrs[key]
    child=_direct_child_text(element,"Id","Name")
    if _text(child):return child
    if kind=="mapping":
        source=attrs.get("source") or attrs.get("from") or _direct_child_text(element,"Source","From")
        target=attrs.get("target") or attrs.get("to") or _direct_child_text(element,"Target","To")
        if _text(source) or _text(target):return f"{source or '?'}->{target or '?'}"
    return f"{_lname(element.tag)}#{ordinal}"


def _xml_contract_nodes(text):
    root,error=_parse_xml(text)
    empty={"actions":{},"fields":{},"mappings":{}}
    if root is None:return empty,error,{"actions":{},"fields":{},"mappings":{}}
    result={"actions":{},"fields":{},"mappings":{}}
    duplicates={"actions":{},"fields":{},"mappings":{}}
    counters={"action":0,"field":0,"mapping":0}
    for element in root.iter():
        tag=_lname(element.tag); lower=tag.lower(); kind=None
        if lower.endswith("action"):kind="action"
        elif lower in FIELD_TAGS or lower.endswith("fieldinfo"):kind="field"
        elif "mapping" in lower or lower in {"map","mapitem","fieldmap"}:kind="mapping"
        if not kind:continue
        counters[kind]+=1; ident=_identity(element,counters[kind],kind)
        bucket={"action":"actions","field":"fields","mapping":"mappings"}[kind]
        _record_unique_identity(result[bucket],duplicates[bucket],ident,{
            "id":ident,"tag":tag,
            "sha256":hashlib.sha256(_canonical_element(element).encode("utf-8")).hexdigest(),
            "ordinal":counters[kind],
        })
    return result,None,duplicates


def _delta_rows(before,after):
    result={}
    for key in sorted(set(before)|set(after)):
        old=before.get(key); new=after.get(key)
        if old and new:
            if old.get("sha256")==new.get("sha256"):continue
            action="modify"
        elif new:action="create"
        else:action="delete"
        result[key]={"action":action,"before":old,"after":new}
    return result


def _requirements_acceptance_ids(plan):
    req=plan.get("requirements") or {}; path=req.get("path")
    if not _text(path) or not Path(path).is_file():return None
    try:doc=json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:return None
    field=(doc.get("functional_contract") or {}).get("acceptance_cases") or {}
    value=field.get("value") if isinstance(field,dict) else None
    ids=set()
    if isinstance(value,list):
        for item in value:
            if isinstance(item,str) and item.strip():ids.add(item.strip())
            elif isinstance(item,dict):
                ident=item.get("id") or item.get("case_id")
                if _text(ident):ids.add(ident)
    elif isinstance(value,dict):
        for key,item in value.items():
            if _text(key):ids.add(key)
            if isinstance(item,dict):
                ident=item.get("id") or item.get("case_id")
                if _text(ident):ids.add(ident)
    return ids


def _surface_rows(plan):
    rows=[]
    for logical,info in artifact_delta(plan).items():
        rows.append({
            "artifact":logical,"action":info["action"],
            "candidate_sha256":info.get("candidate_sha256"),
            "baseline_sha256":info.get("baseline_sha256"),
        })
    return sorted(rows,key=lambda x:x["artifact"])


def build_skeleton(plan:dict)->dict:
    binding=plan_binding(plan)
    return {
        "schema_version":SCHEMA_VERSION,
        "binding":{
            "candidate_fingerprint_sha256":binding["candidate_identity"]["fingerprint_sha256"],
            "baseline_fingerprint_sha256":binding["baseline_identity"]["fingerprint_sha256"],
            "requirements_fingerprint_sha256":binding["requirements_identity"]["fingerprint_sha256"],
            "review_plan_sha256":binding["review_plan_sha256"],
        },
        "change_surface":_surface_rows(plan),
        "rows":[],
        "limitations":[
            "Completeness/identity and structural deltas are machine-checked. Necessity, ownership, alternative rejection and runtime/business semantics require independent evidence."
        ],
    }


def _required_text(row,fields,errors,index):
    for field in fields:
        if not _text(row.get(field)):errors.append({"type":"INTENT_ROW_FIELD_MISSING","index":index,"field":field})


def _ambiguity_errors(errors,logical,side,kind,duplicates):
    for identity,specs in sorted(duplicates.items()):
        row={
            "type":"IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS",
            "artifact":logical,"side":side,"kind":kind,"identity":identity,
            "occurrences":len(specs),
        }
        if kind=="BSL_ROUTINE":
            spellings=[]
            for spec in specs:
                spelling=spec.get("name") if isinstance(spec,dict) else None
                if _text(spelling) and spelling not in spellings:spellings.append(spelling)
            if spellings:
                row["identity"]=spellings[0]
                row["normalized_identity"]=identity
                row["spellings"]=spellings
        errors.append(row)


def _fragment_identity(target_kind,fragment):
    if target_kind=="BSL_ROUTINE" and _text(fragment):
        return _bsl_identity(fragment)
    return fragment


def _without_ambiguous(rows,*duplicate_maps):
    blocked=set()
    for mapping in duplicate_maps:blocked.update(mapping)
    return {identity:spec for identity,spec in rows.items() if identity not in blocked}


def _fragment_deltas(info,logical,errors):
    current=_decode(info.get("candidate_bytes")); previous=_decode(info.get("baseline_bytes"))
    suffix=Path(logical).suffix.lower(); fragments={}
    if suffix in {".bsl",".os"} or info.get("onec"):
        now,now_duplicates=_bsl_routines(current); before,before_duplicates=_bsl_routines(previous)
        _ambiguity_errors(errors,logical,"candidate","BSL_ROUTINE",now_duplicates)
        _ambiguity_errors(errors,logical,"baseline","BSL_ROUTINE",before_duplicates)
        now=_without_ambiguous(now,now_duplicates,before_duplicates)
        before=_without_ambiguous(before,now_duplicates,before_duplicates)
        for name,delta in _delta_rows(before,now).items():
            spec=delta.get("after") or delta.get("before") or {}
            fragments[("BSL_ROUTINE",name)]={
                **delta,"spec":spec,
                "display_identity":spec.get("name") or name,
                "semantic_identity":name,
            }
    if suffix==".mslx" or info.get("cleverence"):
        now_nodes,now_error,now_duplicates=_xml_contract_nodes(current)
        before_nodes,before_error,before_duplicates=_xml_contract_nodes(previous)
        if current.strip() and now_error:
            errors.append({"type":"IMPLEMENTATION_INTENT_XML_PARSE_UNAVAILABLE","artifact":logical,"side":"candidate","error":now_error})
        if previous.strip() and before_error:
            errors.append({"type":"IMPLEMENTATION_INTENT_XML_PARSE_UNAVAILABLE","artifact":logical,"side":"baseline","error":before_error})
        if not now_error and not before_error:
            for bucket,target_kind in (
                ("actions","MSLX_ACTION"),
                ("fields","CLEVERENCE_FIELD"),
                ("mappings","MAPPING"),
            ):
                _ambiguity_errors(errors,logical,"candidate",target_kind,now_duplicates[bucket])
                _ambiguity_errors(errors,logical,"baseline",target_kind,before_duplicates[bucket])
                now_unique=_without_ambiguous(now_nodes[bucket],now_duplicates[bucket],before_duplicates[bucket])
                before_unique=_without_ambiguous(before_nodes[bucket],now_duplicates[bucket],before_duplicates[bucket])
                for name,delta in _delta_rows(before_unique,now_unique).items():
                    fragments[(target_kind,name)]={**delta,"spec":delta.get("after") or delta.get("before")}
    return fragments



def _canonical_source_ref(ref):
    if not _text(ref):return None
    text=str(ref)
    if "!/" in text:
        archive,entry=text.split("!/",1);parts=[]
        for raw in entry.replace("\\","/").split("/"):
            if raw in {"","."}:continue
            if raw=="..":
                if not parts:return None
                parts.pop()
            else:parts.append(raw)
        try:outer=str(Path(archive).resolve(strict=False))
        except OSError:outer=str(Path(archive).absolute())
        return f"{outer}!/{'/'.join(parts)}"
    try:return str(Path(text).resolve(strict=False))
    except OSError:return str(Path(text).absolute())


def _current_origin_sha(origin):
    if not _text(origin):return None
    text=str(origin)
    if "!/" in text:
        import zipfile
        archive_name,entry=text.split("!/",1)
        try:
            with zipfile.ZipFile(Path(archive_name)) as archive:return hashlib.sha256(archive.read(entry)).hexdigest()
        except Exception:return None
    path=Path(text)
    if not path.is_file():return None
    try:return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:return None


def _plan_source_index(plan):
    index={}
    def add(ref,sha,kind):
        canon=_canonical_source_ref(ref)
        if canon and _text(sha):index[canon]={"sha256":str(sha).lower(),"kind":kind}
    for row in plan.get("candidate_artifacts") or []:
        if isinstance(row,dict):
            add(row.get("origin"),row.get("sha256"),"CANDIDATE")
            add(row.get("portable_origin"),row.get("sha256"),"CANDIDATE")
    baseline=plan.get("baseline") or {}
    if isinstance(baseline,dict) and baseline.get("kind")=="FILE":add(baseline.get("path"),baseline.get("sha256"),"BASELINE")
    return index


def current_target_identity(plan:dict)->str:
    binding=plan_binding(plan);baseline=binding["baseline_identity"]
    return baseline["fingerprint_sha256"] if baseline.get("kind")!="NO_BASELINE" else binding["candidate_identity"]["fingerprint_sha256"]


def _rule_row(ledger,rule_id,errors):
    rows=[x for x in (ledger or {}).get("rules") or [] if isinstance(x,dict) and x.get("id")==rule_id]
    if len(rows)!=1:
        errors.append({"type":"IMPLEMENTATION_ADMISSION_RULE_CARDINALITY","rule_id":rule_id,"count":len(rows)})
        return None
    return rows[0]


def _review_proves(ledger,plan,claim_id,rule_id,check_id,errors):
    selected=[row for row in (ledger or {}).get("independent_reviews") or [] if isinstance(row,dict) and row.get("claim_id")==claim_id]
    review_errors=[];index=validate_independent_reviews(selected,plan,review_errors);errors.extend(review_errors)
    if claim_id not in index:
        errors.append({"type":"IMPLEMENTATION_ADMISSION_INDEPENDENT_REVIEW_REQUIRED","claim_id":claim_id,"rule_id":rule_id,"check_id":check_id})
        return False
    return True


def _exact_source_refs(row,plan,errors,scope):
    refs=set();source_index=_plan_source_index(plan);claim_id=(row or {}).get("claim_id")
    for index,item in enumerate((row or {}).get("evidence") or []):
        if not isinstance(item,dict) or str(item.get("kind") or "").upper()!="SOURCE_REQUIRED":continue
        if item.get("claim_id")!=claim_id:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_CLAIM_MISMATCH","scope":scope,"index":index,"expected":claim_id,"actual":item.get("claim_id")});continue
        ref=_canonical_source_ref(item.get("ref"));expected=source_index.get(ref);provenance=item.get("source_provenance")
        if not expected or not isinstance(provenance,dict):
            errors.append({"type":"IMPLEMENTATION_ADMISSION_EXACT_SOURCE_UNVERIFIED","scope":scope,"index":index,"ref":item.get("ref")});continue
        if provenance.get("type")!="CURRENT_CORPUS" or provenance.get("verifier")!=SOURCE_PROVENANCE_VERIFIER_ID or provenance.get("version")!=SOURCE_PROVENANCE_VERSION:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_PROVENANCE_DRIFT","scope":scope,"index":index,"ref":item.get("ref")});continue
        declared=str(provenance.get("source_sha256") or "").lower();current=_current_origin_sha(item.get("ref"))
        if declared!=expected["sha256"] or current is None or current.lower()!=expected["sha256"]:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_STALE_SOURCE_EVIDENCE","scope":scope,"index":index,"ref":item.get("ref"),"expected":expected["sha256"],"declared":declared,"current":current});continue
        refs.add(item.get("ref"))
    if not refs:errors.append({"type":"IMPLEMENTATION_ADMISSION_EXACT_SOURCE_REQUIRED","scope":scope,"claim_id":claim_id})
    return refs


def _claim_ready(row,ledger,plan,errors,scope,rule_id,check_id=None):
    if not isinstance(row,dict):return set()
    if row.get("status")!="PASS":
        errors.append({"type":"IMPLEMENTATION_ADMISSION_CLAIM_UNRESOLVED","scope":scope,"claim_id":row.get("claim_id"),"status":row.get("status")});return set()
    refs=_exact_source_refs(row,plan,errors,scope);_review_proves(ledger,plan,row.get("claim_id"),rule_id,check_id,errors);return refs


def _scope_selector(item,errors,where):
    if not isinstance(item,dict) or not _text(item.get("artifact")):
        errors.append({"type":"IMPLEMENTATION_ADMISSION_SCOPE_INVALID","where":where,"scope":item});return None
    kind=item.get("target_kind") or "ARTIFACT"
    if kind not in TARGET_KINDS:
        errors.append({"type":"IMPLEMENTATION_ADMISSION_SCOPE_KIND_INVALID","where":where,"actual":kind});return None
    fragment=item.get("fragment")
    if kind!="ARTIFACT" and not _text(fragment):
        errors.append({"type":"IMPLEMENTATION_ADMISSION_SCOPE_FRAGMENT_MISSING","where":where,"target_kind":kind});return None
    change_kind=item.get("change_kind")
    if not _text(change_kind):
        errors.append({"type":"IMPLEMENTATION_ADMISSION_SCOPE_CHANGE_KIND_MISSING","where":where});return None
    return {"artifact":item["artifact"],"target_kind":kind,"fragment":fragment if kind!="ARTIFACT" else None,"change_kind":change_kind,"mechanism_scale":bool(item.get("mechanism_scale"))}


def _normalize_scope(items,errors,where):
    result=[]
    for item in items or []:
        normalized=_scope_selector(item,errors,where)
        if normalized is not None and normalized not in result:result.append(normalized)
    return result


def _scope_allows(row,scope):
    for item in scope or []:
        if item.get("artifact")!=row.get("artifact"):continue
        # ARTIFACT intent rows are material-change summaries.  A proven granular
        # scope on the same artifact is enough for the summary row, but an
        # ARTIFACT scope is never a wildcard that silently admits every fragment.
        if row.get("target_kind")=="ARTIFACT":return True
        if item.get("target_kind")==row.get("target_kind") and item.get("fragment")==row.get("fragment"):return True
    return False


def _refs_list(value):
    return [x for x in (value or []) if _text(x)] if isinstance(value,list) else []


def validate_implementation_admission(plan:dict,ledger:dict|None)->dict:
    errors=[]
    if not isinstance(ledger,dict):return {"result":"IMPLEMENTATION_ADMISSION_BLOCKED","errors":[{"type":"IMPLEMENTATION_ADMISSION_LEDGER_MISSING"}]}
    analog=_rule_row(ledger,EXISTING_CAPABILITY_RULE_ID,errors)
    if analog is None:return {"result":"IMPLEMENTATION_ADMISSION_BLOCKED","errors":errors}
    expected_claim=rule_claim_id(EXISTING_CAPABILITY_RULE_ID)
    if analog.get("claim_id")!=expected_claim:errors.append({"type":"IMPLEMENTATION_ADMISSION_ANALOG_CLAIM_ID_DRIFT","expected":expected_claim,"actual":analog.get("claim_id")})
    exact_refs=set(_claim_ready(analog,ledger,plan,errors,"existing_capability_rule",EXISTING_CAPABILITY_RULE_ID))
    standard_check=next((x for x in analog.get("checks") or [] if isinstance(x,dict) and x.get("id")==STANDARD_CAPABILITY_CHECK_ID),None)
    if standard_check is None:errors.append({"type":"IMPLEMENTATION_ADMISSION_STANDARD_CAPABILITY_CHECK_MISSING"})
    else:exact_refs.update(_claim_ready(standard_check,ledger,plan,errors,"standard_capability_check",EXISTING_CAPABILITY_RULE_ID,STANDARD_CAPABILITY_CHECK_ID))
    source_gate=next((x for x in analog.get("checks") or [] if isinstance(x,dict) and x.get("id")==SOURCE_DEPENDENT_CHECK_ID),None)
    if source_gate is None:errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENT_CHECK_MISSING"})
    else:exact_refs.update(_claim_ready(source_gate,ledger,plan,errors,"source_dependent_implementation_check",EXISTING_CAPABILITY_RULE_ID,SOURCE_DEPENDENT_CHECK_ID))

    disposition=analog.get("existing_capability_disposition")
    if not isinstance(disposition,dict):errors.append({"type":"IMPLEMENTATION_ADMISSION_DISPOSITION_MISSING"});disposition={}
    value=disposition.get("disposition")
    if value not in EXISTING_CAPABILITY_DISPOSITIONS:errors.append({"type":"IMPLEMENTATION_ADMISSION_DISPOSITION_INVALID","actual":value})
    target_identity=current_target_identity(plan)

    candidates=disposition.get("discovery_candidates")
    if not isinstance(candidates,list):errors.append({"type":"IMPLEMENTATION_ADMISSION_DISCOVERY_CANDIDATES_INVALID"});candidates=[]
    if len(candidates)>50:errors.append({"type":"IMPLEMENTATION_ADMISSION_DISCOVERY_CANDIDATES_UNBOUNDED","count":len(candidates)})
    for index,candidate in enumerate(candidates):
        provider=(candidate or {}).get("provider") if isinstance(candidate,dict) else None;finding=(candidate or {}).get("finding") if isinstance(candidate,dict) else None
        if not isinstance(candidate,dict) or not _text(candidate.get("candidate_id")) or not isinstance(provider,dict) or not _text(provider.get("id")) or not _text(provider.get("mode")) or not isinstance(finding,dict) or not _text(finding.get("kind")) or not _text(finding.get("ref")):
            errors.append({"type":"IMPLEMENTATION_ADMISSION_DISCOVERY_CANDIDATE_MALFORMED","index":index});continue
        if len(str(finding.get("summary") or ""))>1000:errors.append({"type":"IMPLEMENTATION_ADMISSION_DISCOVERY_CANDIDATE_UNBOUNDED","index":index})

    proof_refs=_refs_list(disposition.get("proof_refs"))
    if value!="EVIDENCE_REQUIRED":
        if not proof_refs:errors.append({"type":"IMPLEMENTATION_ADMISSION_PROOF_REFS_MISSING"})
        for ref in proof_refs:
            if ref not in exact_refs:errors.append({"type":"IMPLEMENTATION_ADMISSION_PROOF_REF_NOT_EXACT_CURRENT_SOURCE","ref":ref})

    existing_owner=disposition.get("existing_owner")
    if value in {"REUSE_EXISTING","EXTEND_EXISTING"}:
        if not isinstance(existing_owner,dict) or not _text(existing_owner.get("owner_ref")):errors.append({"type":"IMPLEMENTATION_ADMISSION_EXISTING_OWNER_MISSING"})
        else:
            if existing_owner.get("target_identity_ref")!=target_identity:errors.append({"type":"IMPLEMENTATION_ADMISSION_EXISTING_OWNER_TARGET_DRIFT","expected":target_identity,"actual":existing_owner.get("target_identity_ref")})
            coverage=existing_owner.get("coverage")
            if not isinstance(coverage,list) or not coverage:errors.append({"type":"IMPLEMENTATION_ADMISSION_EXISTING_OWNER_COVERAGE_MISSING"})
            else:
                for index,row in enumerate(coverage):
                    refs=_refs_list((row or {}).get("exact_source_refs") if isinstance(row,dict) else None)
                    if not isinstance(row,dict) or not _text(row.get("requirement_dimension_id")) or not refs:errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_COVERAGE_INVALID","index":index})
                    for ref in refs:
                        if ref not in proof_refs:errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_COVERAGE_REF_UNBOUND","index":index,"ref":ref})
        if not _text(disposition.get("reused_capability")):errors.append({"type":"IMPLEMENTATION_ADMISSION_REUSED_CAPABILITY_MISSING"})

    gaps=disposition.get("gap")
    if not isinstance(gaps,list):errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_INVALID"});gaps=[]
    global_scope=_normalize_scope(disposition.get("change_scope") or [],errors,"change_scope");gap_scope=[]

    source_dependencies=disposition.get("source_dependencies",[])
    source_dependency_ids=[]
    if not isinstance(source_dependencies,list):
        errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCIES_INVALID"});source_dependencies=[]
    seen_dependency_ids=set()
    for index,dependency in enumerate(source_dependencies):
        if not isinstance(dependency,dict):
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_ROW_INVALID","index":index});continue
        dep_id=dependency.get("id");fact_kind=dependency.get("fact_kind");statement=dependency.get("statement");status=dependency.get("status")
        if not _text(dep_id) or dep_id in seen_dependency_ids:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_ID_INVALID","index":index,"id":dep_id});continue
        seen_dependency_ids.add(dep_id);source_dependency_ids.append(dep_id)
        if fact_kind not in SOURCE_DEPENDENCY_FACT_KINDS:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_FACT_KIND_INVALID","index":index,"id":dep_id,"actual":fact_kind})
        if not _text(statement):
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_STATEMENT_MISSING","index":index,"id":dep_id})
        if status not in SOURCE_DEPENDENCY_STATUSES:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_STATUS_INVALID","index":index,"id":dep_id,"actual":status})
        dep_scope=_normalize_scope(dependency.get("change_scope") or [],errors,f"source_dependency:{dep_id}")
        if not dep_scope:
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_SCOPE_MISSING","index":index,"id":dep_id})
        for item in dep_scope:
            if item not in global_scope:
                errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_SCOPE_OUTSIDE_CHANGE","index":index,"id":dep_id,"scope":item})
        refs=_refs_list(dependency.get("proof_refs"))
        if status=="EVIDENCE_REQUIRED":
            errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_UNPROVEN","index":index,"id":dep_id,"fact_kind":fact_kind})
        elif status=="PROVEN":
            if not refs:
                errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_PROOF_MISSING","index":index,"id":dep_id})
            for ref in refs:
                if ref not in exact_refs:
                    errors.append({"type":"IMPLEMENTATION_ADMISSION_SOURCE_DEPENDENCY_PROOF_REF_NOT_EXACT_CURRENT_SOURCE","index":index,"id":dep_id,"ref":ref})

    if value in {"EXTEND_EXISTING","CUSTOM_REQUIRED"}:
        if not gaps:errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_MISSING"})
        for index,gap in enumerate(gaps):
            if not isinstance(gap,dict):errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_ROW_INVALID","index":index});continue
            if gap.get("target_identity_ref")!=target_identity:errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_TARGET_DRIFT","index":index,"expected":target_identity,"actual":gap.get("target_identity_ref")})
            if not _text(gap.get("requirement_dimension_id")) or not _text(gap.get("required_behavior")) or not _text(gap.get("existing_behavior")):errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_SEMANTICS_MISSING","index":index})
            noncoverage=_refs_list(gap.get("noncoverage_proof_refs"))
            if not noncoverage:errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_PROOF_MISSING","index":index})
            for ref in noncoverage:
                if ref not in proof_refs:errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_PROOF_REF_UNBOUND","index":index,"ref":ref})
            gap_scope.extend(_normalize_scope(gap.get("change_scope") or [],errors,f"gap:{index}"))
        if not global_scope:errors.append({"type":"IMPLEMENTATION_ADMISSION_CHANGE_SCOPE_MISSING"})
        for item in global_scope:
            if item not in gap_scope:errors.append({"type":"IMPLEMENTATION_ADMISSION_CHANGE_SCOPE_EXCEEDS_GAP","scope":item})
        for item in gap_scope:
            if item not in global_scope:errors.append({"type":"IMPLEMENTATION_ADMISSION_GAP_SCOPE_NOT_ADMITTED","scope":item})

    if value=="CUSTOM_REQUIRED" and not _text(disposition.get("why_not_existing")):errors.append({"type":"IMPLEMENTATION_ADMISSION_WHY_NOT_EXISTING_MISSING"})
    if value=="REUSE_EXISTING" and gaps:errors.append({"type":"IMPLEMENTATION_ADMISSION_REUSE_HAS_RESIDUAL_GAP"})

    owner_exception=disposition.get("owner_exception");duplicate_scope=[]
    if owner_exception is not None:
        if not isinstance(owner_exception,dict):errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_EXCEPTION_INVALID"})
        else:
            if owner_exception.get("existing_capability_claim_id")!=expected_claim:errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_EXCEPTION_CLAIM_DRIFT"})
            if owner_exception.get("target_identity_ref")!=target_identity:errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_EXCEPTION_TARGET_DRIFT"})
            if not _text(owner_exception.get("confirmation_ref")) or not _text(owner_exception.get("reason")):errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_EXCEPTION_CONFIRMATION_MISSING"})
            duplicate_scope=_normalize_scope(owner_exception.get("duplicate_scope") or [],errors,"owner_exception")
            if not duplicate_scope:errors.append({"type":"IMPLEMENTATION_ADMISSION_OWNER_EXCEPTION_SCOPE_MISSING"})

    if value=="REUSE_EXISTING":
        for item in global_scope:
            if item.get("change_kind")!="REUSE_WIRING" and (not owner_exception or item not in duplicate_scope):
                errors.append({"type":"IMPLEMENTATION_ADMISSION_REUSE_PARALLEL_OWNER_BLOCKED","scope":item})

    if value in {"EXTEND_EXISTING","CUSTOM_REQUIRED"} and any(item.get("mechanism_scale") for item in global_scope):
        pipeline=_rule_row(ledger,STANDARD_PIPELINE_RULE_ID,errors)
        if pipeline is not None:
            _claim_ready(pipeline,ledger,plan,errors,"standard_pipeline_rule",STANDARD_PIPELINE_RULE_ID)
            for check in pipeline.get("checks") or []:
                if isinstance(check,dict):_claim_ready(check,ledger,plan,errors,"standard_pipeline_check",STANDARD_PIPELINE_RULE_ID,check.get("id"))

    if value=="EVIDENCE_REQUIRED":errors.append({"type":"IMPLEMENTATION_ADMISSION_EVIDENCE_REQUIRED"})
    return {"result":"IMPLEMENTATION_ADMISSION_READY" if not errors else "IMPLEMENTATION_ADMISSION_BLOCKED","claim_id":expected_claim,"disposition":value,"target_identity_ref":target_identity,"change_scope":global_scope,"owner_exception_scope":duplicate_scope,"source_dependency_ids":source_dependency_ids,"errors":errors}


def validate_intent_map(intent:dict|None,plan:dict,ledger:dict|None=None)->dict:
    errors=[]; missing=[]; changed=artifact_delta(plan); binding=plan_binding(plan)
    expected_surface=_surface_rows(plan)
    expected_fragments={}
    for logical,info in changed.items():
        for key,delta in _fragment_deltas(info,logical,errors).items():
            expected_fragments[(logical,*key)]=delta
    if not isinstance(intent,dict):
        errors.append({"type":"IMPLEMENTATION_INTENT_MAP_MISSING"})
        return {"result":"FAIL","errors":errors,"missing_intent_rows":[],"changed_surface":expected_surface}
    if intent.get("schema_version")!=SCHEMA_VERSION:
        errors.append({"type":"IMPLEMENTATION_INTENT_SCHEMA_UNSUPPORTED","expected":SCHEMA_VERSION,"actual":intent.get("schema_version")})
    expected_binding={
        "candidate_fingerprint_sha256":binding["candidate_identity"]["fingerprint_sha256"],
        "baseline_fingerprint_sha256":binding["baseline_identity"]["fingerprint_sha256"],
        "requirements_fingerprint_sha256":binding["requirements_identity"]["fingerprint_sha256"],
        "review_plan_sha256":binding["review_plan_sha256"],
    }
    if intent.get("binding")!=expected_binding:
        errors.append({"type":"IMPLEMENTATION_INTENT_BINDING_MISMATCH","expected":expected_binding,"actual":intent.get("binding")})
    declared=intent.get("change_surface")
    if declared!=expected_surface:
        errors.append({"type":"IMPLEMENTATION_INTENT_CHANGE_SURFACE_MISMATCH","expected":expected_surface,"actual":declared})

    admission=None
    if ledger is not None:
        admission=validate_implementation_admission(plan,ledger)
        if admission.get("result")!="IMPLEMENTATION_ADMISSION_READY":
            errors.append({"type":"IMPLEMENTATION_ADMISSION_BLOCKED","details":admission.get("errors") or []})

    acceptance=_requirements_acceptance_ids(plan)

    rows=intent.get("rows")
    if not isinstance(rows,list):errors.append({"type":"IMPLEMENTATION_INTENT_ROWS_INVALID"});rows=[]
    artifact_rows={}; fragment_rows={}
    for index,row in enumerate(rows):
        if not isinstance(row,dict):errors.append({"type":"IMPLEMENTATION_INTENT_ROW_NOT_OBJECT","index":index});continue
        _required_text(row,("requirement_id","design_decision_id","artifact","target_kind","action","responsibility","necessity","existing_owner_disposition","platform_reuse_decision","existing_capability_claim_id"),errors,index)
        artifact=row.get("artifact"); target_kind=row.get("target_kind"); action=row.get("action"); fragment=row.get("fragment")
        if admission is not None:
            if row.get("existing_capability_claim_id")!=admission.get("claim_id"):
                errors.append({"type":"IMPLEMENTATION_INTENT_EXISTING_CAPABILITY_CLAIM_DRIFT","index":index,"expected":admission.get("claim_id"),"actual":row.get("existing_capability_claim_id")})
            if row.get("existing_owner_disposition")!=admission.get("disposition"):
                errors.append({"type":"IMPLEMENTATION_INTENT_EXISTING_CAPABILITY_DISPOSITION_DRIFT","index":index,"expected":admission.get("disposition"),"actual":row.get("existing_owner_disposition")})
            allowed_scope=list(admission.get("change_scope") or [])+list(admission.get("owner_exception_scope") or [])
            if not _scope_allows(row,allowed_scope):
                errors.append({"type":"IMPLEMENTATION_INTENT_SCOPE_EXCEEDS_ADMISSION","index":index,"artifact":artifact,"target_kind":target_kind,"fragment":fragment})
        if target_kind not in TARGET_KINDS:errors.append({"type":"IMPLEMENTATION_INTENT_TARGET_KIND_INVALID","index":index,"actual":target_kind})
        if action not in ACTIONS:errors.append({"type":"IMPLEMENTATION_INTENT_ACTION_INVALID","index":index,"actual":action})
        if artifact not in changed:
            errors.append({"type":"IMPLEMENTATION_INTENT_ARTIFACT_OUTSIDE_CHANGE_SURFACE","index":index,"artifact":artifact})
        nearest=row.get("nearest_smaller_alternative")
        if not isinstance(nearest,dict) or not _text(nearest.get("alternative")) or not _text(nearest.get("rejection_reason")):
            errors.append({"type":"IMPLEMENTATION_INTENT_SMALLER_ALTERNATIVE_MISSING","index":index})
        hooks=row.get("verification_hooks")
        if not isinstance(hooks,list) or not hooks:errors.append({"type":"IMPLEMENTATION_INTENT_VERIFICATION_HOOKS_MISSING","index":index})
        cases=row.get("acceptance_cases")
        if not isinstance(cases,list) or not cases:
            errors.append({"type":"IMPLEMENTATION_INTENT_ACCEPTANCE_CASES_MISSING","index":index})
        elif acceptance is not None:
            for case in cases:
                if case not in acceptance:errors.append({"type":"IMPLEMENTATION_INTENT_ACCEPTANCE_CASE_UNKNOWN","index":index,"case_id":case})

        if target_kind=="ARTIFACT":
            expected=(changed.get(artifact) or {}).get("action")
            if expected and action!=expected:
                errors.append({"type":"IMPLEMENTATION_INTENT_ACTION_MISMATCH","index":index,"artifact":artifact,"target_kind":"ARTIFACT","expected":expected,"actual":action})
            if artifact in artifact_rows:
                errors.append({"type":"IMPLEMENTATION_INTENT_DUPLICATE_ARTIFACT_ROW","artifact":artifact})
            artifact_rows[artifact]=row
        elif target_kind in {"BSL_ROUTINE","MSLX_ACTION","CLEVERENCE_FIELD","MAPPING"}:
            if not _text(fragment):
                errors.append({"type":"IMPLEMENTATION_INTENT_FRAGMENT_MISSING","index":index,"artifact":artifact,"target_kind":target_kind})
            semantic_fragment=_fragment_identity(target_kind,fragment)
            key=(artifact,target_kind,semantic_fragment)
            expected=expected_fragments.get(key)
            if not expected:
                errors.append({"type":"IMPLEMENTATION_INTENT_FRAGMENT_NOT_CHANGED","index":index,"artifact":artifact,"target_kind":target_kind,"fragment":fragment})
            elif action!=expected["action"]:
                errors.append({"type":"IMPLEMENTATION_INTENT_ACTION_MISMATCH","index":index,"artifact":artifact,"target_kind":target_kind,"fragment":fragment,"expected":expected["action"],"actual":action})
            if key in fragment_rows:
                errors.append({"type":"IMPLEMENTATION_INTENT_DUPLICATE_FRAGMENT_ROW","artifact":artifact,"target_kind":target_kind,"fragment":fragment})
            fragment_rows[key]=row

        entry=row.get("entrypoint")
        if target_kind=="BSL_ROUTINE" and action!="delete":
            if not isinstance(entry,dict) or entry.get("kind") not in ENTRYPOINT_KINDS or not _text(entry.get("ref")):
                errors.append({"type":"IMPLEMENTATION_INTENT_ENTRYPOINT_MISSING","index":index,"artifact":artifact,"fragment":fragment})
        if target_kind=="MSLX_ACTION":
            for field in ("scenario_disposition","writer_disposition","state_disposition"):
                if not _text(row.get(field)):errors.append({"type":"IMPLEMENTATION_INTENT_CLEVERENCE_ACTION_DISPOSITION_MISSING","index":index,"field":field})
        if target_kind in {"CLEVERENCE_FIELD","MAPPING"}:
            for field in ("producer_disposition","consumer_disposition","mapping_disposition"):
                if not _text(row.get(field)):errors.append({"type":"IMPLEMENTATION_INTENT_CLEVERENCE_FIELD_MAPPING_DISPOSITION_MISSING","index":index,"field":field})

    for logical,info in changed.items():
        if logical not in artifact_rows:
            missing.append({"type":"MATERIAL_ARTIFACT_WITHOUT_INTENT","artifact":logical,"expected_action":info["action"]})
    for key,delta in expected_fragments.items():
        logical,target_kind,fragment=key
        row=fragment_rows.get(key)
        display_fragment=delta.get("display_identity") or fragment
        if not row:
            error_type={
                "BSL_ROUTINE":"BSL_ROUTINE_WITHOUT_INTENT",
                "MSLX_ACTION":"MSLX_ACTION_WITHOUT_INTENT",
                "CLEVERENCE_FIELD":"CLEVERENCE_FIELD_WITHOUT_INTENT",
                "MAPPING":"CLEVERENCE_MAPPING_WITHOUT_INTENT",
            }[target_kind]
            missing_row={"type":error_type,"artifact":logical,"fragment":display_fragment,"expected_action":delta["action"]}
            if target_kind=="BSL_ROUTINE":missing_row["semantic_identity"]=fragment
            missing.append(missing_row)
            continue
        spec=delta.get("after") or {}
        if target_kind=="BSL_ROUTINE" and delta["action"]=="create":
            if spec.get("export"):
                entry=row.get("entrypoint") or {}
                if entry.get("kind") not in {"PUBLIC_API","CALLBACK","ENTRYPOINT"}:
                    errors.append({"type":"NEW_EXPORT_WITHOUT_API_CALLBACK_CONTRACT","artifact":logical,"fragment":fragment})
            if spec.get("routine_kind")=="ФУНКЦИЯ":
                entry=row.get("entrypoint") or {}
                if entry.get("kind") not in ENTRYPOINT_KINDS or not _text(entry.get("ref")):
                    errors.append({"type":"NEW_FUNCTION_WITHOUT_REACHABILITY","artifact":logical,"fragment":fragment})

    routing=plan.get("routing") or {}
    if routing.get("surface")=="CROSS_SYSTEM" and changed:
        changed_onec=any(bool(x.get("onec")) for x in changed.values())
        changed_cleverence=any(bool(x.get("cleverence")) for x in changed.values())
        if not (changed_onec and changed_cleverence):
            one_sided=intent.get("one_sided_scope")
            if not isinstance(one_sided,dict) or one_sided.get("status")!="PROVEN" or not _text(one_sided.get("reason")) or not isinstance(one_sided.get("evidence"),list) or not one_sided.get("evidence"):
                errors.append({"type":"CROSS_SYSTEM_ONE_SIDED_SCOPE_UNPROVEN","onec_changed":changed_onec,"cleverence_changed":changed_cleverence})

    errors.extend(missing)
    return {"result":"PASS" if not errors else "FAIL","errors":errors,"missing_intent_rows":missing,"changed_surface":expected_surface}


def main()->int:
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument("--plan",required=True);ap.add_argument("--intent-map");ap.add_argument("--ledger");ap.add_argument("--skeleton",action="store_true");ap.add_argument("--admission",action="store_true");ap.add_argument("--output")
    a=ap.parse_args();plan=json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    ledger=json.loads(Path(a.ledger).read_text(encoding="utf-8-sig")) if a.ledger else None
    if a.admission:
        if ledger is None:ap.error("--admission requires --ledger")
        result=validate_implementation_admission(plan,ledger)
    elif a.skeleton:result=build_skeleton(plan)
    else:
        intent=json.loads(Path(a.intent_map).read_text(encoding="utf-8-sig")) if a.intent_map else None
        result=validate_intent_map(intent,plan,ledger)
    out=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    print(out,end="")
    return 0 if a.skeleton or result.get("result") in {"PASS","IMPLEMENTATION_ADMISSION_READY"} else 2


if __name__=="__main__":raise SystemExit(main())
