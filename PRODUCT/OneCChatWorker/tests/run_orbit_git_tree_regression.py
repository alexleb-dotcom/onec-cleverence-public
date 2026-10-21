#!/usr/bin/env python3
"""Fully isolated committed Git-tree inventory proof regression."""
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

update = Path(__file__).resolve().parents[1] / "update"
spec = importlib.util.spec_from_file_location("orbit_git_tree", update / "release_git_tree.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
checks = 0

def require(value, label):
    global checks
    assert value, label
    checks += 1

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")

def git(repo, *args):
    p = subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True)
    if p.returncode: raise RuntimeError(f"{args}: {p.stderr}")
    return p.stdout.strip()

def manifest(rows):
    ordered = sorted(rows,key=lambda x:x["path"])
    data = dict(mod.CONSTANTS,file_count=len(rows),files=ordered)
    data["snapshot_digest"] = hashlib.sha256(b"SHAREABLE_CORE_SNAPSHOT_V1\x00"+canonical(data)).hexdigest()
    return data

def pair(repo, commit, snapshot):
    index = canonical({
        "schema":"ONEC_ORBIT_APPROVED_RELEASE_INDEX_V1",
        "repository":"alexleb-dotcom/onec-cleverence-public",
        "release_commit_sha":commit,
        "release_counter":31,
        "gui_exe_sha256":"9"*64,
        "distribution_snapshot_sha256":snapshot
    })
    return {"release_commit_sha":commit,"release_counter":31,"index_sha256":hashlib.sha256(index).hexdigest()},index

with tempfile.TemporaryDirectory(prefix="orbit-git-tree-fixture-") as tmp:
    repo = Path(tmp)
    git(repo, "init","-q")
    git(repo, "config","user.name","Fixture")
    git(repo, "config","user.email","fixture")
    (repo/"docs").mkdir()
    (repo/"docs"/"a.txt").write_bytes(b"safe nested file")
    rows=[dict(path="docs/a.txt",size=16,sha256=hashlib.sha256(b"safe nested file").hexdigest())]
    m=manifest(rows)
    (repo/"DISTRIBUTION_MANIFEST.json").write_bytes(canonical(m))
    git(repo,"add","docs/a.txt","DISTRIBUTION_MANIFEST.json")
    git(repo,"commit","-qm","approved fixture")
    original=git(repo,"rev-parse","HEAD")
    approved,index=pair(repo,original,m["snapshot_digest"])
    proof,reason=mod.verify_tree(repo,approved,index)
    require(proof and reason=="SIGNED_INDEX_MATCHES_COMPLETE_GIT_TREE", f"valid tree: {reason}")
    # End-to-end approval must be separately signed with synthetic fixture RSA.
    import runpy
    synthetic = runpy.run_path(str(Path(__file__).with_name("run_orbit_release_authority_regression.py")))
    signed_body = {
        "schema": "ONEC_ORBIT_SIGNED_RELEASE_AUTHORITY_V1",
        "repository": "alexleb-dotcom/onec-cleverence-public",
        "main_commit_sha": original,
        "index_sha256": approved["index_sha256"],
        "release_counter": 31,
    }
    signature = synthetic["sign"](b"ONEC_ORBIT_RELEASE_AUTHORITY_V1" + bytes([0]) + canonical(signed_body))
    signed_envelope = canonical({**signed_body, "signature_hex": signature})
    result, why = mod.verify_complete_release(
        repo, index, signed_envelope,
        trusted_modulus=synthetic["n"], trusted_exponent=65537,
        protected_minimum_counter=31)
    require(result is not None and why == "COMPLETE_SIGNED_RELEASE_PROVENANCE_VERIFIED",
            f"complete signed pipeline: {why}")
    result, why = mod.verify_complete_release(
        repo, index, signed_envelope,
        trusted_modulus=None, trusted_exponent=65537,
        protected_minimum_counter=31)
    require(result is None and why == "AUTHORITY_SIGNATURE_INVALID",
            f"missing independent public key: {why}")
    result, why = mod.verify_complete_release(
        repo, index, signed_envelope,
        trusted_modulus=synthetic["n"], trusted_exponent=65537,
        protected_minimum_counter=32)
    require(result is None and why == "AUTHORITY_ROLLBACK",
            f"protected minimum release floor: {why}")
    for newindex,needed in [
        (index+b"x","TREE_INVALID_OR_UNAVAILABLE"),
        (canonical({**json.loads(index),"distribution_snapshot_sha256":"f"*64}),"TREE_APPROVAL_MISMATCH")
    ]:
        ok,why=mod.verify_tree(repo,approved,newindex)
        require(not ok and why==needed, f"tampered index: {why}")
    changed_index=dict(json.loads(index),distribution_snapshot_sha256="f"*64)
    altered=canonical(changed_index)
    changed_pin={**approved,"index_sha256":hashlib.sha256(altered).hexdigest()}
    ok,why=mod.verify_tree(repo,changed_pin,altered)
    require(not ok and why=="TREE_SIGNED_DISTRIBUTION_MISMATCH",f"wrong independently signed manifest: {why}")
    (repo/"extra.txt").write_text("unauthorized",encoding="utf-8")
    git(repo,"add","extra.txt")
    git(repo,"commit","-qm","injected file")
    altered_commit=git(repo,"rev-parse","HEAD")
    newapproved,newindex=pair(repo,altered_commit,m["snapshot_digest"])
    ok,why=mod.verify_tree(repo,newapproved,newindex)
    require(not ok and why=="TREE_FILE_SET_MISMATCH",f"extra tree blob: {why}")
    # A Git index symlink mode is testable on Windows without creating a real symlink.
    git(repo,"reset","--hard",original)
    oid=subprocess.run(["git","-C",str(repo),"hash-object","-w","--stdin"],
                       input=b"docs/a.txt",capture_output=True,check=True).stdout.decode().strip()
    git(repo,"update-index","--add","--cacheinfo",f"120000,{oid},link")
    git(repo,"commit","-qm","malicious symlink mode")
    symlink_commit=git(repo,"rev-parse","HEAD")
    signed,bytes_index=pair(repo,symlink_commit,m["snapshot_digest"])
    ok,why=mod.verify_tree(repo,signed,bytes_index)
    require(not ok and why=="TREE_SYMLINK_SUBMODULE_OR_MODE_FORBIDDEN",f"symlink: {why}")
    git(repo,"reset","--hard",original)
    git(repo,"update-index","--add","--cacheinfo",f"160000,{original},subproject")
    git(repo,"commit","-qm","malicious submodule mode")
    submodule_commit=git(repo,"rev-parse","HEAD")
    signed,bytes_index=pair(repo,submodule_commit,m["snapshot_digest"])
    ok,why=mod.verify_tree(repo,signed,bytes_index)
    require(not ok and why=="TREE_SYMLINK_SUBMODULE_OR_MODE_FORBIDDEN",f"submodule: {why}")
    for path in ("../evil","docs/../evil","docs\\evil","CON","docs/a.txt:stream","a.","docs//bad","docs/é"):
        require(not mod._safe_path(path) if path != "docs/é" else mod._safe_path(path),
                f"path contract: {path}")
print(f"ORBIT_GIT_TREE_OFFLINE_PASS checks={checks} network_calls=0 production_access=false")
