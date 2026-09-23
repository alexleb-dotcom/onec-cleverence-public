#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import copy, json, re, subprocess, sys, tempfile, zipfile

root=Path(__file__).resolve().parents[1]
errors=[]

def load_json_strict(text):
    def reject_duplicates(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError(f'duplicate JSON key: {key}')
            result[key]=value
        return result
    return json.loads(text,object_pairs_hook=reject_duplicates)

required=[
 'SKILL.md','RULES/rule_registry.json','RULES/README.md','PROFILES/INDEX.json','REQUIREMENTS/README.md','REQUIREMENTS/INDEX.json',
 'KNOWLEDGE/VALIDATION_ENGINE.md','KNOWLEDGE/EXECUTION_CHECKPOINT.md','KNOWLEDGE/RESULT_DELIVERY.md','KNOWLEDGE/PROOF_CLAIM_INTEGRITY.md','KNOWLEDGE/GAP_DISCOVERY_PROTOCOL.md','KNOWLEDGE/REQUIREMENTS_DISCOVERY.md','KNOWLEDGE/REQUIREMENTS_ARTIFACT_INTEGRITY.md','KNOWLEDGE/BSP_USAGE_POLICY.md','KNOWLEDGE/CLEVERENCE_RUNTIME_INTEGRATION.md','KNOWLEDGE/ANTIPATTERN_CATALOG.json',
 'REFERENCE/INDEXES/bsp_public_api.csv','REFERENCE/SOURCES/BSP_COMMON_MODULES.zip','REFERENCE/SOURCES/CLEVERENCE_ORIGINAL_BASELINE.zip',
 'TOOLS/rule_registry.py','TOOLS/generate_registry_views.py','TOOLS/execution_checkpoint.py','TOOLS/build_requirements_contract.py','TOOLS/requirements_gate.py','TOOLS/build_review_plan.py','TOOLS/build_validation_ledger.py','TOOLS/release_gate.py','TOOLS/proof_contract.py','TOOLS/proof_identity.py','TOOLS/performance_review.py','TOOLS/implementation_intent.py','TOOLS/semantic_review.py','TOOLS/semantic_proof_verifier.py',
 'TOOLS/analyze_onec_bsl.py','TOOLS/query_literal_escape_contract.py','TOOLS/analyze_onec_field_flow.py','TOOLS/analyze_onec_reachability.py','TOOLS/analyze_changeset_architecture.py','TOOLS/analyze_onec_xml.py','TOOLS/analyze_cleverence_mslx.py','TOOLS/analyze_cleverence_configuration.py','TOOLS/check_bsl_call_signatures.py',
 'TESTS/RULE_ACTIVATION_CASES.json','TESTS/REQUIREMENTS_ACTIVATION_CASES.json','TESTS/run_execution_checkpoint_regression.py','TESTS/run_execution_checkpoint_integration_regression.py','TESTS/SEMANTIC_BEHAVIOR_CASES.json','TESTS/run_semantic_behavior_regression.py','TESTS/run_result_delivery_contract_regression.py','TESTS/run_review_regression.py','TESTS/run_performance_review_regression.py','TESTS/run_proof_contract_regression.py','TESTS/run_semantic_proof_phase1_regression.py','WORKFLOW/DEVELOPMENT_PIPELINE.json','WORKFLOW/RESULT_DELIVERY_CONTRACT.json','PROFILES/CLEVERENCE_CONFIGURATION.md',
 'KNOWLEDGE/EXTERNAL_1C_STRUCTURAL_REFERENCE.md','KNOWLEDGE/V8STD_SOURCE_POLICY.md','KNOWLEDGE/PROOF_POLICY_INDEX.json','THIRD_PARTY/cc-1c-skills/LICENSE.txt','THIRD_PARTY/cc-1c-skills/NOTICE.md',
 'TEMPLATES/FUNCTIONAL_CONTRACT_TEMPLATE.json'
]
for rel in required:
    if not (root/rel).is_file():errors.append(f'missing:{rel}')

# Parse all active JSON.
for path in root.rglob('*.json'):
    if 'ARCHIVE' in path.parts:continue
    try:load_json_strict(path.read_text(encoding='utf-8-sig'))
    except Exception as exc:errors.append(f'json_parse:{path.relative_to(root)}:{exc}')

try:
    registry=json.loads((root/'RULES/rule_registry.json').read_text(encoding='utf-8'))
    allowed_modes={'MACHINE','SOURCE_REQUIRED','SEMANTIC','RUNTIME'}
    all_check_ids=[]
    machine_finding_owners={}

    def validate_rule_set(rows, order_key, label, profile_check=False):
        ids=[r['id'] for r in rows]
        if len(ids)!=len(set(ids)):errors.append(f'{label}_duplicate_rule_ids')
        order=registry.get(order_key,[])
        if len(order)!=len(set(order)):errors.append(f'{label}_duplicate_rule_order_ids')
        if set(order)!=set(ids):errors.append(f'{label}_rule_order_drift:missing={sorted(set(ids)-set(order))}:extra={sorted(set(order)-set(ids))}')
        for rule in rows:
            rid=rule.get('id','?')
            for field in ['tier','severity','activation','evidence_modes','checks','regression']:
                if field not in rule:errors.append(f'{label}_rule_missing_field:{rid}:{field}')
            if rule.get('tier') not in {0,1}:errors.append(f'{label}_bad_tier:{rid}:{rule.get("tier")}')
            bad_modes=sorted(set(rule.get('evidence_modes',[]))-allowed_modes)
            if bad_modes:errors.append(f'{label}_bad_evidence_mode:{rid}:{bad_modes}')
            activation=rule.get('activation',{})
            if not activation.get('mode'):errors.append(f'{label}_activation_missing:{rid}')
            if activation.get('scope','COMBINED') not in {'COMBINED','ARTIFACT'}:errors.append(f'{label}_activation_scope_bad:{rid}:{activation.get("scope")}')
            for pattern in activation.get('patterns',[]):
                try:re.compile(pattern,re.I|re.M)
                except Exception as exc:errors.append(f'{label}_bad_regex:{rid}:{pattern}:{exc}')
            for pattern in activation.get('path_patterns',[]):
                try:re.compile(pattern,re.I|re.M)
                except Exception as exc:errors.append(f'{label}_bad_path_regex:{rid}:{pattern}:{exc}')
            if profile_check and rule.get('profile') and not (root/f"PROFILES/{rule['profile']}.md").is_file():errors.append(f'{label}_profile_missing:{rid}:{rule.get("profile")}')
            if not rule.get('checks'):errors.append(f'{label}_rule_without_checks:{rid}')
            for check in rule.get('checks',[]):
                cid=check.get('id')
                if not cid:errors.append(f'{label}_check_without_id:{rid}')
                else:all_check_ids.append(cid)
                if not check.get('question'):errors.append(f'{label}_check_without_question:{rid}:{cid}')
                finding_types=check.get('machine_finding_types') or []
                if not isinstance(finding_types,list):
                    errors.append(f'{label}_machine_finding_types_not_list:{rid}:{cid}')
                    finding_types=[]
                for finding_type in finding_types:
                    if not isinstance(finding_type,str) or not finding_type.strip():
                        errors.append(f'{label}_machine_finding_type_invalid:{rid}:{cid}:{finding_type!r}')
                        continue
                    previous=machine_finding_owners.get(finding_type)
                    if previous is not None:
                        errors.append(f'{label}_machine_finding_owner_duplicate:{finding_type}:{previous[0]}:{previous[1]}:{rid}:{cid}')
                    else:
                        machine_finding_owners[finding_type]=(rid,cid)
            reg=rule.get('regression',{})
            if not reg.get('activation_cases'):errors.append(f'{label}_no_activation_regression:{rid}')
            if not reg.get('enforcement_cases'):errors.append(f'{label}_no_enforcement_regression:{rid}')
        return ids

    gates=registry.get('gates',[]); gate_ids=[g.get('id') for g in gates]
    if not gate_ids or any(not x for x in gate_ids):errors.append('registry_gates_missing_or_empty')
    if len(gate_ids)!=len(set(gate_ids)):errors.append('registry_duplicate_gate_ids')
    for gate in gates:
        if 'blocking' not in gate or not gate.get('description'):errors.append(f'registry_gate_incomplete:{gate.get("id")}')

    technical=registry.get('rules',[]); requirements=registry.get('requirements_rules',[])
    validate_rule_set(technical,'rule_order','registry',True)
    validate_rule_set(requirements,'requirements_rule_order','requirements_registry',False)
    if len(all_check_ids)!=len(set(all_check_ids)):errors.append('registry_duplicate_check_ids_across_phases')
    proof_claim_ids=[]
    for _rule in technical:
        proof_claim_ids.append(f"RULE:{_rule['id']}")
        proof_claim_ids.extend(f"CHECK:{_rule['id']}:{_check['id']}" for _check in _rule.get('checks',[]))
    if len(proof_claim_ids)!=len(set(proof_claim_ids)):errors.append('proof_claim_id_collision')

    collection_rule=next((r for r in technical if r.get('id')=='COLLECTION_ALGORITHM'),None)
    expected_performance_review={
        'schema_version':1,
        'required_when_active':True,
        'candidate_bound':True,
        'not_applicable_policy':'VERIFIER_RECOMPUTED_TRIGGER_ABSENCE_ONLY',
        'max_review_rows':100000,
        'measured_acceleration_requires':'RUNTIME_ADAPTER',
    }
    if not collection_rule or collection_rule.get('performance_review')!=expected_performance_review:
        errors.append(f'registry_collection_performance_review_contract_drift:{(collection_rule or {}).get("performance_review")}')

    tier0={r['id'] for r in technical if r.get('tier')==0}
    expected_tier0={'SOURCE_FIRST','EVIDENCE_ACQUISITION','BASELINE_IDENTITY','ANALOG_BEFORE_INVENTION','STANDARD_PIPELINE_SEMANTIC_PRESERVATION','BSP_REUSE','CALL_CONTRACT','IMPLEMENTATION_REACHABILITY','DOMAIN_OWNERSHIP','BUSINESS_IDENTITY','RESPONSIBILITY_COHESION','MINIMAL_COHERENT_CHANGE','PROOF_CLAIM_INTEGRITY','GAP_DISCOVERY','PROJECT_CONVENTION','BIDIRECTIONAL_STANDARDS','DELIVERY_COHERENCE','RUNTIME_EVIDENCE'}
    if tier0!=expected_tier0:errors.append(f'registry_tier0_drift:missing={sorted(expected_tier0-tier0)}:extra={sorted(tier0-expected_tier0)}')
    req_tier0={r['id'] for r in requirements if r.get('tier')==0}
    expected_req_tier0={'REQUIREMENTS_TRACEABILITY','ACCEPTANCE_ORACLE','REQUIREMENTS_ARTIFACT_INTEGRITY'}
    if req_tier0!=expected_req_tier0:errors.append(f'requirements_tier0_drift:missing={sorted(expected_req_tier0-req_tier0)}:extra={sorted(req_tier0-expected_req_tier0)}')

    discovery=registry.get('gap_discovery_contract') or {}
    lenses=discovery.get('lenses') or []
    if not lenses or len(lenses)!=len(set(lenses)):errors.append('gap_discovery_lenses_missing_or_duplicate')
    status_groups=[discovery.get(x) or [] for x in ('resolved_hypothesis_statuses','blocking_hypothesis_statuses','pending_hypothesis_statuses')]
    all_gap_statuses=[item for group in status_groups for item in group]
    if not all_gap_statuses or len(all_gap_statuses)!=len(set(all_gap_statuses)):errors.append('gap_discovery_statuses_missing_or_overlapping')
    required_hypothesis_fields=set(discovery.get('required_hypothesis_fields') or [])
    if not {'id','lens','statement','source_anchors','counterexample','falsifier','status'} <= required_hypothesis_fields:errors.append('gap_discovery_required_fields_incomplete')

    adversarial=registry.get('adversarial_case_contract') or {}
    if adversarial.get('min_risk') not in registry.get('risks',[]):errors.append('adversarial_case_contract_bad_min_risk')
    if not {'id','case','status'} <= set(adversarial.get('required_fields') or []):errors.append('adversarial_case_contract_required_fields_incomplete')
    if not adversarial.get('pass_requires_evidence'):errors.append('adversarial_case_contract_must_require_evidence')
    if 'release:r1_adversarial_cases_missing_blocks' not in (adversarial.get('regression_cases') or []):errors.append('adversarial_case_contract_regression_missing')

    # Requirements contract fields are a second independent fail-closed coverage list.
    field_ids=[f.get('id') for f in registry.get('requirements_contract_fields',[])]
    if not field_ids or any(not x for x in field_ids):errors.append('requirements_contract_fields_missing_or_empty')
    if len(field_ids)!=len(set(field_ids)):errors.append('requirements_contract_duplicate_fields')
    for f in registry.get('requirements_contract_fields',[]):
        if f.get('min_risk') not in registry.get('risks',[]):errors.append(f'requirements_contract_bad_risk:{f.get("id")}:{f.get("min_risk")}')
        if 'blocking' not in f or not f.get('title'):errors.append(f'requirements_contract_field_incomplete:{f.get("id")}')

    # Regression declarations are executable contracts, not free-form labels.
    activation_doc=json.loads((root/'TESTS/RULE_ACTIVATION_CASES.json').read_text(encoding='utf-8'))
    activation_ids={row['id'] for row in activation_doc.get('cases',[])}|{'tier0_disposition_required'}
    req_activation_doc=json.loads((root/'TESTS/REQUIREMENTS_ACTIVATION_CASES.json').read_text(encoding='utf-8'))
    req_activation_ids={row['id'] for row in req_activation_doc.get('cases',[])}
    regression_doc=json.loads((root/'TESTS/REGRESSION_MANIFEST.json').read_text(encoding='utf-8'))
    machine_types={finding for section in ('machine_bad_cases','field_flow_bad_cases','onec_xml_bad_cases','cleverence_bad_cases','cleverence_config_bad_cases','changeset_architecture_bad_cases') for findings in regression_doc.get(section,{}).values() for finding in findings}
    machine_types.update(finding for case in regression_doc.get('reachability_cases',[]) for finding in case.get('bad_expected',[]))
    machine_types.update(finding for case in regression_doc.get('changeset_architecture_scope_cases',[]) for finding in case.get('expected',[]))
    machine_types.update(finding for case in regression_doc.get('cleverence_diff_cases',[]) for finding in case.get('expected',[]))
    machine_types.update(finding for case in regression_doc.get('cleverence_config_diff_cases',[]) for finding in case.get('expected',[]))
    for finding_type,(owner_rule,owner_check) in sorted(machine_finding_owners.items()):
        if finding_type not in machine_types:
            errors.append(f'registry_machine_finding_type_without_executable_fixture:{owner_rule}:{owner_check}:{finding_type}')
    technical_release_cases={'release_gate:pass_without_evidence_blocks','release_gate:unresolved_blocks','release_gate:bidirectional_pass_missing_blocks','release_gate:reverse_na_cannot_hide_pass_rule','release_gate:duplicate_rule_id_blocks','release_gate:nonconcrete_evidence_blocks','release_gate:machine_evidence_requires_named_report','release_gate:failed_machine_report_cannot_prove_pass','release_gate:reuse_dependency_requires_fingerprint','release_gate:changed_dependency_invalidates_reuse','release_gate:reuse_fingerprint_must_match_plan','release_gate:current_candidate_bytes_drift_blocks','release_gate:current_baseline_bytes_drift_blocks','release:forward_na_with_code_blocks','release:required_gate_na_blocks','release:pending_does_not_hide_checks','release:required_artifact_not_requested_blocks','release:unresolved_gap_hypothesis_blocks','release:machine_zero_does_not_close_gap_discovery','release:unanchored_gap_hypothesis_blocks','release:unrouted_existing_rule_cannot_close_hypothesis'}
    requirement_gate_cases={'requirements_gate:unresolved_blocks','requirements_gate:fully_evidenced_ready','requirements_gate:nonblocking_assumption_ready','requirements_gate:blocking_assumption_blocks','requirements_gate:deleted_contract_field_blocks','requirements_gate:duplicate_rule_id_blocks','requirements_gate:nonconcrete_field_evidence_blocks','requirements_gate:core_functional_field_na_blocks','requirements_gate:current_source_bytes_drift_blocks','requirements_gate:task_text_hash_drift_blocks','requirements_gate:empty_input_blocks','requirements_gate:requirements_artifact_claims_missing_blocks','requirements_gate:proposed_solution_as_confirmed_requirement_blocks','requirements_gate:material_open_question_nonblocking_blocks','requirements_gate:correction_dependency_requires_revalidation','requirements_gate:requirements_adversarial_missing_blocks','release:underscoped_requirements_contract_blocks'}
    known_checks=set(all_check_ids)
    def validate_regression_refs(rows,activation_ids,allowed_gate_cases,label):
        for rule in rows:
            rid=rule['id']
            for case_id in rule.get('regression',{}).get('activation_cases',[]):
                if case_id not in activation_ids:errors.append(f'{label}_activation_case_missing:{rid}:{case_id}')
            for case_id in rule.get('regression',{}).get('enforcement_cases',[]):
                if case_id.startswith('check:'):
                    if case_id[6:] not in known_checks:errors.append(f'{label}_enforcement_check_missing:{rid}:{case_id}')
                elif case_id.startswith('fixture:'):
                    if not (root/'TESTS/fixtures'/case_id[8:]).exists():errors.append(f'{label}_enforcement_fixture_missing:{rid}:{case_id}')
                elif case_id.startswith('machine:'):
                    if case_id[8:] not in machine_types:errors.append(f'{label}_enforcement_machine_missing:{rid}:{case_id}')
                elif case_id not in allowed_gate_cases:
                    errors.append(f'{label}_enforcement_case_unknown:{rid}:{case_id}')
    validate_regression_refs(technical,activation_ids,technical_release_cases,'registry')
    validate_regression_refs(requirements,req_activation_ids,requirement_gate_cases,'requirements_registry')
except Exception as exc:
    errors.append(f'registry_parse:{exc}'); registry={}

# Security/contract regressions must be transitively executed by authoritative CI,
# not merely exist in the tree. Full-audit orchestration is intentionally centralized.
try:
    _skill_workflow=(root/'.github/workflows/skill-validation.yml').read_text(encoding='utf-8')
    _full_runner=(root/'MAINTENANCE/INTERNAL/CI/run_ci_full_audit.py').read_text(encoding='utf-8')
    if 'python MAINTENANCE/INTERNAL/CI/run_ci_full_audit.py' not in _skill_workflow:
        errors.append('full_audit_runner_not_executed_by_authoritative_ci')
    if 'load_public_check_sets' not in _full_runner:
        errors.append('public_inventory_not_loaded_by_full_audit_runner')
    _public_inventory=json.loads((root/'TOOLS/PUBLIC_CI_INVENTORY.json').read_text(encoding='utf-8'))
    _inventory_commands={tuple(row.get('command') or []) for row in _public_inventory.get('checks') or [] if isinstance(row,dict)}
    for _command,_error in (
        (('{python}','TESTS/run_proof_contract_regression.py'),'proof_contract_regression_not_executed_by_skill_ci'),
        (('{python}','TESTS/run_semantic_behavior_regression.py'),'semantic_behavior_regression_not_executed_by_skill_ci'),
        (('{python}','TESTS/run_result_delivery_contract_regression.py'),'result_delivery_contract_regression_not_executed_by_skill_ci'),
    ):
        if _command not in _inventory_commands:errors.append(_error)
except Exception as exc:errors.append(f'proof_contract_workflow_check:{exc}')

# Generated views must be exact derivatives of the registry.
gen=subprocess.run([sys.executable,str(root/'TOOLS/generate_registry_views.py'),'--check'],capture_output=True,text=True,encoding='utf-8')
if gen.returncode!=0:errors.append(f'generated_view_drift:{gen.stdout or gen.stderr}')
try:
    compact=json.loads((root/'PROFILES/INDEX.json').read_text(encoding='utf-8'))
    detailed=json.loads((root/'KNOWLEDGE/MECHANISM_REVIEW_PROFILES.json').read_text(encoding='utf-8'))
    req_index=json.loads((root/'REQUIREMENTS/INDEX.json').read_text(encoding='utf-8'))
    if not compact.get('generated') or compact.get('generated_from')!='RULES/rule_registry.json':errors.append('profile_index_not_generated_view')
    if not detailed.get('generated') or detailed.get('generated_from')!='RULES/rule_registry.json':errors.append('detailed_profiles_not_generated_view')
    if not req_index.get('generated') or req_index.get('generated_from')!='RULES/rule_registry.json':errors.append('requirements_index_not_generated_view')
    manifest=json.loads((root/'TESTS/REGRESSION_MANIFEST.json').read_text(encoding='utf-8'))
    if 'semantic_cases' in manifest:errors.append('duplicate_semantic_registry_in_regression_manifest')
except Exception as exc:errors.append(f'generated_view_parse:{exc}')

# Python tools must compile; important CLIs must execute via their actual command path.
py_files=[p for p in [*root.joinpath('TOOLS').glob('*.py'),*root.joinpath('TESTS').glob('*.py')] if p.is_file()]
compile_run=subprocess.run([sys.executable,'-m','py_compile',*[str(p) for p in py_files]],capture_output=True,text=True,encoding='utf-8')
if compile_run.returncode!=0:errors.append(f'python_compile:{compile_run.stderr}')
cli_cases=[
 [sys.executable,str(root/'TOOLS/build_review_plan.py'),str(root/'TESTS/fixtures/call_contract_nonexport_caller.bsl')],
 [sys.executable,str(root/'TOOLS/build_requirements_contract.py'),str(root/'TESTS/fixtures/requirements_local.txt')],
 [sys.executable,str(root/'TOOLS/check_bsl_call_signatures.py'),'--definitions-file',str(root/'TESTS/fixtures/TestApi_Module.bsl'),'--focus',str(root/'TESTS/fixtures/call_signature_good.bsl')],
 [sys.executable,str(root/'TOOLS/analyze_onec_bsl.py'),str(root/'TESTS/fixtures/query_field_good.bsl')],
 [sys.executable,str(root/'TOOLS/analyze_onec_field_flow.py'),str(root/'TESTS/fixtures/post_write_unrelated_same_module_good.bsl')],
 [sys.executable,str(root/'TOOLS/analyze_changeset_architecture.py'),str(root/'TESTS/fixtures/cross_object_duplication_good')],
 [sys.executable,str(root/'TOOLS/analyze_onec_xml.py'),str(root/'TESTS/fixtures/onec_form_xml_good.xml')],
 [sys.executable,str(root/'TOOLS/analyze_cleverence_mslx.py'),str(root/'TESTS/fixtures/cleverence_graph_good.mslx')],
]
for cmd in cli_cases:
    run=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8')
    if run.returncode!=0:errors.append(f'cli_smoke_failed:{Path(cmd[1]).name}:{run.stderr or run.stdout}')

# Requirements gate CLI smoke through the real CLI with a dynamically current registry hash.
try:
    sys.path.insert(0,str(root/'TOOLS'))
    from build_requirements_contract import build_contract
    req=build_contract([root/'TESTS/fixtures/requirements_contract.txt'],risk_override='R1_CONTRACT')
    for f in req['functional_contract'].values():
        f['status']='KNOWN'; f['value']=f['title']+' — validator smoke'; f['evidence']=[{'kind':'SOURCE_REQUIRED','ref':'validator smoke evidence'}]
    for row in req['rules']:
        row['status']='PASS'; row['evidence']=[{'kind':kind,'ref':'validator smoke evidence'} for kind in row['required_evidence_modes']]
        for ch in row['checks']:ch['status']='PASS'; ch['evidence']=[{'kind':'SEMANTIC','ref':'validator smoke check'}]
    with tempfile.NamedTemporaryFile('w',suffix='.json',encoding='utf-8',delete=False) as tf:
        json.dump(req,tf,ensure_ascii=False); req_path=tf.name
    run=subprocess.run([sys.executable,str(root/'TOOLS/requirements_gate.py'),req_path],capture_output=True,text=True,encoding='utf-8')
    if run.returncode!=0:errors.append(f'cli_smoke_failed:requirements_gate.py:{run.stderr or run.stdout}')
except Exception as exc:errors.append(f'cli_smoke_requirements_setup:{exc}')

# Active workflow must be registry/requirements-gate based and independent from historical project state.
workflow=(root/'WORKFLOW/DEVELOPMENT_PIPELINE.json').read_text(encoding='utf-8')
for required_token in ['RULES/rule_registry.json','TOOLS/requirements_gate.py','TOOLS/release_gate.py']:
    if required_token not in workflow:errors.append(f'workflow_missing:{required_token}')

skill_text=(root/'SKILL.md').read_text(encoding='utf-8')
for required_token in ['KNOWLEDGE/EXECUTION_CHECKPOINT.md','TOOLS/execution_checkpoint.py','recover the existing exact operation before any retry']:
    if required_token not in skill_text:errors.append(f'execution_checkpoint_skill_contract_missing:{required_token}')
for forbidden in ['validate_developer_pack.py','AUTHORITATIVE_STATE.json','CURRENT_WORK/']:
    if forbidden in workflow:errors.append(f'active_workflow_historical_reference:{forbidden}')
try:
    workflow_doc=json.loads(workflow)
    registry_gates={row['id'] for row in registry.get('gates',[])}
    workflow_gates={row['id'] for row in workflow_doc.get('stages',[])}
    if registry_gates!=workflow_gates:errors.append(f'workflow_gate_drift:registry_only={sorted(registry_gates-workflow_gates)}:workflow_only={sorted(workflow_gates-registry_gates)}')
except Exception as exc:errors.append(f'workflow_gate_parse:{exc}')

# Manifest is an exact inventory of active (non-ARCHIVE) files.
manifest_path=root/'manifest.txt'
if manifest_path.exists():
    entries=[x for x in manifest_path.read_text(encoding='utf-8-sig').splitlines() if x]
    if len(entries)!=len(set(entries)):errors.append('manifest_duplicate_entries')
    active={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and 'ARCHIVE' not in p.parts and '.git' not in p.parts and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    missing=set(entries)-active; unlisted=active-set(entries)
    for rel in sorted(missing):errors.append(f'manifest_missing:{rel}')
    for rel in sorted(unlisted):errors.append(f'manifest_unlisted:{rel}')
else:errors.append('manifest_missing_file')

# Archive/reference CRC + filename encoding integrity.
def looks_mojibake(name:str)->bool:return '\ufffd' in name or any('\u2500'<=ch<='\u257f' for ch in name) or bool(re.search(r'#U[0-9A-Fa-f]{4}',name))
for path in root.rglob('*'):
    if path.is_file() and looks_mojibake(path.name):errors.append(f'filename_mojibake:{path.relative_to(root)}')
for zp in root.rglob('*.zip'):
    try:
        with zipfile.ZipFile(zp) as z:
            bad=z.testzip()
            if bad:errors.append(f'zip_crc:{zp.relative_to(root)}:{bad}')
            for info in z.infolist():
                if looks_mojibake(info.filename):errors.append(f'zip_filename_mojibake:{zp.relative_to(root)}:{info.filename}')
    except Exception as exc:errors.append(f'zip_open:{zp.relative_to(root)}:{exc}')

# Universal root must not accidentally become current project state.
for forbidden in ['CURRENT_WORK','PROJECT_SNAPSHOT','AUTHORITATIVE_STATE.json','CURRENT_STATE.md']:
    if (root/forbidden).exists():errors.append(f'project_specific_present:{forbidden}')

# Full regression suite and accepted stock Cleverence corpus.
reg=subprocess.run([sys.executable,str(root/'TESTS/run_review_regression.py')],capture_output=True,text=True,encoding='utf-8')
try:reg_json=json.loads(reg.stdout)
except Exception:reg_json={'result':'FAIL','raw':reg.stdout,'stderr':reg.stderr}
if reg.returncode!=0 or reg_json.get('result')!='PASS':errors.append('regression_failed')
clev=subprocess.run([sys.executable,str(root/'TOOLS/analyze_cleverence_mslx.py'),str(root/'REFERENCE/SOURCES/CLEVERENCE_ORIGINAL_BASELINE.zip')],capture_output=True,text=True,encoding='utf-8')
try:clev_json=json.loads(clev.stdout)
except Exception:clev_json={'result':'FAIL','raw':clev.stdout,'stderr':clev.stderr}
if clev.returncode!=0 or clev_json.get('result')!='PASS':errors.append('cleverence_reference_regression_failed')
clev_cfg=subprocess.run([sys.executable,str(root/'TOOLS/analyze_cleverence_configuration.py'),str(root/'REFERENCE/SOURCES/CLEVERENCE_ORIGINAL_BASELINE.zip')],capture_output=True,text=True,encoding='utf-8')
try:clev_cfg_json=json.loads(clev_cfg.stdout)
except Exception:clev_cfg_json={'result':'FAIL','raw':clev_cfg.stdout,'stderr':clev_cfg.stderr}
if clev_cfg.returncode!=0 or clev_cfg_json.get('result')!='PASS':errors.append('cleverence_configuration_reference_regression_failed')

# Field-flow analyzer is calibrated against the retained working BSL corpus.
# The goal is not zero REVIEW: real lifecycle overwrite candidates may exist.
# The guard prevents a broad heuristic from silently exploding back to module-wide noise.
field_flow_corpus=root/'ARCHIVE/DEVELOPER_PACK/PROJECT_SNAPSHOT/OneC/BASELINE_COMPARE.zip'
if field_flow_corpus.exists():
    fr=subprocess.run([sys.executable,str(root/'TOOLS/analyze_onec_field_flow.py'),str(field_flow_corpus)],capture_output=True,text=True,encoding='utf-8')
    try:field_flow_json=json.loads(fr.stdout)
    except Exception:field_flow_json={'result':'FAIL','raw':fr.stdout,'stderr':fr.stderr}
    ff_files=int((field_flow_json.get('summary') or {}).get('files') or len(field_flow_json.get('files') or []))
    ff_findings=field_flow_json.get('findings') or []
    ff_affected=len({x.get('source') for x in ff_findings if x.get('source')})
    max_findings=max(20,int(ff_files*0.20)) if ff_files else 20
    max_affected=max(10,int(ff_files*0.05)) if ff_files else 10
    if fr.returncode!=0 or field_flow_json.get('result')!='PASS':errors.append('field_flow_reference_regression_failed')
    if len(ff_findings)>max_findings:errors.append(f'field_flow_calibration_noise:findings={len(ff_findings)}:limit={max_findings}')
    if ff_affected>max_affected:errors.append(f'field_flow_calibration_spread:affected_files={ff_affected}:limit={max_affected}')
else:field_flow_json={'result':'NOT_AVAILABLE','findings':[],'summary':{}}

# Structural XML analyzer calibrated against retained real 1C corpus.
onec_xml_corpus=root/'ARCHIVE/DEVELOPER_PACK/PROJECT_SNAPSHOT/OneC/BASELINE_COMPARE.zip'
if onec_xml_corpus.exists():
    xr=subprocess.run([sys.executable,str(root/'TOOLS/analyze_onec_xml.py'),str(onec_xml_corpus)],capture_output=True,text=True,encoding='utf-8')
    try:onec_xml_json=json.loads(xr.stdout)
    except Exception:onec_xml_json={'result':'FAIL','raw':xr.stdout,'stderr':xr.stderr}
    if xr.returncode!=0 or onec_xml_json.get('result')!='PASS':errors.append('onec_xml_reference_regression_failed')
else:onec_xml_json={'result':'NOT_AVAILABLE'}

out={'result':'PASS' if not errors else 'FAIL','errors':errors,
     'registry':{'rules':len(registry.get('rules',[])),'checks':sum(len(r.get('checks',[])) for r in registry.get('rules',[])),'tier0':sum(1 for r in registry.get('rules',[]) if r.get('tier')==0),
                 'requirements_rules':len(registry.get('requirements_rules',[])),'requirements_checks':sum(len(r.get('checks',[])) for r in registry.get('requirements_rules',[])),'requirements_tier0':sum(1 for r in registry.get('requirements_rules',[]) if r.get('tier')==0)},
     'regression':reg_json,
     'cleverence_reference':{'result':clev_json.get('result'),'files':clev_json.get('files'),'actions':clev_json.get('actions'),'summary':clev_json.get('summary')},
     'cleverence_configuration_reference':{'result':clev_cfg_json.get('result'),'files':clev_cfg_json.get('files'),'container_types':clev_cfg_json.get('container_types'),'field_declarations':clev_cfg_json.get('field_declarations'),'barcode_overlap_candidates':len(clev_cfg_json.get('barcode_overlap_candidates') or []),'summary':clev_cfg_json.get('summary')},
     'field_flow_reference':{'result':field_flow_json.get('result'),'files':(field_flow_json.get('summary') or {}).get('files'),'findings':len(field_flow_json.get('findings') or []),'affected_files':len({x.get('source') for x in (field_flow_json.get('findings') or []) if x.get('source')}),'summary':field_flow_json.get('summary')},
     'onec_xml_reference':{'result':onec_xml_json.get('result'),'files':onec_xml_json.get('files'),'artifact_kinds':onec_xml_json.get('artifact_kinds'),'summary':onec_xml_json.get('summary')}}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
