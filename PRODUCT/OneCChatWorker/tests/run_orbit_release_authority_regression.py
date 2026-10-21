#!/usr/bin/env python3
"""Offline fake-key S2-L1B authority tests. No production interaction."""
import hashlib
import importlib.util
import json
import random
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = root / "update" / "release_authority.py"
spec = importlib.util.spec_from_file_location("release_authority", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
checks = 0

def require(condition, name):
    global checks
    assert condition, name
    checks += 1

def probable_prime(n):
    if n < 2 or n % 2 == 0: return False
    s, d = 0, n-1
    while d % 2 == 0:
        s += 1
        d //= 2
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41):
        x = pow(a, d, n)
        if x == 1 or x == n-1: continue
        for _ in range(s-1):
            x = pow(x, 2, n)
            if x == n-1: break
        else: return False
    return True

rng = random.Random(567)  # synthetic, public, NOT cryptographic key generation.
def prime():
    while True:
        candidate = rng.getrandbits(1025) | (1 << 1024) | 1
        if probable_prime(candidate): return candidate
p, q = prime(), prime()
while q == p: q = prime()
n, e = p*q, 65537
d = pow(e, -1, (p-1)*(q-1))
def sign(data):
    length = (n.bit_length() + 7)//8
    t = mod.SHA256_DER_PREFIX + hashlib.sha256(data).digest()
    block = b"\x00\x01" + b"\xff"*(length-len(t)-3) + b"\x00" + t
    return pow(int.from_bytes(block,"big"),d,n).to_bytes(length,"big").hex()

def raw(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":")).encode()

def envelope(index_bytes, *, main="a"*40, counter=12):
    base = dict(schema=mod.SCHEMA,repository=mod.REPOSITORY,main_commit_sha=main,
                index_sha256=hashlib.sha256(index_bytes).hexdigest(),release_counter=counter)
    return raw(dict(base,signature_hex=sign(mod.DOMAIN+raw(base))))

index = raw(dict(schema="ONEC_ORBIT_APPROVED_RELEASE_INDEX_V1",repository=mod.REPOSITORY,
                 release_commit_sha="b"*40,release_counter=12,
                 gui_exe_sha256="c"*64,distribution_snapshot_sha256="d"*64))
env = envelope(index)
def verify(i=index, x=env, key=n, minimum=11):
    return mod.verify_approval(i,x,trusted_modulus=key,trusted_exponent=e,minimum_counter=minimum)
a, reason = verify()
require(reason == "SIGNED_APPROVAL_VALID" and a is not None and a["main_commit_sha"] == "a"*40,f"signed authority reason={reason} bits={n.bit_length()}")
for i,x,key,minimum,why in [
    (index+b"x",env,n,11,"AUTHORITY_INDEX_MISMATCH"),
    (index,env,n+2,11,"AUTHORITY_SIGNATURE_INVALID"),
    (index,env,n,13,"AUTHORITY_ROLLBACK"),
    (None,env,n,11,"AUTHORITY_UNAVAILABLE"),
    (index,None,n,11,"AUTHORITY_UNAVAILABLE"),
    (index,env,None,11,"AUTHORITY_SIGNATURE_INVALID"),
    (index,env,n,True,"TRUSTED_COUNTER_MISSING"),
    (index,env.replace(b"onec-cleverence-public",b"evil-cleverence-public"),n,11,"AUTHORITY_ORIGIN_INVALID"),
    (index,env+b"x",n,11,"AUTHORITY_MALFORMED"),
]:
    result, got = verify(i,x,key,minimum)
    require(result is None and got == why, f"{why}: {got}")
extra=json.loads(env)
extra["untrusted_key"]="attack"
require(verify(x=raw(extra))[0] is None,"extra fields blocked")
duplicate=env.replace(b'"schema":',b'"schema":"spoof","schema":')
require(verify(x=duplicate)[0] is None,"duplicate fields blocked")
bad_signature=json.loads(env)
bad_signature["signature_hex"]="00"*256
require(verify(x=raw(bad_signature))[0] is None,"signature forgery blocked")
require(mod.verify_rsa_sha256(b"wrong",bytes.fromhex(json.loads(env)["signature_hex"]),n,e) is False,"wrong signature message")
require(mod.verify_rsa_sha256(b"x",b"x"*256,17,e) is False,"short modulus rejected")
with tempfile.TemporaryDirectory(prefix="orbit-authority-fixture-") as temp:
    repo=Path(temp)
    def git(*args):
        result=subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stderr)
        return result.stdout.strip()
    git("init","-q")
    git("config","user.name","Fixture")
    git("config","user.email","fixture")
    (repo/"fixture.txt").write_text("r1",encoding="utf-8")
    git("add","fixture.txt")
    git("commit","-qm","fixture old")
    old=git("rev-parse","HEAD")
    (repo/"fixture.txt").write_text("r2",encoding="utf-8")
    git("add","fixture.txt")
    git("commit","-qm","fixture new")
    new=git("rev-parse","HEAD")
    yes,why=mod.verify_git_ancestry(repo,dict(release_commit_sha=old,main_commit_sha=new))
    require(yes and why=="SIGNED_MAIN_CONTAINS_RELEASE",f"ancestry true {why}")
    yes,why=mod.verify_git_ancestry(repo,dict(release_commit_sha=new,main_commit_sha=old))
    require(not yes and why=="GIT_ANCESTRY_UNVERIFIED",f"reverse chain {why}")
    yes,why=mod.verify_git_ancestry(repo,dict(release_commit_sha="f"*40,main_commit_sha=new))
    require(not yes and why=="GIT_COMMIT_UNAVAILABLE",f"missing object {why}")
    shallow = repo / ".git" / "shallow"
    shallow.write_text(new + chr(10), encoding="ascii")
    yes,why=mod.verify_git_ancestry(repo,dict(release_commit_sha=old,main_commit_sha=new))
    require(not yes and why=="GIT_HISTORY_INCOMPLETE",f"shallow rejected {why}")
    shallow.unlink()
    grafts = repo / ".git" / "info" / "grafts"
    grafts.write_text(new + chr(10), encoding="ascii")
    yes,why=mod.verify_git_ancestry(repo,dict(release_commit_sha=old,main_commit_sha=new))
    require(not yes and why=="GIT_HISTORY_OVERRIDE",f"graft rejected {why}")
    grafts.unlink()
print(f"ORBIT_RELEASE_AUTHORITY_OFFLINE_PASS checks={checks} network_calls=0 install_calls=0 production_access=false")
