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

SCHEMA_VERSION=2
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


def validate_intent_map(intent:dict|None,plan:dict)->dict:
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

    acceptance=_requirements_acceptance_ids(plan)

    rows=intent.get("rows")
    if not isinstance(rows,list):errors.append({"type":"IMPLEMENTATION_INTENT_ROWS_INVALID"});rows=[]
    artifact_rows={}; fragment_rows={}
    for index,row in enumerate(rows):
        if not isinstance(row,dict):errors.append({"type":"IMPLEMENTATION_INTENT_ROW_NOT_OBJECT","index":index});continue
        _required_text(row,("requirement_id","design_decision_id","artifact","target_kind","action","responsibility","necessity","existing_owner_disposition","platform_reuse_decision"),errors,index)
        artifact=row.get("artifact"); target_kind=row.get("target_kind"); action=row.get("action"); fragment=row.get("fragment")
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
    ap=argparse.ArgumentParser();ap.add_argument("--plan",required=True);ap.add_argument("--intent-map");ap.add_argument("--skeleton",action="store_true");ap.add_argument("--output")
    a=ap.parse_args();plan=json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    if a.skeleton:result=build_skeleton(plan)
    else:
        intent=json.loads(Path(a.intent_map).read_text(encoding="utf-8-sig")) if a.intent_map else None
        result=validate_intent_map(intent,plan)
    out=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    print(out,end="")
    return 0 if a.skeleton or result.get("result")=="PASS" else 2


if __name__=="__main__":raise SystemExit(main())
