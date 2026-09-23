#!/usr/bin/env python3
"""Build an unresolved functional-contract ledger before technical design.

The builder routes requirements rules from task text + declared surface/risk.
It deliberately does not invent missing business facts: unresolved fields are OPEN
and routed checks are EVIDENCE_REQUIRED until the assistant/user supplies proof.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, re, sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from rule_registry import ROOT, load_registry, max_risk, RISK_RANK

SURFACES=('ANALYSIS_ONLY','ONEC_ONLY','CLEVERENCE_ONLY','CROSS_SYSTEM')
RISKS=('R0_LOCAL','R1_CONTRACT','R2_STATEFUL_RUNTIME','R3_CROSS_SYSTEM')
PURPOSES=('IMPLEMENTATION_INPUT','REQUIREMENTS_ARTIFACT')
SURFACE_RANK={'ANALYSIS_ONLY':0,'ONEC_ONLY':1,'CLEVERENCE_ONLY':1,'CROSS_SYSTEM':2}


def _decode(data:bytes)->str:
    for enc in ('utf-8-sig','utf-8','cp1251'):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    return data.decode('utf-8',errors='replace')


def _source_rows(paths):
    rows=[]; texts=[]
    for raw in paths:
        p=Path(raw).resolve(); data=p.read_bytes(); text=_decode(data)
        rows.append({'path':str(p),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)})
        texts.append(text)
    return rows,'\n'.join(texts)


def _infer_surface(text:str)->str:
    cross=re.search(r'(?i)\b(?:Cleverence|Mobile\s+SMARTS|REST|SOAP|HTTP|API|endpoint|интеграц\w*|обмен\w*|ЭТРАН|маркетплейс\w*|внешн\w*\s+систем\w*)\b',text)
    if cross:return 'CROSS_SYSTEM'
    clev=re.search(r'(?i)\b(?:Cleverence|ТСД|MSLX|DeclaredItems|CurrentItems|BindedLine|Mobile\s+SMARTS)\b',text)
    if clev:return 'CLEVERENCE_ONLY'
    onec=re.search(r'(?i)(?:\b1С\b|справочник|документ|регистр|реквизит|табличн\w*\s+част|форма|БСП|конфигурац\w*)',text)
    return 'ONEC_ONLY' if onec else 'ANALYSIS_ONLY'


def _infer_risk(text:str,surface:str)->str:
    if surface=='CROSS_SYSTEM':return 'R3_CROSS_SYSTEM'
    if re.search(r'(?i)\b(?:запис\w*|провед\w*|статус\w*|состояни\w*|повтор\w*|re-?entry|параллел\w*|конкурент\w*|пересчит\w*|заполн\w*|workflow|жизненн\w*\s+цикл)\b',text):
        return 'R2_STATEFUL_RUNTIME'
    if re.search(r'(?i)\b(?:добав\w*|измен\w*|доработ\w*|реализ\w*|провер\w*|правил\w*|расчет\w*|сопостав\w*|поиск\w*|поле|реквизит)\b',text):
        return 'R1_CONTRACT'
    return 'R0_LOCAL'



def _infer_purpose(task_text:str)->str:
    # Purpose is intentionally inferred from the user's task, not from a requirements
    # file that may merely be implementation input. This avoids turning every coding
    # task with an attached TZ into a specification-authoring task.
    if re.search(r'(?i)(?:анализ\w*\s+требован|провер\w*\s+(?:требован|тз|лт)|подготов\w*\s+(?:лт|тз|техническ\w*\s+задан|требован|постановк)|сформир\w*\s+(?:лт|тз|требован|постановк)|доработ\w*\s+(?:требован|тз|лт)|requirements?\s+(?:analysis|review)|(?:write|refine|review)\s+(?:the\s+)?specification)',task_text or ''):
        return 'REQUIREMENTS_ARTIFACT'
    return 'IMPLEMENTATION_INPUT'

def _max_purpose(detected:str,declared:str|None)->str:
    # Explicit context may widen into artifact-authoring mode, never downgrade an
    # already-detected requirements-analysis task to implementation-input mode.
    if detected=='REQUIREMENTS_ARTIFACT' or declared=='REQUIREMENTS_ARTIFACT':
        return 'REQUIREMENTS_ARTIFACT'
    return 'IMPLEMENTATION_INPUT'

def _max_surface(a:str,b:str|None)->str:
    if not b:return a
    if a=='CROSS_SYSTEM' or b=='CROSS_SYSTEM':return 'CROSS_SYSTEM'
    if {a,b}=={'ONEC_ONLY','CLEVERENCE_ONLY'}:return 'CROSS_SYSTEM'
    return b if SURFACE_RANK[b]>=SURFACE_RANK[a] else a


def _surface_ok(rule_surface:str,surface:str)->bool:
    if rule_surface=='ANY':return True
    if rule_surface=='CROSS_SYSTEM':return surface=='CROSS_SYSTEM'
    if rule_surface=='ONEC':return surface in {'ONEC_ONLY','CROSS_SYSTEM'}
    if rule_surface=='CLEVERENCE':return surface in {'CLEVERENCE_ONLY','CROSS_SYSTEM'}
    return True


def _rule_routes(rule:dict,text:str,surface:str,risk:str):
    activation=rule.get('activation',{}); mode=activation.get('mode','ANY_REGEX'); hits=[]
    for pat in activation.get('patterns',[]):
        if re.search(pat,text,re.I|re.M):hits.append(pat)
    active=bool(rule.get('always_disposition'))
    reason='tier-0 requirements disposition required' if active else ''
    if mode=='ANY_REGEX' and hits:active=True; reason='requirements activation pattern matched'
    elif mode=='RISK_FLOOR' and RISK_RANK[risk]>=RISK_RANK[rule.get('risk_floor','R0_LOCAL')]:active=True; reason='derived: requirements risk floor reached'
    elif mode=='SURFACE' and _surface_ok(rule.get('surface','ANY'),surface):active=True; reason='derived: requirements surface applicable'
    elif mode=='ALWAYS':active=True; reason='tier-0 requirements disposition required'
    if not _surface_ok(rule.get('surface','ANY'),surface) and rule.get('tier',1)>0:active=False; reason='surface not applicable'
    return {'id':rule['id'],'tier':rule['tier'],'active':active,'activation_status':activation.get('status_on_match','REQUIRED') if active else 'NOT_ROUTED','detected_by':hits,'reason':reason,'risk_floor':rule.get('risk_floor','R0_LOCAL'),'surface':rule.get('surface','ANY')}


def build_contract(paths,task_text='',surface_override=None,risk_override=None,purpose_override=None)->dict:
    registry=load_registry(); sources,text=_source_rows(paths); combined='\n'.join([text,task_text or ''])
    task_bytes=(task_text or '').encode('utf-8')
    detected_surface=_infer_surface(combined); surface=_max_surface(detected_surface,surface_override)
    detected_risk=_infer_risk(combined,surface); risk=max_risk(detected_risk,risk_override)
    detected_purpose=_infer_purpose(task_text or ''); purpose=_max_purpose(detected_purpose,purpose_override)
    rules=[]
    by_id={r['id']:r for r in registry.get('requirements_rules',[])}
    order=registry.get('requirements_rule_order',[r['id'] for r in registry.get('requirements_rules',[])])
    for rid in order:rules.append(_rule_routes(by_id[rid],combined,surface,risk))
    fields={}
    for spec in registry.get('requirements_contract_fields',[]):
        if RISK_RANK[risk] < RISK_RANK[spec.get('min_risk','R0_LOCAL')]:continue
        fields[spec['id']]={'title':spec['title'],'blocking':bool(spec.get('blocking',True)),'status':'OPEN','value':None,'evidence':[],'claim_ids':[],'reason':''}
    ledger_rules=[]
    for route in rules:
        rule=by_id[route['id']]
        if not route['active'] and rule.get('tier',1)>0:continue
        ledger_rules.append({'id':rule['id'],'tier':rule['tier'],'activation_status':route['activation_status'],'detected_by':route['detected_by'],'status':'EVIDENCE_REQUIRED','reason':'','evidence':[],
            'required_evidence_modes':rule.get('evidence_modes',[]),
            'checks':[{'id':c['id'],'question':c['question'],'status':'EVIDENCE_REQUIRED','reason':'','evidence':[],'kind':c.get('kind','REQUIREMENT')} for c in rule.get('checks',[])]})
    reg_sha=hashlib.sha256((ROOT/'RULES/rule_registry.json').read_bytes()).hexdigest()
    return {
      'schema_version':2,
      'registry':{'path':'RULES/rule_registry.json','schema_version':registry.get('schema_version'),'sha256':reg_sha},
      'routing':{'surface':surface,'risk':risk,'purpose':purpose,'detected_surface':detected_surface,'declared_surface':surface_override,'detected_risk':detected_risk,'declared_risk':risk_override,'detected_purpose':detected_purpose,'declared_purpose':purpose_override},
      'task_input':{'text':task_text or '','sha256':hashlib.sha256(task_bytes).hexdigest(),'size':len(task_bytes)},
      'sources':sources,
      'functional_contract':fields,
      'claims':[],
      'revision_events':[],
      'requirements_adversarial_cases':[],
      'rule_routes':rules,
      'rules':ledger_rules,
      'open_questions':[],
      'evidence_requests':[],
      'assumptions':[],
      'question_policy':'Infer from actual task/source/project evidence first. When a concrete missing artifact can resolve a material gap, request that smallest sufficient artifact instead of guessing or asking the user to restate encoded facts. Ask only unresolved questions that can change behavior, scope, ownership or acceptance; batch the minimum useful set.',
      'completion':{'status':'REQUIREMENTS_BLOCKED','note':'Generated contract is intentionally unresolved. For REQUIREMENTS_ARTIFACT purpose, claim provenance and artifact-level adversarial/revision obligations must also be closed before the artifact is called ready. Fill evidence/statuses and run TOOLS/requirements_gate.py.'}
    }


def compact_summary(result):
    fields=result.get('functional_contract') or {}
    open_fields=[fid for fid,row in fields.items() if isinstance(row,dict) and row.get('status')=='OPEN']
    rules=[]
    for row in result.get('rules') or []:
        checks=[c.get('id') for c in (row.get('checks') or []) if isinstance(c,dict) and c.get('status') not in {'PASS','NOT_APPLICABLE'} and c.get('id')]
        if row.get('status') not in {'PASS','NOT_APPLICABLE'} or checks:
            rules.append({'id':row.get('id'),'status':row.get('status'),'checks':checks})
    return {
        'result':'REQUIREMENTS_CONTRACT_CREATED',
        'routing':result.get('routing'),
        'task_input':{'sha256':(result.get('task_input') or {}).get('sha256'),'size':(result.get('task_input') or {}).get('size')},
        'source_count':len(result.get('sources') or []),
        'open_fields':open_fields,
        'unresolved_rules':rules,
        'open_questions':result.get('open_questions') or [],
        'evidence_requests':result.get('evidence_requests') or [],
        'completion':result.get('completion'),
        'policy':{'full_contract_on_disk':True,'registry_loaded_by_tool':True,'registry_not_required_in_llm_context':True},
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('paths',nargs='*'); ap.add_argument('--task-text',default=''); ap.add_argument('--surface',choices=SURFACES); ap.add_argument('--risk',choices=RISKS); ap.add_argument('--purpose',choices=PURPOSES); ap.add_argument('--output'); ap.add_argument('--summary',action='store_true'); ap.add_argument('--full-json',action='store_true')
    a=ap.parse_args(); result=build_contract(a.paths,a.task_text,a.surface,a.risk,a.purpose); out=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:Path(a.output).write_text(out,encoding='utf-8')
    shown=compact_summary(result) if a.summary or (a.output and not a.full_json) else result
    print(json.dumps(shown,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
