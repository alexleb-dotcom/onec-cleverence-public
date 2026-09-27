#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import copy
import json
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'TESTS/fixtures'
sys.path.insert(0,str(ROOT/'TOOLS'))

from evidence_source_policy import validate_ledger
from build_review_plan import build_plan
from build_validation_ledger import build_ledger
from release_gate import evaluate as release_evaluate
from release_gate_core import evaluate as core_evaluate
from release_gate_hardening import route_fingerprint, validate_trust_boundary
from rule_registry import load_registry

results={}; errors=[]

def record(case,ok,details):
    results[case]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":case,"details":details})

cases={
    'illustrative_pattern':'PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl',
    'illustrative_pattern_dot':'./PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl',
    'illustrative_pattern_absolute':str(ROOT/'PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl'),
    'illustrative_pattern_windows':r'C:\work\onec-cleverence\PATTERNS\ONEC\CALL_CONTRACT_ADAPTER\good.bsl',
    'illustrative_pattern_github':'https://github.com/example/onec-cleverence/blob/main/PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl',
    'illustrative_pattern_archive':'bundle.zip!/PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl',
    'discovery_catalog':'REFERENCE/CATALOGS/bsp_discovery.json',
    'test_fixture':'TESTS/fixtures/call_signature_good.bsl',
}
for cid,ref in cases.items():
    report=validate_ledger({'rules':[{'id':'R','evidence':[{'kind':'SEMANTIC','ref':ref}]}]})
    kinds={x.get('role') for x in report['errors']}
    record(f'{cid}_cannot_be_evidence',report['result']=='FAIL' and bool(kinds),report)

exact=validate_ledger({'rules':[{'id':'R','evidence':[{'kind':'SEMANTIC','ref':'target/CommonModules/ExactOwner/Ext/Module.bsl: Procedure ExactApi'}]}]})
record('exact_target_ref_remains_eligible',exact['result']=='PASS',exact)

# Provenance survives a plain local copy/rename when the bytes are exactly a known
# non-proof artifact. This is intentionally stricter than spelling-only checks.
with tempfile.TemporaryDirectory() as td:
    copied=Path(td)/'renamed-owner-source.bsl'
    shutil.copyfile(ROOT/'PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl',copied)
    report=validate_ledger({'rules':[{'id':'R','evidence':[{'kind':'SEMANTIC','ref':str(copied)}]}]})
    record(
        'renamed_pattern_copy_keeps_nonproof_role',
        report['result']=='FAIL' and any(x.get('matched_by')=='CONTENT_FINGERPRINT' and x.get('role')=='ILLUSTRATIVE_PATTERN' for x in report['errors']),
        report,
    )

# End-to-end: even if a model writes a pattern path into a normal SEMANTIC evidence row,
# both the canonical wrapper and direct core import must remain BLOCKED.
registry=load_registry()
plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'],analysis_only=True)
ledger=copy.deepcopy(build_ledger(plan,registry))
first_rule=ledger['rules'][0]
first_rule['status']='PASS'
first_rule['evidence']=[{'kind':'SEMANTIC','ref':'./PATTERNS/ONEC/CALL_CONTRACT_ADAPTER/good.bsl'}]
report=release_evaluate(plan,ledger,registry)
record(
    'strict_release_blocks_pattern_laundering',
    report['result']=='FAIL' and report['release_outcome']=='BLOCKED'
    and any(x.get('type')=='NON_PROOF_ARTIFACT_USED_AS_EVIDENCE' and x.get('role')=='ILLUSTRATIVE_PATTERN' for x in report.get('errors',[])),
    {'outcome':report.get('release_outcome'),'policy':report.get('evidence_source_policy'),'policy_errors':[x for x in report.get('errors',[]) if x.get('type')=='NON_PROOF_ARTIFACT_USED_AS_EVIDENCE']},
)
core_report=core_evaluate(plan,ledger,registry)
record(
    'core_cannot_bypass_source_policy',
    core_report['result']=='FAIL' and core_report['release_outcome']=='BLOCKED'
    and any(x.get('type')=='NON_PROOF_ARTIFACT_USED_AS_EVIDENCE' for x in core_report.get('errors',[])),
    {'outcome':core_report.get('release_outcome'),'policy':core_report.get('evidence_source_policy')},
)

# Routed N/A is no longer a free-text escape. Child structure remains an obligation.
na_plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'],analysis_only=True)
na_ledger=build_ledger(na_plan,registry)
call_route=next(x for x in na_plan['rules'] if x['id']=='CALL_CONTRACT')
call_row=next(x for x in na_ledger['rules'] if x['id']=='CALL_CONTRACT')
call_row['status']='NOT_APPLICABLE'; call_row['reason']='free-text shortcut'; call_row['checks']=[]
trust=validate_trust_boundary(na_plan,na_ledger,registry)
record(
    'routed_rule_na_requires_structured_rebuttal_and_children',
    any(x.get('type')=='ROUTED_RULE_NA_WITHOUT_REBUTTAL' and x.get('id')=='CALL_CONTRACT' for x in trust['errors'])
    and any(x.get('type')=='NA_RULE_CHECK_STRUCTURE_DRIFT' and x.get('id')=='CALL_CONTRACT' for x in trust['errors']),
    trust,
)

# A false-positive disposition remains possible, but it must be bound to the exact
# routed signal set and preserve every child check as an explicit N/A disposition.
positive_plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'],analysis_only=True)
positive_ledger=build_ledger(positive_plan,registry)
positive_route=next(x for x in positive_plan['rules'] if x['id']=='CALL_CONTRACT')
positive_row=next(x for x in positive_ledger['rules'] if x['id']=='CALL_CONTRACT')
positive_row['status']='NOT_APPLICABLE'; positive_row['reason']='reviewed false-positive routing signal'
positive_row['applicability_rebuttal']={
    'status':'FALSE_POSITIVE',
    'route_fingerprint':route_fingerprint(positive_route),
    'rebutted_signals':positive_route.get('detected_by') or [],
    'reason':'fixture intentionally rebuts the routed signal for trust-boundary mechanics only',
    'evidence':[{'kind':'SEMANTIC','ref':'review:fixture false-positive applicability adjudication'}],
}
for child in positive_row['checks']:
    child['status']='NOT_APPLICABLE'; child['reason']='parent route adjudicated false positive'
trust=validate_trust_boundary(positive_plan,positive_ledger,registry)
record(
    'structured_false_positive_rebuttal_is_allowed',
    not any(x.get('type','').startswith('NA_') or x.get('type')=='ROUTED_RULE_NA_WITHOUT_REBUTTAL' for x in trust['errors']),
    trust,
)

# Missing bound bytes fail closed. A moved-but-byte-identical local source can be
# supplied through portable_origin, so moving a review bundle is not itself a failure.
with tempfile.TemporaryDirectory() as td:
    source=Path(td)/'candidate.bsl'; shutil.copyfile(FIXTURES/'call_contract_nonexport_caller.bsl',source)
    moved=Path(td)/'bundle'/'candidate.bsl'; moved.parent.mkdir(); shutil.copyfile(source,moved)
    source_plan=build_plan([source],analysis_only=True); source_ledger=build_ledger(source_plan,registry)
    source.unlink()
    missing=validate_trust_boundary(source_plan,source_ledger,registry)
    record(
        'missing_candidate_bytes_block',
        any(x.get('type')=='CANDIDATE_SOURCE_UNAVAILABLE' for x in missing['errors']),
        missing,
    )
    source_plan['candidate_artifacts'][0]['portable_origin']=str(moved)
    portable=validate_trust_boundary(source_plan,source_ledger,registry)
    record(
        'portable_identical_candidate_bytes_are_accepted',
        not any(x.get('type') in {'CANDIDATE_SOURCE_UNAVAILABLE','CANDIDATE_PORTABLE_SOURCE_DRIFT','CANDIDATE_SOURCE_DRIFT'} for x in portable['errors']),
        portable,
    )

# A required adversarial gate cannot be satisfied by creating only N/A cases.
adversarial_plan=build_plan([FIXTURES/'call_contract_nonexport_caller.bsl'])
adversarial_ledger=build_ledger(adversarial_plan,registry)
adversarial_ledger['adversarial_cases']=[{'id':'ADV:NA','case':'counterexample placeholder','status':'NOT_APPLICABLE','reason':'not attempted','evidence':[]}]
trust=validate_trust_boundary(adversarial_plan,adversarial_ledger,registry)
record(
    'all_adversarial_na_does_not_satisfy_required_attempt',
    any(x.get('type')=='ADVERSARIAL_CASE_ATTEMPT_MISSING' for x in trust['errors']),
    trust,
)

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
