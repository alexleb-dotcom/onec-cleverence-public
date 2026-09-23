#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import copy
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'TOOLS'))
from build_project_bootstrap import build, _capability_gates

errors=[]; results={}

def record(case,ok,details):
    results[case]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":case,"details":details})

with tempfile.TemporaryDirectory() as td:
    source=Path(td)/'Module.bsl'
    source.write_text('Procedure Test()\nEndProcedure\n',encoding='utf-8')
    bootstrap=build([source])
    gates=bootstrap.get('capability_gates') or {}
    required={'code_output_allowed','metadata_change_allowed','public_interface_change_allowed','delivery_allowed'}
    record('capability_gate_set',required==set(gates),gates)
    record('legacy_gate_maps_code_output',bootstrap['gate']['implementation_allowed']==gates['code_output_allowed']['allowed'],bootstrap['gate'])

    fields=copy.deepcopy(bootstrap['fields'])
    for fid in ('actual_deployed_baseline','modification_policy','author_marker','technical_comment','existing_comment_policy'):
        fields[fid]['status']='KNOWN'; fields[fid]['value']='regression-evidenced'
    isolated=_capability_gates(fields)
    record(
        'metadata_delivery_do_not_false_block_code',
        isolated['code_output_allowed']['allowed'] is True
        and isolated['metadata_change_allowed']['allowed'] is False
        and isolated['delivery_allowed']['allowed'] is False,
        isolated,
    )

    fields['metadata_attribution']['status']='KNOWN'; fields['metadata_attribution']['value']='regression-evidenced'
    metadata_ready=_capability_gates(fields)
    record(
        'metadata_gate_is_independent',
        metadata_ready['metadata_change_allowed']['allowed'] is True
        and metadata_ready['public_interface_change_allowed']['allowed'] is False
        and metadata_ready['delivery_allowed']['allowed'] is False,
        metadata_ready,
    )

    fields['public_interface_comment']['status']='NOT_APPLICABLE'
    public_ready=_capability_gates(fields)
    record('public_interface_gate_can_resolve_independently',public_ready['public_interface_change_allowed']['allowed'] is True,public_ready)

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
