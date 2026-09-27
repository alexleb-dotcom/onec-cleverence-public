#!/usr/bin/env python3
"""Static integration/reachability review for changed 1C BSL routines.

The analyzer is deliberately conservative. It proves only static call paths available
in the supplied corpus. A new routine is not considered integrated merely because it
exists or is Export. Platform/event entrypoints are recognized narrowly; unresolved
external/dynamic dispatch remains REVIEW/EVIDENCE_REQUIRED rather than a false PASS.

With --baseline the analyzer focuses on routines newly introduced by the candidate.
It detects orphan routines and orphan clusters that never connect to a pre-existing
routine, a recognized platform/advice entrypoint, or a resolved caller from another module.
"""
from __future__ import annotations
from pathlib import Path
import argparse, json, re, zipfile

TEXT_EXT={'.bsl','.os'}
DECL_RE=re.compile(r'^\s*(Процедура|Функция)\s+([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\((.*?)\)\s*(Экспорт)?\s*$',re.I)
END_RE=re.compile(r'^\s*Конец(?:Процедуры|Функции)\b',re.I)
QUAL_CALL_RE=re.compile(r'\b([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\.([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\(')
LOCAL_CALL_RE=re.compile(r'(?<![\.\wА-Яа-яЁё])([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\(')
IGNORE_LOCAL={x.lower() for x in [
    'Если','ИначеЕсли','Пока','Для','Возврат','Процедура','Функция','Новый','Тип','ТипЗнч','ЗначениеЗаполнено',
    'Строка','Число','Булево','Дата','Формат','Сообщить','ВызватьИсключение','Мин','Макс','Окр','СокрЛП','НРег','ВРег',
    'СтрНайти','СтрЗаменить','Сред','Лев','Прав','СтрДлина','ПустаяСтрока','XMLСтрока','ЗначениеВСтрокуВнутр',
]}
PLATFORM_NAMES={x.lower() for x in [
    'ПриСозданииНаСервере','ПриОткрытии','ПередЗакрытием','ОбработкаПроверкиЗаполнения','ПередЗаписью','ПриЗаписи',
    'ОбработкаПроведения','ОбработкаУдаленияПроведения','ОбработкаЗаполнения','ПриИзменении','НачалоВыбора','ОбработкаРасшифровки',
    'ПриНачалеРаботыСистемы','ПриЗавершенииРаботыСистемы','ОбработкаПолученияФормы','ОбработкаРасшифровки',
]}
ADVICE_RE=re.compile(r'^\s*&(Перед|После|Вместо)\s*\(',re.I)


def _decode(data:bytes)->str:
    for enc in ('utf-8-sig','utf-8','cp1251'):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    return data.decode('utf-8',errors='replace')


def _entries(path:Path):
    if path.is_dir():
        for p in sorted(path.rglob('*')):
            if p.is_file() and p.suffix.lower() in TEXT_EXT:
                yield p.relative_to(path).as_posix(),_decode(p.read_bytes())
    elif path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir() and Path(info.filename).suffix.lower() in TEXT_EXT:
                    yield info.filename,_decode(z.read(info))
    elif path.is_file():
        yield path.name,_decode(path.read_bytes())
    else:raise FileNotFoundError(path)


def _module_name(logical:str)->str:
    p=logical.replace('\\','/').split('/')
    if 'CommonModules' in p:
        i=p.index('CommonModules')
        if i+1<len(p):return p[i+1]
    name=Path(logical).stem
    name=re.sub(r'_Module(?:\([^)]*\))?$','',name,flags=re.I)
    return name


def _parse_module(logical,text):
    lines=text.splitlines(); routines=[]; i=0; pending=[]
    while i<len(lines):
        line=lines[i]
        if line.lstrip().startswith('&'):
            pending.append(line.strip()); pending=pending[-5:]; i+=1; continue
        m=DECL_RE.match(line)
        if not m:
            if line.strip() and not line.lstrip().startswith('//'):pending=[]
            i+=1; continue
        kind,name,params,export=m.groups(); start=i; body=[]; directives=list(pending); pending=[]; i+=1
        while i<len(lines):
            if END_RE.match(lines[i]):break
            body.append(lines[i]); i+=1
        end=i
        routines.append({'module':_module_name(logical),'logical_path':logical,'name':name,'key':f'{_module_name(logical)}::{name}',
                         'kind':kind.upper(),'export':bool(export),'directives':directives,'start_line':start+1,'end_line':end+1,'body':'\n'.join(body)})
        i+=1
    return routines


def _parse(paths):
    routines=[]
    for source in paths:
        for logical,text in _entries(Path(source)):routines.extend(_parse_module(logical,text))
    by_key={r['key'].lower():r for r in routines}; module_map={}
    for r in routines:module_map.setdefault(r['module'].lower(),set()).add(r['module'])
    edges=[]; unresolved=[]
    for r in routines:
        body=r['body']
        for mod,name in QUAL_CALL_RE.findall(body):
            key=f'{mod}::{name}'.lower()
            if key in by_key:edges.append((r['key'].lower(),key,'QUALIFIED'))
            else:unresolved.append({'caller':r['key'],'target':f'{mod}::{name}','kind':'QUALIFIED'})
        local_names=set(LOCAL_CALL_RE.findall(body))
        for name in local_names:
            if name.lower() in IGNORE_LOCAL:continue
            key=f"{r['module']}::{name}".lower()
            if key in by_key and key!=r['key'].lower():edges.append((r['key'].lower(),key,'LOCAL'))
    # dedup
    edges=list(dict.fromkeys(edges))
    incoming={k:[] for k in by_key}; outgoing={k:[] for k in by_key}
    for a,b,kind in edges:
        outgoing.setdefault(a,[]).append((b,kind)); incoming.setdefault(b,[]).append((a,kind))
    return routines,by_key,edges,incoming,outgoing,unresolved


def _is_platform_entry(r):
    if r['name'].lower() in PLATFORM_NAMES:return True
    return any(ADVICE_RE.match(x) for x in r.get('directives',[]))


def _path_from_anchor(target,anchors,incoming):
    # reverse BFS: can target be reached from any anchor?
    q=[target]; seen={target}
    while q:
        cur=q.pop(0)
        if cur in anchors:return True
        for prev,_ in incoming.get(cur,[]):
            if prev not in seen:seen.add(prev); q.append(prev)
    return False


def analyze(paths,baseline=None,entrypoints=None,targets=None):
    if not isinstance(paths,(list,tuple)):paths=[paths]
    routines,by_key,edges,incoming,outgoing,unresolved=_parse([Path(x) for x in paths])
    baseline_keys=set()
    if baseline:
        bp=baseline if isinstance(baseline,(list,tuple)) else [baseline]
        br,_,_,_,_,_=_parse([Path(x) for x in bp]); baseline_keys={r['key'].lower() for r in br}
    new_keys={k for k in by_key if k not in baseline_keys} if baseline else set()
    platform_roots={k for k,r in by_key.items() if _is_platform_entry(r)}
    # Existing routines are integration anchors: a new helper connected from old executable code is not orphaned.
    existing_anchors={k for k in by_key if baseline and k in baseline_keys}
    explicit={x.replace('.','::').lower() for x in (entrypoints or [])}
    anchors=platform_roots|existing_anchors|explicit
    findings=[]
    def emit(tp,severity,r,detail):
        findings.append({'type':tp,'severity':severity,'source':r['logical_path'],'module':r['module'],'routine':r['name'],'line':r['start_line'],'detail':detail})
    if baseline:
        for k in sorted(new_keys):
            r=by_key[k]
            inc=incoming.get(k,[])
            connected=_path_from_anchor(k,anchors,incoming)
            if connected:continue
            if _is_platform_entry(r):continue
            if not inc:
                if r['export']:
                    emit('NEW_EXPORTED_ROUTINE_WITHOUT_RESOLVED_CALLER','REVIEW',r,
                         'Export is an API visibility modifier, not proof that the intended runtime scenario calls this new routine. Resolve a real caller/entrypoint or document the external callback contract.')
                else:
                    emit('NEW_ROUTINE_WITHOUT_CALLER','HIGH',r,'New non-entrypoint routine has no resolved caller in the candidate corpus.')
            else:
                emit('NEW_ROUTINE_CLUSTER_NOT_CONNECTED','HIGH',r,
                     'New routine is called only from an orphan/new subgraph and has no path from a pre-existing or recognized runtime entrypoint.')
    else:
        for k,r in by_key.items():
            if _is_platform_entry(r) or incoming.get(k):continue
            if not r['export']:
                emit('ROUTINE_WITHOUT_STATIC_CALLER','REVIEW',r,'No static caller was resolved. Without a baseline this may be an event/dynamic entrypoint; provide entrypoint evidence before calling it integrated.')
    if targets:
        ep=explicit or anchors
        for target in targets:
            k=target.replace('.','::').lower()
            r=by_key.get(k)
            if not r:
                findings.append({'type':'TARGET_ROUTINE_NOT_FOUND','severity':'HIGH','target':target})
            elif not _path_from_anchor(k,ep,incoming):
                emit('TARGET_NOT_REACHABLE_FROM_ENTRYPOINT','HIGH',r,f'Target {target} is not statically reachable from declared/resolved entrypoints.')
    high=sum(1 for x in findings if x['severity']=='HIGH'); review=sum(1 for x in findings if x['severity']=='REVIEW')
    return {'result':'FAIL' if high else 'PASS','summary':{'routines':len(routines),'edges':len(edges),'new_routines':len(new_keys),'high':high,'review':review},
            'anchors':[by_key[k]['key'] for k in sorted(anchors) if k in by_key], 'findings':findings,'unresolved_calls':unresolved}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('paths',nargs='+'); ap.add_argument('--baseline',action='append'); ap.add_argument('--entrypoint',action='append',default=[]); ap.add_argument('--target',action='append',default=[])
    a=ap.parse_args(); out=analyze(a.paths,a.baseline,a.entrypoint,a.target); print(json.dumps(out,ensure_ascii=False,indent=2)); raise SystemExit(2 if out['result']=='FAIL' else 0)
if __name__=='__main__':main()
