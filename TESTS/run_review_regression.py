#!/usr/bin/env python3
from pathlib import Path
import copy, hashlib, json, sys, tempfile

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'TESTS/REGRESSION_MANIFEST.json').read_text(encoding='utf-8'))
activation_manifest=json.loads((root/'TESTS/RULE_ACTIVATION_CASES.json').read_text(encoding='utf-8'))
requirements_activation_manifest=json.loads((root/'TESTS/REQUIREMENTS_ACTIVATION_CASES.json').read_text(encoding='utf-8'))
fixtures=root/'TESTS/fixtures'
errors=[]; results={}

sys.dont_write_bytecode=True
sys.path.insert(0,str(root/'TOOLS'))
from analyze_onec_bsl import analyze as analyze_onec, blocks as onec_blocks, query_execute_side_effect_analysis
from analyze_onec_field_flow import analyze as analyze_field_flow
from analyze_onec_reachability import analyze as analyze_reachability
from analyze_changeset_architecture import analyze as analyze_changeset_architecture
from analyze_onec_xml import analyze as analyze_onec_xml
from analyze_cleverence_mslx import analyze as analyze_cleverence
from analyze_cleverence_configuration import analyze as analyze_cleverence_configuration
from build_review_plan import build_plan
from build_requirements_contract import build_contract
from requirements_gate import evaluate as requirements_evaluate
from build_validation_ledger import build_ledger, bind_machine_findings, bind_query_literal_escape_findings
from check_bsl_call_signatures import check_signatures
from release_gate import evaluate as release_evaluate
from machine_receipts import create_receipt
from runtime_evidence import create_adapter_observation
from semantic_review import write_review_receipt
from implementation_intent import build_skeleton as build_intent_skeleton
from rule_registry import load_registry, validate_delivery_bindings
from generate_registry_views import render as render_generated_views
from validation_work_queue import build_work_queue
from evidence_source_policy import classify_non_proof_ref, validate_evidence_items

registry=load_registry()

def run_case(fn):return analyze_onec(fixtures/fn)
for fn,expected in manifest['machine_bad_cases'].items():
    r=run_case(fn); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    results[fn]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':fn,'missing':missing})
for fn,forbidden in manifest['machine_good_cases'].items():
    r=run_case(fn); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    results[fn]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':fn,'unexpected':bad})

# Query literal-escape detector boundary: exact corrupt pairs only, not real whitespace
# or quoted/non-query business data.
_escape_positions=analyze_onec(fixtures/'query_literal_escape_positions_bad.bsl')
_escape_hits=[x for x in _escape_positions.get('findings',[]) if x.get('type')=='QUERY_LITERAL_ESCAPE_CORRUPTION']
_escape_sequences=[x.get('sequence') for x in _escape_hits]
key='query_literal_escape:positions_and_shape'
ok=(
    len(_escape_hits)==3
    and sorted(_escape_sequences)==['\\n','\\r','\\t']
    and all(x.get('severity')=='HIGH' and isinstance(x.get('line'),int) and x.get('procedure')=='ПроверитьПозиции' and x.get('fragment') for x in _escape_hits)
)
results[key]={'findings':_escape_hits,'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_hits})

_escape_crlf=analyze_onec(fixtures/'query_literal_escape_direct_crlf_bad.bsl')
_escape_crlf_hits=[x for x in _escape_crlf.get('findings',[]) if x.get('type')=='QUERY_LITERAL_ESCAPE_CORRUPTION']
key='query_literal_escape:crlf_both_block'
ok=sorted(x.get('sequence') for x in _escape_crlf_hits)==['\\n','\\r']
results[key]={'findings':_escape_crlf_hits,'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_crlf_hits})

for _case,_path in (
    ('real_tab_good','query_literal_escape_real_tab_good.bsl'),
    ('spaces_good','query_literal_escape_spaces_good.bsl'),
    ('nonquery_good','query_literal_escape_nonquery_good.bsl'),
    ('quoted_query_data_good','query_literal_escape_quoted_good.bsl'),
    ('local_alias_good','query_literal_escape_alias_good.bsl'),
):
    _report=analyze_onec(fixtures/_path)
    _hits=[x for x in _report.get('findings',[]) if x.get('type')=='QUERY_LITERAL_ESCAPE_CORRUPTION']
    key='query_literal_escape:'+_case
    ok=not _hits
    results[key]={'findings':_hits,'pass':ok}
    if not ok:errors.append({'case':key,'details':_hits})

# Query literal-escape end-to-end enforcement. The verifier, not a model-authored
# PASS label, owns current-candidate analyzer coverage and exact blocker identity.
_escape_template=fixtures/'query_literal_escape_direct_tab_bad.bsl'
_escape_candidate_dir=Path(tempfile.mkdtemp(prefix='query-escape-candidate-'))
_escape_bad=_escape_candidate_dir/'Module.bsl'
_escape_bad.write_bytes(_escape_template.read_bytes())
_escape_plan=build_plan([_escape_bad],analysis_only=True)
_escape_ledger=build_ledger(_escape_plan,registry)
_escape_release_no_report=release_evaluate(_escape_plan,_escape_ledger,registry)
key='query_literal_escape:e2e_current_analyzer_required'
ok=any(x.get('type')=='QUERY_LITERAL_ESCAPE_CURRENT_ANALYZER_REQUIRED' for x in _escape_release_no_report.get('errors',[]))
results[key]={'errors':_escape_release_no_report.get('errors',[]),'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_release_no_report})

_escape_receipt_dir=Path(tempfile.mkdtemp(prefix='query-escape-receipt-'))
_escape_receipt_path=_escape_receipt_dir/'bad.json'
_escape_receipt=create_receipt(
    'TOOLS/analyze_onec_bsl.py',[str(_escape_bad)],[str(_escape_bad)],
    ['STATIC:ONEC_BSL'],_escape_receipt_path
)
_escape_report={
    'id':'MACHINE:QUERY_ESCAPE:BAD',
    'tool':'TOOLS/analyze_onec_bsl.py',
    'ref':str(_escape_receipt_path),
    'receipt_ref':str(_escape_receipt_path),
    'receipt_sha256':hashlib.sha256(_escape_receipt_path.read_bytes()).hexdigest(),
    'result':_escape_receipt['derived_result'],
    'supersedes':[],
}
_escape_ledger['machine_reports']=[_escape_report]

_escape_prebind=release_evaluate(_escape_plan,_escape_ledger,registry)
_prebind_types={x.get('type') for x in _escape_prebind.get('errors',[])}
key='query_literal_escape:e2e_report_finding_requires_canonical_blocker'
ok={'QUERY_LITERAL_ESCAPE_CORRUPTION_PRESENT','BLOCKING_FINDING_ROW_MISSING'}<=_prebind_types
results[key]={'types':sorted(_prebind_types),'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_prebind})

_escape_bound=bind_query_literal_escape_findings(
    _escape_ledger,_escape_plan,'MACHINE:QUERY_ESCAPE:BAD',
    _escape_plan['candidate_artifacts'][0]['logical_path']
)
key='query_literal_escape:e2e_ledger_exact_identity'
ok=(
    len(_escape_bound)==1
    and _escape_bound[0].get('rule_id')=='QUERY'
    and _escape_bound[0].get('check_id')=='QUERY_LITERAL_ESCAPE_SANITY'
    and _escape_bound[0].get('finding_type')=='QUERY_LITERAL_ESCAPE_CORRUPTION'
    and _escape_bound[0].get('candidate_sha256')==_escape_plan['candidate_artifacts'][0]['sha256']
)
results[key]={'blocking_findings':_escape_bound,'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_bound})

_escape_release_bound=release_evaluate(_escape_plan,_escape_ledger,registry)
_bound_types={x.get('type') for x in _escape_release_bound.get('errors',[])}
key='query_literal_escape:e2e_release_blocked'
ok=(
    _escape_release_bound.get('result')=='FAIL'
    and _escape_release_bound.get('release_outcome')=='BLOCKED'
    and 'QUERY_LITERAL_ESCAPE_CORRUPTION_PRESENT' in _bound_types
    and 'BLOCKING_FINDINGS_PRESENT' in _bound_types
)
results[key]={'types':sorted(_bound_types),'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_release_bound})

_escape_queue=build_work_queue(_escape_ledger)
_escape_queue_text=json.dumps(_escape_queue,ensure_ascii=False)
key='query_literal_escape:e2e_compact_queue_exact_identity'
ok=(
    'QUERY_LITERAL_ESCAPE_CORRUPTION' in _escape_queue_text
    and 'QUERY_LITERAL_ESCAPE_SANITY' in _escape_queue_text
    and _escape_bound[0]['id'] in _escape_queue_text
)
results[key]={'work_queue':_escape_queue.get('work_queue',{}),'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_queue})

# A model-authored generic PASS cannot close the verifier-owned machine blocker.
_escape_manual=copy.deepcopy(_escape_ledger)
_query_row=next(row for row in _escape_manual.get('rules',[]) if row.get('id')=='QUERY')
_query_row['status']='PASS'
_query_row['evidence']=[{'kind':'SEMANTIC','ref':'manual generic PASS declaration'}]
_escape_check=next(row for row in _query_row.get('checks',[]) if row.get('id')=='QUERY_LITERAL_ESCAPE_SANITY')
_escape_check['status']='PASS'
_escape_check['evidence']=[{'kind':'SEMANTIC','ref':'manual generic PASS declaration'}]
_escape_manual['blocking_findings']=[]
_escape_manual_release=release_evaluate(_escape_plan,_escape_manual,registry)
_manual_types={x.get('type') for x in _escape_manual_release.get('errors',[])}
key='query_literal_escape:e2e_generic_pass_cannot_close'
ok={'QUERY_LITERAL_ESCAPE_CORRUPTION_PRESENT','BLOCKING_FINDING_ROW_MISSING'}<=_manual_types
results[key]={'types':sorted(_manual_types),'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_manual_release})

# Deleting the ledger blocker cannot delete the verifier-derived work item.
_escape_deleted=copy.deepcopy(_escape_ledger); _escape_deleted['blocking_findings']=[]
_escape_deleted_release=release_evaluate(_escape_plan,_escape_deleted,registry)
_escape_deleted_queue=build_work_queue(_escape_deleted)
_deleted_queue_text=json.dumps(_escape_deleted_queue,ensure_ascii=False)
key='query_literal_escape:e2e_deleted_blocker_rederived'
ok=(
    any(x.get('type')=='BLOCKING_FINDING_ROW_MISSING' for x in _escape_deleted_release.get('errors',[]))
    and 'QUERY_LITERAL_ESCAPE_CORRUPTION' in _deleted_queue_text
    and 'QUERY_LITERAL_ESCAPE_SANITY' in _deleted_queue_text
)
results[key]={'release_errors':_escape_deleted_release.get('errors',[]),'work_queue':_escape_deleted_queue.get('work_queue',{}),'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

# Analyzer zero on Candidate A is not proof for Candidate B after a one-byte/source
# mutation. Receipt replay and current-candidate identity both fail closed.
_escape_mut_dir=Path(tempfile.mkdtemp(prefix='query-escape-mutation-'))
_escape_mut=_escape_mut_dir/'Module.bsl'
_escape_mut.write_bytes((fixtures/'query_literal_escape_spaces_good.bsl').read_bytes())
_escape_mut_plan=build_plan([_escape_mut],analysis_only=True)
_escape_mut_ledger=build_ledger(_escape_mut_plan,registry)
_escape_mut_receipt_path=_escape_mut_dir/'clean.json'
_escape_mut_receipt=create_receipt(
    'TOOLS/analyze_onec_bsl.py',[str(_escape_mut)],[str(_escape_mut)],
    ['STATIC:ONEC_BSL'],_escape_mut_receipt_path
)
_escape_mut_ledger['machine_reports']=[{
    'id':'MACHINE:QUERY_ESCAPE:CLEAN_A',
    'tool':'TOOLS/analyze_onec_bsl.py',
    'ref':str(_escape_mut_receipt_path),
    'receipt_ref':str(_escape_mut_receipt_path),
    'receipt_sha256':hashlib.sha256(_escape_mut_receipt_path.read_bytes()).hexdigest(),
    'result':_escape_mut_receipt['derived_result'],
    'supersedes':[],
}]
_escape_mut.write_text(
    (fixtures/'query_literal_escape_direct_tab_bad.bsl').read_text(encoding='utf-8'),
    encoding='utf-8'
)
_escape_mut_release=release_evaluate(_escape_mut_plan,_escape_mut_ledger,registry)
_mut_types={x.get('type') for x in _escape_mut_release.get('errors',[])}
key='query_literal_escape:e2e_candidate_byte_drift_invalidates_old_zero'
ok=(
    'QUERY_LITERAL_ESCAPE_CURRENT_ANALYZER_REQUIRED' in _mut_types
    and any(t in _mut_types for t in {'MACHINE_REPORT_RECEIPT_INVALID','CURRENT_CANDIDATE_BYTES_DRIFT'})
)
results[key]={'types':sorted(_mut_types),'pass':ok}
if not ok:errors.append({'case':key,'details':_escape_mut_release})

# Tampering with analyzer stdout to erase a finding invalidates the receipt instead
# of converting the old candidate into a clean result.
_escape_tampered=copy.deepcopy(_escape_ledger)
_escape_stdout=Path((_escape_receipt.get('output') or {}).get('stdout_path'))
_escape_stdout_original=_escape_stdout.read_bytes()
try:
    _escape_payload=json.loads(_escape_stdout_original.decode('utf-8-sig'))
    _escape_payload['findings']=[x for x in _escape_payload.get('findings',[]) if x.get('type')!='QUERY_LITERAL_ESCAPE_CORRUPTION']
    _escape_stdout.write_text(json.dumps(_escape_payload,ensure_ascii=False,indent=2),encoding='utf-8')
    _escape_tampered_release=release_evaluate(_escape_plan,_escape_tampered,registry)
    _tampered_types={x.get('type') for x in _escape_tampered_release.get('errors',[])}
    key='query_literal_escape:e2e_report_finding_deletion_detected'
    ok='MACHINE_REPORT_RECEIPT_INVALID' in _tampered_types and 'QUERY_LITERAL_ESCAPE_CURRENT_ANALYZER_REQUIRED' in _tampered_types
    results[key]={'types':sorted(_tampered_types),'pass':ok}
    if not ok:errors.append({'case':key,'details':_escape_tampered_release})
finally:
    _escape_stdout.write_bytes(_escape_stdout_original)

def _fr_record(key,ok,details=None):
    results[key]={'pass':bool(ok)}
    if details is not None:results[key]['details']=details
    if not ok:errors.append({'case':key,'details':details})

def _fr_types(path):
    report=analyze_onec(fixtures/path)
    return {x.get('type') for x in report.get('findings') or []},report

for _case,_path in (
    ('fr_prp02:direct_query_text_sink_blocks','query_surgery_direct_sink_bad.bsl'),
    ('fr_prp02:constructor_query_sink_blocks','query_surgery_constructor_sink_bad.bsl'),
    ('fr_prp02:query_object_alias_blocks','query_surgery_object_alias_bad.bsl'),
    ('fr_prp02:unresolved_query_receiver_blocks','query_surgery_unresolved_receiver_bad.bsl'),
    ('fr_prp02:factory_query_receiver_blocks','query_surgery_factory_receiver_bad.bsl'),
    ('fr_prp02:neutral_names_query_surgery_blocks','query_surgery_neutral_names_bad.bsl'),
):
    _types,_report=_fr_types(_path)
    _fr_record(_case,'HOMEGROWN_QUERY_STRUCTURE_PARSER' in _types,_report.get('findings'))

_nested_types,_nested_report=_fr_types('query_surgery_nested_boundary_bad.bsl')
_nested_findings=[x for x in _nested_report.get('findings') or [] if x.get('type')=='HOMEGROWN_QUERY_STRUCTURE_PARSER']
_nested_sink_kinds={
    sink.get('sink_kind')
    for finding in _nested_findings
    for sink in (finding.get('chain') or {}).get('sinks') or []
}
_nested_boundary_evidence=[
    item
    for finding in _nested_findings
    for item in finding.get('items') or []
    if item.get('stage')=='BOUNDARY_SEARCH'
]
_fr_record(
    'fr_prp02:nested_boundary_query_sinks_block',
    len(_nested_findings)==2
    and {'QUERY_TEXT_ASSIGNMENT','QUERY_CONSTRUCTOR_ARGUMENT'}<=_nested_sink_kinds
    and len(_nested_boundary_evidence)==2
    and all((finding.get('chain') or {}).get('boundary_searches') for finding in _nested_findings)
    and all(not (finding.get('chain') or {}).get('unresolved_receivers') for finding in _nested_findings),
    {'findings':_nested_findings,'sink_kinds':sorted(_nested_sink_kinds),'boundary_evidence':_nested_boundary_evidence},
)

for _case,_path in (
    ('fr_prp02:unrelated_temp_side_effect_does_not_suppress','query_execute_unrelated_temp_bad.bsl'),
    ('fr_prp02:manager_presence_does_not_suppress','query_execute_manager_presence_bad.bsl'),
    ('fr_prp02:temp_producer_without_consumer_blocks','query_execute_temp_producer_no_consumer_bad.bsl'),
    ('fr_prp02:different_temp_manager_blocks','query_execute_different_manager_bad.bsl'),
    ('fr_prp02:temp_table_identity_mutation_blocks','query_execute_table_identity_mutation_bad.bsl'),
    ('fr_prp02:latin_identifier_execute_blocks','query_execute_latin_identifier_bad.bsl'),
):
    _types,_report=_fr_types(_path)
    _fr_record(_case,'QUERY_EXECUTE_SIDE_EFFECT_TRACE' in _types,_report.get('findings'))

for _case,_path in (
    ('fr_prp02:same_manager_same_table_consumer_good','query_execute_same_manager_consumer_good.bsl'),
    ('fr_prp02:consumed_query_result_good','query_execute_result_consumed_good.bsl'),
):
    _types,_report=_fr_types(_path)
    _fr_record(_case,'QUERY_EXECUTE_SIDE_EFFECT_TRACE' not in _types,_report.get('findings'))

# Temporal identity controls: exact object/manager snapshots must survive aliases
# and must not survive reinitialization of the source variable.
for _case,_path,_line in (
    ('fr_prp02:standalone_execute_trailing_comment_blocks','query_execute_trailing_comment_bad.bsl',4),
    ('fr_prp02:query_rebind_resets_state','query_execute_query_rebind_bad.bsl',7),
    ('fr_prp02:manager_rebind_breaks_same_manager_chain','query_execute_manager_rebind_bad.bsl',6),
    ('fr_prp02:query_alias_snapshots_pre_rebind_identity','query_execute_alias_source_rebind_bad.bsl',8),
):
    _types,_report=_fr_types(_path)
    _hits=[x for x in _report.get('findings') or [] if x.get('type')=='QUERY_EXECUTE_SIDE_EFFECT_TRACE']
    _fr_record(
        _case,
        len(_hits)==1 and _hits[0].get('line')==_line,
        {'expected_line':_line,'findings':_hits},
    )

for _case,_path in (
    ('fr_prp02:query_alias_old_identity_chain_good','query_execute_alias_old_identity_good.bsl'),
    ('fr_prp02:manager_alias_same_identity_good','query_execute_manager_alias_good.bsl'),
    ('fr_prp02:consumed_execute_trailing_comment_good','query_execute_consumed_comment_good.bsl'),
    ('fr_prp02:repeated_producer_identity_good','query_execute_repeated_producer_good.bsl'),
):
    _types,_report=_fr_types(_path)
    _fr_record(_case,'QUERY_EXECUTE_SIDE_EFFECT_TRACE' not in _types,_report.get('findings'))


# Statement/control-flow controls: classify Execute per statement and require a
# guaranteed compatible future path before suppressing an unread producer.
for _case,_path,_expected in (
    ('fr_prp02:same_line_execute_then_statement_blocks','query_execute_same_line_after_bad.bsl',[(4,'query:запрос:1')]),
    ('fr_prp02:same_line_statement_then_execute_blocks','query_execute_same_line_before_bad.bsl',[(4,'query:запрос:1')]),
    ('fr_prp02:same_line_two_standalone_execute_blocks_twice','query_execute_same_line_twice_bad.bsl',[(4,'query:запрос:1'),(4,'query:запрос:1')]),
    ('fr_prp02:same_line_text_then_execute_blocks','query_execute_text_same_line_bad.bsl',[(3,'query:запрос:1')]),
    ('fr_prp02:if_else_consumer_does_not_prove_chain','query_execute_if_else_consumer_bad.bsl',[(7,'query:продюсер:1')]),
    ('fr_prp02:conditional_consumer_does_not_prove_chain','query_execute_conditional_consumer_bad.bsl',[(6,'query:продюсер:1')]),
    ('fr_prp02:sibling_branch_state_does_not_leak','query_execute_sibling_state_bad.bsl',[(8,'query:запрос:1')]),
    ('fr_prp02:try_except_consumer_does_not_prove_chain','query_execute_try_except_consumer_bad.bsl',[(7,'query:продюсер:1')]),
    ('fr_prp02:branch_local_query_rebind_does_not_leak','query_execute_branch_rebind_sibling_bad.bsl',[(7,'query:запрос:1')]),
    ('fr_prp02:conditional_manager_rebind_fails_closed','query_execute_conditional_manager_rebind_bad.bsl',[(6,'query:продюсер:1')]),
):
    _types,_report=_fr_types(_path)
    _hits=[x for x in _report.get('findings') or [] if x.get('type')=='QUERY_EXECUTE_SIDE_EFFECT_TRACE']
    _actual=[(x.get('line'),x.get('query_identity')) for x in _hits]
    _fr_record(
        _case,
        _actual==_expected,
        {'expected':_expected,'actual':_actual,'findings':_hits},
    )

for _case,_path in (
    ('fr_prp02:consumed_execute_then_statement_same_line_good','query_execute_consumed_same_line_good.bsl'),
    ('fr_prp02:return_execute_chain_good','query_execute_return_chain_good.bsl'),
    ('fr_prp02:query_string_semicolon_not_split_good','query_execute_string_semicolon_good.bsl'),
    ('fr_prp02:same_branch_producer_consumer_good','query_execute_same_branch_good.bsl'),
):
    _types,_report=_fr_types(_path)
    _fr_record(_case,'QUERY_EXECUTE_SIDE_EFFECT_TRACE' not in _types,_report.get('findings'))


# Classification coverage / abrupt-flow completeness. Every raw code Execute
# token must bind to exactly one classification event; unsupported forms fail
# closed with the canonical query-trace finding rather than disappearing.
def _query_trace_direct(path):
    _text=(fixtures/path).read_text(encoding='utf-8-sig')
    _blocks=onec_blocks(_text)
    if len(_blocks)!=1:
        return {'findings':[],'coverage':{'raw_token_count':-1,'classified_event_count':-2,'unclassified_count':-3,'source_offset_unique':False,'event_offset_unique':False,'binding_unique':False,'tokens':[],'events':[]}}
    return query_execute_side_effect_analysis(_blocks[0])

def _coverage_ok(_analysis,_raw,_unclassified):
    _coverage=_analysis.get('coverage') or {}
    return (
        _coverage.get('raw_token_count')==_raw
        and _coverage.get('classified_event_count')==_raw
        and _coverage.get('unclassified_count')==_unclassified
        and _coverage.get('source_offset_unique') is True
        and _coverage.get('event_offset_unique') is True
        and _coverage.get('binding_unique') is True
        and len({x.get('token_offset') for x in _coverage.get('events') or []})==_raw
    )

for _case,_path,_raw,_unclassified,_expected in (
    ('fr_prp02:return_barrier_blocks','query_execute_return_barrier_bad.bsl',2,0,[(6,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:conditional_return_blocks','query_execute_conditional_return_bad.bsl',2,0,[(6,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:raise_barrier_blocks','query_execute_raise_barrier_bad.bsl',2,0,[(6,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:continue_barrier_blocks','query_execute_continue_barrier_bad.bsl',2,0,[(7,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:break_barrier_blocks','query_execute_break_barrier_bad.bsl',2,0,[(7,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:goto_barrier_blocks','query_execute_goto_barrier_bad.bsl',2,0,[(6,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:compile_sibling_does_not_prove_chain','query_execute_compile_sibling_bad.bsl',2,0,[(7,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:multiline_standalone_blocks','query_execute_multiline_standalone_bad.bsl',1,0,[(4,'query:запрос:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:multiline_batch_standalone_blocks','query_execute_multiline_batch_bad.bsl',1,0,[(4,'query:запрос:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:multiline_if_sibling_blocks','query_execute_multiline_if_sibling_bad.bsl',2,0,[(8,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:multiline_loop_conditional_consumer_blocks','query_execute_multiline_loop_conditional_bad.bsl',2,0,[(8,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:unsupported_execute_form_fails_closed','query_execute_unsupported_receiver_bad.bsl',1,1,[(4,None,'UNCLASSIFIED_OR_AMBIGUOUS_EXECUTE')]),
):
    _analysis=_query_trace_direct(_path)
    _hits=_analysis.get('findings') or []
    _actual=[(x.get('line'),x.get('query_identity'),x.get('trace_status')) for x in _hits]
    _fr_record(
        _case,
        _coverage_ok(_analysis,_raw,_unclassified) and _actual==_expected,
        {'coverage':_analysis.get('coverage'),'expected':_expected,'actual':_actual,'findings':_hits},
    )

for _case,_path,_raw in (
    ('fr_prp02:multiline_assignment_consumed_good','query_execute_multiline_assignment_good.bsl',1),
    ('fr_prp02:multiline_return_chain_good','query_execute_multiline_return_good.bsl',1),
    ('fr_prp02:multiline_same_branch_chain_good','query_execute_multiline_same_branch_good.bsl',2),
    ('fr_prp02:same_loop_chain_without_barrier_good','query_execute_same_loop_good.bsl',2),
    ('fr_prp02:compile_same_branch_chain_good','query_execute_compile_same_branch_good.bsl',2),
    ('fr_prp02:inventory_ignores_string_and_comment_execute_text','query_execute_inventory_ignored_text_good.bsl',0),
):
    _analysis=_query_trace_direct(_path)
    _fr_record(
        _case,
        _coverage_ok(_analysis,_raw,0) and not (_analysis.get('findings') or []),
        {'coverage':_analysis.get('coverage'),'findings':_analysis.get('findings')},
    )

# Classification coverage is a production invariant for every query-execute
# fixture, not only the dedicated coverage samples.
_all_query_execute_paths=sorted({
    name for section in ('machine_bad_cases','machine_good_cases')
    for name,expectations in (manifest.get(section) or {}).items()
    if name.startswith('query_execute_') and 'QUERY_EXECUTE_SIDE_EFFECT_TRACE' in expectations
})
for _path in _all_query_execute_paths:
    _analysis=_query_trace_direct(_path)
    _coverage=_analysis.get('coverage') or {}
    _events=_coverage.get('events') or []
    _raw=_coverage.get('raw_token_count')
    _terminal={'CLASSIFIED_CONSUMED','CLASSIFIED_UNREAD','AMBIGUOUS_OR_UNPARSED'}
    _ok=(
        isinstance(_raw,int)
        and _coverage.get('classified_event_count')==_raw
        and _coverage.get('source_offset_unique') is True
        and _coverage.get('event_offset_unique') is True
        and _coverage.get('binding_unique') is True
        and _coverage.get('reconciliation_issue_count')==0
        and len(_events)==_raw
        and len({x.get('token_id') for x in _events})==_raw
        and all(x.get('classification_status') in _terminal for x in _events)
    )
    _fr_record('fr_prp02:coverage_all:'+_path,_ok,{'coverage':_coverage})

# Header Execute tokens must be classified exactly once and positively consumed.
for _case,_path in (
    ('fr_prp02:if_header_execute_consumed','query_execute_if_header_good.bsl'),
    ('fr_prp02:elseif_header_execute_consumed','query_execute_elseif_header_good.bsl'),
    ('fr_prp02:while_header_execute_consumed','query_execute_while_header_good.bsl'),
    ('fr_prp02:foreach_header_execute_consumed','query_execute_foreach_header_good.bsl'),
):
    _analysis=_query_trace_direct(_path)
    _events=(_analysis.get('coverage') or {}).get('events') or []
    _fr_record(
        _case,
        _coverage_ok(_analysis,1,0)
        and len(_events)==1
        and _events[0].get('classification_status')=='CLASSIFIED_CONSUMED'
        and not (_analysis.get('findings') or []),
        {'coverage':_analysis.get('coverage'),'findings':_analysis.get('findings')},
    )

# Public analyze() must expose the three audited false-negative shapes at exact
# physical positions; direct-analysis diagnostics are not accepted as a substitute.
for _case,_path,_expected in (
    ('fr_prp02:public_inline_if_unread','query_execute_inline_if_bad.bsl',[(4,'query:запрос:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:public_inline_while_unread','query_execute_inline_while_bad.bsl',[(4,'query:запрос:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
    ('fr_prp02:public_inline_conditional_return_blocks','query_execute_inline_conditional_return_bad.bsl',[(6,'query:продюсер:1','UNRESOLVED_NO_BOUND_CONSUMER')]),
):
    _report=analyze_onec(fixtures/_path)
    _hits=[x for x in _report.get('findings') or [] if x.get('type')=='QUERY_EXECUTE_SIDE_EFFECT_TRACE']
    _actual=[(x.get('line'),x.get('query_identity'),x.get('trace_status')) for x in _hits]
    _fr_record(_case,_actual==_expected,{'expected':_expected,'actual':_actual,'findings':_hits})

# Inline and multiline forms of the same supported control structure must have
# the same semantic findings; source positions are checked separately.
def _trace_semantics(path):
    report=analyze_onec(fixtures/path)
    hits=[x for x in report.get('findings') or [] if x.get('type')=='QUERY_EXECUTE_SIDE_EFFECT_TRACE']
    semantic=[(
        x.get('query_identity'),x.get('classification_status'),x.get('trace_status'),
        tuple(x.get('produced_temp_tables') or []),x.get('manager_identity')
    ) for x in hits]
    positions=[x.get('line') for x in hits]
    return semantic,positions,hits
for _case,_inline,_multiline,_inline_lines,_multiline_lines in (
    ('fr_prp02:inline_multiline_if_semantic_equivalence','query_execute_inline_if_bad.bsl','query_execute_multiline_if_body_bad.bsl',[4],[5]),
    ('fr_prp02:inline_multiline_while_semantic_equivalence','query_execute_inline_while_bad.bsl','query_execute_multiline_while_body_bad.bsl',[4],[5]),
):
    _is,_ip,_ih=_trace_semantics(_inline)
    _ms,_mp,_mh=_trace_semantics(_multiline)
    _fr_record(_case,_is==_ms and _ip==_inline_lines and _mp==_multiline_lines,{
        'inline_semantic':_is,'multiline_semantic':_ms,
        'inline_positions':_ip,'multiline_positions':_mp,
        'inline_findings':_ih,'multiline_findings':_mh,
    })

# Conditional-return inline form is semantically equivalent to the existing
# multiline barrier regression even though its temporary-table spelling differs.
_inline_report=analyze_onec(fixtures/'query_execute_inline_conditional_return_bad.bsl')
_multi_report=analyze_onec(fixtures/'query_execute_conditional_return_bad.bsl')
_inline_hits=[x for x in _inline_report.get('findings') or [] if x.get('type')=='QUERY_EXECUTE_SIDE_EFFECT_TRACE']
_multi_hits=[x for x in _multi_report.get('findings') or [] if x.get('type')=='QUERY_EXECUTE_SIDE_EFFECT_TRACE']
_inline_shape=[(x.get('classification_status'),x.get('trace_status'),bool(x.get('manager_identity')),bool(x.get('produced_temp_tables'))) for x in _inline_hits]
_multi_shape=[(x.get('classification_status'),x.get('trace_status'),bool(x.get('manager_identity')),bool(x.get('produced_temp_tables'))) for x in _multi_hits]
_fr_record('fr_prp02:inline_multiline_conditional_return_semantic_equivalence',
    _inline_shape==_multi_shape and [x.get('line') for x in _inline_hits]==[6] and [x.get('line') for x in _multi_hits]==[6],
    {'inline_shape':_inline_shape,'multiline_shape':_multi_shape,'inline':_inline_hits,'multiline':_multi_hits})

# Keep the original FR-PRP-02 threat-matrix regression identities executable.
# These are compatibility aliases over the strengthened remediation behavior, not
# duplicate proof owners.
_short_types,_short_report=_fr_types('query_surgery_short_bypass_bad.bsl')
_fr_record('fr_prp02:short_query_surgery_detected',
    'HOMEGROWN_QUERY_STRUCTURE_PARSER' in _short_types,_short_report.get('findings'))
_short_plan=build_plan([fixtures/'query_surgery_short_bypass_bad.bsl'],analysis_only=True,risk_override='R2_STATEFUL_RUNTIME')
_short_route=next((x for x in _short_plan.get('rules',[]) if x.get('id')=='QUERY'),{})
_fr_record('fr_prp02:query_owner_activated',
    bool(_short_route.get('active')) and bool(_short_route.get('detected_by')),_short_route)
_short_ledger=build_ledger(_short_plan,registry)
_short_query=next((x for x in _short_ledger.get('rules',[]) if x.get('id')=='QUERY'),{})
_short_check=next((x for x in _short_query.get('checks',[]) if x.get('id')=='HOMEGROWN_QUERY_GRAMMAR_PARSER'),{})
_fr_record('fr_prp02:ledger_contains_query_surgery_obligation',
    bool(_short_check) and _short_check.get('status')=='EVIDENCE_REQUIRED',_short_check)
_short_release=release_evaluate(_short_plan,_short_ledger,registry)
_fr_record('fr_prp02:release_verifier_blocks_unresolved_query_surgery',
    _short_release.get('result')=='FAIL' and _short_release.get('release_outcome')=='BLOCKED',
    _short_release.get('errors'))
_short_queue=build_work_queue(_short_ledger)
_fr_record('fr_prp02:compact_queue_preserves_query_surgery',
    'HOMEGROWN_QUERY_GRAMMAR_PARSER' in json.dumps(_short_queue,ensure_ascii=False),_short_queue)

def run_field_flow_case(fn):return analyze_field_flow(fixtures/fn)
for fn,expected in manifest.get('field_flow_bad_cases',{}).items():
    r=run_field_flow_case(fn); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    key='field_flow:'+fn; results[key]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})
for fn,forbidden in manifest.get('field_flow_good_cases',{}).items():
    r=run_field_flow_case(fn); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    key='field_flow:'+fn; results[key]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':key,'unexpected':bad})

# New-routine reachability regressions: implementation must be connected to a live/pre-existing scenario.
for case in manifest.get('reachability_cases',[]):
    baseline=fixtures/case['baseline']
    bad=analyze_reachability([fixtures/case['bad_candidate']], baseline=baseline)
    bad_types={x['type'] for x in bad.get('findings',[])}
    missing=[x for x in case.get('bad_expected',[]) if x not in bad_types]
    key='reachability:'+case['id']+':bad'; results[key]={'types':sorted(bad_types),'expected':case.get('bad_expected',[]),'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})
    good=analyze_reachability([fixtures/case['good_candidate']], baseline=baseline)
    good_types={x['type'] for x in good.get('findings',[])}
    unexpected=[x for x in case.get('good_forbidden',[]) if x in good_types]
    key='reachability:'+case['id']+':good'; results[key]={'types':sorted(good_types),'forbidden':case.get('good_forbidden',[]),'pass':not unexpected}
    if unexpected:errors.append({'case':key,'unexpected':unexpected})

# Whole-change-set analysis emits REVIEW candidates only. Positive and negative
# fixtures protect both detection and false-positive control.
for fn,expected in manifest.get('changeset_architecture_bad_cases',{}).items():
    r=analyze_changeset_architecture([fixtures/fn]); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    key='changeset_architecture:'+fn; results[key]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})
for fn,forbidden in manifest.get('changeset_architecture_good_cases',{}).items():
    r=analyze_changeset_architecture([fixtures/fn]); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    key='changeset_architecture:'+fn; results[key]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':key,'unexpected':bad})

_local_pipeline=analyze_changeset_architecture([fixtures/'owner_reuse_local_multistage_good'])
_fr_record('fr_prp02:local_multistage_without_owner_boundary_is_good',
    'INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW' not in {x.get('type') for x in _local_pipeline.get('findings') or []},
    _local_pipeline.get('findings'))
_historical_pipeline=analyze_changeset_architecture([fixtures/'owner_reuse_internal_pipeline_bad'])
_fr_record('fr_prp02:historical_owner_pipeline_remains_finding',
    'INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW' in {x.get('type') for x in _historical_pipeline.get('findings') or []},
    _historical_pipeline.get('findings'))
_neutral_owner_pipeline=analyze_changeset_architecture([fixtures/'owner_reuse_neutral_owner_pipeline_bad'])
_fr_record('fr_prp02:neutral_owner_name_does_not_hide_dependency',
    'INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW' in {x.get('type') for x in _neutral_owner_pipeline.get('findings') or []},
    _neutral_owner_pipeline.get('findings'))
_public_pipeline=analyze_changeset_architecture([fixtures/'owner_reuse_public_api_good'])
_fr_record('fr_prp02:public_api_reuse_control_passes',
    'INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW' not in {x.get('type') for x in _public_pipeline.get('findings') or []},
    _public_pipeline.get('findings'))
_fr_record('fr_prp02:internal_pipeline_reconstruction_requires_review',
    results.get('fr_prp02:historical_owner_pipeline_remains_finding',{}).get('pass') is True,
    results.get('fr_prp02:historical_owner_pipeline_remains_finding'))
for case in manifest.get('changeset_architecture_scope_cases',[]):
    r=analyze_changeset_architecture([fixtures/case['input']],max_routines=case['max_routines']); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in case['expected'] if x not in types]
    key='changeset_architecture_scope:'+case['input']; ok=not missing and r.get('analysis_coverage')=='SCOPE_REVIEW_REQUIRED'
    results[key]={'types':sorted(types),'coverage':r.get('analysis_coverage'),'expected':case['expected'],'pass':ok}
    if not ok:errors.append({'case':key,'missing':missing,'coverage':r.get('analysis_coverage')})

# Artifact scope discovery regression: a misleading top-level label cannot hide mixed content.
_scope=build_plan([fixtures/'artifact_scope_mixed'],analysis_only=True)
_inv=_scope.get('artifact_inventory',{})
key='source:artifact_scope_inventory'; ok=(_inv.get('files')==2 and _inv.get('kinds',{}).get('onec',0)>=2 and 'XDTOPackages' in _inv.get('top_roots',{}) and 'Documents' in _inv.get('top_roots',{}))
results[key]={'inventory':_inv,'pass':ok}
if not ok:errors.append({'case':key,'details':_inv})

def run_signature_case(fn):return check_signatures([], [fixtures/'TestApi_Module.bsl'], [fixtures/fn])
for fn,expected in manifest.get('signature_bad_cases',{}).items():
    r=run_signature_case(fn); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    results[fn]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':fn,'missing':missing})
for fn,forbidden in manifest.get('signature_good_cases',{}).items():
    r=run_signature_case(fn); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    results[fn]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':fn,'unexpected':bad})

def run_onec_xml_case(fn):return analyze_onec_xml(fixtures/fn)
for fn,expected in manifest.get('onec_xml_bad_cases',{}).items():
    r=run_onec_xml_case(fn); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    key='onec_xml:'+fn; results[key]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})
for fn,forbidden in manifest.get('onec_xml_good_cases',{}).items():
    r=run_onec_xml_case(fn); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    key='onec_xml:'+fn; results[key]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':key,'unexpected':bad})

for fn,expected in manifest.get('onec_xml_summary_cases',{}).items():
    r=run_onec_xml_case(fn); artifacts=[x for x in r.get('artifacts',[]) if x.get('kind')==expected.get('kind')]
    details=artifacts[0].get('details',{}) if artifacts else {}
    actual_attrs=details.get('constants_set_attributes',[])
    actual_paths=[x.get('path') for x in details.get('constants_set_bindings',[])]
    ok=(actual_attrs==expected.get('constants_set_attributes',[]) and actual_paths==expected.get('constants_set_binding_paths',[]))
    key='onec_xml_summary:'+fn; results[key]={'constants_set_attributes':actual_attrs,'constants_set_binding_paths':actual_paths,'pass':ok}
    if not ok:errors.append({'case':key,'expected':expected,'actual':results[key]})

def run_cleverence_case(fn,baseline=None):return analyze_cleverence(fixtures/fn,fixtures/baseline if baseline else None)
for fn,expected in manifest.get('cleverence_bad_cases',{}).items():
    r=run_cleverence_case(fn); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    results[fn]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':fn,'missing':missing})
for fn,forbidden in manifest.get('cleverence_good_cases',{}).items():
    r=run_cleverence_case(fn); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    results[fn]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':fn,'unexpected':bad})
for case in manifest.get('cleverence_diff_cases',[]):
    r=run_cleverence_case(case['candidate'],case['baseline']); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in case['expected'] if x not in types]
    key=f"{case['candidate']}<-{case['baseline']}"; results[key]={'types':sorted(types),'expected':case['expected'],'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})

def run_cleverence_config_case(fn,baseline=None):return analyze_cleverence_configuration(fixtures/fn,fixtures/baseline if baseline else None)
for fn,expected in manifest.get('cleverence_config_bad_cases',{}).items():
    r=run_cleverence_config_case(fn); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in expected if x not in types]
    key='cleverence_config:'+fn; results[key]={'types':sorted(types),'expected':expected,'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})
for fn,forbidden in manifest.get('cleverence_config_good_cases',{}).items():
    r=run_cleverence_config_case(fn); types={x['type'] for x in r.get('findings',[])}; bad=[x for x in forbidden if x in types]
    key='cleverence_config:'+fn; results[key]={'types':sorted(types),'forbidden':forbidden,'pass':not bad}
    if bad:errors.append({'case':key,'unexpected':bad})
for case in manifest.get('cleverence_config_diff_cases',[]):
    r=run_cleverence_config_case(case['candidate'],case['baseline']); types={x['type'] for x in r.get('findings',[])}; missing=[x for x in case['expected'] if x not in types]
    key=f"cleverence_config:{case['candidate']}<-{case['baseline']}"; results[key]={'types':sorted(types),'expected':case['expected'],'pass':not missing}
    if missing:errors.append({'case':key,'missing':missing})

def _legacy_delivery_commands(plan):
    rows=plan.get('rules') or []; surface=(plan.get('routing') or {}).get('surface'); commands=[]
    if surface in {'ONEC_ONLY','CROSS_SYSTEM'}:commands.append('Run TOOLS/analyze_onec_bsl.py for each changed BSL final byte-set')
    structural_ids={'ONEC_XML_STRUCTURE','FORM_XML_STRUCTURE','METADATA_XML_STRUCTURE','CFE_EXTENSION_STRUCTURE','XDTO_STRUCTURE'}
    if any(r.get('id') in structural_ids and r.get('active') and r.get('detected_by') for r in rows):commands.append('Run TOOLS/analyze_onec_xml.py on the smallest supplied directory/ZIP that preserves companion XML context')
    if any(r.get('id')=='FORM_DATA_BINDING' and r.get('active') and r.get('detected_by') for r in rows):commands.append('Resolve each changed form DataPath against the actual form runtime data source/composition; for ConstantsSet.Member prove concrete set membership instead of inferring it from Constant metadata')
    if any(r.get('id')=='CALL_CONTRACT' and r.get('detected_by') for r in rows):commands.append('Resolve qualified-call boundaries; run TOOLS/check_bsl_call_signatures.py for cross-module calls with exact declarations')
    if any(r.get('id')=='IMPLEMENTATION_REACHABILITY' and r.get('detected_by') for r in rows):commands.append('Run TOOLS/analyze_onec_reachability.py on exact candidate + baseline; prove intended entrypoint → caller(s) → new/changed routine. Export alone is not invocation evidence')
    if any(r.get('id')=='POST_WRITE_STANDARD_OVERWRITE' and r.get('active') and r.get('detected_by') for r in rows):commands.append('Run TOOLS/analyze_onec_field_flow.py on exact changed BSL and resolve same-field reachable writers/unresolved lifecycle calls')
    if any(r.get('id')=='CROSS_OBJECT_DUPLICATION_REVIEW' and r.get('active') for r in rows):commands.append('Run TOOLS/analyze_changeset_architecture.py on the complete changed BSL set; classify REVIEW candidates semantically and perform whole-change-set owner mapping even when candidate count is zero')
    if any(r.get('id')=='CLEVERENCE_MSLX' and r.get('active') and r.get('detected_by') for r in rows):commands.append('Run TOOLS/analyze_cleverence_mslx.py with accepted baseline for Operation/Action graph delta proof')
    if any(r.get('id')=='CLEVERENCE_CONFIGURATION' and r.get('active') and r.get('detected_by') for r in rows):commands.append('Run TOOLS/analyze_cleverence_configuration.py on changed Metadata/DocumentTypes with accepted baseline when available; prove barcode precedence and exact field contracts semantically/runtime')
    return commands


# Backward-compatible routing regressions.
for case in manifest.get('review_plan_cases',[]):
    r=build_plan([fixtures/item for item in case['inputs']],analysis_only=case.get('analysis_only',False),surface_override=case.get('surface_override'),risk_override=case.get('risk_override'),project_context=fixtures/case['project_context'] if case.get('project_context') else None)
    actual=r.get('routing',{}); ok=actual.get('surface')==case['surface'] and actual.get('risk')==case['risk']
    if case.get('mode'):ok=ok and actual.get('mode')==case['mode']
    key='review_plan:'+case.get('id','+'.join(case['inputs']))
    expected_profiles=set(case.get('profiles',[])); forbidden_profiles=set(case.get('forbidden_profiles',[])); actual_profiles={x['name'] for x in r.get('active_profiles',[])}
    missing_profiles=sorted(expected_profiles-actual_profiles); unexpected_profiles=sorted(forbidden_profiles&actual_profiles)
    statuses={x['name']:x['status'] for x in r.get('active_profiles',[])}; wrong={name:{'expected':status,'actual':statuses.get(name)} for name,status in case.get('profile_statuses',{}).items() if statuses.get(name)!=status}
    expected_tools=_legacy_delivery_commands(r); tool_drift=(r.get('deterministic_tools') or [])!=expected_tools
    ok=ok and not missing_profiles and not unexpected_profiles and not wrong and not tool_drift
    results[key]={'routing':actual,'missing_profiles':missing_profiles,'unexpected_profiles':unexpected_profiles,'wrong_statuses':wrong,'expected_tools':expected_tools,'actual_tools':r.get('deterministic_tools') or [],'tool_drift':tool_drift,'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

# New activation regressions: rule existence is useless unless its trigger actually routes it.
for case in activation_manifest['cases']:
    r=build_plan([fixtures/item for item in case['inputs']],project_context=fixtures/case['project_context'] if case.get('project_context') else None)
    routes={x['id']:x for x in r['rules']}
    missing=[]
    for rid in case.get('triggered_rules',[]):
        row=routes.get(rid)
        triggered=bool(row and row.get('active') and (row.get('detected_by') or row.get('reason','').startswith('derived')))
        if not triggered:missing.append(rid)
    unexpected=[]
    for rid in case.get('forbidden_rules',[]):
        row=routes.get(rid)
        triggered=bool(row and row.get('active') and (row.get('detected_by') or row.get('reason','').startswith('derived')))
        if triggered:unexpected.append(rid)
    expected_tools=_legacy_delivery_commands(r); tool_drift=(r.get('deterministic_tools') or [])!=expected_tools
    ok=not missing and not unexpected and not tool_drift and r['routing']['surface']==case['surface'] and (not case.get('risk') or r['routing']['risk']==case['risk'])
    key='activation:'+case['id']; results[key]={'missing':missing,'unexpected':unexpected,'routing':r['routing'],'expected_tools':expected_tools,'actual_tools':r.get('deterministic_tools') or [],'tool_drift':tool_drift,'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

# Requirements activation: pre-code rules must route by risk/surface/text without generic questionnaires.
for case in requirements_activation_manifest['cases']:
    c=build_contract([fixtures/item for item in case['inputs']],task_text=case.get('task_text',''),surface_override=case.get('surface_override'),risk_override=case.get('risk_override'),purpose_override=case.get('purpose_override'))
    routes={x['id']:x for x in c['rule_routes']}
    missing=[]
    for rid in case.get('triggered_rules',[]):
        row=routes.get(rid)
        if not row or not row.get('active'):missing.append(rid)
    unexpected=[]
    for rid in case.get('forbidden_rules',[]):
        row=routes.get(rid)
        if row and row.get('active'):unexpected.append(rid)
    ok=not missing and not unexpected and c['routing']['surface']==case['surface'] and c['routing']['risk']==case['risk']
    key='requirements_activation:'+case['id']; results[key]={'missing':missing,'unexpected':unexpected,'routing':c['routing'],'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

# Requirements gate mechanics.
def prove_requirements(c):
    c=copy.deepcopy(c)
    artifact=c.get('routing',{}).get('purpose')=='REQUIREMENTS_ARTIFACT'
    claims=[]
    for fid,f in c['functional_contract'].items():
        f['status']='KNOWN'; f['value']=([{'id':'AC:SYNTHETIC','expected':'synthetic accepted result'}] if fid=='acceptance_cases' else f['title']+' — synthetic regression value'); f['evidence']=[{'kind':'SOURCE_REQUIRED','ref':'synthetic user/source evidence'}]
        if artifact:
            cid='CLAIM:'+fid; f['claim_ids']=[cid]
            statement=f['value'] if isinstance(f['value'],str) else json.dumps(f['value'],ensure_ascii=False,sort_keys=True)
            claims.append({'id':cid,'statement':statement,'provenance':'USER_CONFIRMED','disposition':'CONFIRMED_REQUIREMENT','blocking':bool(f['blocking']),'evidence':[{'kind':'SOURCE_REQUIRED','ref':'synthetic user/source claim evidence'}],'depends_on':[],'reason':''})
    if artifact:c['claims']=claims
    if artifact and c.get('routing',{}).get('risk')!='R0_LOCAL':
        c['requirements_adversarial_cases']=[{'id':'REQ-ADV:SYNTHETIC','counterexample':'two equally eligible matches lead to different material results','expected_behavior':'ambiguity is explicitly resolved or blocks the artifact','status':'PASS','evidence':[{'kind':'SEMANTIC','ref':'synthetic requirements adversarial evidence'}]}]
    for row in c['rules']:
        row['status']='PASS'; row['evidence']=[{'kind':kind,'ref':f'synthetic {kind} requirements evidence'} for kind in row['required_evidence_modes']]
        for ch in row['checks']:
            ch['status']='PASS'; ch['evidence']=[{'kind':'SEMANTIC','ref':'synthetic requirements check evidence'}]
    return c

# Requirements-artifact integrity: analysis/specification is not allowed to bypass the gate.
req_artifact_unresolved=build_contract([],task_text='Проанализируй требования и подготовь ЛТ для изменения заполнения документа.',surface_override='ONEC_ONLY',risk_override='R1_CONTRACT')
key='requirements_gate:requirements_artifact_purpose_inferred'; ok=req_artifact_unresolved['routing']['purpose']=='REQUIREMENTS_ARTIFACT'; results[key]={'routing':req_artifact_unresolved['routing'],'pass':ok}
if not ok:errors.append({'case':key,'details':req_artifact_unresolved['routing']})
req_artifact_downgrade=build_contract([],task_text='Проанализируй требования и подготовь ЛТ для изменения заполнения документа.',surface_override='ONEC_ONLY',risk_override='R1_CONTRACT',purpose_override='IMPLEMENTATION_INPUT')
key='requirements_gate:requirements_artifact_purpose_downgrade_refused'; ok=req_artifact_downgrade['routing']['purpose']=='REQUIREMENTS_ARTIFACT'; results[key]={'routing':req_artifact_downgrade['routing'],'pass':ok}
if not ok:errors.append({'case':key,'details':req_artifact_downgrade['routing']})
req_artifact_proved=prove_requirements(req_artifact_unresolved)
rg=requirements_evaluate(req_artifact_proved,registry); key='requirements_gate:requirements_artifact_fully_evidenced_ready'; ok=(rg['result']=='PASS' and rg['requirements_outcome']=='REQUIREMENTS_READY'); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_artifact_no_claims=copy.deepcopy(req_artifact_proved); req_artifact_no_claims['claims']=[]
rg=requirements_evaluate(req_artifact_no_claims,registry); key='requirements_gate:requirements_artifact_claims_missing_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIREMENTS_CLAIMS_MISSING' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_proposal_laundered=copy.deepcopy(req_artifact_proved); first_claim=req_proposal_laundered['claims'][0]; first_claim['provenance']='PROPOSED_SOLUTION'; first_claim['disposition']='CONFIRMED_REQUIREMENT'
rg=requirements_evaluate(req_proposal_laundered,registry); key='requirements_gate:proposed_solution_as_confirmed_requirement_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='PROPOSED_SOLUTION_AS_CONFIRMED_REQUIREMENT' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_material_open=copy.deepcopy(req_artifact_proved); req_material_open['open_questions']=[{'question':'Can the same fact be used in two targets?','blocking':False,'status':'OPEN','materiality':'QUANTITY','why_it_changes_design':'Changes duplicate-use semantics.'}]
rg=requirements_evaluate(req_material_open,registry); key='requirements_gate:material_open_question_nonblocking_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='MATERIAL_OPEN_QUESTION_MARKED_NONBLOCKING' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_no_adv=copy.deepcopy(req_artifact_proved); req_no_adv['requirements_adversarial_cases']=[]
rg=requirements_evaluate(req_no_adv,registry); key='requirements_gate:requirements_adversarial_missing_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIREMENTS_ADVERSARIAL_CASES_MISSING' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_correction=copy.deepcopy(req_artifact_proved)
req_correction['claims'].append({'id':'CLAIM:old-source-rule','statement':'Old source rule','provenance':'USER_CONFIRMED','disposition':'SUPERSEDED','blocking':True,'evidence':[{'kind':'SOURCE_REQUIRED','ref':'historical user decision'}],'depends_on':[],'reason':'Corrected by a newer decision.'})
req_correction['claims'].append({'id':'CLAIM:dependent-mapping','statement':'Mapping derived from old source rule','provenance':'DERIVED_WITH_EVIDENCE','disposition':'DERIVED_REQUIREMENT','blocking':True,'evidence':[{'kind':'SEMANTIC','ref':'synthetic derivation evidence'}],'depends_on':['CLAIM:old-source-rule'],'reason':''})
req_correction['revision_events']=[{'id':'REV:source-rule','changed_claim_ids':['CLAIM:old-source-rule'],'invalidated_claim_ids':[],'revalidated_claim_ids':[],'reason':'Newer evidence corrected the source rule.','evidence':[]}]
rg=requirements_evaluate(req_correction,registry); key='requirements_gate:correction_dependency_requires_revalidation'; ok=(rg['result']=='FAIL' and any(e['type']=='DEPENDENT_CLAIM_NOT_REVALIDATED' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_correction_fixed=copy.deepcopy(req_correction); req_correction_fixed['revision_events'][0]['revalidated_claim_ids']=['CLAIM:dependent-mapping']; req_correction_fixed['revision_events'][0]['evidence']=[{'kind':'SEMANTIC','ref':'synthetic revalidation evidence'}]
rg=requirements_evaluate(req_correction_fixed,registry); key='requirements_gate:correction_dependency_revalidated_ready'; ok=(rg['result']=='PASS' and rg['requirements_outcome']=='REQUIREMENTS_READY'); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})

req_unresolved=build_contract([fixtures/'requirements_contract.txt'],risk_override='R1_CONTRACT')
rg=requirements_evaluate(req_unresolved,registry); key='requirements_gate:unresolved_blocks'; ok=(rg['result']=='FAIL' and rg['requirements_outcome']=='REQUIREMENTS_BLOCKED'); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_proved=prove_requirements(req_unresolved)
rg=requirements_evaluate(req_proved,registry); key='requirements_gate:fully_evidenced_ready'; ok=(rg['result']=='PASS' and rg['requirements_outcome']=='REQUIREMENTS_READY'); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})

# Removing a blocking contract row must never turn UNKNOWN into implicit success.
req_deleted_field=copy.deepcopy(req_proved); deleted_field=next(iter(req_deleted_field['functional_contract'])); del req_deleted_field['functional_contract'][deleted_field]
rg=requirements_evaluate(req_deleted_field,registry); key='requirements_gate:deleted_contract_field_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='FUNCTIONAL_FIELD_MISSING' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})

# Duplicate adjudication rows and non-concrete evidence are invalid proof, not harmless formatting.
req_duplicate_rule=copy.deepcopy(req_proved); req_duplicate_rule['rules'].append(copy.deepcopy(req_duplicate_rule['rules'][0]))
rg=requirements_evaluate(req_duplicate_rule,registry); key='requirements_gate:duplicate_rule_id_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='DUPLICATE_ROW_ID' and e.get('scope')=='requirements_rule' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_weak_evidence=copy.deepcopy(req_proved); first_field=next(iter(req_weak_evidence['functional_contract'].values())); first_field['evidence']=[{'kind':'SOURCE_REQUIRED'}]
rg=requirements_evaluate(req_weak_evidence,registry); key='requirements_gate:nonconcrete_field_evidence_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='EVIDENCE_NOT_CONCRETE' and e.get('scope')=='functional_field' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_missing_artifact=copy.deepcopy(req_proved)
req_missing_artifact['evidence_requests']=[{'id':'event-subscription-source','status':'REQUEST_REQUIRED','blocking':True,'claim':'prove event → subscription → handler reachability','artifacts':['EventSubscriptions metadata/XML','handler common module']}]
rg=requirements_evaluate(req_missing_artifact,registry); key='requirements_gate:missing_artifact_must_be_requested'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIRED_ARTIFACT_NOT_REQUESTED' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})

req_requested_artifact=copy.deepcopy(req_proved)
req_requested_artifact['evidence_requests']=[{'id':'event-subscription-source','status':'REQUESTED','blocking':True,'claim':'prove event → subscription → handler reachability','artifacts':['EventSubscriptions metadata/XML','handler common module'],'request_text':'Please provide the subscription metadata and handler module.'}]
rg=requirements_evaluate(req_requested_artifact,registry); key='requirements_gate:requested_blocking_artifact_waits'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIRED_ARTIFACT_PENDING' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})

req_provided_artifact=copy.deepcopy(req_proved)
req_provided_artifact['evidence_requests']=[{'id':'event-subscription-source','status':'PROVIDED','blocking':True,'claim':'prove event → subscription → handler reachability','artifacts':['EventSubscriptions metadata/XML','handler common module'],'evidence':[{'kind':'SOURCE_REQUIRED','ref':'synthetic subscription source'}]}]
rg=requirements_evaluate(req_provided_artifact,registry); key='requirements_gate:provided_artifact_allows_ready'; ok=(rg['result']=='PASS' and rg['requirements_outcome']=='REQUIREMENTS_READY'); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_assumed=copy.deepcopy(req_proved); nonblocking=next(v for v in req_assumed['functional_contract'].values() if not v['blocking']); nonblocking['status']='ASSUMED'; nonblocking['reason']='synthetic non-blocking assumption'; nonblocking['value']='explicit assumption'; nonblocking['evidence']=[]
rg=requirements_evaluate(req_assumed,registry); key='requirements_gate:nonblocking_assumption_ready'; ok=(rg['result']=='PASS' and rg['requirements_outcome']=='REQUIREMENTS_READY_WITH_ASSUMPTIONS'); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_block_assume=copy.deepcopy(req_proved); blocking=next(v for v in req_block_assume['functional_contract'].values() if v['blocking']); blocking['status']='ASSUMED'; blocking['reason']='synthetic business assumption'; blocking['value']='assumed business behavior'; blocking['evidence']=[]
rg=requirements_evaluate(req_block_assume,registry); key='requirements_gate:blocking_assumption_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='BLOCKING_BUSINESS_FIELD_ASSUMED' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_core_na=copy.deepcopy(req_proved); req_core_na['functional_contract']['need']['status']='NOT_APPLICABLE'; req_core_na['functional_contract']['need']['reason']='synthetic attempt to erase the need'; req_core_na['functional_contract']['need']['evidence']=[]
rg=requirements_evaluate(req_core_na,registry); key='requirements_gate:core_functional_field_na_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='FUNCTIONAL_FIELD_NA_FORBIDDEN' and e.get('id')=='need' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
with tempfile.TemporaryDirectory() as td:
    req_source=Path(td)/'requirements.txt'; req_source.write_text('Original requirement',encoding='utf-8')
    req_source_contract=prove_requirements(build_contract([req_source],risk_override='R1_CONTRACT'))
    req_source.write_text('Changed requirement',encoding='utf-8')
    rg=requirements_evaluate(req_source_contract,registry); key='requirements_gate:current_source_bytes_drift_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIREMENTS_SOURCE_DRIFT' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
    if not ok:errors.append({'case':key,'details':rg})
req_task_contract=prove_requirements(build_contract([],task_text='Original task text',surface_override='ONEC_ONLY',risk_override='R1_CONTRACT'))
req_task_contract['task_input']['text']='Changed task text'
rg=requirements_evaluate(req_task_contract,registry); key='requirements_gate:task_text_hash_drift_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIREMENTS_TASK_INPUT_HASH_DRIFT' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})
req_empty_input=build_contract([])
rg=requirements_evaluate(req_empty_input,registry); key='requirements_gate:empty_input_blocks'; ok=(rg['result']=='FAIL' and any(e['type']=='REQUIREMENTS_INPUT_EMPTY' for e in rg['errors'])); results[key]={'outcome':rg['requirements_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':rg})

# Tier-0 activation is independent from regex routing and must never disappear.
tier0_plan=build_plan([fixtures/'call_contract_nonexport_caller.bsl'])
tier0_expected={rule['id'] for rule in registry['rules'] if rule.get('tier')==0}
tier0_actual={row['id'] for row in tier0_plan['rules'] if row.get('tier')==0 and row.get('active') and row.get('activation_status') in {'REQUIRED','CONDITIONAL_REVIEW','ROUTED'}}
tier0_missing=sorted(tier0_expected-tier0_actual)
key='activation:tier0_disposition_required'; ok=not tier0_missing
results[key]={'missing':tier0_missing,'expected':sorted(tier0_expected),'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

# Technical release must also fail closed when a non-trivial change has no accepted requirements contract.
missing_req_plan=build_plan([fixtures/'call_contract_nonexport_caller.bsl'])
missing_req_ledger=build_ledger(missing_req_plan,registry)
mr=release_evaluate(missing_req_plan,missing_req_ledger,registry)
key='release:requirements_contract_missing_blocks'; ok=(mr['result']=='FAIL' and any(x['type']=='REQUIREMENTS_CONTRACT_MISSING' for x in mr['errors'])); results[key]={'outcome':mr['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':mr})

# Release gate regressions: generated ledger must fail closed; evidence-backed ledger may pass.
release_req=prove_requirements(build_contract([fixtures/'requirements_contract.txt'],risk_override='R1_CONTRACT'))
with tempfile.NamedTemporaryFile('w',suffix='.json',encoding='utf-8',delete=False) as _rf:
    json.dump(release_req,_rf,ensure_ascii=False); release_req_path=Path(_rf.name)
with tempfile.NamedTemporaryFile('wb',suffix='.bsl',delete=False) as _release_source:
    _release_source.write((fixtures/'call_contract_nonexport_caller.bsl').read_bytes())
    _release_source.write(b"\n// synthetic release-mechanics source; intentionally not fixture-identical\n")
    release_source_path=Path(_release_source.name)
plan=build_plan([release_source_path],requirements_contract=release_req_path)
ledger=build_ledger(plan,registry)
r=release_evaluate(plan,ledger,registry)
key='release:unresolved_blocks'; ok=(r['release_outcome']=='BLOCKED' and r['result']=='FAIL'); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# A valid but narrower requirements contract cannot authorize a wider technical plan.
underscoped_req=prove_requirements(build_contract([],task_text='Documentation-only local task'))
with tempfile.NamedTemporaryFile('w',suffix='.json',encoding='utf-8',delete=False) as _urf:
    json.dump(underscoped_req,_urf,ensure_ascii=False); underscoped_req_path=Path(_urf.name)
underscoped_plan=build_plan([fixtures/'call_contract_nonexport_caller.bsl'],requirements_contract=underscoped_req_path)
underscoped_ledger=build_ledger(underscoped_plan,registry)
r=release_evaluate(underscoped_plan,underscoped_ledger,registry); key='release:underscoped_requirements_contract_blocks'; ok=(not underscoped_plan['requirements']['technical_design_allowed'] and not underscoped_plan['requirements']['coverage_sufficient'] and r['result']=='FAIL' and any(x['type']=='REQUIREMENTS_CONTRACT_SCOPE_INSUFFICIENT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# Construct a synthetic fully-adjudicated ledger to test release mechanics, not domain correctness.
proved=copy.deepcopy(ledger)
_receipt_dir=Path(tempfile.mkdtemp(prefix='onec-skill-receipts-'))
_machine_input=_receipt_dir/'machine_input.bsl'; _machine_input.write_bytes((fixtures/'query_field_good.bsl').read_bytes())
_machine_receipt_path=_receipt_dir/'machine.json'
_machine_receipt=create_receipt('TOOLS/analyze_onec_bsl.py',[str(_machine_input)],[str(_machine_input)],['STATIC:ONEC_BSL'],_machine_receipt_path)
_machine_receipt_sha=hashlib.sha256(_machine_receipt_path.read_bytes()).hexdigest()
proved['machine_reports']=[{'id':'MACHINE:SYNTHETIC','tool':'TOOLS/analyze_onec_bsl.py','ref':str(_machine_receipt_path),'receipt_ref':str(_machine_receipt_path),'receipt_sha256':_machine_receipt_sha,'result':_machine_receipt['derived_result'],'supersedes':[]}]
proved['runtime_cases']=[]

def runtime_evidence_for_claim(claim_id):
    digest=hashlib.sha256(claim_id.encode('utf-8')).hexdigest()[:16]
    case_id=f'RUNTIME:SYNTHETIC:{digest}'
    existing=next((x for x in proved['runtime_cases'] if x['id']==case_id),None)
    if existing:
        return {'kind':'RUNTIME','ref':existing['observation_ref'],'case_id':case_id,'property_id':claim_id,'claim_id':claim_id}
    runtime_log=_receipt_dir/f'runtime-{digest}.log'; runtime_log.write_text(f'synthetic observed runtime claim {claim_id}',encoding='utf-8')
    observation_path=_receipt_dir/f'runtime-{digest}.json'
    create_adapter_observation(observation_path,claim_id,runtime_log,'synthetic-regression-adapter','test-runtime',f'synthetic observed runtime claim {claim_id}')
    observation_sha=hashlib.sha256(observation_path.read_bytes()).hexdigest()
    proved['runtime_cases'].append({'id':case_id,'status':'PASS','property_id':claim_id,'observation_ref':str(observation_path),'observation_sha256':observation_sha,'evidence':[{'kind':'RUNTIME','ref':str(observation_path),'case_id':case_id,'property_id':claim_id,'claim_id':claim_id}]})
    return {'kind':'RUNTIME','ref':str(observation_path),'case_id':case_id,'property_id':claim_id,'claim_id':claim_id}

def synthetic_evidence(kind,ref,claim_id=None):
    if kind=='RUNTIME':
        return runtime_evidence_for_claim(claim_id or 'RUNTIME:SYNTHETIC')
    item={'kind':kind,'ref':ref}
    if claim_id:item['claim_id']=claim_id
    if kind=='SOURCE_REQUIRED':
        candidate=plan['candidate_artifacts'][0]
        item['ref']=candidate['origin']
        item['source_provenance']={
            'type':'CURRENT_CORPUS',
            'verifier':'release_gate_core.source_identity',
            'version':1,
            'source_sha256':candidate['sha256'],
        }
    if kind=='MACHINE':
        item.update({'report_id':'MACHINE:SYNTHETIC','property_id':'STATIC:ONEC_BSL','supporting_only':True})
    return item

for gate in proved['gates']:
    if gate['status']=='NOT_APPLICABLE':continue
    if gate['id']=='RUNTIME_MATRIX':
        gate['status']='PASS'; gate['evidence']=[synthetic_evidence('RUNTIME','synthetic completed runtime matrix','GATE:RUNTIME_MATRIX')]; continue
    gate['status']='PASS'; gate['evidence']=[synthetic_evidence('SEMANTIC','regression synthetic gate evidence')]
for level in proved['review_levels']:
    level['status']='PASS'; level['evidence']=[synthetic_evidence('SEMANTIC','regression synthetic level evidence')]
for lens in proved['gap_discovery']['lenses']:
    lens['status']='PASS'; lens['evidence']=[synthetic_evidence('SEMANTIC','synthetic independent discovery-lens evidence')]
proved['adversarial_cases']=[{'id':'ADV:SYNTHETIC','case':'call boundary receives an incompatible argument shape','status':'PASS','reason':'','evidence':[synthetic_evidence('SEMANTIC','synthetic adversarial counterexample was checked')]}]
for row in proved['rules']:
    # For tier-0 profile rules without a direct/derived trigger, exercise reasoned N/A instead of pretending applicability.
    route=next(x for x in plan['rules'] if x['id']==row['id'])
    routed=bool(route.get('detected_by') or route.get('reason','').startswith('derived') or route.get('tier',1)>0)
    primary_kind=next((kind for kind in ('SOURCE_REQUIRED','SEMANTIC','RUNTIME') if kind in row['required_evidence_modes']),None)
    if primary_kind is None:
        primary_kind='MACHINE'
    if not routed and row['id'] in {'BSP_REUSE','BUSINESS_IDENTITY'}:
        row['status']='NOT_APPLICABLE'; row['reason']='synthetic fixture has no source mechanism that makes this Tier-0 profile applicable'
        row['evidence']=[synthetic_evidence(primary_kind,'synthetic non-applicability source evidence',row['claim_id'])]
        for check in row['checks']:
            check['status']='NOT_APPLICABLE'; check['reason']='synthetic fixture omits the mechanism owned by this check'; check['evidence']=[]
        continue
    row['status']='PASS'; row['evidence']=[synthetic_evidence(kind,f'synthetic {kind} evidence',row['claim_id']) for kind in row['required_evidence_modes']]
    for check in row['checks']:
        check['status']='PASS'; check['evidence']=[synthetic_evidence(primary_kind,'synthetic check evidence',check['claim_id'])]
# Reverse passes are separate proof obligations. They are not inferred from local PASS labels.
proved['code_to_standards'][0]['status']='PASS'
proved['code_to_standards'][0]['rule_ids']=[row['id'] for row in proved['rules']]
proved['code_to_standards'][0]['evidence']=[synthetic_evidence('SEMANTIC','synthetic source-construction to standards pass')]
rule_status={row['id']:row for row in proved['rules']}
for row in proved['standards_to_code']:
    owner=rule_status[row['rule_id']]
    if owner['status']=='NOT_APPLICABLE':
        row['status']='NOT_APPLICABLE'; row['reason']='synthetic fixture: owner rule not applicable'; row['evidence']=[]
    else:
        row['status']='PASS'; row['evidence']=[synthetic_evidence('SEMANTIC','synthetic independent registry-to-code pass')]
# Phase-1 semantic proof: build a complete intent map and separated review receipts
# for this synthetic release-mechanics positive control.
intent=build_intent_skeleton(plan)
logical=plan['candidate_artifacts'][0]['logical_path']
intent['rows']=[
    {
        'requirement_id':'REQ:SYNTHETIC','design_decision_id':'DD:SYNTHETIC','artifact':logical,
        'target_kind':'ARTIFACT','action':'create',
        'responsibility':'carry the synthetic changed source','necessity':'required by synthetic release mechanics',
        'existing_owner_disposition':'new candidate artifact is the explicit delivery surface','platform_reuse_decision':'no alternate artifact mechanism',
        'acceptance_cases':['AC:SYNTHETIC'],
        'nearest_smaller_alternative':{'alternative':'no artifact','rejection_reason':'would not exercise release mechanics'},
        'verification_hooks':['release regression'],
    },
    {
        'requirement_id':'REQ:SYNTHETIC','design_decision_id':'DD:SYNTHETIC','artifact':logical,
        'target_kind':'BSL_ROUTINE','fragment':'ПроверитьДоговор','action':'create',
        'responsibility':'exercise release mechanics','necessity':'synthetic required behavior',
        'existing_owner_disposition':'routine is carried by the explicit new candidate artifact','platform_reuse_decision':'no new platform mechanism',
        'entrypoint':{'kind':'ENTRYPOINT','ref':'ПроверитьДоговор'},
        'acceptance_cases':['AC:SYNTHETIC'],
        'nearest_smaller_alternative':{'alternative':'no routine','rejection_reason':'would not exercise the changed candidate'},
        'verification_hooks':['release regression'],
    }
]
proved['implementation_intent_map']=intent
source_anchors=[{'logical_path':x['logical_path'],'candidate_sha256':x['sha256']} for x in plan['candidate_artifacts']]
proved['independent_reviews']=[]
def add_independent_review(claim_id,rule_id,check_id=None):
    digest=hashlib.sha256(claim_id.encode('utf-8')).hexdigest()[:16]
    path=_receipt_dir/f'review-{digest}.json'
    write_review_receipt(path,plan,author_execution_id='AUTHOR:SYNTHETIC',
        reviewer_execution_id=f'REVIEWER:{digest}',claim_id=claim_id,rule_id=rule_id,check_id=check_id,
        source_anchors=source_anchors,reviewer_verdict='PASS',defects=[],
        limitations=['Synthetic regression validates binding/separation mechanics, not domain correctness.'])
    proved['independent_reviews'].append({
        'claim_id':claim_id,'rule_id':rule_id,'check_id':check_id,'receipt_ref':str(path),
        'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'author_execution_id':'AUTHOR:SYNTHETIC'
    })
for rr in proved['rules']:
    policy=rr.get('proof_policy') or {}
    if policy.get('claim_class')!='ARCHITECTURE_SEMANTIC' or rr.get('status')!='PASS':continue
    add_independent_review(rr['claim_id'],rr['id'])
    for ch in rr.get('checks') or []:
        if ch.get('status')=='PASS':add_independent_review(ch['claim_id'],rr['id'],ch['id'])
for level in proved['review_levels']:
    policy=level.get('proof_policy') or {}
    if policy.get('claim_class')!='ARCHITECTURE_SEMANTIC':continue
    claim=level['claim_id']
    level['evidence']=[synthetic_evidence('SOURCE_REQUIRED','synthetic review-level exact source',claim)]
    add_independent_review(claim,'REVIEW_LEVEL',level['id'])

proved['knowledge_extraction']={'outcome':'NO_REUSABLE_KNOWLEDGE','reason':'synthetic release-mechanics fixture','project_context_updates':[],'items':[]}
r=release_evaluate(plan,proved,registry); key='release:evidence_allows_proven'; ok=(r['result']=='PASS' and r['release_outcome']=='PROVEN'); results[key]={'outcome':r['release_outcome'],'errors':r['errors'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# P1 delivery/proof binding regressions.
_gating=[x for x in plan.get('active_deliveries',[]) if x.get('enforcement')=='GATING']
_advisory=[x for x in plan.get('active_deliveries',[]) if x.get('enforcement')=='ADVISORY']
key='delivery_binding:positive_control_has_gating'; ok=bool(_gating); results[key]={'gating':[x.get('capability_id') for x in _gating],'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})
if _gating:
    removed=_gating[0]; defective=copy.deepcopy(plan); defective['active_deliveries']=[x for x in defective.get('active_deliveries',[]) if x.get('capability_id')!=removed.get('capability_id')]
    removed_payload=(removed.get('executor_payload') or {}).get('value'); defective['deterministic_tools']=[x for x in defective.get('deterministic_tools',[]) if x!=removed_payload]
    dr=release_evaluate(defective,proved,registry); key='delivery_binding:mandatory_delivery_removed_blocks'; ok=(dr['result']=='FAIL' and any(x.get('type')=='RELEASE_PLAN_RECOMPUTE_DRIFT' for x in dr.get('errors',[])))
    results[key]={'capability':removed.get('capability_id'),'errors':dr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':dr})
key='delivery_binding:positive_control_has_advisory'; ok=bool(_advisory); results[key]={'advisory':[x.get('capability_id') for x in _advisory],'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})
if _advisory:
    omitted=_advisory[0]; advisory_plan=copy.deepcopy(plan); advisory_plan['active_deliveries']=[x for x in advisory_plan.get('active_deliveries',[]) if x.get('capability_id')!=omitted.get('capability_id')]
    omitted_payload=(omitted.get('executor_payload') or {}).get('value'); advisory_plan['deterministic_tools']=[x for x in advisory_plan.get('deterministic_tools',[]) if x!=omitted_payload]
    ar=release_evaluate(advisory_plan,proved,registry); key='delivery_binding:advisory_omission_nonblocking'; ok=(ar['result']=='PASS' and ar['release_outcome']=='PROVEN' and not any(x.get('type')=='RELEASE_PLAN_RECOMPUTE_DRIFT' for x in ar.get('errors',[])))
    results[key]={'capability':omitted.get('capability_id'),'errors':ar.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':ar})

_bad_registry=copy.deepcopy(registry)
_bad_binding=next(x for rule in _bad_registry.get('rules',[]) for x in rule.get('delivery',[]) if x.get('enforcement')=='GATING')
_bad_binding['proof_binding']=None
_schema_errors=validate_delivery_bindings(_bad_registry); key='delivery_binding:gating_without_proof_route_rejected'; ok=any(x.startswith('delivery_gating_proof_binding_missing:') for x in _schema_errors)
results[key]={'schema_errors':_schema_errors,'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

def _binding_ref(registry_doc,capability_id):
    for _rule in registry_doc.get('rules',[]):
        for _binding in _rule.get('delivery',[]):
            if _binding.get('capability_id')==capability_id:return _rule,_binding
    raise AssertionError(f'missing delivery binding {capability_id}')

# Focused registry mutations: fail closed without a second schema/test framework.
_mut=copy.deepcopy(registry); _,_a=_binding_ref(_mut,'CAP.CALL_SIGNATURE_ANALYSIS'); _,_b=_binding_ref(_mut,'CAP.REACHABILITY_ANALYSIS'); _b['capability_id']=_a['capability_id']
_mut_errors=validate_delivery_bindings(_mut); key='delivery_binding:duplicate_capability_owner_rejected'; ok=any(x.startswith('delivery_duplicate_capability_owner:') for x in _mut_errors); results[key]={'errors':_mut_errors,'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

_mut=copy.deepcopy(registry); _,_a=_binding_ref(_mut,'CAP.CALL_SIGNATURE_ANALYSIS'); _,_b=_binding_ref(_mut,'CAP.REACHABILITY_ANALYSIS'); _b['sequence']=_a['sequence']
_mut_errors=validate_delivery_bindings(_mut); key='delivery_binding:duplicate_sequence_rejected'; ok=any(x.startswith('delivery_duplicate_sequence:') for x in _mut_errors); results[key]={'errors':_mut_errors,'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

_mut=copy.deepcopy(registry); _,_a=_binding_ref(_mut,'CAP.CALL_SIGNATURE_ANALYSIS'); _a['proof_binding']['owner']='CHECK:SOURCE_FIRST:SOURCE_FIRST_T01'
_mut_errors=validate_delivery_bindings(_mut); key='delivery_binding:foreign_proof_owner_rejected'; ok=any(x.startswith('delivery_proof_owner_invalid:') for x in _mut_errors); results[key]={'errors':_mut_errors,'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

_mut=copy.deepcopy(registry); _,_a=_binding_ref(_mut,'CAP.CALL_SIGNATURE_ANALYSIS'); _a['proof_binding']['accepted_evidence'].append('RUNTIME')
_mut_errors=validate_delivery_bindings(_mut); key='delivery_binding:evidence_mode_escalation_rejected'; ok=any(x.startswith('delivery_proof_evidence_outside_rule:') for x in _mut_errors); results[key]={'errors':_mut_errors,'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

# Release recomputation tamper matrix: exact canonical present subset + derived outputs.
if _gating:
    _base_gating=_gating[0]; _base_cap=_base_gating.get('capability_id')

    _tampered=copy.deepcopy(plan)
    next(x for x in _tampered['active_deliveries'] if x.get('capability_id')==_base_cap)['sequence']+=1
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:sequence_tamper_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_BINDING_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

    _tampered=copy.deepcopy(plan)
    _tampered['active_deliveries']=[x for x in _tampered['active_deliveries'] if x.get('capability_id')!=_base_cap]
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:command_only_without_gating_binding_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_GATING_MISSING' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

    _tampered=copy.deepcopy(plan)
    _payload=(_base_gating.get('executor_payload') or {}).get('value')
    _tampered['deterministic_tools']=[x for x in _tampered.get('deterministic_tools',[]) if x!=_payload]
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:gating_binding_without_command_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_TOOL_PROJECTION_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

    _tampered=copy.deepcopy(plan)
    _row=next(x for x in _tampered['active_deliveries'] if x.get('capability_id')==_base_cap)
    _row['proof_binding']=copy.deepcopy(_row.get('proof_binding') or {}); _row['proof_binding']['owner']='CHECK:SOURCE_FIRST:SOURCE_FIRST_T01'
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:proof_owner_rewrite_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_BINDING_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

    _tampered=copy.deepcopy(plan)
    _row=next(x for x in _tampered['active_deliveries'] if x.get('capability_id')==_base_cap); _row['enforcement']='ADVISORY'
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:gating_enforcement_downgrade_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_BINDING_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

if len(plan.get('deterministic_tools') or [])>1:
    _tampered=copy.deepcopy(plan); _tampered['deterministic_tools']=list(reversed(_tampered['deterministic_tools']))
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:command_order_tamper_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_TOOL_PROJECTION_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

if len(plan.get('active_deliveries') or [])>1:
    _tampered=copy.deepcopy(plan); _tampered['active_deliveries']=list(reversed(_tampered['active_deliveries']))
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:active_delivery_order_tamper_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_ORDER_OR_SUBSET_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

_tampered=copy.deepcopy(plan); _tampered['context_load_plan']=copy.deepcopy(_tampered.get('context_load_plan') or {}); _tampered['context_load_plan']['references']=['REFERENCE/SYNTHETIC-TAMPER']
_rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:reference_projection_tamper_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_REFERENCE_PROJECTION_DRIFT' for x in _rr.get('errors',[])))
results[key]={'errors':_rr.get('errors',[]),'pass':ok}
if not ok:errors.append({'case':key,'details':_rr})

if _advisory:
    _tampered=copy.deepcopy(plan); _adv=_advisory[0]; _adv_cap=_adv.get('capability_id')
    _row=next(x for x in _tampered['active_deliveries'] if x.get('capability_id')==_adv_cap)
    _old_value=(_row.get('executor_payload') or {}).get('value'); _new_value=_old_value+' [tampered]'
    _row['executor_payload']=copy.deepcopy(_row.get('executor_payload') or {}); _row['executor_payload']['value']=_new_value
    _tampered['deterministic_tools']=[_new_value if x==_old_value else x for x in _tampered.get('deterministic_tools',[])]
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:mutated_advisory_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_BINDING_DRIFT' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

    _tampered=copy.deepcopy(plan)
    _unknown={'capability_id':'CAP.UNKNOWN_ADVISORY','sequence':999,'owner_rule_id':'BIDIRECTIONAL_STANDARDS','enforcement':'ADVISORY','executor_payload':{'kind':'INSTRUCTION','value':'synthetic unknown advisory'},'references':[],'proof_binding':None}
    _tampered['active_deliveries'].append(_unknown); _tampered['deterministic_tools'].append('synthetic unknown advisory')
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:unknown_advisory_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_UNKNOWN_CAPABILITY' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

    _tampered=copy.deepcopy(plan)
    _row=next(x for x in _tampered['active_deliveries'] if x.get('capability_id')==_adv_cap)
    _tampered['active_deliveries'].append(copy.deepcopy(_row))
    _rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:duplicate_advisory_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type')=='RELEASE_DELIVERY_DUPLICATE_CAPABILITY' for x in _rr.get('errors',[])))
    results[key]={'errors':_rr.get('errors',[]),'pass':ok}
    if not ok:errors.append({'case':key,'details':_rr})

_tampered=copy.deepcopy(plan); _tampered['registry']=copy.deepcopy(_tampered['registry']); _tampered['registry']['sha256']='0'*64
_rr=release_evaluate(_tampered,proved,registry); key='delivery_binding:stale_registry_plan_blocks'; ok=(_rr['result']=='FAIL' and any(x.get('type') in {'REGISTRY_DEPENDENCY_DRIFT','RELEASE_PLAN_RECOMPUTE_DRIFT'} for x in _rr.get('errors',[])))
results[key]={'errors':_rr.get('errors',[]),'pass':ok}
if not ok:errors.append({'case':key,'details':_rr})

# Conditional GATING N/A is not a prose-only escape hatch.
_call_route=next(x for x in plan.get('rules',[]) if x.get('id')=='CALL_CONTRACT')
_call_binding=next(x for x in plan.get('active_deliveries',[]) if x.get('capability_id')=='CAP.CALL_SIGNATURE_ANALYSIS')
_call_owner=(_call_binding.get('proof_binding') or {}).get('owner'); _call_check_id=_call_owner.split(':',2)[2]
_na=copy.deepcopy(proved); _call_rule=next(x for x in _na['rules'] if x.get('id')=='CALL_CONTRACT')
_call_rule['status']='NOT_APPLICABLE'; _call_rule['reason']='Exact candidate review concludes that no applicable cross-module call contract remains for this disposition.'; _call_rule['evidence']=[]
for _check in _call_rule.get('checks',[]):
    _check['status']='NOT_APPLICABLE'; _check['reason']='Exact candidate review concludes this check is not applicable to the accepted disposition.'; _check['evidence']=[]
_s2c=next(x for x in _na['standards_to_code'] if x.get('rule_id')=='CALL_CONTRACT'); _s2c['status']='NOT_APPLICABLE'; _s2c['reason']='Owner rule is not applicable in this synthetic disposition.'; _s2c['evidence']=[]
_rr=release_evaluate(plan,_na,registry); key='delivery_binding:conditional_gating_na_without_proof_blocks'; ok=(_call_route.get('activation_status')=='CONDITIONAL_REVIEW' and _rr['result']=='FAIL' and any(x.get('type')=='CAPABILITY_BOUND_CHECK_NA_WITHOUT_PROOF' and x.get('id')==_call_check_id for x in _rr.get('errors',[])))
results[key]={'route_status':_call_route.get('activation_status'),'errors':_rr.get('errors',[]),'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

_na_proved=copy.deepcopy(_na); _call_rule=next(x for x in _na_proved['rules'] if x.get('id')=='CALL_CONTRACT'); _bound=next(x for x in _call_rule['checks'] if x.get('id')==_call_check_id)
_bound['evidence']=[synthetic_evidence('SOURCE_REQUIRED','synthetic capability N/A exact-source evidence',_bound['claim_id'])]
_rr=release_evaluate(plan,_na_proved,registry); key='delivery_binding:conditional_gating_na_with_verified_proof_allowed'; ok=(_rr['result']=='PASS' and _rr['release_outcome']=='PROVEN')
results[key]={'errors':_rr.get('errors',[]),'outcome':_rr.get('release_outcome'),'pass':ok}
if not ok:errors.append({'case':key,'details':_rr})

_field_source=fixtures/'post_write_reachable_same_field_bad.bsl'
_field_plan=build_plan([_field_source],analysis_only=True)
_field_binding=next((x for x in _field_plan.get('active_deliveries',[]) if x.get('capability_id')=='CAP.FIELD_FLOW_ANALYSIS'),None)
_field_ledger=build_ledger(_field_plan,registry)
_field_receipt_path=_receipt_dir/'field-flow-delivered.json'
_field_receipt=create_receipt('TOOLS/analyze_onec_field_flow.py',[str(_field_source)],[str(_field_source)],['STATIC:FIELD_FLOW'],_field_receipt_path)
_field_ledger['machine_reports']=[{'id':'MACHINE:FIELD_FLOW:DELIVERED','tool':'TOOLS/analyze_onec_field_flow.py','ref':str(_field_receipt_path),'receipt_ref':str(_field_receipt_path),'receipt_sha256':hashlib.sha256(_field_receipt_path.read_bytes()).hexdigest(),'result':_field_receipt['derived_result'],'supersedes':[]}]
_field_release=release_evaluate(_field_plan,_field_ledger,registry); key='delivery_binding:tool_run_without_bound_proof_blocks'; ok=bool(_field_binding) and _field_receipt['derived_result']=='PASS' and _field_release['result']=='FAIL' and any(x.get('type')=='CAPABILITY_PROOF_BINDING_UNRESOLVED' and x.get('capability_id')=='CAP.FIELD_FLOW_ANALYSIS' for x in _field_release.get('errors',[]))
results[key]={'binding':_field_binding,'machine_result':_field_receipt['derived_result'],'errors':_field_release.get('errors',[]),'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})

_builder_text=(root/'TOOLS/build_review_plan.py').read_text(encoding='utf-8')
_migrated_tool_literals=['TOOLS/analyze_onec_bsl.py','TOOLS/analyze_onec_xml.py','TOOLS/check_bsl_call_signatures.py','TOOLS/analyze_onec_reachability.py','TOOLS/analyze_onec_field_flow.py','TOOLS/analyze_changeset_architecture.py','TOOLS/analyze_cleverence_mslx.py','TOOLS/analyze_cleverence_configuration.py']
key='delivery_binding:builder_has_no_migrated_tool_authority'; ok=not any(x in _builder_text for x in _migrated_tool_literals); results[key]={'present':[x for x in _migrated_tool_literals if x in _builder_text],'pass':ok}
if not ok:errors.append({'case':key,'details':results[key]})


# FR-PRP-02 remediation: machine finding identity must propagate through the
# canonical machine report -> ledger -> release verifier -> compact queue path.
def _finding_case_source_evidence(target_plan,claim_id):
    candidate=target_plan['candidate_artifacts'][0]
    return {
        'kind':'SOURCE_REQUIRED','ref':candidate['origin'],'claim_id':claim_id,
        'source_provenance':{
            'type':'CURRENT_CORPUS','verifier':'release_gate_core.source_identity',
            'version':1,'source_sha256':candidate['sha256'],
        },
    }

_FINDING_CASE_SPECIMENS={
    'HOMEGROWN_QUERY_STRUCTURE_PARSER': '''Процедура СобратьЗапросИзФрагмента(ИсходныйТекст) Экспорт
    Граница = СтрНайти(ВРег(ИсходныйТекст), " СОЕДИНЕНИЕ ");
    ФрагментЗапроса = Сред(ИсходныйТекст, Граница + 1);
    ЛокальныйЗапрос = Новый Запрос;
    ЛокальныйЗапрос.Текст = ФрагментЗапроса;
КонецПроцедуры
''',
    'QUERY_EXECUTE_SIDE_EFFECT_TRACE': '''Процедура СоздатьВременнуюВыборку(ТабличныйМенеджер) Экспорт
    ЛокальныйЗапрос = Новый Запрос;
    ЛокальныйЗапрос.МенеджерВременныхТаблиц = ТабличныйМенеджер;
    ЛокальныйЗапрос.Текст = "ВЫБРАТЬ Код ПОМЕСТИТЬ ВТКандидат ИЗ Справочник.Контрагенты";
    ЛокальныйЗапрос.Выполнить();
КонецПроцедуры
''',
    'INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW': '''Процедура ПроверитьСхемуВладельца() Экспорт
    ТекстИсточника = ПровайдерДанных.СформироватьТекстПакета();
    Граница = СтрНайти(ВРег(ТекстИсточника), " ВЫБРАТЬ ");
    Сегмент = Прав(ТекстИсточника, СтрДлина(ТекстИсточника) - Граница);
    ПроверочныйЗапрос = Новый Запрос;
    ПроверочныйЗапрос.Текст = "ВЫБРАТЬ 1 КАК Значение";
    РезультатПроверки = ПроверочныйЗапрос.Выполнить();
КонецПроцедуры
''',
}

def _build_finding_case(case_id,fixture_path,tool,property_id,finding_type,rule_id,check_id):
    # A fixture is only a non-proof template. An external byte-identical copy must
    # remain TEST_FIXTURE by content fingerprint and may never close SOURCE_REQUIRED.
    fixture_copy_dir=Path(tempfile.mkdtemp(prefix=f'fr-prp02-fixture-copy-{case_id}-'))
    fixture_copy=fixture_copy_dir/fixture_path.name
    fixture_copy.write_bytes(fixture_path.read_bytes())
    fixture_copy_errors=validate_evidence_items(
        [{'kind':'SOURCE_REQUIRED','ref':str(fixture_copy)}],
        scope=f'fr_prp02.fixture_copy.{case_id}',
    )
    key=f'fr_prp02:finding_binding:{case_id}:fixture_copy_content_fingerprint_blocks'
    ok=(len(fixture_copy_errors)==1
        and fixture_copy_errors[0].get('type')=='NON_PROOF_ARTIFACT_USED_AS_EVIDENCE'
        and fixture_copy_errors[0].get('matched_by')=='CONTENT_FINGERPRINT'
        and fixture_copy_errors[0].get('role')=='TEST_FIXTURE')
    results[key]={'errors':fixture_copy_errors,'pass':ok}
    if not ok:errors.append({'case':key,'details':fixture_copy_errors})

    # Positive proof uses independently authored target-corpus bytes rather than a
    # mutated/cosmetic copy of any fixture. Exact candidate identity then propagates
    # through plan -> machine report -> evidence -> independent review.
    candidate_dir=Path(tempfile.mkdtemp(prefix=f'fr-prp02-candidate-{case_id}-'))
    candidate_path=candidate_dir/'Target_Module.bsl'
    candidate_path.write_text(_FINDING_CASE_SPECIMENS[case_id],encoding='utf-8')
    specimen_hit=classify_non_proof_ref(str(candidate_path))
    key=f'fr_prp02:finding_binding:{case_id}:independent_specimen_not_non_proof'
    ok=(candidate_path.read_bytes()!=fixture_path.read_bytes() and specimen_hit is None)
    results[key]={'classification':specimen_hit,'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    target_plan=build_plan([candidate_path],analysis_only=True)
    target_ledger=build_ledger(target_plan,registry)
    receipt_dir=candidate_dir/'receipts'; receipt_dir.mkdir()
    receipt_path=receipt_dir/'machine.json'
    receipt=create_receipt(tool,[str(candidate_path)],[str(candidate_path)],[property_id],receipt_path)
    receipt_sha=hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    report_id=f'MACHINE:FR_PRP02:{case_id}'
    machine_reports=[{
        'id':report_id,'tool':tool,'ref':str(receipt_path),'receipt_ref':str(receipt_path),
        'receipt_sha256':receipt_sha,'result':receipt['derived_result'],'supersedes':[],
    }]
    query_route=next((row for row in target_plan.get('rules') or [] if row.get('id')=='QUERY'),{})
    if candidate_path.suffix.lower()=='.bsl' and query_route.get('active') and tool!='TOOLS/analyze_onec_bsl.py':
        query_receipt_path=receipt_dir/'query-current.json'
        query_receipt=create_receipt(
            'TOOLS/analyze_onec_bsl.py',[str(candidate_path)],[str(candidate_path)],
            ['STATIC:ONEC_BSL'],query_receipt_path
        )
        query_report_id=f'MACHINE:FR_PRP02:{case_id}:QUERY_CURRENT'
        machine_reports.append({
            'id':query_report_id,'tool':'TOOLS/analyze_onec_bsl.py',
            'ref':str(query_receipt_path),'receipt_ref':str(query_receipt_path),
            'receipt_sha256':hashlib.sha256(query_receipt_path.read_bytes()).hexdigest(),
            'result':query_receipt['derived_result'],'supersedes':[],
        })
    target_ledger['machine_reports']=machine_reports
    logical=target_plan['candidate_artifacts'][0]['logical_path']
    bound=bind_machine_findings(target_ledger,target_plan,report_id,logical,registry)
    target=[x for x in bound if x.get('finding_type')==finding_type]
    key=f'fr_prp02:finding_binding:{case_id}:analyzer_exact_identity'
    ok=(len(target)==1 and target[0].get('rule_id')==rule_id and target[0].get('check_id')==check_id)
    results[key]={'bound':bound,'pass':ok}
    if not ok:errors.append({'case':key,'details':bound})
    if len(target)!=1:return
    target_row=target[0]; target_claim=target_row['claim_id']
    input_shas={x.get('sha256') for x in receipt.get('inputs') or []}
    candidate_sha=target_plan['candidate_artifacts'][0]['sha256']
    key=f'fr_prp02:finding_binding:{case_id}:machine_report_candidate_bound'
    ok=(candidate_sha in input_shas and target_row.get('candidate_sha256')==candidate_sha
        and target_row.get('report_output_sha256')==(receipt.get('output') or {}).get('stdout_sha256'))
    results[key]={'candidate_sha':candidate_sha,'receipt_inputs':sorted(input_shas),'row':target_row,'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    runtime_cases=[]
    target_ledger['runtime_cases']=runtime_cases
    reviews=[]
    target_ledger['independent_reviews']=reviews
    source_anchors=[{'logical_path':x['logical_path'],'candidate_sha256':x['sha256']} for x in target_plan['candidate_artifacts']]

    def runtime_evidence(claim_id):
        digest=hashlib.sha256(claim_id.encode('utf-8')).hexdigest()[:16]
        runtime_log=receipt_dir/f'runtime-{digest}.log'
        runtime_log.write_text(f'fr-prp02 synthetic runtime observation {claim_id}',encoding='utf-8')
        observation=receipt_dir/f'runtime-{digest}.json'
        create_adapter_observation(observation,claim_id,runtime_log,'fr-prp02-regression-adapter','test-runtime',
            f'fr-prp02 synthetic runtime observation {claim_id}')
        observation_sha=hashlib.sha256(observation.read_bytes()).hexdigest()
        case=f'RUNTIME:FR_PRP02:{digest}'
        runtime_cases.append({
            'id':case,'status':'PASS','property_id':claim_id,'observation_ref':str(observation),
            'observation_sha256':observation_sha,
            'evidence':[{'kind':'RUNTIME','ref':str(observation),'case_id':case,'property_id':claim_id,'claim_id':claim_id}],
        })
        return {'kind':'RUNTIME','ref':str(observation),'case_id':case,'property_id':claim_id,'claim_id':claim_id}

    def evidence(kind,claim_id,ref='fr-prp02 synthetic proof'):
        if kind=='SOURCE_REQUIRED':return _finding_case_source_evidence(target_plan,claim_id)
        if kind=='RUNTIME':return runtime_evidence(claim_id)
        if kind=='MACHINE':
            return {
                'kind':'MACHINE','ref':str(receipt_path),'report_id':report_id,'property_id':property_id,
                'claim_id':claim_id,'supporting_only':True,
            }
        return {'kind':'SEMANTIC','ref':ref,'claim_id':claim_id}

    def review(claim_id,owner_rule,owner_check=None):
        digest=hashlib.sha256(claim_id.encode('utf-8')).hexdigest()[:16]
        path=receipt_dir/f'review-{digest}.json'
        write_review_receipt(
            path,target_plan,author_execution_id=f'AUTHOR:{case_id}',
            reviewer_execution_id=f'REVIEWER:{case_id}:{digest}',claim_id=claim_id,
            rule_id=owner_rule,check_id=owner_check,source_anchors=source_anchors,
            reviewer_verdict='PASS',defects=[],
            limitations=['Synthetic FR-PRP-02 regression proves binding and fail-closed mechanics only.'],
        )
        row={
            'claim_id':claim_id,'rule_id':owner_rule,'check_id':owner_check,'receipt_ref':str(path),
            'receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'author_execution_id':f'AUTHOR:{case_id}',
        }
        reviews.append(row);return row

    # Close every ordinary obligation using its existing registry policy.
    for gate in target_ledger['gates']:
        if gate['status']=='NOT_APPLICABLE':continue
        gate['status']='PASS'
        gate['evidence']=[runtime_evidence(f"GATE:{gate['id']}")] if gate['id']=='RUNTIME_MATRIX' else [
            {'kind':'SEMANTIC','ref':f'fr-prp02 gate {gate["id"]}'}
        ]
    for level in target_ledger['review_levels']:
        level['status']='PASS'; policy=level.get('proof_policy') or {}
        claim=level.get('claim_id')
        if policy.get('claim_class')=='ARCHITECTURE_SEMANTIC':
            level['evidence']=[_finding_case_source_evidence(target_plan,claim)]
            if policy.get('runtime_required_from')=='R2_STATEFUL_RUNTIME':
                level['evidence'].append(runtime_evidence(claim))
            review(claim,'REVIEW_LEVEL',level['id'])
        else:
            level['evidence']=[{'kind':'SEMANTIC','ref':f'fr-prp02 review level {level["id"]}'}]
    for lens in target_ledger['gap_discovery']['lenses']:
        lens['status']='PASS';lens['evidence']=[{'kind':'SEMANTIC','ref':f'fr-prp02 lens {lens["id"]}'}]

    route_by={x['id']:x for x in target_plan['rules']}
    for rule_row in target_ledger['rules']:
        owner=next(x for x in registry['rules'] if x['id']==rule_row['id'])
        modes=list(owner.get('evidence_modes') or [])
        rule_row['status']='PASS'
        policy=rule_row.get('proof_policy') or {}
        rule_evidence=[evidence(mode,rule_row['claim_id'],f'fr-prp02 {mode} rule evidence') for mode in modes]
        if policy.get('runtime_required_from')=='R2_STATEFUL_RUNTIME':
            rule_evidence.append(runtime_evidence(rule_row['claim_id']))
        rule_row['evidence']=rule_evidence
        if policy.get('claim_class')=='ARCHITECTURE_SEMANTIC':
            if 'SOURCE_REQUIRED' not in modes:
                # This is a contract error, not a reason to fake proof.
                key=f'fr_prp02:finding_binding:{case_id}:architecture_rule_source_mode'
                results[key]={'rule':rule_row['id'],'modes':modes,'pass':False}
                errors.append({'case':key,'details':results[key]})
            review(rule_row['claim_id'],rule_row['id'])
        for check in rule_row.get('checks') or []:
            check['status']='PASS'
            if 'SOURCE_REQUIRED' in modes:
                check['evidence']=[_finding_case_source_evidence(target_plan,check['claim_id'])]
            elif 'RUNTIME' in modes:
                check['evidence']=[runtime_evidence(check['claim_id'])]
            else:
                check['evidence']=[{'kind':'SEMANTIC','ref':f'fr-prp02 check {check["id"]}','claim_id':check['claim_id']}]
            check_policy=check.get('proof_policy') or policy
            if check_policy.get('runtime_required_from')=='R2_STATEFUL_RUNTIME' and not any(
                item.get('kind')=='RUNTIME' for item in check.get('evidence') or [] if isinstance(item,dict)
            ):
                check['evidence'].append(runtime_evidence(check['claim_id']))
            if policy.get('claim_class')=='ARCHITECTURE_SEMANTIC':
                review(check['claim_id'],rule_row['id'],check['id'])

    target_ledger['code_to_standards'][0]['status']='PASS'
    target_ledger['code_to_standards'][0]['rule_ids']=[x['id'] for x in target_ledger['rules']]
    target_ledger['code_to_standards'][0]['evidence']=[{'kind':'SEMANTIC','ref':'fr-prp02 complete forward review'}]
    owners={x['id']:x for x in target_ledger['rules']}
    for reverse in target_ledger['standards_to_code']:
        owner=owners[reverse['rule_id']]
        if owner['status']=='NOT_APPLICABLE':
            reverse['status']='NOT_APPLICABLE';reverse['reason']='owner not applicable';reverse['evidence']=[]
        else:
            reverse['status']='PASS';reverse['evidence']=[{'kind':'SEMANTIC','ref':f'fr-prp02 reverse {reverse["rule_id"]}'}]
    target_ledger['knowledge_extraction']={
        'outcome':'NO_REUSABLE_KNOWLEDGE','reason':'FR-PRP-02 synthetic regression has no reusable knowledge',
        'project_context_updates':[],'items':[],
    }

    unresolved=release_evaluate(target_plan,target_ledger,registry)
    target_errors=[x for x in unresolved.get('errors') or [] if x.get('scope')=='machine_finding' and x.get('id')==target_claim]
    unrelated=[x for x in unresolved.get('errors') or [] if x not in target_errors]
    key=f'fr_prp02:finding_binding:{case_id}:release_only_target_blocks'
    ok=(unresolved.get('result')=='FAIL' and len(target_errors)==1
        and target_errors[0].get('type')=='MACHINE_FINDING_BLOCKING_OR_UNRESOLVED' and not unrelated)
    results[key]={'target_errors':target_errors,'unrelated':unrelated,'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    queue=build_work_queue(target_ledger)
    queue_rows=queue.get('work_queue',{}).get('machine_findings') or []
    key=f'fr_prp02:finding_binding:{case_id}:compact_queue_exact_target'
    ok=(len(queue_rows)==1 and queue_rows[0].get('id')==target_claim
        and queue_rows[0].get('finding_type')==finding_type
        and queue_rows[0].get('artifact')==logical)
    results[key]={'rows':queue_rows,'pass':ok}
    if not ok:errors.append({'case':key,'details':queue_rows})

    generic=copy.deepcopy(target_ledger); generic_row=generic['machine_findings'][0]
    generic_row['status']='PASS'
    generic_row['evidence']=[{'kind':'SEMANTIC','ref':'self-authored generic semantic assertion','claim_id':target_claim}]
    generic_release=release_evaluate(target_plan,generic,registry)
    key=f'fr_prp02:finding_binding:{case_id}:generic_semantic_cannot_close'
    generic_types={x.get('type') for x in generic_release.get('errors') or [] if x.get('scope')=='machine_finding' and x.get('id')==target_claim}
    ok=generic_release.get('result')=='FAIL' and {'PRIMARY_PROOF_MISSING','EXACT_SOURCE_REQUIRED','INDEPENDENT_REVIEW_REQUIRED'}<=generic_types
    results[key]={'types':sorted(generic_types),'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    closed=copy.deepcopy(target_ledger); closed_row=closed['machine_findings'][0]
    closed_row['status']='PASS'; closed_row['evidence']=[_finding_case_source_evidence(target_plan,target_claim)]
    # Review must be added to the copied ledger, not only to the unresolved source.
    review_row=review(target_claim,rule_id,check_id)
    closed['independent_reviews']=copy.deepcopy(reviews)
    closed_release=release_evaluate(target_plan,closed,registry)
    key=f'fr_prp02:finding_binding:{case_id}:exact_source_review_closes_correct_claim'
    ok=(closed_release.get('result')=='PASS' and closed_release.get('release_outcome')=='ANALYSIS_COMPLETE')
    results[key]={'errors':closed_release.get('errors'),'outcome':closed_release.get('release_outcome'),'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    mutated_candidate=copy.deepcopy(closed)
    mutated_candidate['machine_findings'][0]['candidate_sha256']='0'*64
    mr=release_evaluate(target_plan,mutated_candidate,registry)
    key=f'fr_prp02:finding_binding:{case_id}:candidate_identity_mutation_blocks'
    ok=mr.get('result')=='FAIL' and any(x.get('type')=='MACHINE_FINDING_BINDING_DRIFT' and x.get('id')==target_claim for x in mr.get('errors') or [])
    results[key]={'errors':mr.get('errors'),'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    mutated_report=copy.deepcopy(closed)
    mutated_report['machine_findings'][0]['report_output_sha256']='f'*64
    mr=release_evaluate(target_plan,mutated_report,registry)
    key=f'fr_prp02:finding_binding:{case_id}:report_identity_mutation_blocks'
    ok=mr.get('result')=='FAIL' and any(x.get('type')=='MACHINE_FINDING_BINDING_DRIFT' and x.get('id')==target_claim for x in mr.get('errors') or [])
    results[key]={'errors':mr.get('errors'),'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

    mutated_review=copy.deepcopy(closed)
    finding_review=next(x for x in mutated_review['independent_reviews'] if x.get('claim_id')==target_claim)
    finding_review['claim_id']=target_claim+':MUTATED'
    mr=release_evaluate(target_plan,mutated_review,registry)
    key=f'fr_prp02:finding_binding:{case_id}:review_identity_mutation_blocks'
    ok=mr.get('result')=='FAIL' and any(
        x.get('type') in {'INDEPENDENT_REVIEW_INVALID','INDEPENDENT_REVIEW_REQUIRED'}
        for x in mr.get('errors') or [])
    results[key]={'errors':mr.get('errors'),'pass':ok}
    if not ok:errors.append({'case':key,'details':results[key]})

# Exact evidence location regression for the stale-line bug.
_direct_evidence=analyze_onec(fixtures/'query_surgery_direct_sink_bad.bsl')
_direct_finding=next((x for x in _direct_evidence.get('findings') or [] if x.get('type')=='HOMEGROWN_QUERY_STRUCTURE_PARSER'),{})
_boundary_item=next((x for x in _direct_finding.get('items') or [] if x.get('stage')=='BOUNDARY_SEARCH'),{})
key='fr_prp02:query_surgery_boundary_evidence_exact_line'
ok=(_boundary_item.get('line')==2 and _boundary_item.get('code')=='Позиция = СтрНайти(ВРег(Текст), " ИЗ ");')
results[key]={'item':_boundary_item,'pass':ok}
if not ok:errors.append({'case':key,'details':_boundary_item})

_build_finding_case(
    'HOMEGROWN_QUERY_STRUCTURE_PARSER',fixtures/'query_surgery_direct_sink_bad.bsl',
    'TOOLS/analyze_onec_bsl.py','STATIC:ONEC_BSL','HOMEGROWN_QUERY_STRUCTURE_PARSER',
    'QUERY','HOMEGROWN_QUERY_GRAMMAR_PARSER')
_build_finding_case(
    'QUERY_EXECUTE_SIDE_EFFECT_TRACE',fixtures/'query_execute_temp_producer_no_consumer_bad.bsl',
    'TOOLS/analyze_onec_bsl.py','STATIC:ONEC_BSL','QUERY_EXECUTE_SIDE_EFFECT_TRACE',
    'QUERY','QUERY_EXECUTE_SIDE_EFFECT_TRACE')
_build_finding_case(
    'INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW',fixtures/'owner_reuse_internal_pipeline_bad/Consumer_Module.bsl',
    'TOOLS/analyze_changeset_architecture.py','STATIC:CHANGESET_ARCHITECTURE','INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW',
    'STANDARD_PIPELINE_SEMANTIC_PRESERVATION','INTERNAL_PIPELINE_RECONSTRUCTION')

# Literal inventory bridges dynamically generated E2E IDs to the static LLM
# threat-matrix resolver.  The loop also proves every listed identity was actually
# emitted and passed by this run.
FR_PRP02_FINDING_REGRESSION_IDS=[
    'fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:release_only_target_blocks',
    'fr_prp02:finding_binding:QUERY_EXECUTE_SIDE_EFFECT_TRACE:release_only_target_blocks',
    'fr_prp02:finding_binding:INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW:release_only_target_blocks',
    'fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:compact_queue_exact_target',
    'fr_prp02:finding_binding:QUERY_EXECUTE_SIDE_EFFECT_TRACE:compact_queue_exact_target',
    'fr_prp02:finding_binding:INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW:compact_queue_exact_target',
    'fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:generic_semantic_cannot_close',
    'fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:candidate_identity_mutation_blocks',
    'fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:report_identity_mutation_blocks',
    'fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:review_identity_mutation_blocks',
    'fr_prp02:finding_binding:QUERY_EXECUTE_SIDE_EFFECT_TRACE:candidate_identity_mutation_blocks',
    'fr_prp02:finding_binding:QUERY_EXECUTE_SIDE_EFFECT_TRACE:report_identity_mutation_blocks',
    'fr_prp02:finding_binding:QUERY_EXECUTE_SIDE_EFFECT_TRACE:review_identity_mutation_blocks',
    'fr_prp02:finding_binding:INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW:candidate_identity_mutation_blocks',
    'fr_prp02:finding_binding:INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW:report_identity_mutation_blocks',
    'fr_prp02:finding_binding:INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW:review_identity_mutation_blocks',
]
_missing_finding_regressions=[
    rid for rid in FR_PRP02_FINDING_REGRESSION_IDS
    if results.get(rid,{}).get('pass') is not True
]
_fr_record('fr_prp02:finding_binding_literal_inventory_complete',
    not _missing_finding_regressions,_missing_finding_regressions)
_fr_record('fr_prp02:generic_semantic_exception_cannot_close_blocker',
    results.get('fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:generic_semantic_cannot_close',{}).get('pass') is True,
    results.get('fr_prp02:finding_binding:HOMEGROWN_QUERY_STRUCTURE_PARSER:generic_semantic_cannot_close'))

missing_adversarial=copy.deepcopy(proved); missing_adversarial['adversarial_cases']=[]
r=release_evaluate(plan,missing_adversarial,registry); key='release:r1_adversarial_cases_missing_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='ADVERSARIAL_CASES_MISSING' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
required_gate_na=copy.deepcopy(proved); required_gate=next(x for x in required_gate_na['gates'] if x['id']=='ADVERSARIAL_VALIDATION'); required_gate['status']='NOT_APPLICABLE'; required_gate['reason']='synthetic attempt to bypass a required gate'; required_gate['evidence']=[]
r=release_evaluate(plan,required_gate_na,registry); key='release:required_gate_na_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='GATE_NA_FOR_REQUIRED_PLAN' and x.get('id')=='ADVERSARIAL_VALIDATION' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# Proof-integrity regressions learned from whole-change-set review: written requirements must be gate-enforced.
missing_reverse=copy.deepcopy(proved); missing_reverse['code_to_standards']=[]
r=release_evaluate(plan,missing_reverse,registry); key='release:bidirectional_pass_missing_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='CODE_TO_STANDARDS_MISSING' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
reverse_na=copy.deepcopy(proved); pass_owner=next(x for x in reverse_na['rules'] if x['status']=='PASS'); reverse_row=next(x for x in reverse_na['standards_to_code'] if x['rule_id']==pass_owner['id']); reverse_row['status']='NOT_APPLICABLE'; reverse_row['reason']='synthetic attempt to hide a proven rule from reverse review'; reverse_row['evidence']=[]
r=release_evaluate(plan,reverse_na,registry); key='release:reverse_na_cannot_hide_pass_rule'; ok=(r['result']=='FAIL' and any(x['type']=='STANDARDS_TO_CODE_NA_FOR_PROVEN_RULE' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
forward_na=copy.deepcopy(proved); forward_na['code_to_standards'][0]['status']='NOT_APPLICABLE'; forward_na['code_to_standards'][0]['reason']='synthetic attempt to skip forward review for BSL source'; forward_na['code_to_standards'][0]['evidence']=[]
r=release_evaluate(plan,forward_na,registry); key='release:forward_na_with_code_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='CODE_TO_STANDARDS_NA_WITH_CODE_SOURCE' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
duplicate_rule=copy.deepcopy(proved); duplicate_rule['rules'].append(copy.deepcopy(duplicate_rule['rules'][0]))
r=release_evaluate(plan,duplicate_rule,registry); key='release:duplicate_rule_id_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='DUPLICATE_ROW_ID' and x.get('scope')=='rule' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
weak_evidence=copy.deepcopy(proved); pass_rule=next(x for x in weak_evidence['rules'] if x['status']=='PASS'); pass_rule['evidence']=[{'kind':'SEMANTIC'}]
r=release_evaluate(plan,weak_evidence,registry); key='release:nonconcrete_evidence_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='EVIDENCE_NOT_CONCRETE' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
missing_machine_link=copy.deepcopy(proved); machine_rule=next(x for x in missing_machine_link['rules'] if any(e.get('kind')=='MACHINE' for e in x.get('evidence',[]))); next(e for e in machine_rule['evidence'] if e.get('kind')=='MACHINE').pop('report_id',None)
r=release_evaluate(plan,missing_machine_link,registry); key='release:machine_evidence_requires_named_report'; ok=(r['result']=='FAIL' and any(x['type']=='MACHINE_EVIDENCE_REPORT_MISSING' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
failed_machine=copy.deepcopy(proved); failed_machine['machine_reports'][0]['result']='FAIL'
r=release_evaluate(plan,failed_machine,registry); key='release:failed_machine_report_cannot_prove_pass'; ok=(r['result']=='FAIL' and any(x['type'] in {'MACHINE_REPORT_RESULT_DECLARATION_MISMATCH','MACHINE_EVIDENCE_REPORT_NOT_PASS'} for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# Reused evidence is identity/fingerprint-bound. A dependency name alone or a changed dependency cannot be reused.
reuse_weak=copy.deepcopy(proved); reuse_weak['evidence_registry']=[{'id':'E:SYNTHETIC','kind':'SEMANTIC','ref':'synthetic reusable proof','dependencies':[{'kind':'CANDIDATE','id':plan['candidate_artifacts'][0]['logical_path']}]}]; reuse_weak['evidence_reuse']['reused_ids']=['E:SYNTHETIC']
r=release_evaluate(plan,reuse_weak,registry); key='release:reuse_dependency_requires_fingerprint'; ok=(r['result']=='FAIL' and any(x['type']=='EVIDENCE_DEPENDENCY_NOT_FINGERPRINT_BOUND' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
reuse_changed=copy.deepcopy(proved); dep={'kind':'CANDIDATE','id':plan['candidate_artifacts'][0]['logical_path'],'fingerprint':plan['candidate_artifacts'][0]['sha256']}; reuse_changed['evidence_registry']=[{'id':'E:SYNTHETIC','kind':'SEMANTIC','ref':'synthetic reusable proof','dependencies':[dep]}]; reuse_changed['evidence_reuse']['reused_ids']=['E:SYNTHETIC']; reuse_changed['evidence_reuse']['changed_dependencies']=[{'kind':'CANDIDATE','id':dep['id'],'fingerprint':'new fingerprint'}]
r=release_evaluate(plan,reuse_changed,registry); key='release:changed_dependency_invalidates_reuse'; ok=(r['result']=='FAIL' and any(x['type']=='REUSED_EVIDENCE_DEPENDENCY_CHANGED' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
reuse_wrong_hash=copy.deepcopy(proved); reuse_wrong_hash['evidence_registry']=[{'id':'E:SYNTHETIC','kind':'SEMANTIC','ref':'synthetic reusable proof','dependencies':[{'kind':'CANDIDATE','id':dep['id'],'fingerprint':'0'*64}]}]; reuse_wrong_hash['evidence_reuse']['reused_ids']=['E:SYNTHETIC']
r=release_evaluate(plan,reuse_wrong_hash,registry); key='release:reuse_fingerprint_must_match_plan'; ok=(r['result']=='FAIL' and any(x['type']=='EVIDENCE_DEPENDENCY_FINGERPRINT_DRIFT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# If the original candidate/baseline source is still accessible, release validates current bytes against the plan snapshot.
with tempfile.TemporaryDirectory() as td:
    current_file=Path(td)/'candidate.bsl'; current_file.write_bytes((fixtures/'call_contract_nonexport_caller.bsl').read_bytes())
    source_drift_plan=copy.deepcopy(plan); source_drift_ledger=copy.deepcopy(proved)
    sha=hashlib.sha256(current_file.read_bytes()).hexdigest(); source_drift_plan['candidate_artifacts'][0]['origin']=str(current_file); source_drift_plan['candidate_artifacts'][0]['sha256']=sha; source_drift_ledger['candidate_artifacts'][0]['origin']=str(current_file); source_drift_ledger['candidate_artifacts'][0]['sha256']=sha
    current_file.write_text(current_file.read_text(encoding='utf-8')+'\n// drift',encoding='utf-8')
    r=release_evaluate(source_drift_plan,source_drift_ledger,registry); key='release:current_candidate_bytes_drift_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='CANDIDATE_SOURCE_DRIFT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
    if not ok:errors.append({'case':key,'details':r})
with tempfile.TemporaryDirectory() as td:
    baseline_file=Path(td)/'baseline.bsl'; baseline_file.write_text('Procedure Baseline()\nEndProcedure',encoding='utf-8'); data=baseline_file.read_bytes(); snap={'path':str(baseline_file),'kind':'FILE','sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
    baseline_drift_plan=copy.deepcopy(plan); baseline_drift_ledger=copy.deepcopy(proved); baseline_drift_plan['baseline']=copy.deepcopy(snap); baseline_drift_ledger['baseline']=copy.deepcopy(snap)
    baseline_file.write_text('Procedure BaselineChanged()\nEndProcedure',encoding='utf-8')
    r=release_evaluate(baseline_drift_plan,baseline_drift_ledger,registry); key='release:current_baseline_bytes_drift_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='BASELINE_SOURCE_DRIFT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
    if not ok:errors.append({'case':key,'details':r})
with tempfile.TemporaryDirectory() as td:
    context_file=Path(td)/'context.json'; context_file.write_text('{"surface":"ONEC_ONLY"}',encoding='utf-8'); sha=hashlib.sha256(context_file.read_bytes()).hexdigest()
    context_drift_plan=copy.deepcopy(plan); context_drift_ledger=copy.deepcopy(proved); dep={'path':str(context_file),'sha256':sha,'surface':None,'risk':None}; context_drift_plan['project_context']=copy.deepcopy(dep); context_drift_ledger['project_context']=copy.deepcopy(dep)
    context_file.write_text('{"surface":"CROSS_SYSTEM"}',encoding='utf-8')
    r=release_evaluate(context_drift_plan,context_drift_ledger,registry); key='release:current_project_context_drift_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='PROJECT_CONTEXT_SOURCE_DRIFT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
    if not ok:errors.append({'case':key,'details':r})
with tempfile.TemporaryDirectory() as td:
    requirements_file=Path(td)/'requirements.json'; requirements_file.write_text('{"contract":1}',encoding='utf-8'); sha=hashlib.sha256(requirements_file.read_bytes()).hexdigest()
    requirements_drift_plan=copy.deepcopy(plan); requirements_drift_ledger=copy.deepcopy(proved); requirements_drift_plan['requirements']['path']=str(requirements_file); requirements_drift_plan['requirements']['sha256']=sha; requirements_drift_ledger['requirements']['path']=str(requirements_file); requirements_drift_ledger['requirements']['sha256']=sha
    requirements_file.write_text('{"contract":2}',encoding='utf-8')
    r=release_evaluate(requirements_drift_plan,requirements_drift_ledger,registry); key='release:current_requirements_contract_drift_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='REQUIREMENTS_SOURCE_DRIFT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
    if not ok:errors.append({'case':key,'details':r})
blocking_finding=copy.deepcopy(proved); blocking_finding['blocking_findings']=[{'id':'synthetic-owner-defect','type':'SAME_BUSINESS_RULE_MULTIPLE_OWNERS','ref':'FormA + FormB'}]
r=release_evaluate(plan,blocking_finding,registry); key='release:blocking_finding_cannot_be_hidden'; ok=(r['result']=='FAIL' and any(x['type']=='BLOCKING_FINDINGS_PRESENT' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# Clean machine output cannot close an unresolved discovery lens.
machine_zero=copy.deepcopy(proved)
machine_zero['machine_reports']=[{'id':'MACHINE:SYNTHETIC','tool':'synthetic','ref':'clean machine report with zero findings','high':0,'medium':0,'result':'PASS'}]
machine_zero['gap_discovery']['lenses'][0]={'id':'CHANGESET_COHERENCE','status':'EVIDENCE_REQUIRED','reason':'','evidence':[]}
r=release_evaluate(plan,machine_zero,registry); key='release:machine_zero_does_not_close_gap_discovery'; ok=(r['result']=='FAIL' and any(x['type']=='GAP_DISCOVERY_LENS_UNRESOLVED' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

unresolved_hypothesis=copy.deepcopy(proved)
unresolved_hypothesis['gap_discovery']['hypotheses']=[{
    'id':'synthetic-later-writer','lens':'TEMPORAL_STATE','statement':'a later reachable writer may overwrite the changed value',
    'source_anchors':['SyntheticModule.bsl:10 assignment','SyntheticModule.bsl:14 unresolved lifecycle call'],
    'counterexample':'invoke the lifecycle call after assigning a different value',
    'falsifier':'exact callee/call-graph evidence proves no same-field writer on the reachable path',
    'status':'EVIDENCE_REQUIRED','missing_evidence':'exact lifecycle callee source'
}]
r=release_evaluate(plan,unresolved_hypothesis,registry); key='release:unresolved_gap_hypothesis_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='GAP_HYPOTHESIS_BLOCKING' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

unanchored_hypothesis=copy.deepcopy(proved)
unanchored_hypothesis['gap_discovery']['hypotheses']=[{
    'id':'synthetic-unanchored','lens':'BOUNDARY_CONTRACT','statement':'some unknown callback may exist','source_anchors':[],
    'counterexample':'unknown','falsifier':'unknown','status':'DISPROVED','evidence':[{'kind':'SEMANTIC','ref':'synthetic'}]
}]
r=release_evaluate(plan,unanchored_hypothesis,registry); key='release:unanchored_gap_hypothesis_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='GAP_HYPOTHESIS_WITHOUT_SOURCE_ANCHORS' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

unrouted_owner=copy.deepcopy(proved)
unrouted_owner['gap_discovery']['hypotheses']=[{
    'id':'synthetic-unrouted-owner','lens':'IDENTITY_CARDINALITY','statement':'query cardinality may violate the consumer contract',
    'source_anchors':['SyntheticModule.bsl:20 consumer expects one row'],
    'counterexample':'the query returns two rows for one business key',
    'falsifier':'source and runtime evidence prove uniqueness for the exact key',
    'status':'COVERED_BY_EXISTING_RULE','existing_rule_id':'QUERY',
    'evidence':[{'kind':'SEMANTIC','ref':'registry search found QUERY but routing fixture did not activate it'}]
}]
r=release_evaluate(plan,unrouted_owner,registry); key='release:unrouted_existing_rule_cannot_close_hypothesis'; ok=(r['result']=='FAIL' and any(x['type']=='GAP_HYPOTHESIS_OWNER_NOT_ROUTED' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})
artifact_gap=copy.deepcopy(proved)
artifact_gap['artifact_requests']=[{'id':'subscription-gap','status':'REQUEST_REQUIRED','blocking':True,'claim':'prove event → subscription → handler reachability','artifacts':['EventSubscriptions metadata/XML','handler common module']}]
r=release_evaluate(plan,artifact_gap,registry); key='release:required_artifact_not_requested_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='REQUIRED_ARTIFACT_NOT_REQUESTED' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

artifact_requested=copy.deepcopy(proved)
artifact_requested['artifact_requests']=[{'id':'subscription-gap','status':'REQUESTED','blocking':True,'claim':'prove event → subscription → handler reachability','artifacts':['EventSubscriptions metadata/XML','handler common module'],'request_text':'Please provide EventSubscriptions metadata/XML and the handler common module.'}]
r=release_evaluate(plan,artifact_requested,registry); key='release:requested_blocking_artifact_blocks_until_received'; ok=(r['result']=='FAIL' and any(x['type']=='REQUIRED_ARTIFACT_PENDING' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

artifact_provided=copy.deepcopy(proved)
artifact_provided['artifact_requests']=[{'id':'subscription-gap','status':'PROVIDED','blocking':True,'claim':'prove event → subscription → handler reachability','artifacts':['EventSubscriptions metadata/XML','handler common module'],'evidence':[{'kind':'SOURCE_REQUIRED','ref':'synthetic subscription evidence'}]}]
r=release_evaluate(plan,artifact_provided,registry); key='release:provided_artifact_allows_proven'; ok=(r['result']=='PASS' and r['release_outcome']=='PROVEN'); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

noe=copy.deepcopy(proved)
row=next(x for x in noe['rules'] if x['status']=='PASS'); row['evidence']=[]
r=release_evaluate(plan,noe,registry); key='release:pass_without_evidence_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='PASS_WITHOUT_EVIDENCE' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

pending_extraction=copy.deepcopy(proved)
pending_extraction['knowledge_extraction']={'outcome':'EVIDENCE_PENDING','reason':'','project_context_updates':[],'items':[]}
r=release_evaluate(plan,pending_extraction,registry); key='release:knowledge_extraction_pending_blocks'; ok=(r['result']=='FAIL' and any(x['type']=='KNOWLEDGE_EXTRACTION_PENDING' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

pending_ledger=copy.deepcopy(proved)
rr=next(x for x in pending_ledger['rules'] if x['id']=='RUNTIME_EVIDENCE')
rr['status']='RUNTIME_PENDING'; rr['reason']='synthetic runtime pending'; rr['evidence']=[{'kind':'SEMANTIC','ref':'non-runtime review done'}]
rr['checks'][0]['status']='EVIDENCE_REQUIRED'; rr['checks'][0]['evidence']=[]
r=release_evaluate(plan,pending_ledger,registry); key='release:pending_does_not_hide_checks'; ok=(r['result']=='FAIL' and any(x['type']=='CHECK_BLOCKING_OR_UNRESOLVED' for x in r['errors'])); results[key]={'outcome':r['release_outcome'],'pass':ok}
if not ok:errors.append({'case':key,'details':r})

# Minimal-change is a real Tier-0 release obligation, not only prose in SKILL.md.
minimal_rule=next((x for x in registry.get('rules',[]) if x.get('id')=='MINIMAL_COHERENT_CHANGE'),None)
minimal_checks={x.get('id') for x in (minimal_rule or {}).get('checks',[])}
minimal_expected={'MINIMAL_COHERENT_CHANGE_T01','MINIMAL_COHERENT_CHANGE_T02','MINIMAL_COHERENT_CHANGE_T03','MINIMAL_COHERENT_CHANGE_T04','UNJUSTIFIED_CHANGE_SURFACE_EXPANSION','OPPORTUNISTIC_REFACTOR_IN_TASK_CHANGE','PARALLEL_MECHANISM_WHEN_EXISTING_EXTENSION_POINT_EXISTS','LOC_MINIMIZATION_DAMAGES_COHESION'}
key='registry:minimal_coherent_change_contract'; ok=bool(minimal_rule and minimal_rule.get('tier')==0 and minimal_rule.get('severity')=='BLOCKING' and minimal_rule.get('always_disposition') is True and minimal_expected<=minimal_checks and 'MINIMAL_COHERENT_CHANGE' in registry.get('rule_order',[])); results[key]={'pass':ok,'checks':sorted(minimal_checks)}
if not ok:errors.append({'case':key,'details':minimal_rule})

# Generated views must match the registry exactly.
for rel,text in render_generated_views(registry).items():
    actual=(root/rel).read_text(encoding='utf-8-sig')
    if actual!=text:errors.append({'case':'generated_view_drift','file':rel})

semantic_count=sum(1 for rule in registry['rules'] for check in rule.get('checks',[]) if check.get('kind') in {'SEMANTIC_REGRESSION','META'})
requirements_semantic_count=sum(1 for rule in registry.get('requirements_rules',[]) for check in rule.get('checks',[]) if check.get('kind') in {'SEMANTIC_REGRESSION','META'})
out={'result':'PASS' if not errors else 'FAIL','machine_results':results,'semantic_cases_registered':semantic_count,'requirements_semantic_cases_registered':requirements_semantic_count,'rules_registered':len(registry['rules']),'requirements_rules_registered':len(registry.get('requirements_rules',[])),'checks_registered':sum(len(r.get('checks',[])) for r in registry['rules']),'requirements_checks_registered':sum(len(r.get('checks',[])) for r in registry.get('requirements_rules',[])),'errors':errors}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
