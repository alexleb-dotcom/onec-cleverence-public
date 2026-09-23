#!/usr/bin/env python3
"""Field-aware temporal write analysis for 1C BSL.

The analyzer is a routing/evidence tool for POST_WRITE_STANDARD_OVERWRITE.
It deliberately avoids module-wide keyword correlation. It follows statically
reachable calls, maps actual arguments to formal parameters, and reports only:

* a proven later write of the same field on the same logical object/row;
* an unresolved lifecycle-like call in a position that can plausibly mutate the
  object/row and therefore still requires source/runtime evidence.

Known platform writers such as `ЗаполнитьЗначенияСвойств` are modeled by their
argument semantics so a value passed as the *source* is not treated as a writer.
"""
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, re, zipfile

ROUTINE_START=re.compile(
    r'^\s*(Процедура|Функция)\s+([A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*\((.*?)\)\s*(Экспорт)?', re.I)
ROUTINE_END=re.compile(r'^\s*Конец(?:Процедуры|Функции)\b',re.I)
ASSIGN_RE=re.compile(r'\b([A-Za-zА-Яа-я_][\wА-Яа-я]*)\.([A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*=(?!=)',re.I)
CALL_RE=re.compile(r'(?<![\w.])(?:(?P<qual>[A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*\.)?(?P<name>[A-Za-zА-Яа-я_][\wА-Яа-я]*)\s*\((?P<args>[^()]*)\)',re.I)
LIFECYCLE_RE=re.compile(r'^(?:Заполн|Перезаполн|Пересчит|Рассчит|ОбработкаЗаполнения|ПередЗапис|ПриИзмен|ОбработатьВыбор|ПриВыбор)',re.I)
TEXT_SUFFIXES={'.bsl','.os'}
SIMPLE_NAME_RE=re.compile(r'^[A-Za-zА-Яа-я_][\wА-Яа-я]*$',re.I)
STRING_LITERAL_RE=re.compile(r'^"((?:[^"]|"")*)"$')


def _decode(data:bytes)->str:
    for enc in ('utf-8-sig','utf-8','cp1251'):
        try:return data.decode(enc)
        except UnicodeDecodeError:pass
    return data.decode('utf-8',errors='replace')


def _strip_strings_and_comment(line:str)->str:
    out=[]; i=0; in_str=False
    while i<len(line):
        ch=line[i]
        if in_str:
            if ch=='"':
                if i+1<len(line) and line[i+1]=='"':out.extend('  '); i+=2; continue
                in_str=False; out.append(' '); i+=1; continue
            out.append(' '); i+=1; continue
        if ch=='"':in_str=True; out.append(' '); i+=1; continue
        if ch=='/' and i+1<len(line) and line[i+1]=='/':out.extend(' '*(len(line)-i)); break
        out.append(ch); i+=1
    return ''.join(out)


def _split_args(text:str)->list[str]:
    parts=[]; cur=[]; depth=0; in_str=False; i=0
    while i<len(text):
        ch=text[i]
        if ch=='"':
            if in_str and i+1<len(text) and text[i+1]=='"':cur.extend(['"','"']); i+=2; continue
            in_str=not in_str; cur.append(ch); i+=1; continue
        if not in_str:
            if ch in '([':depth+=1
            elif ch in ')]' and depth:depth-=1
            elif ch==',' and depth==0:
                parts.append(''.join(cur).strip()); cur=[]; i+=1; continue
        cur.append(ch); i+=1
    if cur or text.strip():parts.append(''.join(cur).strip())
    return parts


def _literal_property_set(expr:str|None):
    """Return (known, set). Empty literal means an empty set.

    1C `ЗаполнитьЗначенияСвойств` accepts comma-separated property names in
    string parameters. Non-literal expressions remain unknown and therefore
    cannot prove inclusion/exclusion statically.
    """
    if expr is None:return True,set()
    m=STRING_LITERAL_RE.match(expr.strip())
    if not m:return False,set()
    value=m.group(1).replace('""','"')
    return True,{x.strip().lower() for x in value.split(',') if x.strip()}


def _module_name(source:str)->str|None:
    parts=source.replace('\\','/').split('/')
    lowered=[x.lower() for x in parts]
    if 'commonmodules' in lowered:
        i=lowered.index('commonmodules')
        if i+1<len(parts):return parts[i+1]
    # Standalone files named Foo_Module.bsl are useful in focused validation.
    name=Path(source).name
    m=re.match(r'(.+)_Module\.(?:bsl|os)$',name,re.I)
    return m.group(1) if m else None


def parse_routines(text:str,source:str='<memory>')->list[dict]:
    lines=text.splitlines(); routines=[]; current=None
    module=_module_name(source)
    for idx,raw in enumerate(lines,1):
        clean=_strip_strings_and_comment(raw)
        if current is None:
            m=ROUTINE_START.match(clean)
            if not m:continue
            params=[]
            for item in _split_args(m.group(3)):
                name=item.split('=',1)[0].strip()
                if name:params.append(name)
            current={'kind':m.group(1),'name':m.group(2),'params':params,'export':bool(m.group(4)),
                     'start_line':idx,'lines':[],'source':source,'module':module}
            continue
        if ROUTINE_END.match(clean):
            current['end_line']=idx; routines.append(current); current=None; continue
        current['lines'].append({'line':idx,'raw':raw,'clean':clean})
    if current:
        current['end_line']=len(lines); routines.append(current)
    for r in routines:
        assignments=[]; calls=[]
        for pos,row in enumerate(r['lines']):
            for m in ASSIGN_RE.finditer(row['clean']):
                assignments.append({'base':m.group(1),'field':m.group(2),'line':row['line'],'pos':pos,'code':row['raw'].strip()})
            for m in CALL_RE.finditer(row['clean']):
                calls.append({'qualifier':m.group('qual'),'name':m.group('name'),'args':_split_args(m.group('args')),
                              'line':row['line'],'pos':pos,'code':row['raw'].strip()})
        r['assignments']=assignments; r['calls']=calls
    return routines


def _same_simple(expr:str,variable:str)->bool:
    return bool(re.fullmatch(re.escape(variable),expr.strip(),re.I))


def _builtin_fill_values_properties_effect(call:dict,variable:str,field:str):
    """Model `ЗаполнитьЗначенияСвойств(Приемник, Источник, Поля, Исключения)`.

    Returns None when this is not the known builtin. Otherwise returns one of:
    `NO_WRITE`, `PROVEN_WRITE`, `POSSIBLE_WRITE`.
    """
    if call.get('qualifier') or call['name'].lower()!='заполнитьзначениясвойств':return None
    args=call.get('args',[])
    if not args:return 'NO_WRITE'
    # Only the first argument is mutated. Passing our value as Source is safe
    # for the current field and was the main source of historical noise.
    if not _same_simple(args[0],variable):return 'NO_WRITE'
    include_known,includes=_literal_property_set(args[2] if len(args)>2 else None)
    exclude_known,excludes=_literal_property_set(args[3] if len(args)>3 else None)
    f=field.lower()
    if exclude_known and f in excludes:return 'NO_WRITE'
    if len(args)>2:
        if include_known:
            if includes and f not in includes:return 'NO_WRITE'
            # Explicit empty include means the platform fills all matching properties.
        else:
            return 'POSSIBLE_WRITE'
    if not exclude_known:return 'POSSIBLE_WRITE'
    return 'PROVEN_WRITE'


def _build_indexes(routines:list[dict]):
    by_source={}; by_module={}
    for r in routines:
        by_source.setdefault(r['source'],{})[r['name'].lower()]=r
        if r.get('module'):
            by_module[(r['module'].lower(),r['name'].lower())]=r
    return by_source,by_module


def _analyze_routines(routines:list[dict])->list[dict]:
    by_source,by_module=_build_indexes(routines); findings=[]; seen=set()

    def emit(kind,severity,origin,field,details):
        key=(kind,origin['source'],origin['name'].lower(),field.lower(),str(details.get('target_routine','')).lower(),details.get('line'))
        if key in seen:return
        seen.add(key)
        findings.append({'severity':severity,'type':kind,'source':origin['source'],'procedure':origin['name'],
                         'origin_line':origin.get('line'),'field':field,**details})

    def resolve_call(routine,call):
        if call.get('qualifier'):
            return by_module.get((call['qualifier'].lower(),call['name'].lower()))
        return by_source.get(routine['source'],{}).get(call['name'].lower())

    def traverse(origin,field,variable,routine,min_pos,path,visited,depth=0):
        if depth>10:return
        state=(routine['source'].lower(),routine['name'].lower(),variable.lower(),field.lower(),min_pos)
        if state in visited:return
        visited=visited|{state}

        # Once we crossed at least one call edge, a same-field assignment is real
        # temporal evidence regardless of the callee name.
        if depth>0 and LIFECYCLE_RE.match(routine['name']):
            for a in routine['assignments']:
                if a['pos']<min_pos:continue
                if a['base'].lower()==variable.lower() and a['field'].lower()==field.lower():
                    emit('POST_WRITE_REACHABLE_FIELD_OVERWRITE','REVIEW',origin,field,{
                        'line':a['line'],'target_routine':f"{routine.get('module')+'.' if routine.get('module') else ''}{routine['name']}",
                        'target_source':routine['source'],'path':path+[f"{routine.get('module')+'.' if routine.get('module') else ''}{routine['name']}"],
                        'note':'A statically reachable later routine writes the same field. Prove final ownership and execution order.'})

        for call in routine['calls']:
            if call['pos']<min_pos:continue
            args=[x.strip() for x in call['args']]

            # Precise semantics for the common platform copier.
            effect=_builtin_fill_values_properties_effect(call,variable,field)
            if effect is not None:
                if effect=='PROVEN_WRITE':
                    emit('POST_WRITE_REACHABLE_FIELD_OVERWRITE','REVIEW',origin,field,{
                        'line':call['line'],'target_routine':'ЗаполнитьЗначенияСвойств','target_source':'platform builtin',
                        'path':path+['ЗаполнитьЗначенияСвойств'],
                        'note':'The object/row is the receiver of ЗаполнитьЗначенияСвойств and the same field is not statically excluded.'})
                elif effect=='POSSIBLE_WRITE':
                    emit('POST_WRITE_EXTERNAL_LIFECYCLE_WRITER_REVIEW','REVIEW',origin,field,{
                        'line':call['line'],'target_routine':'ЗаполнитьЗначенияСвойств','target_source':'platform builtin',
                        'path':path+['ЗаполнитьЗначенияСвойств'],
                        'note':'The object/row is the receiver, but dynamic include/exclude arguments prevent proving whether this exact field is written.'})
                continue

            target=resolve_call(routine,call)
            if target:
                # A qualified call whose source is available is resolved, so follow
                # actual argument -> formal parameter flow instead of treating the
                # method name as lifecycle evidence.
                for ix,arg in enumerate(args):
                    if not _same_simple(arg,variable) or ix>=len(target['params']):continue
                    traverse(origin,field,target['params'][ix],target,0,
                             path+[f"{routine.get('module')+'.' if routine.get('module') else ''}{routine['name']}"],visited,depth+1)
                # Object-method form `Variable.Method()` cannot be mapped to a module
                # routine by static source naming; handled below as unresolved.
                continue

            # Unresolved writer review is deliberately narrow:
            # 1) lifecycle-like method invoked on the object itself; or
            # 2) lifecycle-like procedure receiving the object as first argument.
            # Merely appearing as a source/secondary argument is not writer evidence.
            qualifier_is_object=bool(call.get('qualifier') and call['qualifier'].lower()==variable.lower())
            first_arg_is_object=bool(args and _same_simple(args[0],variable))
            if LIFECYCLE_RE.match(call['name']) and (qualifier_is_object or first_arg_is_object):
                emit('POST_WRITE_EXTERNAL_LIFECYCLE_WRITER_REVIEW','REVIEW',origin,field,{
                    'line':call['line'],'target_routine':'.'.join(x for x in [call.get('qualifier'),call['name']] if x),
                    'target_source':None,'path':path+[f"{routine.get('module')+'.' if routine.get('module') else ''}{routine['name']}"],
                    'note':'A later unresolved lifecycle-like writer receives/owns the same object. Resolve actual source or runtime dispatch for this exact field.'})

    for r in routines:
        params={x.lower() for x in r.get('params',[])}
        for a in r['assignments']:
            base=a['base']
            object_like=bool(re.match(r'(?i)^(?:Объект|Источник|ДанныеФормы|Строка|Текущ|Элемент|Данные|Документ)',base)) or base.lower() in params
            if not object_like:continue
            origin={'name':r['name'],'line':a['line'],'source':r['source']}
            traverse(origin,a['field'],base,r,a['pos']+1,[],set(),0)
    return findings




def _aggregate_findings(findings:list[dict])->list[dict]:
    """Collapse many field rows caused by one later writer into one evidence item.

    The routing question is writer-centric: one call that may replace twelve fields
    should produce one review item carrying twelve field names, not twelve noisy
    items. Proven writers at different target lines remain separate.
    """
    groups={}
    for f in findings:
        key=(f.get('severity'),f.get('type'),f.get('source'),f.get('procedure'),
             f.get('line'),f.get('target_routine'),f.get('target_source'),tuple(f.get('path') or []),f.get('note'))
        row=groups.get(key)
        if row is None:
            row={k:v for k,v in f.items() if k not in {'field','origin_line'}}
            row['fields']=[]; row['origin_lines']=[]; groups[key]=row
        if f.get('field') and f['field'] not in row['fields']:row['fields'].append(f['field'])
        if f.get('origin_line') is not None and f['origin_line'] not in row['origin_lines']:row['origin_lines'].append(f['origin_line'])
    out=[]
    for row in groups.values():
        row['fields']=sorted(row['fields'],key=str.lower); row['origin_lines']=sorted(row['origin_lines'])
        if len(row['fields'])==1:row['field']=row['fields'][0]
        if len(row['origin_lines'])==1:row['origin_line']=row['origin_lines'][0]
        out.append(row)
    return sorted(out,key=lambda x:(x.get('source',''),x.get('procedure',''),x.get('line') or 0,x.get('type',''),x.get('target_routine','')))


def analyze_sources(sources:list[tuple[str,str]])->dict:
    """Analyze an in-memory multi-file corpus with qualified-call resolution."""
    routines=[]
    for name,text in sources:routines.extend(parse_routines(text,name))
    findings=_aggregate_findings(_analyze_routines(routines))
    return {'sources':len(sources),'routines':len(routines),'findings':findings,'summary':{
        'by_severity':{s:sum(1 for f in findings if f['severity']==s) for s in sorted({f['severity'] for f in findings})},
        'by_type':{t:sum(1 for f in findings if f['type']==t) for t in sorted({f['type'] for f in findings})}}}


def analyze_text(text:str,source:str='<memory>')->dict:
    routines=parse_routines(text,source); findings=_aggregate_findings(_analyze_routines(routines))
    return {'source':source,'routines':len(routines),'findings':findings,'summary':{
        'by_severity':{s:sum(1 for f in findings if f['severity']==s) for s in sorted({f['severity'] for f in findings})},
        'by_type':{t:sum(1 for f in findings if f['type']==t) for t in sorted({f['type'] for f in findings})}}}


def _entries(path:Path):
    if path.is_dir():
        for p in sorted(path.rglob('*')):
            if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:yield p.relative_to(path).as_posix(),p.read_bytes()
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir() and Path(info.filename.replace('\\','/')).suffix.lower() in TEXT_SUFFIXES:
                    yield info.filename,z.read(info)
    elif path.is_file():yield path.name,path.read_bytes()
    else:raise FileNotFoundError(path)


def analyze(path)->dict:
    p=Path(path); files=[]; routines=[]
    for name,data in _entries(p):
        parsed=parse_routines(_decode(data),name); routines.extend(parsed)
        files.append({'path':name,'sha256':hashlib.sha256(data).hexdigest(),'routines':len(parsed)})
    findings=_aggregate_findings(_analyze_routines(routines))
    return {'result':'PASS','input':str(p),'files':files,'findings':findings,'summary':{
        'files':len(files),
        'by_severity':{s:sum(1 for f in findings if f['severity']==s) for s in sorted({f['severity'] for f in findings})},
        'by_type':{t:sum(1 for f in findings if f['type']==t) for t in sorted({f['type'] for f in findings})}}}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('path'); ap.add_argument('--output'); a=ap.parse_args()
    r=analyze(a.path); out=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if a.output:Path(a.output).write_text(out,encoding='utf-8')
    print(out,end='')

if __name__=='__main__':main()
