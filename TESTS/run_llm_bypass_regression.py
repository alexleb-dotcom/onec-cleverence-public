#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import subprocess
import re

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'TESTS/fixtures'
sys.path.insert(0,str(ROOT/'TOOLS'))

from artifact_corpus import inventory_paths, summarize
from build_review_plan import build_plan
from build_validation_ledger import build_ledger

results={}; errors=[]

def record(case,ok,details):
    key=f'llm_bypass:{case}' if not case.startswith(('external_source:','cold_start:')) else case
    results[key]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":key,"details":details})

# The model may try to narrow explicit routing to save work. Source detection wins.
plan=build_plan([FIXTURES/'query_in_loop_bad.bsl'],analysis_only=False,surface_override='ANALYSIS_ONLY')
record('surface_downgrade',plan['routing']['surface']=='ONEC_ONLY',plan['routing'])

plan=build_plan([FIXTURES/'query_in_loop_bad.bsl'],analysis_only=False,risk_override='R0_LOCAL')
record('risk_downgrade',plan['routing']['risk']=='R2_STATEFUL_RUNTIME',plan['routing'])

# Analysis-only changes mode, not detected source identity.
plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'],analysis_only=True)
record('analysis_only_preserves_detection',plan['routing']['mode']=='ANALYSIS_ONLY' and plan['routing']['detected_surface']=='ONEC_ONLY',plan['routing'])

# Two separate changed objects with the same basename must never collapse.
paths=[FIXTURES/'cross_object_same_filename/A/Module.bsl',FIXTURES/'cross_object_same_filename/B/Module.bsl']
plan=build_plan(paths,analysis_only=True)
logical=[x['logical_path'] for x in plan['candidate_artifacts']]
route=next(x for x in plan['rules'] if x['id']=='CROSS_OBJECT_DUPLICATION_REVIEW')
record('duplicate_name_preserved',len(plan['candidate_artifacts'])==2 and len(set(logical))==2 and route['active'] and bool(route['detected_by']),{'logical_paths':logical,'route':route})

# BSL-looking words inside Mobile SMARTS XML are not proof of a second 1C artifact surface.
plan=build_plan([FIXTURES/'cleverence_controls_good.mslx'],analysis_only=True)
record('embedded_script_isolation',plan['routing']['detected_surface']=='CLEVERENCE_ONLY' and plan['routing']['surface']=='CLEVERENCE_ONLY',plan['routing'])

# A misleading folder/archive label cannot hide mixed contents from the inventory.
plan=build_plan([FIXTURES/'artifact_scope_mixed'],analysis_only=True)
inv=plan['artifact_inventory']
record('artifact_scope_inventory',inv.get('files')==2 and inv.get('kinds',{}).get('onec',0)>=2 and {'Documents','XDTOPackages'}<=set(inv.get('top_roots',{})),inv)

# Missing requirements may not be optimized away for non-trivial change work.
plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'])
record('requirements_missing',plan['requirements']['required'] is True and plan['requirements']['technical_design_allowed'] is False,plan['requirements'])

with tempfile.TemporaryDirectory() as td:
    root=Path(td)

    subset=root/'subset'; (subset/'Operations').mkdir(parents=True)
    (subset/'Operations/Test.mslx').write_text('<?xml version="1.0" encoding="utf-8"?><Operation name="Test"><Actions><ShowMessageAction id="a" name="A"/></Actions></Operation>',encoding='utf-8')
    plan=build_plan([subset],analysis_only=True)
    state=plan['artifact_delivery_state']
    record('subset_not_full_compare',state['implementation_source_usable'] is True and state['exact_delivery_allowed'] is False and state['full_compare_from_candidate_allowed'] is False,state)

    change_plan=build_plan([subset])
    ledger=build_ledger(change_plan)
    request_ids={x.get('id') for x in ledger.get('artifact_requests',[])}
    record('subset_requests_authoritative_delivery','ARTIFACT_ROLE_AND_DELIVERY' in request_ids,ledger.get('artifact_requests',[]))

    runtime=root/'runtime'; (runtime/'Logs').mkdir(parents=True)
    (runtime/'Cells.sqlite').write_bytes(b'SQLite format 3\0'); (runtime/'Logs/log.txt').write_text('runtime',encoding='utf-8')
    plan=build_plan([runtime],analysis_only=True); state=plan['artifact_delivery_state']
    record('runtime_not_exact_delivery',plan['artifact_model']['role']=='RUNTIME_DATABASE' and state['exact_delivery_allowed'] is False and state['implementation_source_usable'] is False,{'model':plan['artifact_model'],'state':state})

    unknown=root/'unknown'; unknown.mkdir(); (unknown/'blob.dat').write_bytes(b'not source')
    plan=build_plan([unknown],analysis_only=True); state=plan['artifact_delivery_state']
    record('unknown_not_exact_delivery',plan['artifact_model']['role']=='UNKNOWN' and state['exact_delivery_allowed'] is False,{'model':plan['artifact_model'],'state':state})

# Experienced lifecycle regression: fill-check-only validation must route write-lifecycle review.
plan=build_plan([FIXTURES/'onec_write_guard_fill_check_only_bad.bsl'],analysis_only=True)
write_route=next(x for x in plan['rules'] if x['id']=='TRANSACTION_WRITE')
record('object_write_validation_lifecycle_routed',write_route['active'] and any('ОбработкаПроверкиЗаполнения' in x for x in write_route.get('detected_by',[])),write_route)

# A normal 1C changed-source patch is not forced through Cleverence delivery-shape logic.
plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'])
ledger=build_ledger(plan)
record('onec_patch_not_false_delivery_block',not any(x.get('id')=='ARTIFACT_ROLE_AND_DELIVERY' for x in ledger.get('artifact_requests',[])),ledger.get('artifact_requests',[]))

# Supporting external sources may not silently become normative or become an implicit distribution dependency.
catalog=json.loads((ROOT/'KNOWLEDGE/EXTERNAL_SOURCE_CATALOG.json').read_text(encoding='utf-8'))
rows={x['id']:x for x in catalog.get('sources',[])}
trust_ok=(
    rows.get('CC_1C_SKILLS',{}).get('trust')=='SUPPORTING_REFERENCE'
    and rows.get('V8STD',{}).get('trust')=='SUPPORTING_DISCOVERY'
    and rows.get('REQUIREMENTS_METHOD_ORIGIN',{}).get('trust')=='CONCEPTUAL_SOURCE'
    and rows.get('REQUIREMENTS_METHOD_ORIGIN',{}).get('load')=='NOT_DISTRIBUTED'
)
record('external_source:catalog_trust_hierarchy',trust_ok,{k:{'trust':v.get('trust'),'load':v.get('load')} for k,v in rows.items()})

# Resolve threat-matrix proof bindings before treating a case as gate-enforced.
_registry_doc=json.loads((ROOT/'RULES/rule_registry.json').read_text(encoding='utf-8'))
_check_rows={}
_check_enforcement={}
for _rule in _registry_doc.get('rules',[])+_registry_doc.get('requirements_rules',[]):
    _enforced=set(_rule.get('regression',{}).get('enforcement_cases',[]))
    for _check in _rule.get('checks',[]):
        _check_rows[_check.get('id')]={'rule':_rule.get('id'),'check':_check}
        _check_enforcement[_check.get('id')]=f"check:{_check.get('id')}" in _enforced
_reg_manifest=json.loads((ROOT/'TESTS/REGRESSION_MANIFEST.json').read_text(encoding='utf-8'))
_machine_types={finding for section in ('machine_bad_cases','field_flow_bad_cases','onec_xml_bad_cases','cleverence_bad_cases','cleverence_config_bad_cases','changeset_architecture_bad_cases') for findings in _reg_manifest.get(section,{}).values() for finding in findings}
_machine_types.update(finding for case in _reg_manifest.get('reachability_cases',[]) for finding in case.get('bad_expected',[]))
_machine_types.update(finding for case in _reg_manifest.get('changeset_architecture_scope_cases',[]) for finding in case.get('expected',[]))
_machine_types.update(finding for case in _reg_manifest.get('cleverence_diff_cases',[]) for finding in case.get('expected',[]))
_machine_types.update(finding for case in _reg_manifest.get('cleverence_config_diff_cases',[]) for finding in case.get('expected',[]))
_test_source_corpus='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'TESTS').glob('run_*.py'))
_test_json_corpus='\n'.join(path.read_text(encoding='utf-8') for path in (ROOT/'TESTS').glob('*.json'))

def _mechanical_ref_status(ref):
    if ref.startswith('check:'):
        cid=ref[6:]; row=_check_rows.get(cid); check=(row or {}).get('check',{})
        ok=bool(row and check.get('blocking') and check.get('evidence_required') and _check_enforcement.get(cid))
        return ok, {'kind':'CHECK','check':cid,'owner':(row or {}).get('rule'),'blocking':check.get('blocking'),'evidence_required':check.get('evidence_required'),'enforcement_declared':_check_enforcement.get(cid)}
    if ref.startswith('fixture:'):
        path=ROOT/'TESTS/fixtures'/ref[8:]
        return path.exists(), {'kind':'FIXTURE','path':ref[8:]}
    if ref.startswith('machine:'):
        return ref[8:] in _machine_types, {'kind':'MACHINE','finding':ref[8:]}
    # Other refs are executable regression result IDs. Static/dynamic IDs must be anchored
    # in an active regression script or its JSON case manifest; matrix text alone is excluded.
    ok=ref in _test_source_corpus or ref in _test_json_corpus
    if not ok and ref.startswith('llm_bypass:'):
        ok=ref[len('llm_bypass:'):] in _test_source_corpus
    return ok, {'kind':'EXECUTED_REGRESSION','ref':ref}

# A current-1C evidence gap may not silently fall back to "send XML/BSL/extension ZIP" without
# first dispositioning the maintained ProjectSnapshot acquisition path. This protects the real
# audit-chat failure where the model remembered evidence-first but forgot the Collector.
_project_snapshot_orchestration=json.loads((ROOT/'WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json').read_text(encoding='utf-8'))
_pre_manual_gate=_project_snapshot_orchestration.get('pre_manual_current_onec_gate') or {}
_manual_gate_rules='\n'.join(_pre_manual_gate.get('rules') or [])
_project_snapshot_manual_bypass_ok=(
    _pre_manual_gate.get('required_before_manual_current_onec_request') is True
    and {'PROJECT_SNAPSHOT_REQUIRED','SPLIT_ACQUISITION','DISCOVERY_BOOTSTRAP','MANUAL_FALLBACK_UNSUPPORTED'}<=set(_pre_manual_gate.get('dispositions') or [])
    and 'a broad audit or review is not by itself a reason to bypass ProjectSnapshot' in _manual_gate_rules
    and 'after DISCOVERY_BOOTSTRAP is inventoried the gate must be re-run before any further current-1C evidence request' in _manual_gate_rules
    and 'do not duplicate acquisition when supplied or bootstrap source already closes the supported claim' in _manual_gate_rules
    and 'resolve ProjectSnapshot disposition before every manual current-1C source request' in set(_project_snapshot_orchestration.get('chat_responsibilities') or [])
)
record('project_snapshot_manual_bypass',_project_snapshot_manual_bypass_ok,_pre_manual_gate)

# ProjectSnapshot/ChangePackage templates are durable machine-readable interfaces, not prose-only suggestions.
_snapshot_request=json.loads((ROOT/'TEMPLATES/PROJECT_SNAPSHOT_REQUEST.json').read_text(encoding='utf-8'))
_snapshot_manifest=json.loads((ROOT/'TEMPLATES/PROJECT_SNAPSHOT_MANIFEST.json').read_text(encoding='utf-8'))
_change_package=json.loads((ROOT/'TEMPLATES/CHANGE_PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
_snapshot_template_ok=(
    _snapshot_request.get('schema_version')==1
    and _snapshot_request.get('dependency_expansion',{}).get('mode')=='MINIMAL_SUFFICIENT'
    and _snapshot_request.get('collector_policy',{}).get('read_only_collection') is True
    and _snapshot_request.get('collector_policy',{}).get('unsupported_items_must_be_reported') is True
    and _snapshot_manifest.get('schema_version')==1
    and 'missing_required' in _snapshot_manifest.get('coverage',{})
    and 'unsupported' in _snapshot_manifest.get('coverage',{})
    and _snapshot_manifest.get('coverage',{}).get('claims_full_configuration') is False
)
record('project_snapshot_template_contract',_snapshot_template_ok,{'request':_snapshot_request,'manifest':_snapshot_manifest})
_source_evidence=_change_package.get('source_evidence',{})
_change_bindings=_source_evidence.get('bindings') or []
_project_snapshot_bindings=[row for row in _change_bindings if isinstance(row,dict) and row.get('kind')=='PROJECT_SNAPSHOT_PACKAGE']
_change_package_has_snapshot_id='snapshot_id' in json.dumps(_change_package,ensure_ascii=False)
_change_package_ok=(
    _change_package.get('schema_version')==2
    and not _change_package_has_snapshot_id
    and 'baseline_fingerprint' in _source_evidence
    and isinstance(_change_bindings,list) and bool(_change_bindings)
    and all(isinstance(row,dict) and set(('kind','id','sha256','scope'))<=set(row) and isinstance(row.get('scope'),list) and bool(row.get('scope')) for row in _change_bindings)
    and all('request_id' in row for row in _project_snapshot_bindings)
    and _change_package.get('post_transfer_verification',{}).get('policy')=='OPTIONAL'
    and _change_package.get('post_transfer_verification',{}).get('verification_hooks_retained') is True
    and _change_package.get('proof_boundary',{}).get('applied_target_observed') is False
    and _change_package.get('proof_boundary',{}).get('deployment_or_import_observed') is False
    and _change_package.get('proof_boundary',{}).get('runtime_behavior_observed') is False
)
record('change_package_template_contract',_change_package_ok,_change_package)

# The threat matrix itself is a required coverage inventory, not prose that can silently shrink.
matrix=json.loads((ROOT/'TESTS/LLM_BYPASS_MATRIX.json').read_text(encoding='utf-8'))
ids=[x.get('id') for x in matrix.get('cases',[])]
incomplete=[x.get('id') for x in matrix.get('cases',[]) if not x.get('id') or not x.get('shortcut') or not x.get('primary_owner') or not isinstance(x.get('related_owners',[]),list) or not x.get('family') or not x.get('mechanical_regressions')]
_behavior_doc=json.loads((ROOT/'TESTS/SEMANTIC_BEHAVIOR_CASES.json').read_text(encoding='utf-8'))
_behavior_ids={f"semantic_behavior:{row.get('id')}" for row in _behavior_doc.get('cases',[])}
_behavior_proc=subprocess.run(
    [sys.executable, str(ROOT/'TESTS/run_semantic_behavior_regression.py')],
    cwd=ROOT,
    capture_output=True,
    text=True,
)
try:
    _behavior_report=json.loads(_behavior_proc.stdout) if _behavior_proc.stdout.strip() else {}
except json.JSONDecodeError:
    _behavior_report={}
_behavior_results=_behavior_report.get('results',{}) if isinstance(_behavior_report,dict) else {}
_behavior_runner_executed=_behavior_proc.returncode==0 and _behavior_report.get('result')=='PASS'
matrix_ref_errors=[]
coverage_by_case={}
for _case in matrix.get('cases',[]):
    _cid=_case.get('id')
    _mech=[]
    for _ref in _case.get('mechanical_regressions',[]):
        _ok,_detail=_mechanical_ref_status(_ref); _mech.append({'ref':_ref,'pass':_ok,'detail':_detail})
        if not _ok:matrix_ref_errors.append({'case':_cid,'ref':_ref,'detail':_detail})
    _gate_enforced=bool(_mech) and all(x['pass'] for x in _mech)
    _behavior_refs=_case.get('behavioral_regressions',[])
    _behavior_ok=bool(_behavior_refs) and _behavior_runner_executed and all(ref in _behavior_ids and _behavior_results.get(ref,{}).get('pass') is True for ref in _behavior_refs)
    _runtime_refs=_case.get('runtime_evidence',[])
    _runtime_ok=bool(_runtime_refs) and _behavior_ok and all((ROOT/ref).exists() for ref in _runtime_refs if isinstance(ref,str))
    _state='REGISTERED'
    if _gate_enforced:_state='GATE_ENFORCED'
    if _gate_enforced and _behavior_ok:_state='BEHAVIORALLY_SAMPLED'
    if _gate_enforced and _behavior_ok and _runtime_ok:_state='RUNTIME_PROVEN'
    coverage_by_case[_cid]={'state':_state,'family':_case.get('family'),'primary_owner':_case.get('primary_owner'),'related_owners':_case.get('related_owners',[]),'mechanical':_mech,'behavioral_regressions':_behavior_refs,'runtime_evidence':_runtime_refs}
coverage_counts={state:sum(1 for row in coverage_by_case.values() if row['state']==state) for state in ('REGISTERED','GATE_ENFORCED','BEHAVIORALLY_SAMPLED','RUNTIME_PROVEN')}
REQUIRED_FAMILY_COUNTS={
    "ABSENCE_SEMANTICS": 2,
    "COLD_START_EMPIRICAL": 5,
    "CORE_ANTI_BYPASS": 40,
    "DATA_STATE_RUNTIME": 14,
    "DISTRIBUTION_PRIVACY": 4,
    "EXTERNAL_COMPONENT": 7,
    "FACT_SET_COMPLETENESS": 2,
    "MEASURE_SEMANTICS": 3,
    "MINIMAL_CHANGE": 9,
    "PRACTICAL_EXPERIENCE": 8,
    "PROJECT_CONTEXT_CROSS_SYSTEM": 5,
    "PROJECT_EXPERIENCE": 8,
    "PROJECT_UI_RUNTIME": 3,
    "PROOF_BINDING": 15,
    "PROOF_DISCIPLINE": 5,
    "RELATIONAL_COMPOSITION": 3,
    "REQUIREMENTS_INTEGRITY": 6,
    "SKILL_FRESHNESS": 5,
    "TEMPORAL_STATE": 3,
    "TERMINOLOGY": 3
}

SUBSYSTEM_OWNER_SOURCES={
    "PROJECT_BOOTSTRAP": "KNOWLEDGE/PROJECT_BOOTSTRAP.md",
    "SKILL_FRESHNESS": "KNOWLEDGE/SKILL_FRESHNESS.md",
    "PROJECT_CONTEXT_LIFECYCLE": "KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md",
    "DISTRIBUTION_PRIVACY": "DISTRIBUTION.md",
    "PATTERN_GUIDANCE": "PATTERNS/README.md",
    "ONEC_TERMINOLOGY_CONTRACT": "KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md"
}
_subsystem_owner_missing={owner:path for owner,path in SUBSYSTEM_OWNER_SOURCES.items() if not (ROOT/path).is_file()}
_registry_owner_ids={row['id'] for section in ('rules','requirements_rules','gates') for row in _registry_doc.get(section,[])}
_owner_ids=_registry_owner_ids|set(SUBSYSTEM_OWNER_SOURCES)

def _owner_contract_status(case):
    primary=case.get('primary_owner')
    related=case.get('related_owners',[])
    problems=[]
    if not primary: problems.append('PRIMARY_OWNER_MISSING')
    if not isinstance(related,list): problems.append('RELATED_OWNERS_NOT_LIST'); related=[]
    owners=([primary] if primary else [])+related
    if len(owners)!=len(set(owners)): problems.append('OWNER_DUPLICATE_OR_PRIMARY_RELATED_OVERLAP')
    unknown=sorted(owner for owner in owners if owner not in _owner_ids)
    if unknown: problems.append({'UNKNOWN_OWNER_IDS':unknown})
    return not problems,problems

matrix_owner_errors=[]
for _case in matrix.get('cases',[]):
    _ok,_problems=_owner_contract_status(_case)
    if not _ok: matrix_owner_errors.append({'case':_case.get('id'),'problems':_problems})

record('threat_subsystem_owner_sources_exist',not _subsystem_owner_missing,_subsystem_owner_missing)
_probe_owner=next(iter(sorted(_owner_ids)))
_owner_unknown_ok,_owner_unknown_details=_owner_contract_status({'primary_owner':'__UNKNOWN_OWNER__','related_owners':[]})
record('threat_owner_unknown_rejected',not _owner_unknown_ok,_owner_unknown_details)
_owner_missing_ok,_owner_missing_details=_owner_contract_status({'related_owners':[]})
record('threat_primary_owner_required',not _owner_missing_ok,_owner_missing_details)
_owner_overlap_ok,_owner_overlap_details=_owner_contract_status({'primary_owner':_probe_owner,'related_owners':[_probe_owner]})
record('threat_primary_related_overlap_rejected',not _owner_overlap_ok,_owner_overlap_details)

_family_names={case.get('family') for case in matrix.get('cases',[]) if case.get('family')}
family_counts={family:sum(1 for case in matrix.get('cases',[]) if case.get('family')==family) for family in _family_names}
family_count_errors={family:{'expected':expected,'actual':family_counts.get(family,0)} for family,expected in REQUIRED_FAMILY_COUNTS.items() if family_counts.get(family,0)!=expected}
unknown_families=sorted(set(family_counts)-set(REQUIRED_FAMILY_COUNTS))
record(
    'threat_matrix_complete',
    len(ids)==len(set(ids)) and matrix.get('version',0)>=23 and matrix.get('ownership_schema_version')==1 and matrix.get('family_schema_version')==1 and not incomplete and not matrix_ref_errors and not matrix_owner_errors and not _subsystem_owner_missing and not family_count_errors and not unknown_families,
    {
      'count':len(ids),'version':matrix.get('version'),'ownership_schema_version':matrix.get('ownership_schema_version'),'family_schema_version':matrix.get('family_schema_version'),
      'incomplete':incomplete,'matrix_ref_errors':matrix_ref_errors,'matrix_owner_errors':matrix_owner_errors,
      'subsystem_owner_sources':SUBSYSTEM_OWNER_SOURCES,'subsystem_owner_missing':_subsystem_owner_missing,
      'family_counts':family_counts,'required_family_counts':REQUIRED_FAMILY_COUNTS,'family_count_errors':family_count_errors,'unknown_families':unknown_families,
      'coverage_counts':coverage_counts,'behavioral_runner_executed':_behavior_runner_executed,
    }
)

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results,"threat_cases":len(ids),"coverage_counts":coverage_counts,"coverage_by_case":coverage_by_case}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
