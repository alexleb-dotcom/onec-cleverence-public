#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, sys

ROOT=Path(__file__).resolve().parents[1]

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def stable_bytes(value)->bytes:return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
def fail(code,**detail):
    print(json.dumps({"status":"FAIL","error_class":code,**detail},ensure_ascii=False,sort_keys=True))
    raise SystemExit(3)
def resolve_under(root:Path,rel:str)->Path:
    if not isinstance(rel,str) or not rel or Path(rel).is_absolute() or ":" in rel:
        fail("REPORT_PATH_INVALID",path=rel)
    parts=rel.replace("\\","/").split("/")
    if any(x in ("",".","..") for x in parts):fail("REPORT_PATH_INVALID",path=rel)
    target=(root.joinpath(*parts)).resolve()
    try:target.relative_to(root.resolve())
    except ValueError:fail("REPORT_PATH_ESCAPE",path=rel)
    return target

def collect_manifest_artifacts(doc):
    rows=[]
    for p in doc.get("participants") or []:
        if p.get("active") is False:continue
        pid=str(p.get("participant_id") or "")
        for side in ("target","reference"):
            g=p.get(side) or {}
            main=g.get("main")
            if main and main.get("active") is not False and main.get("canonical_path"):
                rows.append((pid,"MAIN","main",str(main["canonical_path"]).replace("\\","/").strip("/")))
            for e in g.get("extensions") or []:
                if e.get("active") is False or not e.get("canonical_path"):continue
                rows.append((pid,"EXTENSION",str(e.get("extension_id") or e.get("artifact_id") or ""),str(e["canonical_path"]).replace("\\","/").strip("/")))
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--report",required=True)
    ap.add_argument("--project-root",required=True)
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--project",required=True)
    ap.add_argument("--task",required=True)
    ap.add_argument("--session",required=True)
    ap.add_argument("--snapshot",required=True)
    ap.add_argument("--manifest-sha",required=True)
    ap.add_argument("--runtime-lock",default=str(ROOT/"PRODUCT/OneCChatWorker/runtime.lock.json"))
    a=ap.parse_args()

    report_path=Path(a.report).resolve()
    project_root=Path(a.project_root).resolve()
    manifest_path=Path(a.manifest).resolve()
    lock_path=Path(a.runtime_lock).resolve()
    for p,label in ((report_path,"report"),(manifest_path,"manifest"),(lock_path,"runtime_lock")):
        if not p.is_file():fail("INPUT_MISSING",input=label,path=str(p))
    try:r=json.loads(report_path.read_text(encoding="utf-8-sig"))
    except Exception as e:fail("REPORT_PARSE_ERROR",error=str(e))
    if r.get("schema_version")!="LOCAL_QUALITY_REPORT_V1":fail("REPORT_SCHEMA_INVALID")
    if r.get("operation")!="FORM_VALIDATE":fail("REPORT_OPERATION_UNSUPPORTED",operation=r.get("operation"))
    if r.get("project_id")!=a.project or r.get("task_id")!=a.task or r.get("session_id")!=a.session:fail("REPORT_TASK_BINDING_MISMATCH")
    if r.get("source_snapshot_id")!=a.snapshot or r.get("manifest_sha256")!=a.manifest_sha:fail("REPORT_SNAPSHOT_BINDING_MISMATCH")

    manifest_raw=manifest_path.read_bytes()
    if sha(manifest_raw)!=a.manifest_sha:fail("MANIFEST_SHA_MISMATCH")
    try:m=json.loads(manifest_raw.decode("utf-8-sig"))
    except Exception as e:fail("MANIFEST_PARSE_ERROR",error=str(e))
    if str(m.get("project_id"))!=a.project:fail("MANIFEST_PROJECT_MISMATCH")
    accepted=m.get("accepted_snapshot") or {}
    if accepted.get("snapshot_contract")!="ACCEPTED_SNAPSHOT_V1" or str(accepted.get("source_snapshot_id") or "")!=a.snapshot:fail("MANIFEST_SNAPSHOT_MISMATCH")

    artifact_matches=[x for x in collect_manifest_artifacts(m) if x[0]==str(r.get("participant_id")) and x[1]==str(r.get("artifact_type")) and x[2]==str(r.get("artifact_id"))]
    if len(artifact_matches)!=1:fail("REPORT_PPA_BINDING_NON_UNIQUE",matches=len(artifact_matches))
    artifact_root=artifact_matches[0][3]
    target=str(r.get("relative_target") or "").replace("\\","/").strip("/")
    if not(target==artifact_root or target.startswith(artifact_root+"/")):fail("REPORT_TARGET_OUTSIDE_ARTIFACT")
    if not target.endswith("/Ext/Form.xml"):fail("REPORT_FORM_TARGET_INVALID",target=target)

    confirming=r.get("confirming_read") or {}
    confirming_rel=str(confirming.get("relative_path") or "").replace("\\","/").strip("/")
    if not(confirming_rel==artifact_root or confirming_rel.startswith(artifact_root+"/")):fail("REPORT_CONFIRMING_READ_OUTSIDE_ARTIFACT")
    confirming_file=resolve_under(project_root,confirming_rel)
    if not confirming_file.is_file() or sha(confirming_file.read_bytes())!=str(confirming.get("sha256") or ""):fail("REPORT_CONFIRMING_READ_DRIFT")

    target_file=resolve_under(project_root,target)
    if not target_file.is_file():fail("REPORT_TARGET_MISSING")
    expected=[target]
    module_rel=target[:-len("Form.xml")]+"Form/Module.bsl"
    module_file=resolve_under(project_root,module_rel)
    if module_file.is_file():expected.append(module_rel)
    expected=sorted(expected)

    closure=r.get("input_closure")
    if not isinstance(closure,list) or not closure:fail("REPORT_INPUT_CLOSURE_MISSING")
    actual_rows=[]
    for row in closure:
        rel=str((row or {}).get("relative_path") or "").replace("\\","/").strip("/")
        f=resolve_under(project_root,rel)
        if not f.is_file():fail("REPORT_INPUT_MISSING",path=rel)
        h=sha(f.read_bytes())
        if h!=str((row or {}).get("sha256") or ""):fail("REPORT_INPUT_DRIFT",path=rel)
        actual_rows.append({"relative_path":rel,"sha256":h})
    actual_rows=sorted(actual_rows,key=lambda x:x["relative_path"])
    if [x["relative_path"] for x in actual_rows]!=expected:fail("REPORT_INPUT_CLOSURE_NOT_EXACT",expected=expected,actual=[x["relative_path"] for x in actual_rows])
    if sha(stable_bytes(actual_rows))!=r.get("input_closure_sha256"):fail("REPORT_INPUT_CLOSURE_DIGEST_MISMATCH")

    lock=json.loads(lock_path.read_text(encoding="utf-8-sig"))
    q=lock.get("local_quality_adapter") or {}
    if r.get("adapter_contract_version")!=q.get("contract") or r.get("upstream_commit")!=q.get("upstream_commit"):fail("REPORT_ADAPTER_PIN_MISMATCH")
    selected=(q.get("selected_scripts") or {}).get("form-validate.ps1") or {}
    if r.get("script_sha256")!=selected.get("sha256") or r.get("script_git_blob")!=selected.get("git_blob"):fail("REPORT_SCRIPT_PIN_MISMATCH")
    script_path=(ROOT/"PRODUCT/OneCChatWorker/runtime/quality/cc-1c-skills/form-validate.ps1").resolve()
    if not script_path.is_file() or sha(script_path.read_bytes())!=selected.get("sha256"):fail("REPORT_SCRIPT_COMPONENT_DRIFT")
    if r.get("normalized_args")!=["Detailed=false","MaxErrors=30"]:fail("REPORT_ARGS_MISMATCH")
    adapter_rel="PRODUCT/OneCChatWorker/runtime/local-quality-adapter.mjs"
    adapter_path=(ROOT/adapter_rel).resolve()
    expected_adapter=(lock.get("components") or {}).get("runtime/local-quality-adapter.mjs")
    if not adapter_path.is_file() or sha(adapter_path.read_bytes())!=expected_adapter:fail("REPORT_ADAPTER_COMPONENT_DRIFT")
    if r.get("overlay_sha256")!=q.get("overlay_sha256"):fail("REPORT_OVERLAY_PIN_MISMATCH")

    declared=r.get("report_sha256")
    base=dict(r);base.pop("report_sha256",None)
    if declared!=sha(stable_bytes(base)):fail("REPORT_SHA256_MISMATCH")

    result=str(r.get("result_class") or "")
    if result=="OK":
        print(json.dumps({"status":"PASS","property":"FORM_VALIDATE_CANONICAL_OK","report_sha256":declared,"target":target,"input_closure_sha256":r.get("input_closure_sha256")},ensure_ascii=False,sort_keys=True))
        raise SystemExit(0)
    if result=="FINDINGS":
        print(json.dumps({"status":"FAIL","error_class":"FORM_VALIDATE_FINDINGS","report_sha256":declared,"findings_count":len(r.get("findings") or []),"truncated":bool(r.get("truncated"))},ensure_ascii=False,sort_keys=True))
        raise SystemExit(2)
    fail("FORM_VALIDATE_EXECUTION_OR_INPUT_ERROR",result_class=result)

if __name__=="__main__":main()
