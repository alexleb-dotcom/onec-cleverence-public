#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import copy
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'TOOLS'))
from build_project_bootstrap import build, _capability_gates, _requests, _author_marker_gate_state, CANONICAL_ONEC_AUTHOR_MARKER

errors=[]; results={}

COMMENT_POLICY=(ROOT/"KNOWLEDGE/COMMENTING_POLICY.md").read_text(encoding="utf-8")
PROJECT_CONTEXT=(ROOT/"TEMPLATES/PROJECT_CONTEXT_TEMPLATE.md").read_text(encoding="utf-8")
SKILL=(ROOT/"SKILL.md").read_text(encoding="utf-8-sig")
PIPELINE=json.loads((ROOT/"WORKFLOW/DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))


def record(case,ok,details):
    results[case]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":case,"details":details})

with tempfile.TemporaryDirectory() as td:
    source=Path(td)/'Module.bsl'
    source.write_text('Procedure Test()\nEndProcedure\n',encoding='utf-8')
    bootstrap=build([source])
    gates=bootstrap.get('capability_gates') or {}
    required={'code_output_allowed','metadata_change_allowed','public_interface_change_allowed','delivery_allowed'}
    record('capability_gate_set',required==set(gates),gates)
    record('legacy_gate_maps_code_output',bootstrap['gate']['implementation_allowed']==gates['code_output_allowed']['allowed'],bootstrap['gate'])


    marker=bootstrap['fields']['author_marker']
    marker_request=next((x for x in bootstrap['evidence_requests'] if x['id']=='AUTHOR_MARKER'),None)
    record(
        'author_marker_skill_default_shape',
        marker.get('value',{}).get('syntax_source')=='SKILL_DEFAULT_1C'
        and marker.get('value',{}).get('canonical_shape')==CANONICAL_ONEC_AUTHOR_MARKER
        and CANONICAL_ONEC_AUTHOR_MARKER.get('field_order')==['ФамилияИО','ПервыйБит','Дата','НомерТЗ','пункты ТЗ']
        and CANONICAL_ONEC_AUTHOR_MARKER.get('organization_marker')=='ПервыйБит',
        marker,
    )
    record(
        'author_marker_exact_block_and_one_line_forms',
        CANONICAL_ONEC_AUTHOR_MARKER.get('block_open')=='// ++ ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ'
        and CANONICAL_ONEC_AUTHOR_MARKER.get('block_close')=='// -- ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ'
        and CANONICAL_ONEC_AUTHOR_MARKER.get('one_line')=='// ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ'
        and CANONICAL_ONEC_AUTHOR_MARKER.get('metadata_comment')==CANONICAL_ONEC_AUTHOR_MARKER.get('one_line'),
        CANONICAL_ONEC_AUTHOR_MARKER,
    )
    record(
        'author_marker_missing_values_block_implementation',
        bootstrap['gate'].get('author_marker_state')=='AUTHOR_MARKER_BLOCKED'
        and bootstrap['gate']['implementation_allowed'] is False
        and marker_request is not None
        and marker_request.get('controls')=='1C implementation/development entry',
        {'gate':bootstrap['gate'],'request':marker_request},
    )
    record(
        'author_marker_default_syntax_not_reasked',
        marker_request is not None
        and 'недостающие значения AUTHOR_MARKER' in marker_request.get('what','')
        and 'актуальный формат маркеров' not in marker_request.get('what','')
        and 'ПервыйБит фиксирован' in marker_request.get('what',''),
        marker_request,
    )
    record(
        'author_marker_block_allows_analysis_evidence_work',
        'inspect evidence candidates semantically' in bootstrap.get('next_sequence',[])
        and 'perform task-specific evidence acquisition' in bootstrap.get('next_sequence',[]),
        bootstrap.get('next_sequence'),
    )

    partial=copy.deepcopy(bootstrap['fields'])
    partial['author_marker']['value']['values']['ФамилияИО']='ИвановИИ'
    partial['author_marker']['value']['values']['НомерТЗ']='ТЗ-42'
    partial_requests=_requests(partial,bootstrap['artifact_model'],bootstrap['discovery_candidates'])
    partial_marker=next((x for x in partial_requests if x['id']=='AUTHOR_MARKER'),None)
    record(
        'author_marker_requests_only_missing_values',
        partial_marker is not None
        and 'Дата' in partial_marker.get('what','')
        and 'пункты ТЗ' in partial_marker.get('what','')
        and 'ФамилияИО,' not in partial_marker.get('what','')
        and 'НомерТЗ,' not in partial_marker.get('what',''),
        partial_marker,
    )

    bound=copy.deepcopy(bootstrap['fields'])
    bound_values=bound['author_marker']['value']['values']
    bound_values.update({'ФамилияИО':'ИвановИИ','Дата':'28.09.2026','НомерТЗ':'ТЗ-42','пункты ТЗ':'1.2'})
    bound['author_marker']['status']='KNOWN'
    bound_requests=_requests(bound,bootstrap['artifact_model'],bootstrap['discovery_candidates'])
    record(
        'author_marker_bound_values_reused_without_question',
        _author_marker_gate_state(bound)=='AUTHOR_MARKER_READY'
        and not any(x['id']=='AUTHOR_MARKER' for x in bound_requests),
        {'state':_author_marker_gate_state(bound),'requests':bound_requests},
    )


    incomplete_known=copy.deepcopy(bound)
    incomplete_known['author_marker']['value']['values']['Дата']=None
    incomplete_known['author_marker']['status']='KNOWN'
    incomplete_known_gates=_capability_gates(incomplete_known)
    record(
        'author_marker_incomplete_known_is_fail_closed',
        _author_marker_gate_state(incomplete_known)=='AUTHOR_MARKER_BLOCKED'
        and incomplete_known_gates['code_output_allowed']['allowed'] is False
        and 'author_marker' in incomplete_known_gates['code_output_allowed']['blocking_open_fields'],
        {'state':_author_marker_gate_state(incomplete_known),'gates':incomplete_known_gates},
    )

    incomplete_derived=copy.deepcopy(bound)
    incomplete_derived['author_marker']['value']['values']['пункты ТЗ']=None
    incomplete_derived['author_marker']['status']='DERIVED_WITH_EVIDENCE'
    incomplete_derived_gates=_capability_gates(incomplete_derived)
    record(
        'author_marker_incomplete_derived_is_fail_closed',
        _author_marker_gate_state(incomplete_derived)=='AUTHOR_MARKER_BLOCKED'
        and incomplete_derived_gates['code_output_allowed']['allowed'] is False
        and 'author_marker' in incomplete_derived_gates['code_output_allowed']['blocking_open_fields'],
        {'state':_author_marker_gate_state(incomplete_derived),'gates':incomplete_derived_gates},
    )

    complete_derived=copy.deepcopy(bound)
    complete_derived['author_marker']['status']='DERIVED_WITH_EVIDENCE'
    complete_derived_gates=_capability_gates(complete_derived)
    record(
        'author_marker_complete_derived_is_ready',
        _author_marker_gate_state(complete_derived)=='AUTHOR_MARKER_READY'
        and complete_derived_gates['code_output_allowed']['allowed'] is True,
        {'state':_author_marker_gate_state(complete_derived),'gates':complete_derived_gates},
    )

    not_applicable=copy.deepcopy(bound)
    not_applicable['author_marker']['status']='NOT_APPLICABLE'
    not_applicable['author_marker']['value']=None
    not_applicable_gates=_capability_gates(not_applicable)
    record(
        'author_marker_not_applicable_uses_existing_disposition',
        _author_marker_gate_state(not_applicable)=='AUTHOR_MARKER_READY'
        and not_applicable_gates['code_output_allowed']['allowed'] is True,
        {'state':_author_marker_gate_state(not_applicable),'gates':not_applicable_gates},
    )

    applicable_cases=[bootstrap,incomplete_known,incomplete_derived,bound,complete_derived]
    contradictions=[]
    for row in applicable_cases:
        state=_author_marker_gate_state(row)
        gates_row=_capability_gates(row)
        if state=='AUTHOR_MARKER_BLOCKED' and gates_row['code_output_allowed']['allowed']:
            contradictions.append({'state':state,'gates':gates_row})
    record(
        'author_marker_state_never_contradicts_code_gate',
        not contradictions,
        contradictions,
    )

    override=copy.deepcopy(bound)
    override['author_marker']['value']['syntax_source']='EXPLICIT_PROJECT_OVERRIDE'
    override['author_marker']['value']['explicit_override_syntax']='// explicit project override'
    override_requests=_requests(override,bootstrap['artifact_model'],bootstrap['discovery_candidates'])
    record(
        'author_marker_explicit_override_respected',
        _author_marker_gate_state(override)=='AUTHOR_MARKER_READY'
        and not any(x['id']=='AUTHOR_MARKER' for x in override_requests)
        and 'EXPLICIT_PROJECT_OVERRIDE' in PROJECT_CONTEXT
        and 'explicit override syntax' in PROJECT_CONTEXT,
        {'state':_author_marker_gate_state(override),'requests':override_requests},
    )

    record(
        'author_marker_policy_and_entrypoint_are_single_owner_contract',
        '## Canonical 1C AUTHOR_MARKER' in COMMENT_POLICY
        and '## AUTHOR_MARKER pre-development gate' in COMMENT_POLICY
        and 'AUTHOR_MARKER_READY' in COMMENT_POLICY
        and 'AUTHOR_MARKER_BLOCKED' in COMMENT_POLICY
        and '### 4.5. Resolve 1C AUTHOR_MARKER before development' in SKILL
        and any(
            'require AUTHOR_MARKER_READY' in action
            for stage in PIPELINE.get('stages') or []
            if stage.get('id')=='IMPLEMENTATION'
            for action in stage.get('actions') or []
        ),
        None,
    )

    fields=copy.deepcopy(bootstrap['fields'])
    for fid in ('actual_deployed_baseline','modification_policy','author_marker','technical_comment','existing_comment_policy'):
        fields[fid]['status']='KNOWN'; fields[fid]['value']='regression-evidenced'
    isolated=_capability_gates(fields)
    record(
        'metadata_delivery_do_not_false_block_code',
        isolated['code_output_allowed']['allowed'] is True
        and isolated['metadata_change_allowed']['allowed'] is False
        and isolated['delivery_allowed']['allowed'] is False,
        isolated,
    )

    fields['metadata_attribution']['status']='KNOWN'; fields['metadata_attribution']['value']='regression-evidenced'
    metadata_ready=_capability_gates(fields)
    record(
        'metadata_gate_is_independent',
        metadata_ready['metadata_change_allowed']['allowed'] is True
        and metadata_ready['public_interface_change_allowed']['allowed'] is False
        and metadata_ready['delivery_allowed']['allowed'] is False,
        metadata_ready,
    )

    fields['public_interface_comment']['status']='NOT_APPLICABLE'
    public_ready=_capability_gates(fields)
    record('public_interface_gate_can_resolve_independently',public_ready['public_interface_change_allowed']['allowed'] is True,public_ready)

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
