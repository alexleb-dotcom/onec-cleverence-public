#!/usr/bin/env python3
from pathlib import Path
import copy, json, sys

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'TESTS/fixtures'
sys.path.insert(0,str(ROOT/'TOOLS'))

from build_review_plan import build_plan
from build_validation_ledger import build_ledger
from proof_contract import rule_claim_id, check_claim_id, validate_obligation_evidence
from release_gate_core import evaluate
from rule_registry import load_registry

registry=load_registry(); errors=[]; results={}

def record(cid,ok,details=None):
    results[cid]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":cid,"details":details})

# Claim ids are deterministic, unique and exercised for every registered check.
claim_ids=[]; exercised=0
for rule in registry.get('rules',[]):
    rid=rule['id']; rclaim=rule_claim_id(rid); claim_ids.append(rclaim)
    local=[]
    validate_obligation_evidence([{'kind':next(iter(rule.get('evidence_modes') or ['SEMANTIC'])),'ref':'synthetic','claim_id':'WRONG'}],rclaim,rule.get('evidence_modes',[]),local,'rule',rid,require_primary=True)
    if any(x.get('type')=='PROOF_CLAIM_BINDING_MISMATCH' for x in local):exercised+=1
    for check in rule.get('checks',[]):
        cid=check['id']; claim=check_claim_id(rid,cid); claim_ids.append(claim); local=[]
        allowed=rule.get('evidence_modes',[]); kind=next(iter(allowed or ['SEMANTIC']))
        validate_obligation_evidence([{'kind':kind,'ref':'synthetic','claim_id':'WRONG'}],claim,allowed,local,'check',f'{rid}:{cid}',require_primary=True)
        if any(x.get('type')=='PROOF_CLAIM_BINDING_MISMATCH' for x in local):exercised+=1
record('phase3:registered_claims_unique',len(claim_ids)==len(set(claim_ids)),{'registered':len(claim_ids),'unique':len(set(claim_ids))})
record('phase3:registered_claim_binding_executed',exercised==len(claim_ids),{'registered':len(claim_ids),'exercised':exercised})

# Attach-only/supporting receipt semantics always demote intrinsically-primary kinds.
support_claim='CHECK:TEST:SUPPORT_ONLY'
for cid,evidence in (
    ('phase3:supporting_only_flag_not_primary',{'kind':'SOURCE_REQUIRED','ref':'source','claim_id':support_claim,'supporting_only':True}),
    ('phase3:supporting_role_not_primary',{'kind':'SOURCE_REQUIRED','ref':'source','claim_id':support_claim,'proof_role':'SUPPORTING_ONLY'}),
    ('phase3:attach_only_mode_not_primary',{'kind':'SOURCE_REQUIRED','ref':'source','claim_id':support_claim,'verification_mode':'ATTACH_ONLY'}),
    ('phase3:receipt_without_predicate_not_primary',{'kind':'SOURCE_REQUIRED','ref':'source','claim_id':support_claim,'receipt_id':'E:ATTACH'}),
    ('phase3:verifier_supporting_annotation_not_primary',{'kind':'SEMANTIC','ref':'source','claim_id':support_claim,'_verifier_proof_role':'SUPPORTING_ONLY'}),
):
    local=[]
    result=validate_obligation_evidence([evidence],support_claim,[evidence['kind']],local,'check','TEST:SUPPORT_ONLY',require_primary=True)
    record(cid,result['primary_count']==0 and any(x.get('type')=='ATTACH_ONLY_EVIDENCE_CANNOT_CLOSE_CLAIM' for x in local) and any(x.get('type')=='PRIMARY_PROOF_MISSING' for x in local),local)

# Generic analyzer capability may support a claim but may not become its primary semantic proof.
local=[]; claim='CHECK:TEST:GENERIC_MACHINE'
validate_obligation_evidence([{'kind':'MACHINE','ref':'machine','claim_id':claim,'property_id':'STATIC:ONEC_BSL','supporting_only':True}],claim,['MACHINE'],local,'check','TEST:GENERIC_MACHINE',require_primary=True)
record('phase3:generic_machine_support_not_primary',any(x.get('type')=='PRIMARY_PROOF_MISSING' for x in local),local)

# A generic machine capability must be explicitly labeled supporting-only.
local=[]
validate_obligation_evidence([{'kind':'MACHINE','ref':'machine','claim_id':claim,'property_id':'STATIC:ONEC_BSL'}],claim,['MACHINE'],local,'check','TEST:GENERIC_MACHINE',require_primary=False)
record('phase3:generic_machine_requires_supporting_label',any(x.get('type')=='GENERIC_MACHINE_PROPERTY_MUST_BE_SUPPORTING' for x in local),local)

# Runtime observation must prove the exact claim property, not merely any passing runtime case.
local=[]; runtime_claim='CHECK:TEST:RUNTIME'
validate_obligation_evidence([{'kind':'RUNTIME','ref':'runtime','claim_id':runtime_claim,'property_id':'RUNTIME:OTHER'}],runtime_claim,['RUNTIME'],local,'check','TEST:RUNTIME',require_primary=True)
record('phase3:runtime_property_claim_mismatch_blocks',any(x.get('type')=='RUNTIME_EVIDENCE_CLAIM_PROPERTY_MISMATCH' for x in local) and any(x.get('type')=='PRIMARY_PROOF_MISSING' for x in local),local)
local=[]
validate_obligation_evidence([{'kind':'RUNTIME','ref':'runtime','claim_id':runtime_claim,'property_id':runtime_claim}],runtime_claim,['RUNTIME'],local,'check','TEST:RUNTIME',require_primary=True)
record('phase3:runtime_exact_property_can_be_primary',not local,local)

# Evidence bound to one obligation cannot be reused to close another obligation.
local=[]; first='CHECK:TEST:A'; second='CHECK:TEST:B'
evidence={'kind':'SEMANTIC','ref':'source:exact','claim_id':first}
validate_obligation_evidence([evidence],second,['SEMANTIC'],local,'check','TEST:B',require_primary=True)
record('phase3:cross_claim_evidence_reuse_blocks',any(x.get('type')=='PROOF_CLAIM_BINDING_MISMATCH' for x in local),local)

# Parent evidence mode constrains child evidence kind.
local=[]; source_claim='CHECK:SOURCE_FIRST:SOURCE_FIRST_T01'
validate_obligation_evidence([{'kind':'SEMANTIC','ref':'semantic','claim_id':source_claim}],source_claim,['SOURCE_REQUIRED'],local,'check','SOURCE_FIRST:SOURCE_FIRST_T01',require_primary=True)
record('phase3:check_kind_inherits_rule_contract',any(x.get('type')=='EVIDENCE_KIND_NOT_ALLOWED_FOR_OBLIGATION' for x in local),local)

# Integration: release gate recomputes expected row claim ids rather than trusting ledger text.
plan=build_plan([FIX/'call_contract_nonexport_caller.bsl'],analysis_only=True)
ledger=build_ledger(plan,registry)
first_rule=ledger['rules'][0]; first_rule['claim_id']='RULE:OTHER'
r=evaluate(plan,ledger,registry)
record('phase3:rule_claim_row_tamper_blocks',any(x.get('type')=='PROOF_CLAIM_ROW_ID_DRIFT' and x.get('scope')=='rule' for x in r['errors']),[x for x in r['errors'] if x.get('type')=='PROOF_CLAIM_ROW_ID_DRIFT'])
ledger=build_ledger(plan,registry); first_rule=ledger['rules'][0]; first_rule['checks'][0]['claim_id']='CHECK:OTHER:OTHER'
r=evaluate(plan,ledger,registry)
record('phase3:check_claim_row_tamper_blocks',any(x.get('type')=='PROOF_CLAIM_ROW_ID_DRIFT' and x.get('scope')=='check' for x in r['errors']),[x for x in r['errors'] if x.get('type')=='PROOF_CLAIM_ROW_ID_DRIFT'])

# Distinguish states: all checks are registered and gate-binding-exercised here;
# this is not a claim that every domain semantic has a dedicated behavioral fixture.
registered_checks=sum(len(x.get('checks',[])) for x in registry.get('rules',[]))
behavioral_refs=sum(1 for rule in registry.get('rules',[]) for ref in rule.get('regression',{}).get('enforcement_cases',[]) if not str(ref).startswith('check:'))
out={
    'result':'PASS' if not errors else 'FAIL',
    'errors':errors,
    'results':results,
    'coverage_states':{
        'registered_checks':registered_checks,
        'gate_claim_binding_executed':registered_checks,
        'rules_with_or_without_behavioral_refs_are_not_conflated':True,
        'non_check_behavioral_regression_refs':behavioral_refs,
        'note':'Gate enforcement coverage is not equivalent to dedicated domain-behavior sampling.'
    }
}
print(json.dumps(out,ensure_ascii=False,indent=2)); raise SystemExit(0 if not errors else 2)
