#!/usr/bin/env python3
"""Fail-closed gate for the pre-code functional requirements contract.

The gate treats coverage structure as proof: required contract fields/routes/checks
cannot be deleted to obtain READY, duplicate IDs cannot collapse through dicts, and
PASS/KNOWN evidence must be concrete {kind, ref} records.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, re, sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from rule_registry import ROOT, load_registry, RISK_RANK

ALLOWED_EVIDENCE_KINDS={'MACHINE','SOURCE_REQUIRED','SEMANTIC','RUNTIME'}


def _text(v):return isinstance(v,str) and bool(v.strip())
def _nonempty(v):return v is not None and v!='' and v!=[] and v!={}
def _concrete_evidence(items):return bool(items) and all(isinstance(x,dict) and _text(x.get('kind')) and _text(x.get('ref')) for x in items)


def _validate_evidence(items,errors,scope,rid):
    if not items:errors.append({'type':'PASS_WITHOUT_EVIDENCE','scope':scope,'id':rid});return
    if not _concrete_evidence(items):errors.append({'type':'EVIDENCE_NOT_CONCRETE','scope':scope,'id':rid});return
    for index,item in enumerate(items):
        kind=str(item.get('kind','')).upper()
        if kind not in ALLOWED_EVIDENCE_KINDS:errors.append({'type':'UNKNOWN_EVIDENCE_KIND','scope':scope,'id':rid,'index':index,'kind':kind})


def _index_rows(rows,key,scope,errors):
    result={}
    for index,row in enumerate(rows or []):
        if not isinstance(row,dict):errors.append({'type':'ROW_NOT_OBJECT','scope':scope,'index':index});continue
        rid=row.get(key)
        if not _text(rid):errors.append({'type':'ROW_WITHOUT_ID','scope':scope,'index':index,'key':key});continue
        if rid in result:errors.append({'type':'DUPLICATE_ROW_ID','scope':scope,'id':rid});continue
        result[rid]=row
    return result


def _validate_source_snapshots(rows,errors):
    seen=set()
    for index,row in enumerate(rows or []):
        if not isinstance(row,dict):errors.append({'type':'REQUIREMENTS_SOURCE_NOT_OBJECT','index':index});continue
        path=row.get('path'); expected=row.get('sha256')
        if not _text(path) or not isinstance(expected,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',expected):
            errors.append({'type':'REQUIREMENTS_SOURCE_IDENTITY_INVALID','index':index,'path':path,'sha256':expected});continue
        if path in seen:errors.append({'type':'REQUIREMENTS_SOURCE_DUPLICATE','path':path});continue
        seen.add(path); current=Path(path)
        if current.is_file():
            actual=hashlib.sha256(current.read_bytes()).hexdigest()
            if actual.lower()!=expected.lower():errors.append({'type':'REQUIREMENTS_SOURCE_DRIFT','path':path,'expected':expected,'actual':actual})


def _validate_task_input(task_input, sources, errors):
    if not isinstance(task_input,dict):
        errors.append({'type':'REQUIREMENTS_TASK_INPUT_MISSING'});return
    text=task_input.get('text'); expected=task_input.get('sha256'); size=task_input.get('size')
    if not isinstance(text,str):errors.append({'type':'REQUIREMENTS_TASK_TEXT_INVALID'});return
    data=text.encode('utf-8'); actual=hashlib.sha256(data).hexdigest()
    if expected!=actual:errors.append({'type':'REQUIREMENTS_TASK_INPUT_HASH_DRIFT','expected':expected,'actual':actual})
    if size!=len(data):errors.append({'type':'REQUIREMENTS_TASK_INPUT_SIZE_DRIFT','expected':size,'actual':len(data)})
    if not text.strip() and not sources:errors.append({'type':'REQUIREMENTS_INPUT_EMPTY'})


def _validate_evidence_requests(rows, errors, assumptions):
    seen=set()
    for i,row in enumerate(rows or []):
        rid=row.get('id') or f'index:{i}'
        if rid in seen:errors.append({'type':'DUPLICATE_EVIDENCE_REQUEST_ID','id':rid});continue
        seen.add(rid)
        status=row.get('status','REQUEST_REQUIRED'); blocking=bool(row.get('blocking',True)); artifacts=row.get('artifacts') or []; claim=row.get('claim')
        if status in {'REQUEST_REQUIRED','REQUESTED','UNAVAILABLE','DECLINED'} and (not artifacts or not _text(claim)):
            errors.append({'type':'EVIDENCE_REQUEST_INCOMPLETE','id':rid,'status':status})
        if status=='REQUEST_REQUIRED':errors.append({'type':'REQUIRED_ARTIFACT_NOT_REQUESTED','id':rid,'claim':claim})
        elif status=='REQUESTED':
            if not _text(row.get('request_text')):errors.append({'type':'EVIDENCE_REQUEST_WITHOUT_USER_REQUEST','id':rid})
            if blocking:errors.append({'type':'REQUIRED_ARTIFACT_PENDING','id':rid,'claim':claim})
            else:assumptions.append({'type':'NONBLOCKING_ARTIFACT_PENDING','id':rid,'claim':claim})
        elif status in {'UNAVAILABLE','DECLINED'}:
            if not _text(row.get('reason')):errors.append({'type':'EVIDENCE_REQUEST_STATUS_WITHOUT_REASON','id':rid,'status':status})
            if blocking:errors.append({'type':'REQUIRED_ARTIFACT_UNAVAILABLE','id':rid,'status':status,'claim':claim})
            else:assumptions.append({'type':'NONBLOCKING_ARTIFACT_UNAVAILABLE','id':rid,'status':status,'claim':claim})
        elif status=='PROVIDED':_validate_evidence(row.get('evidence'),errors,'requirements_artifact_request',rid)
        elif status=='RESOLVED_NOT_NEEDED':
            if not _text(row.get('reason')):errors.append({'type':'RESOLVED_NOT_NEEDED_WITHOUT_REASON','id':rid})
        elif status not in {'REQUEST_REQUIRED','REQUESTED','UNAVAILABLE','DECLINED','PROVIDED','RESOLVED_NOT_NEEDED'}:
            errors.append({'type':'UNKNOWN_EVIDENCE_REQUEST_STATUS','id':rid,'status':status})



def _validate_requirements_claims(contract, spec, errors, purpose):
    claims=_index_rows(contract.get('claims') or [],'id','requirements_claim',errors)
    if purpose=='REQUIREMENTS_ARTIFACT' and not claims:
        errors.append({'type':'REQUIREMENTS_CLAIMS_MISSING'})
        return claims
    allowed_provenance=set(spec.get('provenance',[])); allowed_dispositions=set(spec.get('dispositions',[]))
    confirmed_provenance={'USER_CONFIRMED','SOURCE_OBSERVED','TYPICAL_RELEASE_PROVEN'}
    for cid,row in claims.items():
        statement=row.get('statement'); provenance=row.get('provenance'); disposition=row.get('disposition')
        if not _text(statement):errors.append({'type':'REQUIREMENTS_CLAIM_WITHOUT_STATEMENT','id':cid})
        if provenance not in allowed_provenance:errors.append({'type':'UNKNOWN_REQUIREMENTS_CLAIM_PROVENANCE','id':cid,'provenance':provenance})
        if disposition not in allowed_dispositions:errors.append({'type':'UNKNOWN_REQUIREMENTS_CLAIM_DISPOSITION','id':cid,'disposition':disposition})
        if provenance=='PROPOSED_SOLUTION' and disposition in {'CONFIRMED_REQUIREMENT','DERIVED_REQUIREMENT'}:
            errors.append({'type':'PROPOSED_SOLUTION_AS_CONFIRMED_REQUIREMENT','id':cid})
        if disposition=='CONFIRMED_REQUIREMENT':
            if provenance not in confirmed_provenance:
                errors.append({'type':'CONFIRMED_REQUIREMENT_PROVENANCE_INVALID','id':cid,'provenance':provenance})
            _validate_evidence(row.get('evidence'),errors,'requirements_claim',cid)
        elif disposition=='DERIVED_REQUIREMENT':
            if provenance!='DERIVED_WITH_EVIDENCE':errors.append({'type':'DERIVED_REQUIREMENT_PROVENANCE_INVALID','id':cid,'provenance':provenance})
            _validate_evidence(row.get('evidence'),errors,'requirements_claim',cid)
        elif disposition=='PROPOSAL':
            if provenance!='PROPOSED_SOLUTION':errors.append({'type':'PROPOSAL_PROVENANCE_INVALID','id':cid,'provenance':provenance})
        elif disposition=='OPEN':
            if provenance!='OPEN':errors.append({'type':'OPEN_CLAIM_PROVENANCE_INVALID','id':cid,'provenance':provenance})
            if row.get('blocking',True):errors.append({'type':'BLOCKING_OPEN_REQUIREMENTS_CLAIM','id':cid})
        elif disposition in {'REJECTED','SUPERSEDED'} and not _text(row.get('reason')):
            errors.append({'type':'TERMINAL_REQUIREMENTS_CLAIM_WITHOUT_REASON','id':cid,'disposition':disposition})
        if provenance=='TYPICAL_RELEASE_PROVEN' and not any(str(e.get('kind','')).upper()=='SOURCE_REQUIRED' for e in row.get('evidence',[]) if isinstance(e,dict)):
            errors.append({'type':'TYPICAL_RELEASE_CLAIM_WITHOUT_RELEASE_SOURCE','id':cid})
        deps=row.get('depends_on') or []
        if not isinstance(deps,list):
            errors.append({'type':'REQUIREMENTS_CLAIM_DEPENDENCIES_INVALID','id':cid}); continue
        if len(deps)!=len(set(deps)):errors.append({'type':'REQUIREMENTS_CLAIM_DEPENDENCY_DUPLICATE','id':cid})
        for dep in deps:
            if dep==cid:errors.append({'type':'REQUIREMENTS_CLAIM_SELF_DEPENDENCY','id':cid})
            elif dep not in claims:errors.append({'type':'REQUIREMENTS_CLAIM_DEPENDENCY_MISSING','id':cid,'depends_on':dep})
    return claims

def _validate_revision_events(contract, claims, errors):
    events=_index_rows(contract.get('revision_events') or [],'id','requirements_revision_event',errors)
    changed_to_event={}
    for eid,row in events.items():
        changed=row.get('changed_claim_ids') or []; invalidated=row.get('invalidated_claim_ids') or []; revalidated=row.get('revalidated_claim_ids') or []
        if not changed or not _text(row.get('reason')):errors.append({'type':'REQUIREMENTS_REVISION_EVENT_INCOMPLETE','id':eid})
        for field,ids in [('changed_claim_ids',changed),('invalidated_claim_ids',invalidated),('revalidated_claim_ids',revalidated)]:
            if not isinstance(ids,list):errors.append({'type':'REQUIREMENTS_REVISION_IDS_INVALID','id':eid,'field':field});continue
            for cid in ids:
                if cid not in claims:errors.append({'type':'REQUIREMENTS_REVISION_UNKNOWN_CLAIM','id':eid,'field':field,'claim_id':cid})
        for cid in changed:changed_to_event.setdefault(cid,[]).append((eid,set(invalidated),set(revalidated)))
        if revalidated:_validate_evidence(row.get('evidence'),errors,'requirements_revision_event',eid)
    for cid,row in claims.items():
        if row.get('disposition')=='SUPERSEDED' and cid not in changed_to_event:
            errors.append({'type':'SUPERSEDED_CLAIM_WITHOUT_REVISION_EVENT','id':cid})
    for changed_id,event_rows in changed_to_event.items():
        impacted={cid for cid,row in claims.items() if changed_id in (row.get('depends_on') or [])}
        covered=set()
        for _,invalidated,revalidated in event_rows:covered |= invalidated | revalidated
        for cid in sorted(impacted-covered):
            errors.append({'type':'DEPENDENT_CLAIM_NOT_REVALIDATED','changed_claim_id':changed_id,'dependent_claim_id':cid})

def _validate_requirements_adversarial(contract, errors, purpose, risk):
    rows=_index_rows(contract.get('requirements_adversarial_cases') or [],'id','requirements_adversarial_case',errors)
    required=purpose=='REQUIREMENTS_ARTIFACT' and RISK_RANK.get(risk,0)>=RISK_RANK['R1_CONTRACT']
    if required and not rows:
        errors.append({'type':'REQUIREMENTS_ADVERSARIAL_CASES_MISSING'});return
    for cid,row in rows.items():
        if not _text(row.get('counterexample')) or not _text(row.get('expected_behavior')):
            errors.append({'type':'REQUIREMENTS_ADVERSARIAL_CASE_INCOMPLETE','id':cid})
        status=row.get('status')
        if status=='PASS':_validate_evidence(row.get('evidence'),errors,'requirements_adversarial_case',cid)
        elif status in {'OPEN','BLOCKING_DEFECT',None,''}:errors.append({'type':'REQUIREMENTS_ADVERSARIAL_CASE_UNRESOLVED','id':cid,'status':status})
        elif status=='NOT_APPLICABLE':
            if required:errors.append({'type':'REQUIREMENTS_ADVERSARIAL_NA_FOR_REQUIRED_ARTIFACT','id':cid})
            elif not _text(row.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'requirements_adversarial_case','id':cid})
        else:errors.append({'type':'UNKNOWN_REQUIREMENTS_ADVERSARIAL_STATUS','id':cid,'status':status})

def evaluate(contract:dict,registry:dict|None=None)->dict:
    registry=registry or load_registry(); errors=[]; assumptions=[]; covered=[]
    routing=contract.get('routing') or {}; purpose=routing.get('purpose'); risk=routing.get('risk')
    purpose_values=set((registry.get('requirements_claim_contract') or {}).get('purposes',[]))
    if purpose not in purpose_values:errors.append({'type':'REQUIREMENTS_PURPOSE_INVALID','purpose':purpose})
    actual=hashlib.sha256((ROOT/'RULES/rule_registry.json').read_bytes()).hexdigest()
    if (contract.get('registry') or {}).get('sha256')!=actual:errors.append({'type':'REGISTRY_DEPENDENCY_DRIFT','expected':actual,'actual':(contract.get('registry') or {}).get('sha256')})
    sources=contract.get('sources') or []
    _validate_source_snapshots(sources,errors)
    _validate_task_input(contract.get('task_input'),sources,errors)

    rules={r['id']:r for r in registry.get('requirements_rules',[])}
    route_rows=contract.get('rule_routes') or []; routes=_index_rows(route_rows,'id','requirements_route',errors)
    if set(routes)!=set(rules):errors.append({'type':'REQUIREMENTS_ROUTE_COVERAGE_DRIFT','missing':sorted(set(rules)-set(routes)),'extra':sorted(set(routes)-set(rules))})
    for rid,rule in rules.items():
        route=routes.get(rid)
        if rule.get('tier')==0 and route and not route.get('active'):errors.append({'type':'REQUIREMENTS_TIER0_ROUTE_DISABLED','id':rid})

    rows=_index_rows(contract.get('rules') or [],'id','requirements_rule',errors)
    expected=[rid for rid,route in routes.items() if route.get('active') or rules.get(rid,{}).get('tier')==0]
    for rid in sorted(set(rows)-set(expected)):errors.append({'type':'UNROUTED_REQUIREMENTS_RULE_ROW','id':rid})
    for rid in expected:
        rule=rules.get(rid); row=rows.get(rid)
        if not rule:errors.append({'type':'UNKNOWN_REQUIREMENTS_RULE','id':rid});continue
        if not row:errors.append({'type':'REQUIREMENTS_RULE_MISSING','id':rid});continue
        st=row.get('status')
        if st in {'EVIDENCE_REQUIRED','BLOCKING_DEFECT','NEEDS_REVISION',None,''}:errors.append({'type':'REQUIREMENTS_RULE_UNRESOLVED','id':rid,'status':st});continue
        if st=='NOT_APPLICABLE':
            if rid in {'REQUIREMENTS_TRACEABILITY','ACCEPTANCE_ORACLE'} or (rid=='REQUIREMENTS_ARTIFACT_INTEGRITY' and purpose=='REQUIREMENTS_ARTIFACT'):errors.append({'type':'REQUIREMENTS_TIER0_NA_FORBIDDEN','id':rid});continue
            if not _text(row.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'requirements_rule','id':rid})
            covered.append(rid);continue
        if st!='PASS':errors.append({'type':'UNKNOWN_REQUIREMENTS_RULE_STATUS','id':rid,'status':st});continue
        _validate_evidence(row.get('evidence'),errors,'requirements_rule',rid)
        kinds={str(e.get('kind','')).upper() for e in row.get('evidence',[]) if isinstance(e,dict)}
        for mode in rule.get('evidence_modes',[]):
            if mode not in kinds:errors.append({'type':'EVIDENCE_MODE_MISSING','scope':'requirements_rule','id':rid,'mode':mode})
        checks=_index_rows(row.get('checks') or [],'id',f'requirements_check:{rid}',errors)
        expected_checks={x['id'] for x in rule.get('checks',[])}
        for cid in sorted(set(checks)-expected_checks):errors.append({'type':'UNPLANNED_REQUIREMENTS_CHECK_ROW','rule':rid,'id':cid})
        for spec in rule.get('checks',[]):
            c=checks.get(spec['id'])
            if not c:errors.append({'type':'REQUIREMENTS_CHECK_MISSING','rule':rid,'id':spec['id']});continue
            cs=c.get('status')
            if cs in {'EVIDENCE_REQUIRED','BLOCKING_DEFECT','NEEDS_REVISION',None,''}:errors.append({'type':'REQUIREMENTS_CHECK_UNRESOLVED','rule':rid,'id':spec['id'],'status':cs})
            elif cs=='PASS':_validate_evidence(c.get('evidence'),errors,'requirements_check',f"{rid}:{spec['id']}")
            elif cs=='NOT_APPLICABLE':
                if not _text(c.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'requirements_check','rule':rid,'id':spec['id']})
            else:errors.append({'type':'UNKNOWN_REQUIREMENTS_CHECK_STATUS','rule':rid,'id':spec['id'],'status':cs})
        covered.append(rid)

    claim_spec=registry.get('requirements_claim_contract') or {}
    claims=_validate_requirements_claims(contract,claim_spec,errors,purpose)
    _validate_revision_events(contract,claims,errors)
    field_specs={spec['id']:spec for spec in registry.get('requirements_contract_fields',[])}
    if risk not in RISK_RANK:errors.append({'type':'REQUIREMENTS_ROUTING_RISK_INVALID','risk':risk}); expected_fields=set()
    else:expected_fields={spec['id'] for spec in registry.get('requirements_contract_fields',[]) if RISK_RANK[risk]>=RISK_RANK[spec.get('min_risk','R0_LOCAL')]}
    fields=contract.get('functional_contract') or {}; actual_fields=set(fields)
    for fid in sorted(expected_fields-actual_fields):errors.append({'type':'FUNCTIONAL_FIELD_MISSING','id':fid})
    for fid in sorted(actual_fields-expected_fields):errors.append({'type':'FUNCTIONAL_FIELD_UNPLANNED','id':fid})
    for fid in sorted(expected_fields & actual_fields):
        row=fields[fid]; st=row.get('status'); blocking=bool(row.get('blocking',True))
        if st=='OPEN' or not st:
            if blocking:errors.append({'type':'FUNCTIONAL_FIELD_OPEN','id':fid})
            else:assumptions.append({'type':'NONBLOCKING_OPEN_FIELD','id':fid})
        elif st in {'KNOWN','DERIVED_WITH_EVIDENCE'}:
            if not _nonempty(row.get('value')):errors.append({'type':'FUNCTIONAL_FIELD_WITHOUT_VALUE','id':fid,'status':st})
            _validate_evidence(row.get('evidence'),errors,'functional_field',fid)
            if purpose=='REQUIREMENTS_ARTIFACT':
                claim_ids=row.get('claim_ids') or []
                if not claim_ids:errors.append({'type':'FUNCTIONAL_FIELD_WITHOUT_REQUIREMENTS_CLAIM','id':fid})
                else:
                    linked=[claims.get(cid) for cid in claim_ids if cid in claims]
                    for cid in claim_ids:
                        if cid not in claims:errors.append({'type':'FUNCTIONAL_FIELD_UNKNOWN_CLAIM','id':fid,'claim_id':cid})
                    if not any(c and c.get('disposition') in {'CONFIRMED_REQUIREMENT','DERIVED_REQUIREMENT'} for c in linked):
                        errors.append({'type':'FUNCTIONAL_FIELD_WITHOUT_PROVEN_REQUIREMENT_CLAIM','id':fid})
        elif st=='ASSUMED':
            if not _nonempty(row.get('value')) or not _text(row.get('reason')):errors.append({'type':'ASSUMPTION_INCOMPLETE','id':fid})
            if blocking:errors.append({'type':'BLOCKING_BUSINESS_FIELD_ASSUMED','id':fid})
            else:assumptions.append({'type':'EXPLICIT_FIELD_ASSUMPTION','id':fid})
        elif st=='NOT_APPLICABLE':
            if field_specs.get(fid,{}).get('na_allowed',True) is False:errors.append({'type':'FUNCTIONAL_FIELD_NA_FORBIDDEN','id':fid})
            if not _text(row.get('reason')):errors.append({'type':'NA_WITHOUT_REASON','scope':'functional_field','id':fid})
        else:errors.append({'type':'UNKNOWN_FUNCTIONAL_FIELD_STATUS','id':fid,'status':st})

    hard_materiality=set(claim_spec.get('hard_blocking_materiality',[])); allowed_materiality=hard_materiality | set(claim_spec.get('nonblocking_materiality',[]))
    for i,q in enumerate(contract.get('open_questions') or []):
        if q.get('status')=='RESOLVED':continue
        materiality=q.get('materiality')
        if purpose=='REQUIREMENTS_ARTIFACT' and materiality not in allowed_materiality:
            errors.append({'type':'OPEN_QUESTION_MATERIALITY_REQUIRED','index':i,'materiality':materiality})
        if materiality in hard_materiality and not q.get('blocking',True):
            errors.append({'type':'MATERIAL_OPEN_QUESTION_MARKED_NONBLOCKING','index':i,'materiality':materiality,'question':q.get('question')})
            continue
        if q.get('blocking',True):errors.append({'type':'BLOCKING_OPEN_QUESTION','index':i,'question':q.get('question')})
        else:assumptions.append({'type':'NONBLOCKING_OPEN_QUESTION','index':i,'question':q.get('question')})
    for i,a in enumerate(contract.get('assumptions') or []):
        for key in ('statement','impact','validation_plan'):
            if not _text(a.get(key)):errors.append({'type':'ASSUMPTION_INCOMPLETE','index':i,'field':key})
        if a.get('blocking_business_decision',False):errors.append({'type':'BLOCKING_BUSINESS_ASSUMPTION','index':i,'statement':a.get('statement')})
        else:assumptions.append({'type':'EXPLICIT_ASSUMPTION','index':i,'statement':a.get('statement')})
    _validate_evidence_requests(contract.get('evidence_requests') or [],errors,assumptions)
    _validate_requirements_adversarial(contract,errors,purpose,risk)

    if errors:outcome='REQUIREMENTS_BLOCKED'
    elif assumptions:outcome='REQUIREMENTS_READY_WITH_ASSUMPTIONS'
    else:outcome='REQUIREMENTS_READY'
    return {'result':'PASS' if not errors else 'FAIL','requirements_outcome':outcome,'errors':errors,'assumptions_or_nonblocking_gaps':assumptions,'covered_rules':covered,
            'rule':'READY requires complete risk-routed functional fields, exact rule/check coverage and concrete evidence. Deleting unresolved rows is not a valid way to close requirements.'}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('contract'); ap.add_argument('--output'); a=ap.parse_args(); contract=json.loads(Path(a.contract).read_text(encoding='utf-8-sig')); r=evaluate(contract); out=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if a.output:Path(a.output).write_text(out,encoding='utf-8')
    print(out,end=''); raise SystemExit(0 if r['result']=='PASS' else 2)

if __name__=='__main__':main()
