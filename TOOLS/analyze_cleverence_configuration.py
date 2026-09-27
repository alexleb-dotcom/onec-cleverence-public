#!/usr/bin/env python3
"""Deterministic structural review for Cleverence configuration metadata.

Covers semantic Metadata and DocumentTypes separately from the MSLX execution graph.
It extracts exact field declarations and container barcode templates, compares the
candidate to an accepted baseline, and emits REVIEW findings for changed contracts
that require semantic/runtime adjudication. It deliberately does not guess Mobile
SMARTS parser precedence or infer that similarly named fields are equivalent.

Artifact/container discovery is delegated to artifact_corpus so Configuration-root,
legacy Documents.zip and unpacked subsets can be compared without making their
physical delivery path the semantic identity of a configuration contract.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, re, sys, unicodedata, xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifact_corpus import inventory_paths, analyzable_entries

XML_SUFFIXES={'.mslx','.xml'}
CONFIG_PREFIXES=(
    'Configuration/Metadata/',
    'Configuration/DocumentTypes/',
    'WinClient/Configuration/Metadata/',
    'WinClient/Configuration/DocumentTypes/',
    'Metadata/',
    'DocumentTypes/',
)
ROOT_TAGS={'ContainerTypesBook','CommonFieldInfoCollection','DocumentType'}


def local_name(tag:str)->str:return tag.rsplit('}',1)[-1]

def finding(kind,severity,message,file,**extra):
    row={'type':kind,'severity':severity,'file':file,'message':message}; row.update(extra); return row

def looks_mojibake(name:str)->bool:return '\ufffd' in name or any('\u2500'<=ch<='\u257f' for ch in name)

def physical_leaf(row)->str:
    return row.physical_path.split('!/')[-1].replace('\\','/')

def physical_variant(logical:str)->str:
    normalized=logical.replace('\\','/')
    if normalized.startswith('WinClient/Configuration/'):return 'WINCLIENT'
    if normalized.startswith('Configuration/'):return 'MAIN'
    return 'SUBSET'

def path_is_configuration_contract(logical:str)->bool:
    normalized=logical.replace('\\','/')
    return any(normalized.startswith(prefix) for prefix in CONFIG_PREFIXES)

def standalone_configuration_candidate(path:Path)->bool:
    return path.is_file() and path.suffix.lower() in XML_SUFFIXES

def root_is_configuration_contract(data:bytes)->bool:
    """Probe unscoped valid XML without converting unrelated parse failures into findings."""
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:return False
    try:root=ET.fromstring(text)
    except ET.ParseError:return False
    return local_name(root.tag) in ROOT_TAGS

def read_entries(path:Path):
    entries={}; metadata={}; findings=[]
    corpus=inventory_paths([path])
    direct_candidate=standalone_configuration_candidate(path)
    for warning in corpus.get('warnings',[]):
        severity='HIGH' if warning.get('type') in {'BAD_ZIP','ZIP_ENTRY_READ_FAILED'} else 'REVIEW'
        findings.append(finding(
            f"CLEVERENCE_CONFIG_{warning.get('type','ARTIFACT_WARNING')}",
            severity,
            json.dumps(warning,ensure_ascii=False),
            str(path),
            artifact_warning=warning,
        ))
    for semantic,data,origin,row in analyzable_entries(corpus):
        logical=physical_leaf(row)
        if Path(logical).suffix.lower() not in XML_SUFFIXES:continue

        # Physical inventory is intentionally broad; this mechanism is not. Files
        # outside Metadata/DocumentTypes participate only if this is a standalone
        # candidate or their valid XML root proves a configuration contract.
        semantic_normalized=semantic.replace('\\','/')
        relevant=(
            path_is_configuration_contract(logical)
            or path_is_configuration_contract(semantic_normalized)
            or direct_candidate
            or root_is_configuration_contract(data)
        )
        if not relevant:continue

        if looks_mojibake(logical):findings.append(finding('CLEVERENCE_CONFIG_ZIP_FILENAME_MOJIBAKE','HIGH',logical,str(path)))
        key=logical
        if key in entries and entries[key]!=data:
            prefix=PurePosixPath(row.physical_path.split('!/',1)[0]).stem or 'artifact'
            candidate=f'{prefix}/{logical}'
            suffix=2
            while candidate in entries:
                candidate=f'{prefix}-{suffix}/{logical}'; suffix+=1
            key=candidate
        entries[key]=data
        metadata[key]={
            'semantic_path':semantic_normalized,
            'origin':origin,
            'physical_path':row.physical_path,
            'container_chain':row.container_chain,
            'variant':physical_variant(logical),
        }
    return entries,metadata,findings,corpus.get('artifact_model',{})

def is_configuration_document(logical:str,root)->bool:
    normalized=logical.replace('\\','/')
    return any(normalized.startswith(p) for p in CONFIG_PREFIXES) or local_name(root.tag) in ROOT_TAGS

def parse_document(logical:str,data:bytes,metadata=None):
    findings=[]
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:return None,[finding('CLEVERENCE_CONFIG_ENCODING','HIGH',str(exc),logical)]
    try:root=ET.fromstring(text)
    except ET.ParseError as exc:return None,[finding('CLEVERENCE_CONFIG_XML_PARSE','HIGH',str(exc),logical)]
    if not is_configuration_document(logical,root):return None,[]
    fields=[]; containers=[]
    for elem in root.iter():
        tag=local_name(elem.tag)
        if tag=='ContainerType':
            containers.append({'name':elem.attrib.get('name',''),'barcode':elem.attrib.get('barcode',''),'index':len(containers)})
        field_name=elem.attrib.get('fieldName')
        if field_name is not None:
            fields.append({'name':field_name,'type':elem.attrib.get('fieldType',''),'tag':tag,'dirName':elem.attrib.get('dirName',''),'alias':elem.attrib.get('alias','')})
    for name,count in Counter(x['name'] for x in containers if x['name']).items():
        if count>1:findings.append(finding('CLEVERENCE_CONTAINER_NAME_DUPLICATE','REVIEW',f'ContainerType name {name!r} occurs {count} times',logical,name=name))
    metadata=metadata or {}
    return {
        'logical_path':logical,
        'semantic_path':metadata.get('semantic_path',logical),
        'physical_path':metadata.get('physical_path',logical),
        'container_chain':metadata.get('container_chain',[]),
        'variant':metadata.get('variant',physical_variant(logical)),
        'sha256':hashlib.sha256(data).hexdigest(),
        'root_tag':local_name(root.tag),
        'fields':fields,
        'containers':containers,
    },findings

def parse_corpus(path:Path):
    entries,metadata,findings,artifact_model=read_entries(path); docs={}
    for logical,data in entries.items():
        doc,rows=parse_document(logical,data,metadata.get(logical)); findings.extend(rows)
        if doc:docs[logical]=doc
    return entries,docs,findings,artifact_model

def compact_template(value:str)->str:return re.sub(r'\s+','',value or '')

def prefix_overlap(a:str,b:str)->bool:
    a=compact_template(a); b=compact_template(b)
    if not a or not b or a==b:return a==b and bool(a)
    return a.startswith(b) or b.startswith(a)

def overlap_candidates(doc):
    rows=[]; items=doc.get('containers',[])
    for i,left in enumerate(items):
        for right in items[i+1:]:
            if prefix_overlap(left.get('barcode',''),right.get('barcode','')):
                rows.append({'left':left,'right':right,'reason':'textual template-prefix overlap; parser precedence/runtime match semantics not inferred'})
    return rows

# Conservative Cyrillic/Latin look-alike skeleton. This intentionally catches only
# visual code-point collisions, not transliteration such as NomerKoroba vs НомерКороба.
CONFUSABLES={
    'а':'a','А':'A','е':'e','Е':'E','о':'o','О':'O','р':'p','Р':'P','с':'c','С':'C','х':'x','Х':'X','у':'y','У':'Y','к':'k','К':'K','м':'m','М':'M','т':'t','Т':'T','в':'b','В':'B','н':'h','Н':'H',
}
def confusable_skeleton(value:str)->str:
    return ''.join(CONFUSABLES.get(ch,ch) for ch in unicodedata.normalize('NFC',value))

def inspect_confusable_fields(docs,findings):
    occurrences=defaultdict(list)
    for logical,doc in docs.items():
        for field in doc.get('fields',[]):
            name=field.get('name','')
            if name:occurrences[confusable_skeleton(name).casefold()].append((name,logical,field,doc.get('semantic_path')))
    for skeleton,rows in occurrences.items():
        names=sorted({x[0] for x in rows})
        if len(names)>1:
            findings.append(finding(
                'CLEVERENCE_FIELD_NAME_CONFUSABLE_REVIEW',
                'REVIEW',
                f'Distinct exact field names share a Cyrillic/Latin confusable skeleton: {names}',
                rows[0][1],
                names=names,
                skeleton=skeleton,
                occurrences=[{'name':name,'file':file,'semantic_path':semantic} for name,file,_,semantic in rows],
            ))

def field_map(doc):
    # Multiple declarations of the same exact name may exist in nested collections;
    # compare the set of declared types rather than silently selecting one.
    out=defaultdict(set)
    for f in doc.get('fields',[]):out[f['name']].add(f.get('type',''))
    return {k:sorted(v) for k,v in out.items()}

def container_map(doc):return {x['name']:x for x in doc.get('containers',[]) if x.get('name')}

def canonical_documents(docs):
    grouped=defaultdict(list)
    for logical,doc in docs.items():
        grouped[doc.get('semantic_path',logical)].append((logical,doc))
    preference={'MAIN':0,'SUBSET':1,'WINCLIENT':2}
    result={}
    for semantic,rows in grouped.items():
        result[semantic]=min(rows,key=lambda row:(preference.get(row[1].get('variant'),9),row[0]))[1]
    return result

def compare_to_baseline(candidate_docs,baseline_docs,findings):
    candidate_docs=canonical_documents(candidate_docs)
    baseline_docs=canonical_documents(baseline_docs)
    for semantic in sorted(set(candidate_docs)|set(baseline_docs)):
        c=candidate_docs.get(semantic); b=baseline_docs.get(semantic)
        logical=(c or b).get('logical_path',semantic)
        if c and not b:
            findings.append(finding('CLEVERENCE_CONFIG_FILE_ADDED','REVIEW','Configuration metadata file is absent from baseline',logical,semantic_path=semantic))
            continue
        if b and not c:
            findings.append(finding('CLEVERENCE_CONFIG_FILE_REMOVED','REVIEW','Baseline configuration metadata file is absent from candidate',logical,semantic_path=semantic))
            continue
        cf,bf=field_map(c),field_map(b)
        added=sorted(set(cf)-set(bf)); removed=sorted(set(bf)-set(cf))
        if added or removed:
            findings.append(finding('CLEVERENCE_FIELD_DECLARATION_SET_CHANGED','REVIEW',f'field declarations changed: added={added}; removed={removed}',logical,semantic_path=semantic,added=added,removed=removed))
        for name in sorted(set(cf)&set(bf)):
            if cf[name]!=bf[name]:findings.append(finding('CLEVERENCE_FIELD_TYPE_CHANGED','REVIEW',f'field {name!r} declared type set changed',logical,semantic_path=semantic,field=name,before=bf[name],after=cf[name]))
        cc,bc=container_map(c),container_map(b)
        changed_names=[]
        for name in sorted(set(cc)|set(bc)):
            if name not in bc or name not in cc or cc[name].get('barcode','')!=bc[name].get('barcode',''):
                changed_names.append(name)
                findings.append(finding('CLEVERENCE_CONTAINER_TEMPLATE_CHANGED','REVIEW',f'ContainerType {name!r} barcode contract changed',logical,semantic_path=semantic,name=name,before=(bc.get(name) or {}).get('barcode'),after=(cc.get(name) or {}).get('barcode')))
        if changed_names:
            changed=set(changed_names)
            for overlap in overlap_candidates(c):
                if overlap['left'].get('name') in changed or overlap['right'].get('name') in changed:
                    findings.append(finding('CLEVERENCE_BARCODE_TEMPLATE_OVERLAP_CHANGED','REVIEW','Changed/new barcode template textually overlaps another template; actual parser precedence must be proven by stock/runtime evidence',logical,semantic_path=semantic,left=overlap['left'],right=overlap['right']))

def inspect_mirrors(entries,findings):
    config={n for n in entries if n.startswith('Configuration/Metadata/') or n.startswith('Configuration/DocumentTypes/')}
    win={n for n in entries if n.startswith('WinClient/Configuration/Metadata/') or n.startswith('WinClient/Configuration/DocumentTypes/')}
    if not config or not win:return
    for source in sorted(config):
        mirror='WinClient/'+source
        if mirror not in entries:findings.append(finding('CLEVERENCE_CONFIG_MIRROR_COUNTERPART_MISSING','REVIEW',f'Mirror is absent for {source}',source))
        elif entries[source]!=entries[mirror]:findings.append(finding('CLEVERENCE_CONFIG_MIRROR_DRIFT','HIGH',f'{source} and {mirror} differ',source))

def analyze(candidate:Path,baseline:Path|None=None):
    entries,docs,findings,artifact_model=parse_corpus(candidate); inspect_mirrors(entries,findings); inspect_confusable_fields(docs,findings)
    baseline_docs={}; baseline_artifact_model=None
    if baseline:
        _,baseline_docs,baseline_findings,baseline_artifact_model=parse_corpus(baseline)
        for row in baseline_findings:
            row=dict(row); row['baseline']=True; findings.append(row)
        compare_to_baseline(docs,baseline_docs,findings)
    counts=Counter(x['severity'] for x in findings); types=Counter(x['type'] for x in findings)
    overlaps=[]
    for logical,doc in docs.items():
        for row in overlap_candidates(doc):overlaps.append({'file':logical,'semantic_path':doc.get('semantic_path'),**row})
    result='FAIL' if counts.get('HIGH',0) else 'PASS'
    return {
        'result':result,
        'candidate':str(candidate),
        'baseline':str(baseline) if baseline else None,
        'artifact_model':artifact_model,
        'baseline_artifact_model':baseline_artifact_model,
        'files':len(docs),
        'semantic_files':len(canonical_documents(docs)),
        'container_types':sum(len(d.get('containers',[])) for d in docs.values()),
        'field_declarations':sum(len(d.get('fields',[])) for d in docs.values()),
        'summary':{'by_severity':dict(sorted(counts.items())),'by_type':dict(sorted(types.items()))},
        'barcode_overlap_candidates':overlaps,
        'documents':docs,
        'findings':findings,
        'rule':'Structural extraction proves exact declarations/templates only. Physical inventory is broader than this mechanism: unrelated Operation/service XML is not parsed as configuration metadata. Mirrors remain reviewable while equivalent Configuration-root/Documents.zip/subset paths compare by semantic contract. Similar field names are not equivalent; changed barcode overlap requires stock parser/runtime precedence evidence.'
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('candidate'); ap.add_argument('--baseline'); ap.add_argument('--output'); args=ap.parse_args()
    report=analyze(Path(args.candidate),Path(args.baseline) if args.baseline else None); text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:Path(args.output).write_text(text,encoding='utf-8')
    print(text,end=''); raise SystemExit(2 if report['result']=='FAIL' else 0)

if __name__=='__main__':main()
