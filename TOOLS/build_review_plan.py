#!/usr/bin/env python3
"""Build a deterministic rule activation/review plan from the executable registry.

Routing never proves correctness. It only determines which rule/check evidence is required.
Tier-0 rules always require a disposition, even when the final disposition is NOT_APPLICABLE.
Artifact discovery is delegated to artifact_corpus so routing and analyzers share one bounded intake model.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, re, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rule_registry import ROOT, load_registry, max_risk, regex_hits, RISK_RANK, proof_policy_for, materialize_delivery_bindings, materialize_delivery_applicability, materialize_supporting_artifacts
from analyze_onec_field_flow import analyze_sources as analyze_field_flow_sources
from requirements_gate import evaluate as evaluate_requirements
from artifact_corpus import inventory_paths, analyzable_entries, summarize as summarize_corpus
from release_intake import intake_from_build_args, intake_record
from performance_review import build_plan_contract as build_performance_review_plan_contract

SURFACES=("ANALYSIS_ONLY","ONEC_ONLY","CLEVERENCE_ONLY","CROSS_SYSTEM")
RISKS=("R0_LOCAL","R1_CONTRACT","R2_STATEFUL_RUNTIME","R3_CROSS_SYSTEM")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig","utf-8","cp1251"):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    return data.decode("utf-8",errors="replace")


def _dependency_snapshot(path):
    """Bind baseline/context-like filesystem evidence to exact bytes, not only a path label."""
    if not path:
        return None
    p=Path(path)
    if p.is_file():
        data=p.read_bytes()
        return {"path":str(p),"kind":"FILE","sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}
    if p.is_dir():
        digest=hashlib.sha256(); files=0; total=0
        for item in sorted(x for x in p.rglob("*") if x.is_file()):
            rel=item.relative_to(p).as_posix(); data=item.read_bytes(); file_sha=hashlib.sha256(data).hexdigest()
            digest.update(rel.encode("utf-8")); digest.update(b"\0"); digest.update(file_sha.encode("ascii")); digest.update(b"\n")
            files+=1; total+=len(data)
        return {"path":str(p),"kind":"DIRECTORY","sha256":digest.hexdigest(),"files":files,"size":total}
    raise FileNotFoundError(p)


def _surface_for(name: str, text: str):
    normalized=name.replace("\\","/")
    suffix=Path(normalized).suffix.lower()
    basename=Path(normalized).name.lower()
    semantic_cleverence_path=normalized.startswith(("Operations/","Metadata/","DocumentTypes/"))
    cleverence_path=(suffix==".mslx" or semantic_cleverence_path)
    onec_path=suffix in {".bsl",".os"}
    # 1C XML dumps consistently expose v8.1c.ru namespaces; XDTO Package.bin is XML
    # but can use its own/default namespace, so root <package targetNamespace=...> is also 1C.
    onec_xml = bool(re.search(r"https?://v8\.1c\.ru/|<MetaDataObject\b|<Form\b[^>]*xcf/logform|<package\b[^>]*targetNamespace", text, re.I))
    cleverence=cleverence_path or (not onec_path and bool(re.search(r"<(?:\w+:)?(?:Operation|\w+Action)\b",text)))
    onec=onec_path or (not cleverence_path and (onec_xml or basename=="package.bin" or bool(re.search(r"(?:&НаКлиенте|&НаСервере|\bПроцедура\b|\bФункция\b|\bНовый\s+Запрос\b)",text))))
    return onec,cleverence


def _surface_set(surface: str|None):
    if surface in {None,"ANALYSIS_ONLY"}:return set()
    if surface=="ONEC_ONLY":return {"ONEC"}
    if surface=="CLEVERENCE_ONLY":return {"CLEVERENCE"}
    return {"ONEC","CLEVERENCE"}


def _surface_from_set(values):
    if values=={"ONEC","CLEVERENCE"}:return "CROSS_SYSTEM"
    if values=={"ONEC"}:return "ONEC_ONLY"
    if values=={"CLEVERENCE"}:return "CLEVERENCE_ONLY"
    return "ANALYSIS_ONLY"


def _route_surface(onec:bool, cleverence:bool, *declared):
    detected=({"ONEC"} if onec else set()) | ({"CLEVERENCE"} if cleverence else set())
    effective=set(detected)
    for surface in declared:effective.update(_surface_set(surface))
    return _surface_from_set(detected),_surface_from_set(effective)


def _requirements_cover(requirements_surface, requirements_risk, effective_surface, effective_risk):
    if requirements_surface not in SURFACES or requirements_risk not in RISKS:return False
    return _surface_set(requirements_surface).issuperset(_surface_set(effective_surface)) and RISK_RANK[requirements_risk]>=RISK_RANK[effective_risk]


def _load_project_context(path):
    if not path:return {"path":None,"sha256":None,"surface":None,"risk":None,"text":""}
    p=Path(path); data=p.read_bytes(); text=_decode(data); surface=risk=None
    if p.suffix.lower()==".json":
        payload=json.loads(text); routing=payload.get("routing",{}) if isinstance(payload,dict) else {}
        surface=routing.get("surface") or payload.get("surface"); risk=routing.get("risk") or payload.get("risk")
    else:
        sm=re.search(r"(?im)^\s*-?\s*surface\s*:\s*([^\r\n]+)",text); rm=re.search(r"(?im)^\s*-?\s*risk\s*:\s*([^\r\n]+)",text)
        if sm and "|" not in sm.group(1):surface=sm.group(1).strip().split()[0]
        if rm and "|" not in rm.group(1):risk=rm.group(1).strip().split()[0]
    if surface and surface not in SURFACES:raise ValueError(f"Unsupported project-context surface: {surface}")
    if risk and risk not in RISKS:raise ValueError(f"Unsupported project-context risk: {risk}")
    return {"path":str(p),"sha256":hashlib.sha256(data).hexdigest(),"surface":surface,"risk":risk,"text":text}


def _load_requirements_contract(path):
    if not path:
        return {"path":None,"sha256":None,"surface":None,"risk":None,"gate":{"result":"MISSING","requirements_outcome":"REQUIREMENTS_BLOCKED","errors":[{"type":"REQUIREMENTS_CONTRACT_MISSING"}]}}
    p=Path(path); data=p.read_bytes(); payload=json.loads(_decode(data)); gate=evaluate_requirements(payload)
    routing=payload.get("routing",{}) if isinstance(payload,dict) else {}
    surface=routing.get("surface"); risk=routing.get("risk")
    if surface and surface not in SURFACES:raise ValueError(f"Unsupported requirements surface: {surface}")
    if risk and risk not in RISKS:raise ValueError(f"Unsupported requirements risk: {risk}")
    return {"path":str(p),"sha256":hashlib.sha256(data).hexdigest(),"surface":surface,"risk":risk,"gate":gate,"registry_sha256":(payload.get("registry") or {}).get("sha256")}

def _rule_surface_compatible(rule_surface:str, effective_surface:str)->bool:
    if rule_surface=="ANY":return True
    if rule_surface=="ONEC":return effective_surface in {"ONEC_ONLY","CROSS_SYSTEM"}
    if rule_surface=="CLEVERENCE":return effective_surface in {"CLEVERENCE_ONLY","CROSS_SYSTEM"}
    if rule_surface=="CROSS_SYSTEM":return effective_surface=="CROSS_SYSTEM"
    return True


def _gate_plan(registry, surface, risk, analysis_only):
    rows=[]
    for gate in registry.get("gates",[]):
        gid=gate["id"]; status="REQUIRED"; reason=gate.get("description","")
        if gid=="IMPLEMENTATION" and analysis_only:status,reason="NOT_APPLICABLE","analysis-only request"
        elif gid=="ADVERSARIAL_VALIDATION" and (analysis_only or risk=="R0_LOCAL"):status,reason="CONDITIONAL","analysis-only/R0 may use a reasoned NOT_APPLICABLE disposition; R1+ change work requires an attempted failure"
        elif gid=="EXTERNAL_ITS_DISCOVERY" and surface=="CLEVERENCE_ONLY":status,reason="NOT_APPLICABLE","no 1C mechanism; use vendor/source evidence"
        elif gid=="PROMOTION":status,reason="CONDITIONAL","only after accepted runtime evidence when a maintained baseline exists"
        elif gid=="RUNTIME_MATRIX" and risk=="R0_LOCAL":status,reason="CONDITIONAL","may be reasoned NOT_APPLICABLE only when no runtime-visible contract changed"
        rows.append({"gate":gid,"status":status,"reason":reason,"blocking":bool(gate.get("blocking",True))})
    return rows


def _activate_rules(registry, combined_text, onec_texts, cleverence_texts, surface, analysis_only, onec_sources=None, cleverence_sources=None, all_sources=None):
    rows=[]; active_profile_rules=[]
    # First pass: direct regex and Tier-0 disposition.
    for rule in registry.get("rules",[]):
        mode=rule.get("activation",{}).get("mode","ANY_REGEX")
        relevant_texts=[combined_text]
        rs=rule.get("surface","ANY")
        if rs=="ONEC":relevant_texts=onec_texts
        elif rs=="CLEVERENCE":relevant_texts=cleverence_texts
        activation=rule.get("activation",{})
        if activation.get("patterns"):
            if activation.get("scope")=="ARTIFACT":
                hits=[]
                for text in relevant_texts:
                    hits.extend(regex_hits(rule,text))
                hits=list(dict.fromkeys(hits))
            else:
                hits=regex_hits(rule,"\n".join(relevant_texts))
        else:
            hits=[]
        # Some mechanisms are defined by their configuration location rather than by
        # a unique XML token. Path routing is explicit evidence and is kept separate
        # from content regexes so metadata-only Cleverence .mslx files do not get
        # misclassified as Operation/Action execution graphs. artifact_corpus exposes
        # canonical routing aliases for legacy Documents.zip/unpacked representations.
        source_pairs=list(all_sources or [])
        if rs=="ONEC":source_pairs=list(onec_sources or [])
        elif rs=="CLEVERENCE":source_pairs=list(cleverence_sources or [])
        for pattern in activation.get("path_patterns",[]):
            try:
                if any(re.search(pattern,name.replace("\\","/"),re.I|re.M) for name,_ in source_pairs):
                    hits.append(f"path:{pattern}")
            except re.error as exc:
                raise ValueError(f"Invalid activation path regex for {rule['id']}: {pattern}: {exc}") from exc
        hits=list(dict.fromkeys(hits))
        active=False; reason=""
        if rule.get("always_disposition"):
            active=True; reason="tier-0 disposition required"
        elif mode=="ANY_REGEX" and hits:
            active=True; reason="activation pattern matched"
        # Derived rules handled below.
        rows.append({
            "id":rule["id"],"tier":rule["tier"],"profile":rule.get("profile"),"active":active,
            "activation_status":rule.get("activation",{}).get("status_on_match","REQUIRED") if active else "NOT_ROUTED",
            "detected_by":hits,"reason":reason,"surface":rule.get("surface","ANY"),"risk_floor":rule.get("risk_floor","R0_LOCAL"),
            "check_count":len(rule.get("checks",[])),"evidence_modes":rule.get("evidence_modes",[]),
            "proof_policy":proof_policy_for(rule,registry)
        })
    by={r["id"]:r for r in rows}
    # Non-trivial 1C => BSP disposition is not merely tier-0, it is applicable/routed.
    nontrivial_onec=surface in {"ONEC_ONLY","CROSS_SYSTEM"} and any(
        r["active"] and r["id"] not in {"BSP_REUSE","CALL_CONTRACT","BUSINESS_IDENTITY"} and r["risk_floor"]!="R0_LOCAL"
        for r in rows
    )
    if nontrivial_onec:
        row=by.get("BSP_REUSE")
        if row:
            row["active"]=True; row["activation_status"]="REQUIRED"; row["reason"]="derived: non-trivial 1C behavior"
    if surface=="CROSS_SYSTEM":
        row=by.get("CLEVERENCE_INTEGRATION")
        if row:
            row["active"]=True; row["activation_status"]="REQUIRED"; row["reason"]="derived: effective surface is CROSS_SYSTEM"
    # Field-aware lifecycle routing: same-module keyword co-occurrence is not enough.
    row=by.get("POST_WRITE_STANDARD_OVERWRITE")
    if row:
        ff=analyze_field_flow_sources(onec_sources or [(f"artifact-{i}.bsl",text) for i,text in enumerate(onec_texts)]).get("findings",[])
        if ff:
            row["active"]=True; row["activation_status"]="CONDITIONAL_REVIEW"
            row["detected_by"]=list(dict.fromkeys(f"field-flow:{x.get('type')}" for x in ff))
            row["reason"]="derived: field-aware reachable writer/lifecycle flow"

    # Whole-change-set architecture is not inferable from per-file regexes. Every
    # multi-BSL candidate set receives a conditional cross-object review, even when
    # the structural analyzer later reports zero similarity candidates.
    row=by.get("CROSS_OBJECT_DUPLICATION_REVIEW")
    bsl_sources=[(name,text) for name,text in (onec_sources or []) if Path(name.replace("\\","/")).suffix.lower() in {".bsl",".os"}]
    bsl_files={name.replace("\\","/") for name,_ in bsl_sources}
    if row and len(bsl_files)>1:
        row["active"]=True; row["activation_status"]="CONDITIONAL_REVIEW"
        row["detected_by"]=[f"changeset:bsl_artifacts={len(bsl_files)}"]
        row["reason"]="derived: multi-BSL whole-change-set review"

    # Tier-0 CALL/BUSINESS rules remain disposition-required but direct trigger is surfaced distinctly.
    for rid in ("CALL_CONTRACT","BUSINESS_IDENTITY"):
        row=by.get(rid)
        if row and row["detected_by"]:
            if rid == "CALL_CONTRACT" and any("Экспорт" in pattern for pattern in row["detected_by"]):
                row["activation_status"]="ROUTED"
            else:
                row["activation_status"]="CONDITIONAL_REVIEW"
            row["reason"]="tier-0 + direct trigger matched"
    # Surface mismatch never erases tier-0 disposition; Tier-1 mismatches stay inactive.
    for row in rows:
        rule_surface=row["surface"]
        if not _rule_surface_compatible(rule_surface,surface) and row["tier"]>0:
            row["active"]=False; row["activation_status"]="NOT_ROUTED"; row["reason"]="surface not applicable"
    return rows


def _artifact_delivery_state(model, warnings):
    blockers=[]
    role=model.get("role")
    confidence=model.get("confidence")

    implementation_source_usable=role not in {"UNKNOWN","RUNTIME_DATABASE"} and confidence!="UNRESOLVED" and not warnings
    exact_delivery_allowed=role in {"CONFIGURATION_EXPORT","CONFIGURATION_SOURCE_TREE"} and confidence!="UNRESOLVED" and not warnings
    full_compare_from_candidate_allowed=exact_delivery_allowed

    if role in {"UNKNOWN","MIXED_ARTIFACT"}:
        blockers.append("ARTIFACT_CLASSIFICATION_UNRESOLVED")
    if role=="RUNTIME_DATABASE":
        blockers.append("RUNTIME_DATABASE_IS_NOT_CONFIGURATION_DELIVERY_BASELINE")
    if role=="CONFIGURATION_SUBSET":
        blockers.append("CONFIGURATION_SUBSET_REQUIRES_AUTHORITATIVE_BASELINE_FOR_EXACT_DELIVERY")
    if warnings:
        blockers.append("ARTIFACT_TRAVERSAL_LIMIT_OR_READ_WARNING")

    return {
        "implementation_source_usable":implementation_source_usable,
        "exact_delivery_allowed":exact_delivery_allowed,
        "full_compare_from_candidate_allowed":full_compare_from_candidate_allowed,
        "blockers":blockers,
        "rule":"Analysis may continue with partial/unknown inputs. A configuration subset may be a valid implementation source when paired with an accepted baseline, but exact delivery/FULL_COMPARE requires a proven authoritative target shape. UNKNOWN/MIXED/runtime-only inputs must never be silently treated as exact configuration delivery baselines."
    }


def build_plan(paths, baseline=None, analysis_only=False, surface_override=None, risk_override=None, project_context=None, requirements_contract=None):
    release_intake_manifest=intake_from_build_args(paths,baseline,analysis_only,surface_override,risk_override,project_context,requirements_contract)
    registry=load_registry(); artifacts=[]; onec=cleverence=False; onec_texts=[]; onec_sources=[]; cleverence_texts=[]; cleverence_sources=[]; all_sources=[]; logical_origins={}
    corpus=inventory_paths(paths)
    corpus_summary=summarize_corpus(corpus)
    artifact_model=corpus["artifact_model"]
    if artifact_model.get("family")=="CLEVERENCE":cleverence=True
    if artifact_model.get("family")=="ONEC":onec=True

    for semantic,data,origin,row in analyzable_entries(corpus):
        logical=semantic.replace("\\","/")
        if logical in logical_origins and logical_origins[logical] != origin:
            physical=row.physical_path.replace("\\","/")
            wrapper=physical.split("!/",1)[0]
            prefix=Path(wrapper).stem or "artifact"
            candidate=f"{prefix}/{logical}"
            suffix=2
            while candidate in logical_origins:
                candidate=f"{prefix}-{suffix}/{logical}"; suffix+=1
            logical=candidate
        logical_origins[logical]=origin
        text=_decode(data); is_onec,is_cleverence=_surface_for(logical,text)
        onec|=is_onec; cleverence|=is_cleverence
        routing_names=list(dict.fromkeys([logical,*getattr(row,"routing_aliases",[])]))
        if is_onec:
            onec_texts.append(text)
            onec_sources.extend((name,text) for name in routing_names)
        if is_cleverence:
            cleverence_texts.append(text)
            cleverence_sources.extend((name,text) for name in routing_names)
        all_sources.extend((name,text) for name in routing_names)
        artifacts.append({
            "logical_path":logical,
            "physical_path":row.physical_path,
            "routing_aliases":routing_names,
            "origin":origin,
            "container_chain":row.container_chain,
            "sha256":hashlib.sha256(data).hexdigest(),
            "size":len(data),
            "onec":is_onec,
            "cleverence":is_cleverence,
            "text":text,
        })
    context=_load_project_context(project_context)
    requirements=_load_requirements_contract(requirements_contract)
    detected_surface,surface=_route_surface(onec,cleverence,context["surface"],requirements["surface"],surface_override)
    combined="\n".join([*(a["text"] for a in artifacts),context["text"]])
    rule_rows=_activate_rules(registry,combined,onec_texts,cleverence_texts,surface,analysis_only,onec_sources,cleverence_sources,all_sources)
    detected_risk="R0_LOCAL"
    for row in rule_rows:
        # detected source risk excludes rules active only because tier-0 disposition is required.
        if row["detected_by"] and row["active"]:
            detected_risk=max_risk(detected_risk,row["risk_floor"])
    routed_risk="R0_LOCAL"
    for row in rule_rows:
        if row["active"] and (row["detected_by"] or row["tier"]>0 or row["reason"].startswith("derived")):
            routed_risk=max_risk(routed_risk,row["risk_floor"])
    risk=max_risk(routed_risk,context["risk"],requirements["risk"],risk_override)
    requirements_coverage_sufficient=_requirements_cover(requirements.get("surface"),requirements.get("risk"),surface,risk)
    active_profiles=[]
    for row in rule_rows:
        if not row["profile"] or not row["active"]:
            continue
        # Tier-0 disposition does not automatically load an expensive profile.
        # Load it only after a direct trigger or derived applicability decision.
        routed_profile = bool(row["detected_by"]) or row["reason"].startswith("derived") or row["tier"] > 0
        if not routed_profile:
            continue
        active_profiles.append({"name":row["profile"],"rule_id":row["id"],"file":f"PROFILES/{row['profile']}.md","detected_by":row["detected_by"],"status":row["activation_status"]})
    active_deliveries=materialize_delivery_bindings(registry,rule_rows,surface)
    delivery_applicability=materialize_delivery_applicability(registry,rule_rows,surface)
    applicable_ids={row["capability_id"] for row in delivery_applicability if row["status"]=="APPLICABLE"}
    active_delivery_ids={row["capability_id"] for row in active_deliveries}
    if applicable_ids!=active_delivery_ids:
        raise ValueError(f"Delivery applicability drift: applicable={sorted(applicable_ids)} active={sorted(active_delivery_ids)}")
    gate_plan=_gate_plan(registry,surface,risk,analysis_only)
    active_support=materialize_supporting_artifacts(registry,rule_rows,gate_plan)
    commands=list(dict.fromkeys(
        row["executor_payload"]["value"] for row in active_deliveries
        if row.get("executor_payload",{}).get("kind")=="INSTRUCTION"
    ))
    active_references=list(dict.fromkeys(ref for row in active_deliveries for ref in row.get("references",[])))
    runtime_focus=[]
    active_ids={r["id"] for r in rule_rows if r["active"] and (r["detected_by"] or r["tier"]>0 or r["reason"].startswith("derived"))}
    if active_ids & {"QUERY","DYNAMIC_LIST"}:runtime_focus += ["1C query parser/final variants","representative list/query cardinality/performance"]
    if "TRANSACTION_WRITE" in active_ids:runtime_focus += ["rollback/retry/concurrency/partial failure"]
    if "CFE_EXTENSION_STRUCTURE" in active_ids:runtime_focus += ["extension load/update in Configurator","borrowed-object/base-form compatibility"]
    if "XDTO_STRUCTURE" in active_ids:runtime_focus += ["configuration update/XDTO model acceptance","representative serialization/deserialization"]
    if "FORM_XML_STRUCTURE" in active_ids:runtime_focus += ["Configurator form open/save","representative form open and event interception"]
    if "FORM_DATA_BINDING" in active_ids:runtime_focus += ["representative form open with changed DataPath","changed binding read/edit/save lifecycle and persisted value"]
    if "CLEVERENCE_MSLX" in active_ids:runtime_focus += ["emulator/device main path","condition-false/back/cancel/error/re-entry paths","fresh-scan stale-state/re-entry path when scan state changes","new-picking vs reallocation decision before quantity control when applicable","all applicable writer paths for changed fact fields","live CurrentItem Uid rebind + verify/rollback for fact mutation"]
    if "CLEVERENCE_CONFIGURATION" in active_ids:runtime_focus += ["Cleverence configuration load with changed schema","barcode parser selection for representative full/prefix/competing templates when applicable","changed field exact name/native type availability"]
    if surface=="CROSS_SYSTEM":runtime_focus += ["end-to-end producer/mapping/writer/grouping/consumer/retry"]
    for artifact in artifacts:
        artifact.pop("text",None)
    delivery_state=_artifact_delivery_state(artifact_model,corpus.get("warnings",[]))
    plan={
        "result":"PLAN_CREATED",
        "release_intake":intake_record(release_intake_manifest),
        "registry":{"path":"RULES/rule_registry.json","schema_version":registry.get("schema_version"),"sha256":hashlib.sha256((ROOT/'RULES/rule_registry.json').read_bytes()).hexdigest()},
        "rule":"Routing is not proof. Tier-0 rules always require disposition; routed rules require evidence-backed checks before release.",
        "routing":{"surface":surface,"risk":risk,"mode":"ANALYSIS_ONLY" if analysis_only else "CHANGE_ALLOWED","detected_surface":detected_surface,"declared_surface":surface_override or requirements["surface"] or context["surface"],"detected_risk":detected_risk,"routed_minimum_risk":routed_risk,"declared_risk":risk_override or requirements["risk"] or context["risk"],"rule":"Declared context may only widen surface/raise risk."},
        "artifact_model":artifact_model,
        "artifact_delivery_state":delivery_state,
        "artifact_inventory":corpus_summary,
        "candidate_artifacts":artifacts,
        "baseline":_dependency_snapshot(baseline),
        "rules":rule_rows,
        "active_deliveries":active_deliveries,
        "delivery_applicability":delivery_applicability,
        "active_supporting_artifacts":active_support,
        "active_profiles":active_profiles,
        "context_load_plan":{
            "profiles":[x["file"] for x in active_profiles],
            "references":active_references,
            "knowledge":"Read only knowledge files referenced by active profiles/checks; use external source catalog and ARCHIVE on demand.",
            "archive":"ARCHIVE_ONLY unless a specific historical/provenance claim requires it.",
        },
        "project_context":{k:v for k,v in context.items() if k!="text"},
        "requirements":{
            "required": bool(not analysis_only and risk != "R0_LOCAL"),
            "technical_design_allowed": bool(analysis_only or risk == "R0_LOCAL" or (requirements_coverage_sufficient and requirements.get("gate",{}).get("result")=="PASS" and requirements.get("gate",{}).get("requirements_outcome") in {"REQUIREMENTS_READY","REQUIREMENTS_READY_WITH_ASSUMPTIONS"})),
            "coverage_sufficient":requirements_coverage_sufficient,
            "path":requirements.get("path"),
            "sha256":requirements.get("sha256"),
            "registry_sha256":requirements.get("registry_sha256"),
            "surface":requirements.get("surface"),
            "risk":requirements.get("risk"),
            "gate_result":requirements.get("gate",{}).get("result"),
            "gate_outcome":requirements.get("gate",{}).get("requirements_outcome"),
            "gate_errors":requirements.get("gate",{}).get("errors",[]),
        },
        "gate_plan":gate_plan,
        "deterministic_tools":commands,
        "runtime_focus":list(dict.fromkeys(runtime_focus)),
        "evidence_dependencies":["artifact-model/layout/authoritative-root","requirements-contract hash/gate outcome","candidate/baseline hashes","declaration/caller hashes","reference archive/vendor/BSP/configuration version","active Cleverence Business Process","runtime environment for version-sensitive/measured claims"]
    }
    plan["performance_review"]=build_performance_review_plan_contract(plan)
    return plan


def compact_summary(plan):
    """Small projection for human/LLM routing; the full plan remains the proof artifact."""
    compact_context_load=dict(plan.get("context_load_plan") or {})
    compact_context_load["supporting_artifacts"]=[
        {k:row.get(k) for k in ("path","owner_kind","owner_id")}
        for row in plan.get("active_supporting_artifacts",[])
    ]
    return {
        "result":plan.get("result"),
        "routing":plan.get("routing"),
        "artifact_model":plan.get("artifact_model"),
        "artifact_delivery_state":plan.get("artifact_delivery_state"),
        "artifact_inventory":plan.get("artifact_inventory"),
        "requirements":plan.get("requirements"),
        "performance_review":{
            "owner_rule_id":(plan.get("performance_review") or {}).get("owner_rule_id"),
            "required":(plan.get("performance_review") or {}).get("required"),
        },
        "active_profiles":[{k:profile.get(k) for k in ("name","rule_id","file","status")} for profile in plan.get("active_profiles",[])],
        "active_deliveries":[{k:row.get(k) for k in ("capability_id","enforcement")} | ({"proof_owner":(row.get("proof_binding") or {}).get("owner")} if row.get("proof_binding") else {}) for row in plan.get("active_deliveries",[])],
        "deterministic_tools":plan.get("deterministic_tools"),
        "runtime_focus":plan.get("runtime_focus"),
        "context_load_plan":compact_context_load,
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="+"); ap.add_argument("--baseline"); ap.add_argument("--analysis-only",action="store_true"); ap.add_argument("--surface",choices=SURFACES); ap.add_argument("--risk",choices=RISKS); ap.add_argument("--project-context"); ap.add_argument("--requirements-contract"); ap.add_argument("--output"); ap.add_argument("--summary",action="store_true",help="Print compact human/LLM projection; --output still stores the full immutable plan"); ap.add_argument("--full-json",action="store_true",help="Print full plan JSON even when --output is used")
    a=ap.parse_args(); plan=build_plan(a.paths,a.baseline,a.analysis_only,a.surface,a.risk,a.project_context,a.requirements_contract)
    out=json.dumps(plan,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    shown=compact_summary(plan) if a.summary or (a.output and not a.full_json) else plan
    print(json.dumps(shown,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
