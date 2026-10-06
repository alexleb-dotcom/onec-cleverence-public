#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib,json,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"TOOLS"))
from machine_receipts import create_receipt, verify_receipt

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def stable(v)->bytes:return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
results=[]; errors=[]
def rec(name,ok,detail=None):
    results.append({"case":name,"pass":bool(ok),"detail":detail})
    if not ok:errors.append({"case":name,"detail":detail})

lock_path=ROOT/"PRODUCT/OneCChatWorker/runtime.lock.json"
adapter_path=ROOT/"PRODUCT/OneCChatWorker/runtime/local-quality-adapter.mjs"
script_path=ROOT/"PRODUCT/OneCChatWorker/runtime/quality/cc-1c-skills/form-validate.ps1"
verifier="TOOLS/verify_local_quality_report.py"
prop="STATIC:ONEC_FORM_VALIDATE_CANONICAL_OK"
lock=json.loads(lock_path.read_text(encoding="utf-8-sig"))
q=lock["local_quality_adapter"]
script=q["selected_scripts"]["form-validate.ps1"]

with tempfile.TemporaryDirectory(prefix="s4-quality-receipt-") as td:
    temp=Path(td); project=temp/"project"
    artrel="Participants/p/Target/Main"
    formrel=artrel+"/Documents/Order/Forms/Main/Ext/Form.xml"
    modrel=artrel+"/Documents/Order/Forms/Main/Ext/Form/Module.bsl"
    form=project.joinpath(*formrel.split("/")); module=project.joinpath(*modrel.split("/"))
    form.parent.mkdir(parents=True,exist_ok=True); module.parent.mkdir(parents=True,exist_ok=True)
    form.write_text("<Form><Items/></Form>\n",encoding="utf-8")
    module.write_text("&НаКлиенте\nПроцедура OnOpen()\nКонецПроцедуры\n",encoding="utf-8")
    snapshot="1"*64
    manifest_doc={
      "schema_version":2,"project_id":"P","project_root":str(project),
      "participants":[{"participant_id":"p","platform":"ONEC","role":"UT","active":True,
        "target":{"main":{"active":True,"canonical_path":artrel},"extensions":[]},"reference":None}],
      "accepted_snapshot":{"snapshot_contract":"ACCEPTED_SNAPSHOT_V1","source_snapshot_id":snapshot,"publication_generation":1}
    }
    manifest=temp/"project.json"
    manifest.write_text(json.dumps(manifest_doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    manifest_sha=sha(manifest.read_bytes())
    closure=[
      {"relative_path":formrel,"sha256":sha(form.read_bytes())},
      {"relative_path":modrel,"sha256":sha(module.read_bytes())},
    ]
    closure=sorted(closure,key=lambda x:x["relative_path"])
    base={
      "schema_version":"LOCAL_QUALITY_REPORT_V1","project_id":"P","participant_id":"p","artifact_type":"MAIN","artifact_id":"main",
      "source_snapshot_id":snapshot,"manifest_sha256":manifest_sha,"task_id":"T","session_id":"S","relative_target":formrel,
      "confirming_read":{"relative_path":formrel,"sha256":sha(form.read_bytes())},
      "operation":"FORM_VALIDATE","adapter_contract_version":q["contract"],"upstream_commit":q["upstream_commit"],
      "script_git_blob":script["git_blob"],"script_sha256":script["sha256"],"overlay_sha256":q["overlay_sha256"],
      "normalized_args":["Detailed=false","MaxErrors=30"],"input_closure":closure,"input_closure_sha256":sha(stable(closure)),
      "elapsed_ms":1.0,"result_class":"OK","warnings":0,"findings":[],"stdout_sha256":sha(b"canonical ok"),"stderr_sha256":sha(b""),"truncated":False
    }
    base["report_sha256"]=sha(stable(base))
    report=temp/"report.json";report.write_text(json.dumps(base,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    def argv(report_path=report,session="S"):
        return ["--report",str(report_path),"--project-root",str(project),"--manifest",str(manifest),"--project","P","--task","T","--session",session,
                "--snapshot",snapshot,"--manifest-sha",manifest_sha,"--runtime-lock",str(lock_path)]
    inputs=[str(report),str(manifest),str(lock_path),str(adapter_path),str(script_path),str(form),str(module)]
    receipt=temp/"machine.json"
    r=create_receipt(verifier,argv(),inputs,[prop],receipt)
    v=verify_receipt(receipt,replay=True)
    rec("canonical_full_report_machine_pass",r["derived_result"]=="PASS" and v["integrity_result"]=="PASS" and v["derived_result"]=="PASS" and v["verified_properties"]==[prop],v)

    raw=json.loads(report.read_text(encoding="utf-8"))
    raw["warnings"]=1
    report.write_text(json.dumps(raw,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    drift=verify_receipt(receipt,replay=False)
    rec("report_drift_invalidates_receipt",drift["integrity_result"]=="FAIL" and any(x.get("type")=="MACHINE_RECEIPT_INPUT_DRIFT" for x in drift["errors"]),drift["errors"])
    report.write_text(json.dumps(base,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    stale=temp/"stale-session.json"; stale_doc=dict(base);stale_doc["session_id"]="OLD";stale_doc.pop("report_sha256",None);stale_doc["report_sha256"]=sha(stable(stale_doc));stale.write_text(json.dumps(stale_doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    stale_inputs=[str(stale),str(manifest),str(lock_path),str(adapter_path),str(script_path),str(form),str(module)]
    stale_receipt=temp/"stale-machine.json"
    sr=create_receipt(verifier,argv(stale),stale_inputs,[prop],stale_receipt)
    rec("stable_session_drift_never_passes",sr["derived_result"]=="FAIL",sr["derived_result"])

    findings=temp/"findings.json";fd=dict(base);fd["result_class"]="FINDINGS";fd["findings"]=[{"code":"FORM_HANDLER_MISSING","message":"x"}];fd.pop("report_sha256",None);fd["report_sha256"]=sha(stable(fd));findings.write_text(json.dumps(fd,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    fi=[str(findings),str(manifest),str(lock_path),str(adapter_path),str(script_path),str(form),str(module)]
    fr=create_receipt(verifier,argv(findings),fi,[prop],temp/"findings-machine.json")
    rec("findings_do_not_mint_ok_machine_pass",fr["derived_result"]=="FAIL",fr["derived_result"])

    prepared=temp/"prepared.json";prepared.write_text(json.dumps({"schema":"PREPARED_QUALITY_V1","target":{"kind":"FORM","path":formrel},"summary":{"FORM_VALIDATE":"OK"}},ensure_ascii=False)+"\n",encoding="utf-8")
    pi=[str(prepared),str(manifest),str(lock_path),str(adapter_path),str(script_path),str(form),str(module)]
    pr=create_receipt(verifier,argv(prepared),pi,[prop],temp/"prepared-machine.json")
    rec("prepared_projection_alone_never_mints_machine_pass",pr["derived_result"]=="FAIL",pr["derived_result"])

    source_before=form.read_bytes();form.write_text("<Form><Items/><Drift/></Form>\n",encoding="utf-8")
    source_drift=verify_receipt(receipt,replay=False)
    rec("source_input_drift_invalidates_receipt",source_drift["integrity_result"]=="FAIL" and any(x.get("type")=="MACHINE_RECEIPT_INPUT_DRIFT" for x in source_drift["errors"]),source_drift["errors"])
    form.write_bytes(source_before)

    p=subprocess.run([sys.executable,str(ROOT/"TOOLS/verify_local_quality_report.py"),*argv()],cwd=ROOT,capture_output=True,text=True)
    rec("epoch_absent_from_freshness_binding",p.returncode==0 and "epoch_id" not in base and "epoch_seq" not in base,p.stdout[-500:])

out={"status":"PASS" if not errors else "FAIL","cases":len(results),"results":results,"errors":errors}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
