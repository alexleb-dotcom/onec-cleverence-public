#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'KNOWLEDGE/EXTERNAL_SOURCE_CATALOG.json'
errors=[]; results={}

def record(case,ok,details):
    results[case]={'pass':bool(ok),'details':details}
    if not ok:errors.append({'case':case,'details':details})

catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
sources={row['id']:row for row in catalog.get('sources',[])}
record('catalog_source_set',{'CC_1C_SKILLS','V8STD','REQUIREMENTS_METHOD_ORIGIN'}<=set(sources),sorted(sources))
record('catalog_distribution_schema',catalog.get('schema_version',0)>=2 and 'redistribution' in catalog.get('principle','').lower(),catalog)

cc=sources.get('CC_1C_SKILLS',{})
cc_paths=[cc.get('local_notice'),cc.get('local_license')]
record('cc_local_attribution',all(x and (ROOT/x).is_file() for x in cc_paths),cc_paths)
record('cc_on_demand',cc.get('load')=='ON_DEMAND' and cc.get('trust')=='SUPPORTING_REFERENCE',cc)
record('cc_redistribution_declared',cc.get('redistribution_status')=='LICENSED_WITH_NOTICE',cc)

v8=sources.get('V8STD',{})
record('v8std_on_demand',v8.get('load')=='ON_DEMAND' and v8.get('trust')=='SUPPORTING_DISCOVERY',v8)
record('v8std_reference_by_url',v8.get('redistribution_status')=='REFERENCE_BY_URL',v8)

method=sources.get('REQUIREMENTS_METHOD_ORIGIN',{})
record('requirements_origin_not_distributed',method.get('load')=='NOT_DISTRIBUTED' and method.get('trust')=='CONCEPTUAL_SOURCE' and method.get('redistribution_status')=='SOURCE_ARCHIVE_REMOVED_FROM_SHAREABLE_TREE',method)
record('requirements_origin_has_no_local_archive',not method.get('local_archive') and not method.get('local_readme'),method)
record('removed_external_archive_absent',not (ROOT/'ARCHIVE/EXTERNAL_METHODS').exists(),str(ROOT/'ARCHIVE/EXTERNAL_METHODS'))

out={'result':'PASS' if not errors else 'FAIL','errors':errors,'results':results}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
