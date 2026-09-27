#!/usr/bin/env python3
from pathlib import Path
import copy, hashlib, json, shutil, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'TESTS/fixtures'
sys.path.insert(0,str(ROOT/'TOOLS'))
from build_review_plan import build_plan
from build_validation_ledger import build_ledger
from release_gate_core import evaluate
from release_intake import validate_plan_recomputation, intake_from_build_args
from machine_receipts import create_receipt, verify_receipt
from runtime_evidence import create_adapter_observation, create_manual_observation, verify_observation
from release_evidence_receipts import validate_machine_reports
from rule_registry import load_registry

errors=[]; results={}
def check(cid,ok,details=None):
    results[cid]={'pass':bool(ok),'details':details}
    if not ok:errors.append({'case':cid,'details':details})

registry=load_registry()
plan=build_plan([FIX/'call_contract_nonexport_caller.bsl'],analysis_only=True)
check('intake:recompute_clean',validate_plan_recomputation(plan)['result']=='PASS',validate_plan_recomputation(plan))
tampered=copy.deepcopy(plan); next(x for x in tampered['rules'] if x['id']=='CALL_CONTRACT')['active']=False
r=validate_plan_recomputation(tampered)
check('intake:route_active_tamper_blocks',r['result']=='FAIL' and any(x['type']=='RELEASE_PLAN_RECOMPUTE_DRIFT' and 'rules' in x.get('changed',[]) for x in r['errors']),r)
tampered_req=copy.deepcopy(plan); tampered_req['requirements']['gate_result']='PASS'; tampered_req['requirements']['gate_outcome']='REQUIREMENTS_READY'
r=validate_plan_recomputation(tampered_req)
check('intake:stale_requirements_summary_blocks',r['result']=='FAIL' and any(x['type']=='RELEASE_PLAN_RECOMPUTE_DRIFT' and 'requirements' in x.get('changed',[]) for x in r['errors']),r)
external=intake_from_build_args([FIX/'query_field_good.bsl'],analysis_only=True)
r=validate_plan_recomputation(plan,external)
check('intake:external_manifest_mismatch_blocks',r['result']=='FAIL' and any(x['type']=='RELEASE_INTAKE_EXTERNAL_MISMATCH' for x in r['errors']),r)

with tempfile.TemporaryDirectory() as td:
    td=Path(td); src=td/'input.bsl'; shutil.copyfile(FIX/'query_field_good.bsl',src); receipt_path=td/'receipt.json'
    receipt=create_receipt('TOOLS/analyze_onec_bsl.py',[str(src)],[str(src)],['STATIC:ONEC_BSL'],receipt_path)
    v=verify_receipt(receipt_path)
    check('machine:replayed_receipt_passes',v['integrity_result']=='PASS' and v['derived_result']=='PASS',v)
    src.write_text(src.read_text(encoding='utf-8')+'\n// drift',encoding='utf-8')
    v=verify_receipt(receipt_path)
    check('machine:input_drift_blocks',v['integrity_result']=='FAIL' and any(x['type']=='MACHINE_RECEIPT_INPUT_DRIFT' for x in v['errors']),v)

with tempfile.TemporaryDirectory() as td:
    td=Path(td); log=td/'device.log'; log.write_text('device observed ok',encoding='utf-8'); obs=td/'runtime.json'
    create_adapter_observation(obs,'RUNTIME:DEVICE',log,'fixture-adapter','fixture-device','device observed ok')
    sha=hashlib.sha256(obs.read_bytes()).hexdigest(); v=verify_observation(obs,'RUNTIME:DEVICE',sha,require_adapter=True)
    check('runtime:adapter_leaf_passes',v['integrity_result']=='PASS' and v['derived_result']=='PASS',v)
    log.write_text('changed',encoding='utf-8'); v=verify_observation(obs,'RUNTIME:DEVICE',sha,require_adapter=True)
    check('runtime:bound_log_drift_blocks',v['integrity_result']=='FAIL' and any(x['type']=='RUNTIME_OBSERVATION_SOURCE_DRIFT' for x in v['errors']),v)
    manual=td/'manual.json'; create_manual_observation(manual,'RUNTIME:DEVICE','looks good','reviewer')
    v=verify_observation(manual,'RUNTIME:DEVICE',require_adapter=True)
    check('runtime:manual_attestation_not_final_proof',v['integrity_result']=='FAIL' and any(x['type']=='RUNTIME_OBSERVATION_NOT_ADAPTER_EVIDENCE' for x in v['errors']),v)

# A ledger may not silently diverge from the intake record even before other
# unresolved skeleton obligations are adjudicated.
ledger=build_ledger(plan,registry); ledger['release_intake']=copy.deepcopy(plan['release_intake']); ledger['release_intake']['sha256']='0'*64
r=evaluate(plan,ledger,registry)
check('release:intake_dependency_drift_blocks',r['result']=='FAIL' and any(x['type']=='RELEASE_INTAKE_DEPENDENCY_DRIFT' for x in r['errors']),{'errors':[x for x in r['errors'] if x['type'].startswith('RELEASE_')]})

out={'result':'PASS' if not errors else 'FAIL','errors':errors,'results':results}
print(json.dumps(out,ensure_ascii=False,indent=2)); raise SystemExit(0 if not errors else 2)
