#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import io
import json
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'TOOLS'))
from artifact_corpus import inventory_paths, summarize
from build_project_bootstrap import build as build_bootstrap
from build_review_plan import build_plan
from analyze_cleverence_configuration import analyze as analyze_configuration
from analyze_cleverence_mslx import analyze as analyze_mslx

results={}; errors=[]

def record(case,ok,details):
    results[case]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":case,"details":details})

def zip_bytes(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    return buf.getvalue()

def make_operation(direction=''):
    attr=f' nextDirection="{direction}"' if direction else ''
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<Operation name="Test"><Actions><ShowMessageAction id="a1" name="A"{attr}/></Actions></Operation>'''.encode()

def make_document_type(field='FieldA'):
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<DocumentType name="Test"><Field fieldName="{field}" fieldType="String"/></DocumentType>'''.encode()

operation=make_operation()
metadata=b'''<?xml version="1.0" encoding="utf-8"?>\n<ContainerTypesBook><ContainerType name="Box" barcode="(01)"/></ContainerTypesBook>'''
doc_type=make_document_type()
onec=b'''<?xml version="1.0" encoding="utf-8"?>\n<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Catalog uuid="00000000-0000-0000-0000-000000000001" /></MetaDataObject>'''

with tempfile.TemporaryDirectory() as td:
    root=Path(td)

    # Modern/source-tree layout.
    modern=root/'modern'; (modern/'Configuration/Operations').mkdir(parents=True); (modern/'Configuration/Metadata').mkdir(parents=True); (modern/'Configuration/DocumentTypes').mkdir(parents=True)
    (modern/'Configuration/Operations/Test.mslx').write_bytes(operation); (modern/'Configuration/Metadata/Test.mslx').write_bytes(metadata); (modern/'Configuration/DocumentTypes/Test.mslx').write_bytes(doc_type)
    c=inventory_paths([modern]); s=summarize(c); m=s['artifact_model']
    record('modern_configuration_root',m['family']=='CLEVERENCE' and m['role']=='CONFIGURATION_SOURCE_TREE' and m['layout']=='CONFIGURATION_ROOT' and 'Configuration/' in m['authoritative_roots'],m)
    semantics={x.semantic_path for x in c['entries'] if x.analyzable}
    record('modern_semantic_paths',{'Operations/Test.mslx','Metadata/Test.mslx','DocumentTypes/Test.mslx'}.issubset(semantics),sorted(semantics))
    aliases={alias for x in c['entries'] if x.semantic_path=='DocumentTypes/Test.mslx' for alias in x.routing_aliases}
    record('modern_routing_aliases','Configuration/DocumentTypes/Test.mslx' in aliases,sorted(aliases))

    # Legacy config export with nested Documents.zip.
    docs=zip_bytes({'Operations/Test.mslx':operation,'Metadata/Test.mslx':metadata,'DocumentTypes/Test.mslx':doc_type})
    legacy=root/'legacy.zip'
    with zipfile.ZipFile(legacy,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('1CConfigs.xml','<x/>'); z.writestr('AppDescription.xml','<x/>'); z.writestr('settings.xml','<x/>'); z.writestr('Documents.zip',docs)
    c=inventory_paths([legacy]); s=summarize(c); m=s['artifact_model']
    record('legacy_documents_archive',m['family']=='CLEVERENCE' and m['role']=='CONFIGURATION_EXPORT' and m['layout']=='DOCUMENTS_ARCHIVE' and 'Documents.zip!/' in m['authoritative_roots'],m)
    nested=[x for x in c['entries'] if 'Documents.zip!/' in x.physical_path and x.analyzable]
    record('legacy_nested_traversal',len(nested)==3 and {x.semantic_path for x in nested}=={'Operations/Test.mslx','Metadata/Test.mslx','DocumentTypes/Test.mslx'},[(x.physical_path,x.semantic_path) for x in nested])
    legacy_aliases={alias for x in nested if x.semantic_path=='DocumentTypes/Test.mslx' for alias in x.routing_aliases}
    record('legacy_routing_aliases','Configuration/DocumentTypes/Test.mslx' in legacy_aliases,sorted(legacy_aliases))

    # Planner must route legacy content through the same semantic mechanisms.
    plan=build_plan([str(legacy)],analysis_only=True)
    routed={x['id'] for x in plan['rules'] if x.get('active') and x.get('detected_by')}
    record('legacy_review_plan_surface',plan['routing']['detected_surface']=='CLEVERENCE_ONLY',plan['routing'])
    record('legacy_review_plan_mechanisms',{'CLEVERENCE_CONFIGURATION','CLEVERENCE_MSLX'}.issubset(routed),sorted(routed))
    record('legacy_review_plan_artifact_model',plan['artifact_model']['layout']=='DOCUMENTS_ARCHIVE' and plan['artifact_delivery_state']['exact_delivery_allowed'],{'model':plan['artifact_model'],'delivery':plan['artifact_delivery_state']})

    # Cross-layout baseline comparison must not report false add/remove.
    config_report=analyze_configuration(legacy,modern)
    config_types={x['type'] for x in config_report['findings']}
    record('configuration_cross_layout_identity',not {'CLEVERENCE_CONFIG_FILE_ADDED','CLEVERENCE_CONFIG_FILE_REMOVED'} & config_types,config_report['findings'])
    mslx_report=analyze_mslx(legacy,modern)
    mslx_types={x['type'] for x in mslx_report['findings']}
    record('mslx_cross_layout_identity',not {'CLEVERENCE_FILE_ADDED','CLEVERENCE_FILE_REMOVED'} & mslx_types,mslx_report['findings'])

    # The broad physical corpus may include malformed/non-XML operation/service files.
    # Configuration analysis must ignore those outside its mechanism rather than
    # converting them into configuration XML parse failures.
    noisy_docs=zip_bytes({
        'Operations/Test.mslx':operation,
        'Operations/NonConfigurationPayload.mslx':b'not-an-xml-configuration-contract',
        'Metadata/Test.mslx':metadata,
        'DocumentTypes/Test.mslx':doc_type,
    })
    noisy=root/'legacy-noisy.zip'
    with zipfile.ZipFile(noisy,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('1CConfigs.xml','<x/>'); z.writestr('AppDescription.xml','<x/>'); z.writestr('settings.xml','<x/>'); z.writestr('Documents.zip',noisy_docs)
    noisy_config=analyze_configuration(noisy)
    noisy_types={x['type'] for x in noisy_config['findings']}
    record('configuration_ignores_nonmechanism_parse_noise',noisy_config['result']=='PASS' and 'CLEVERENCE_CONFIG_XML_PARSE' not in noisy_types and noisy_config['semantic_files']==2,{'summary':noisy_config['summary'],'semantic_files':noisy_config['semantic_files'],'findings':noisy_config['findings']})

    # Real semantic delta across two layouts must still be detected.
    changed_docs=zip_bytes({'Operations/Test.mslx':make_operation('return'),'Metadata/Test.mslx':metadata,'DocumentTypes/Test.mslx':make_document_type('FieldB')})
    changed=root/'changed-legacy.zip'
    with zipfile.ZipFile(changed,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('1CConfigs.xml','<x/>'); z.writestr('AppDescription.xml','<x/>'); z.writestr('settings.xml','<x/>'); z.writestr('Documents.zip',changed_docs)
    changed_config=analyze_configuration(changed,modern); changed_config_types={x['type'] for x in changed_config['findings']}
    record('configuration_cross_layout_real_delta','CLEVERENCE_FIELD_DECLARATION_SET_CHANGED' in changed_config_types,changed_config['findings'])
    changed_mslx=analyze_mslx(changed,modern); changed_mslx_types={x['type'] for x in changed_mslx['findings']}
    record('mslx_cross_layout_real_delta','CLEVERENCE_EXPLICIT_DIRECTION_CHANGED' in changed_mslx_types,changed_mslx['findings'])

    # Unpacked configuration subset is a supported semantic layout, not "unknown".
    subset=root/'subset'; (subset/'Operations').mkdir(parents=True); (subset/'Operations/Test.mslx').write_bytes(operation)
    c=inventory_paths([subset]); m=summarize(c)['artifact_model']
    record('unpacked_subset',m['family']=='CLEVERENCE' and m['role']=='CONFIGURATION_SUBSET' and m['layout']=='SUBSET_ROOT' and './' in m['authoritative_roots'],m)

    # Runtime database must not be mistaken for a configuration export.
    runtime=root/'runtime'; (runtime/'Logs').mkdir(parents=True); (runtime/'DeviceStorage').mkdir(parents=True)
    (runtime/'Cells.sqlite').write_bytes(b'SQLite format 3\0'); (runtime/'Logs/log.txt').write_text('runtime',encoding='utf-8')
    c=inventory_paths([runtime]); m=summarize(c)['artifact_model']
    record('runtime_database',m['family']=='CLEVERENCE' and m['role']=='RUNTIME_DATABASE' and m['layout']=='RUNTIME_TREE' and not m['authoritative_roots'],m)
    runtime_plan=build_plan([str(runtime)],analysis_only=True)
    record('runtime_not_exact_delivery',runtime_plan['artifact_delivery_state']['exact_delivery_allowed'] is False,runtime_plan['artifact_delivery_state'])

    # Config + runtime noise is explicitly mixed and may not silently become exact delivery baseline.
    mixed=root/'mixed'; (mixed/'Configuration/Operations').mkdir(parents=True); (mixed/'Logs').mkdir(parents=True)
    (mixed/'Configuration/Operations/Test.mslx').write_bytes(operation); (mixed/'Logs/log.txt').write_text('runtime',encoding='utf-8')
    c=inventory_paths([mixed]); m=summarize(c)['artifact_model']
    record('mixed_config_runtime',m['family']=='CLEVERENCE' and m['role']=='MIXED_ARTIFACT',m)
    mixed_plan=build_plan([str(mixed)],analysis_only=True)
    record('mixed_not_exact_delivery',mixed_plan['artifact_delivery_state']['exact_delivery_allowed'] is False,mixed_plan['artifact_delivery_state'])

    # 1C XML must be detected from content, not only BSL suffix.
    onec_dir=root/'onec'; onec_dir.mkdir(); (onec_dir/'Catalog.xml').write_bytes(onec)
    c=inventory_paths([onec_dir]); m=summarize(c)['artifact_model']
    record('onec_xml_content_detection',m['family']=='ONEC' and m['contains_onec_source'],m)

    # Unknown binary corpus stays unknown and cannot be exact delivery.
    unknown=root/'unknown'; unknown.mkdir(); (unknown/'blob.dat').write_bytes(b'abc')
    c=inventory_paths([unknown]); m=summarize(c)['artifact_model']
    record('unknown_stays_unknown',m['family']=='UNKNOWN' and m['role']=='UNKNOWN',m)
    unknown_plan=build_plan([str(unknown)],analysis_only=True)
    record('unknown_not_exact_delivery',unknown_plan['artifact_delivery_state']['exact_delivery_allowed'] is False,unknown_plan['artifact_delivery_state'])

    # Depth limit is explicit evidence, not silent truncation.
    z3=zip_bytes({'Operations/Test.mslx':operation}); z2=zip_bytes({'level3.zip':z3}); z1=root/'deep.zip'
    with zipfile.ZipFile(z1,'w') as z:z.writestr('level2.zip',z2)
    c=inventory_paths([z1],{'max_depth':1}); types={x['type'] for x in c['warnings']}
    record('nested_depth_limit_explicit','CONTAINER_DEPTH_LIMIT' in types,c['warnings'])

    # Bootstrap first asks for durable project contracts instead of inventing them.
    # Code-comment policy is independently resolved from author attribution; a new chat
    # may not silently choose its own technical-comment/history policy before final code.
    b=build_bootstrap([legacy]); request_ids={x['id'] for x in b['evidence_requests']}
    required={
        'DEPLOYED_BASELINE','MODIFICATION_POLICY','METADATA_ATTRIBUTION','AUTHOR_MARKER',
        'TECHNICAL_COMMENT_POLICY','EXISTING_COMMENT_POLICY','PUBLIC_INTERFACE_COMMENT_POLICY',
        'DELIVERY_CONTRACT'
    }
    blocking=set(b['gate']['blocking_open_fields'])
    record('bootstrap_requests_material_project_contracts',required.issubset(request_ids) and b['gate']['status']=='BLOCKED',{'requests':sorted(request_ids),'gate':b['gate']})
    record('bootstrap_blocks_unresolved_code_comment_contract',{'author_marker','technical_comment','existing_comment_policy'}.issubset(blocking) and b['gate']['implementation_allowed'] is False,{'blocking':sorted(blocking),'gate':b['gate']})
    public_request=next((x for x in b['evidence_requests'] if x['id']=='PUBLIC_INTERFACE_COMMENT_POLICY'),None)
    record('bootstrap_public_interface_comment_is_conditional',public_request is not None and public_request['blocking'] is False,public_request)
    record('bootstrap_continues_analysis_while_blocked',b['gate']['implementation_allowed'] is False and 'inspect evidence candidates semantically' in b['next_sequence'],b['next_sequence'])

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
