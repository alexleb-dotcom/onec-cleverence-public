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
GUI_FAKE = b"SAFE_FA_FAKE_EXECUTABLE_BYTES_ONLY"

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
        "gui_exe_sha256":hashlib.sha256(GUI_FAKE).hexdigest(),
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
    gui = repo / mod.GUI_EXE_PATH
    gui.parent.mkdir(parents=True)
    gui.write_bytes(GUI_FAKE)
    rows=[dict(path="docs/a.txt",size=16,sha256=hashlib.sha256(b"safe nested file").hexdigest()),
          dict(path=mod.GUI_EXE_PATH,size=len(GUI_FAKE),sha256=hashlib.sha256(GUI_FAKE).hexdigest())]
    m=manifest(rows)
    (repo/"DISTRIBUTION_MANIFEST.json").write_bytes(canonical(m))
    git(repo,"add","docs/a.txt",mod.GUI_EXE_PATH,"DISTRIBUTION_MANIFEST.json")
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
    def signed_index_for(commit, snapshot, *, exe_sha=None, counter=31):
        payload = {
            "schema": "ONEC_ORBIT_APPROVED_RELEASE_INDEX_V1",
            "repository": "alexleb-dotcom/onec-cleverence-public",
            "release_commit_sha": commit,
            "release_counter": counter,
            "gui_exe_sha256": exe_sha or hashlib.sha256(GUI_FAKE).hexdigest(),
            "distribution_snapshot_sha256": snapshot,
        }
        body = canonical(payload)
        authority = {
            "schema": "ONEC_ORBIT_SIGNED_RELEASE_AUTHORITY_V1",
            "repository": "alexleb-dotcom/onec-cleverence-public",
            "main_commit_sha": commit,
            "index_sha256": hashlib.sha256(body).hexdigest(),
            "release_counter": counter,
        }
        signature = synthetic["sign"](b"ONEC_ORBIT_RELEASE_AUTHORITY_V1" + bytes([0]) + canonical(authority))
        return body, canonical({**authority, "signature_hex": signature})
    mismatch_index, mismatch_envelope = signed_index_for(
        original, m["snapshot_digest"], exe_sha="f" * 64)
    refused, why = mod.verify_complete_release(
        repo, mismatch_index, mismatch_envelope,
        trusted_modulus=synthetic["n"], trusted_exponent=65537,
        protected_minimum_counter=31)
    require(refused is None and why == "TREE_GUI_EXE_SHA256_MISMATCH",
            f"FA blocker 1: independently signed contradictory GUI hash: {why}")
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
    # FA blocker 3: a NON-shallow local promisor clone must not fetch blobs
    # even if its configured origin is a local file:// fixture.
    import os
    with tempfile.TemporaryDirectory(prefix="orbit-promisor-fixture-") as prom:
        bare = Path(prom) / "origin.git"
        partial = Path(prom) / "partial"
        git(repo, "clone", "--bare", str(repo), str(bare))
        git(bare, "config", "uploadpack.allowFilter", "true")
        git(repo, "clone", "--no-checkout", "--filter=blob:none", bare.as_uri(), str(partial))
        require(git(partial, "rev-parse", "--is-shallow-repository") == "false",
                "promisor partial fixture must be non-shallow")
        missing_oid = git(repo, "rev-parse", original + ":" + mod.GUI_EXE_PATH)
        nofetch_env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
        def absent():
            result = subprocess.run(["git", "-C", str(partial), "cat-file", "-e", missing_oid],
                                    env=nofetch_env, capture_output=True)
            return result.returncode != 0
        require(absent(), "promisor EXE blob absent before offline verifier")
        denied, why = mod.verify_complete_release(
            partial, index, signed_envelope,
            trusted_modulus=synthetic["n"], trusted_exponent=65537,
            protected_minimum_counter=31)
        require(denied is None and why == "GIT_PROMISOR_PARTIAL_REPOSITORY_FORBIDDEN",
                f"FA blocker 3: complete verifier must refuse promisor: {why}")
        require(absent(), "complete verifier cannot fetch or mutate missing Git objects")
        nofetch = mod._git(partial, "cat-file", "blob", missing_oid)
        require(nofetch.returncode != 0 and absent(), "direct tree Git wrapper must not lazily fetch")
        refused, why = mod.verify_tree(partial, approved, index)
        require(not refused and why == "TREE_PROMISOR_PARTIAL_REPOSITORY_FORBIDDEN",
                f"tree verifier refuses promisor independently: {why}")
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
    # FA blocker 1: no GUI image in the signed tree and manifest.
    git(repo, "reset", "--hard", original)
    git(repo, "rm", "--", mod.GUI_EXE_PATH)
    missing_manifest = manifest([row for row in rows if row["path"] != mod.GUI_EXE_PATH])
    (repo/"DISTRIBUTION_MANIFEST.json").write_bytes(canonical(missing_manifest))
    git(repo, "add", "DISTRIBUTION_MANIFEST.json")
    git(repo, "commit", "-qm", "missing GUI fixture")
    missing_commit = git(repo, "rev-parse", "HEAD")
    missing_idx, missing_envelope = signed_index_for(missing_commit, missing_manifest["snapshot_digest"])
    rejected, why = mod.verify_complete_release(
        repo, missing_idx, missing_envelope,
        trusted_modulus=synthetic["n"], trusted_exponent=65537, protected_minimum_counter=31)
    require(rejected is None and why == "TREE_GUI_EXE_MISSING",
            f"FA blocker 1: missing image must be refused: {why}")

    # FA blocker 2: a real Git index entry with a Windows superscript device.
    git(repo, "reset", "--hard", original)
    bad_name = "COM" + chr(0xB9) + ".txt"
    payload = b"fake reserved-path fixture"
    bad_oid = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                             input=payload, capture_output=True, check=True).stdout.decode().strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"100644,{bad_oid},{bad_name}")
    bad_rows = rows + [dict(path=bad_name, size=len(payload),
                            sha256=hashlib.sha256(payload).hexdigest())]
    bad_manifest = manifest(bad_rows)
    (repo/"DISTRIBUTION_MANIFEST.json").write_bytes(canonical(bad_manifest))
    git(repo, "add", "DISTRIBUTION_MANIFEST.json")
    git(repo, "commit", "-qm", "Windows device name fixture")
    bad_commit = git(repo, "rev-parse", "HEAD")
    bad_index, bad_envelope = signed_index_for(bad_commit, bad_manifest["snapshot_digest"])
    rejected, why = mod.verify_complete_release(
        repo, bad_index, bad_envelope,
        trusted_modulus=synthetic["n"], trusted_exponent=65537, protected_minimum_counter=31)
    require(rejected is None and why == "TREE_UNSAFE_OR_COLLIDING_PATH",
            f"FA blocker 2: signed reserved Windows path must be denied: {why}")
    for prefix in ("COM", "LPT"):
        for num in (chr(0xB9), chr(0xB2), chr(0xB3)):
            for name in (prefix + num, prefix.lower() + num + ".txt", "docs/" + prefix + num + ".dat"):
                require(not mod._safe_path(name), f"Windows reserved superscript: {name}")
    for path in ("../evil","docs/../evil","docs\\evil","CON","docs/a.txt:stream","a.","docs//bad","docs/é"):
        require(not mod._safe_path(path) if path != "docs/é" else mod._safe_path(path),
                f"path contract: {path}")
print(f"ORBIT_GIT_TREE_OFFLINE_PASS checks={checks} network_calls=0 production_access=false")
