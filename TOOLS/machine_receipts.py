#!/usr/bin/env python3
"""Execute deterministic analyzers and verify content-bound machine receipts.

The verifier derives PASS/FAIL from the registered command, current tool bytes,
current input bytes and replayed output. A model-authored ``result=PASS`` field is
not proof. Declared properties are restricted to capabilities owned by each tool.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SCHEMA_VERSION=2
TOOL_CAPABILITIES={
    "TOOLS/analyze_onec_bsl.py":{"STATIC:ONEC_BSL"},
    "TOOLS/analyze_onec_xml.py":{"STATIC:ONEC_XML"},
    "TOOLS/analyze_onec_field_flow.py":{"STATIC:FIELD_FLOW"},
    "TOOLS/analyze_onec_reachability.py":{"STATIC:REACHABILITY"},
    "TOOLS/analyze_changeset_architecture.py":{"STATIC:CHANGESET_ARCHITECTURE"},
    "TOOLS/analyze_cleverence_mslx.py":{"STATIC:CLEVERENCE_MSLX"},
    "TOOLS/analyze_cleverence_configuration.py":{"STATIC:CLEVERENCE_CONFIGURATION"},
    "TOOLS/check_bsl_call_signatures.py":{"STATIC:CALL_SIGNATURE"},
    "TOOLS/validate_project_snapshot_package.py":{"EVIDENCE:PROJECT_SNAPSHOT_PACKAGE_BINDING"},
}
ALLOWED_TOOLS=set(TOOL_CAPABILITIES)


def _sha(data):return hashlib.sha256(data).hexdigest()
def _has_text(value):return isinstance(value,str) and bool(value.strip())


def _tool_path(tool):
    if not _has_text(tool):raise ValueError("machine receipt tool is required")
    candidate=Path(tool)
    if candidate.is_absolute():
        try:relative=candidate.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:raise ValueError("machine receipt tool must be inside repository")
    else:relative=candidate.as_posix().lstrip("./")
    if relative not in ALLOWED_TOOLS:raise ValueError(f"tool is not a registered deterministic analyzer: {relative}")
    path=(ROOT/relative).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    return relative,path


def _input_snapshot(path_value):
    path=Path(path_value)
    if not path.is_file():raise FileNotFoundError(path)
    data=path.read_bytes()
    return {"path":str(path),"sha256":_sha(data),"size":len(data)}


def _run(relative_tool,tool_path,argv):
    proc=subprocess.run([sys.executable,str(tool_path),*argv],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    return {"exit_code":proc.returncode,"stdout":proc.stdout,"stderr":proc.stderr}


def _validate_properties(relative_tool,properties):
    if not isinstance(properties,(list,tuple)) or not properties or any(not _has_text(x) for x in properties):
        raise ValueError("at least one verified property is required")
    unique=list(dict.fromkeys(str(x) for x in properties))
    unsupported=sorted(set(unique)-TOOL_CAPABILITIES[relative_tool])
    if unsupported:raise ValueError(f"properties are not supported by {relative_tool}: {unsupported}")
    return unique


def create_receipt(tool,argv,input_paths,properties,receipt_path):
    relative,tool_path=_tool_path(tool)
    properties=_validate_properties(relative,properties)
    inputs=[_input_snapshot(x) for x in input_paths]
    if not inputs:raise ValueError("machine receipt requires at least one explicit input snapshot")
    argv=list(argv)
    if any(not isinstance(x,str) for x in argv):raise ValueError("machine receipt argv must contain strings")
    run=_run(relative,tool_path,argv)
    receipt_path=Path(receipt_path); receipt_path.parent.mkdir(parents=True,exist_ok=True)
    stdout_path=receipt_path.with_suffix(receipt_path.suffix+".stdout")
    stderr_path=receipt_path.with_suffix(receipt_path.suffix+".stderr")
    stdout_path.write_bytes(run["stdout"]); stderr_path.write_bytes(run["stderr"])
    receipt={
        "schema_version":SCHEMA_VERSION,
        "kind":"MACHINE_RECEIPT",
        "tool":relative,
        "tool_sha256":_sha(tool_path.read_bytes()),
        "python_version":sys.version.split()[0],
        "argv":argv,
        "inputs":inputs,
        "verified_properties":properties,
        "derived_result":"PASS" if run["exit_code"]==0 else "FAIL",
        "exit_code":run["exit_code"],
        "output":{
            "stdout_path":str(stdout_path),"stdout_sha256":_sha(run["stdout"]),
            "stderr_path":str(stderr_path),"stderr_sha256":_sha(run["stderr"]),
        },
        "limitations":["Receipt proves only execution of the registered deterministic analyzer for its declared capability. It is not runtime, business, performance or concurrency proof."],
    }
    receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return receipt


def _validate_output_file(path_value,expected,label,errors):
    if not _has_text(path_value) or not _has_text(expected):
        errors.append({"type":"MACHINE_RECEIPT_OUTPUT_INCOMPLETE","field":label}); return None
    path=Path(path_value)
    if not path.is_file():errors.append({"type":"MACHINE_RECEIPT_OUTPUT_MISSING","field":label,"path":str(path)}); return None
    actual=_sha(path.read_bytes())
    if actual!=expected:errors.append({"type":"MACHINE_RECEIPT_OUTPUT_DRIFT","field":label,"path":str(path),"expected":expected,"actual":actual})
    return actual


def verify_receipt(path_value,replay=True):
    errors=[]; path=Path(path_value)
    if not path.is_file():return {"integrity_result":"FAIL","derived_result":None,"errors":[{"type":"MACHINE_RECEIPT_MISSING","path":str(path)}]}
    raw=path.read_bytes(); receipt_sha=_sha(raw)
    try:receipt=json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:return {"integrity_result":"FAIL","derived_result":None,"errors":[{"type":"MACHINE_RECEIPT_PARSE_ERROR","path":str(path),"error":str(exc)}],"receipt_sha256":receipt_sha}
    if receipt.get("schema_version")!=SCHEMA_VERSION:errors.append({"type":"MACHINE_RECEIPT_SCHEMA_UNSUPPORTED","actual":receipt.get("schema_version")})
    if receipt.get("kind")!="MACHINE_RECEIPT":errors.append({"type":"MACHINE_RECEIPT_KIND_INVALID","actual":receipt.get("kind")})
    try:relative,tool_path=_tool_path(receipt.get("tool"))
    except Exception as exc:
        errors.append({"type":"MACHINE_RECEIPT_TOOL_INVALID","tool":receipt.get("tool"),"error":str(exc)}); relative=tool_path=None
    if tool_path:
        actual_tool_sha=_sha(tool_path.read_bytes())
        if actual_tool_sha!=receipt.get("tool_sha256"):errors.append({"type":"MACHINE_RECEIPT_TOOL_DRIFT","tool":relative,"expected":receipt.get("tool_sha256"),"actual":actual_tool_sha})
    properties=receipt.get("verified_properties")
    if not isinstance(properties,list) or not properties or any(not _has_text(x) for x in properties):
        errors.append({"type":"MACHINE_RECEIPT_PROPERTIES_MISSING"}); properties=[]
    elif relative:
        unsupported=sorted(set(properties)-TOOL_CAPABILITIES[relative])
        if unsupported:errors.append({"type":"MACHINE_RECEIPT_PROPERTY_UNSUPPORTED","tool":relative,"properties":unsupported})
    inputs=receipt.get("inputs")
    if not isinstance(inputs,list) or not inputs:errors.append({"type":"MACHINE_RECEIPT_INPUTS_MISSING"}); inputs=[]
    for index,row in enumerate(inputs):
        if not isinstance(row,dict) or not _has_text(row.get("path")) or not _has_text(row.get("sha256")):
            errors.append({"type":"MACHINE_RECEIPT_INPUT_INCOMPLETE","index":index}); continue
        candidate=Path(row["path"])
        if not candidate.is_file():errors.append({"type":"MACHINE_RECEIPT_INPUT_MISSING","index":index,"path":row["path"]}); continue
        actual=_sha(candidate.read_bytes())
        if actual!=row["sha256"]:errors.append({"type":"MACHINE_RECEIPT_INPUT_DRIFT","index":index,"path":row["path"],"expected":row["sha256"],"actual":actual})
    output=receipt.get("output") or {}
    _validate_output_file(output.get("stdout_path"),output.get("stdout_sha256"),"stdout",errors)
    _validate_output_file(output.get("stderr_path"),output.get("stderr_sha256"),"stderr",errors)
    argv=receipt.get("argv")
    if not isinstance(argv,list) or any(not isinstance(x,str) for x in argv):errors.append({"type":"MACHINE_RECEIPT_ARGV_INVALID"}); argv=[]
    stored_exit=receipt.get("exit_code")
    if not isinstance(stored_exit,int):errors.append({"type":"MACHINE_RECEIPT_EXIT_INVALID","actual":stored_exit})
    derived="PASS" if stored_exit==0 else "FAIL"
    if receipt.get("derived_result")!=derived:errors.append({"type":"MACHINE_RECEIPT_RESULT_INCONSISTENT","declared":receipt.get("derived_result"),"exit_code":stored_exit})
    replay_result=None
    if replay and not errors and tool_path:
        replay_run=_run(relative,tool_path,argv); replay_result="PASS" if replay_run["exit_code"]==0 else "FAIL"
        if replay_run["exit_code"]!=stored_exit:errors.append({"type":"MACHINE_RECEIPT_REPLAY_EXIT_DRIFT","stored":stored_exit,"actual":replay_run["exit_code"]})
        if _sha(replay_run["stdout"])!=output.get("stdout_sha256"):errors.append({"type":"MACHINE_RECEIPT_REPLAY_STDOUT_DRIFT"})
        if _sha(replay_run["stderr"])!=output.get("stderr_sha256"):errors.append({"type":"MACHINE_RECEIPT_REPLAY_STDERR_DRIFT"})
    return {
        "integrity_result":"PASS" if not errors else "FAIL",
        "derived_result":derived,
        "errors":errors,
        "receipt":receipt,
        "verified_properties":properties,
        "replay_result":replay_result,
        "receipt_sha256":receipt_sha,
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--tool",required=True); ap.add_argument("--input",action="append",dest="inputs",default=[]); ap.add_argument("--property",action="append",dest="properties",default=[]); ap.add_argument("--receipt",required=True); ap.add_argument("tool_args",nargs=argparse.REMAINDER)
    a=ap.parse_args(); args=a.tool_args[1:] if a.tool_args[:1]==["--"] else a.tool_args
    receipt=create_receipt(a.tool,args,a.inputs,a.properties,a.receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2)); raise SystemExit(0 if receipt["derived_result"]=="PASS" else 2)

if __name__=="__main__":main()
