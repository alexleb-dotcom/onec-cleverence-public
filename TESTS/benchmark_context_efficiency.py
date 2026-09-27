#!/usr/bin/env python3
"""Context/performance benchmark for compact validation and real large corpora.

Small R1/R2/R3 scenarios protect compact-context behavior. Large-corpus scenarios
exercise actual files through hashing, inventory, routing, full plan, full ledger
and verifier-owned compact projection instead of simulating scale with evidence rows.
"""
from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import tempfile
import time

try:
    import resource as _resource
except ImportError:  # Windows
    _resource=None

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"TOOLS"))

import build_review_plan as review_plan
from artifact_corpus import inventory_paths, analyzable_entries
from build_review_plan import build_plan, compact_summary
from build_validation_ledger import build_ledger
from validation_work_queue import build_work_queue
from rule_registry import load_registry

MAX_R1_BYTES=12*1024
MAX_SMALL_SECONDS=10.0
MAX_RSS_KIB=512*1024
LARGE_TOTAL_LIMITS={1000:30.0,10000:120.0,20000:240.0}


def peak_rss_kib():
    if _resource is None:return None
    value=_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes.
    if sys.platform=="darwin":return int(value/1024)
    return int(value)


def compact_size(plan,ledger):
    queue=build_work_queue(ledger)
    payload=json.dumps(compact_summary(plan),ensure_ascii=False,separators=(",",":"))+"\n"+json.dumps(queue,ensure_ascii=False,separators=(",",":"))+"\n"
    return len(payload.encode("utf-8")),queue


def run_case(name,paths,risk,surface=None):
    start=time.perf_counter()
    plan=build_plan([str(x) for x in paths],analysis_only=True,risk_override=risk,surface_override=surface)
    ledger=build_ledger(plan); size,queue=compact_size(plan,ledger); elapsed=time.perf_counter()-start
    return {
        "name":name,"risk":risk,"surface":plan.get("routing",{}).get("surface"),
        "compact_bytes":size,"elapsed_ms":round(elapsed*1000,2),
        "active_profiles":len(plan.get("active_profiles") or []),"ledger_rules":len(ledger.get("rules") or []),
        "queued_rules":queue.get("counts",{}).get("rules"),"queued_checks":queue.get("counts",{}).get("checks"),
        "verifier_status":queue.get("verifier",{}).get("status"),
    },plan,ledger


def _write_corpus(directory:Path,count:int):
    directory.mkdir(parents=True,exist_ok=True)
    payload="Процедура Обработать()\n    Значение = 1;\nКонецПроцедуры\n".encode("utf-8")
    for i in range(count):(directory/f"module_{i:05d}.bsl").write_bytes(payload)
    return payload


def _decode(data):
    try:return data.decode("utf-8-sig")
    except UnicodeDecodeError:return data.decode("utf-8",errors="replace")


def benchmark_real_corpus(directory:Path,count:int):
    _write_corpus(directory,count)
    files=sorted(directory.glob("*.bsl"))

    start=time.perf_counter()
    digest=hashlib.sha256()
    for path in files:
        data=path.read_bytes(); digest.update(path.name.encode("utf-8")); digest.update(hashlib.sha256(data).digest())
    hashing=time.perf_counter()-start

    start=time.perf_counter(); corpus=inventory_paths([str(directory)]); inventory=time.perf_counter()-start

    entries=list(analyzable_entries(corpus))
    texts=[]; sources=[]
    for semantic,data,_origin,row in entries:
        text=_decode(data); texts.append(text)
        names=list(dict.fromkeys([semantic,*getattr(row,"routing_aliases",[])]))
        sources.extend((name,text) for name in names)
    start=time.perf_counter()
    review_plan._activate_rules(load_registry(),"\n".join(texts),texts,[],"ONEC_ONLY",True,sources,[],sources)
    routing=time.perf_counter()-start

    total_start=time.perf_counter()
    start=time.perf_counter(); plan=build_plan([str(directory)],analysis_only=True,risk_override="R1_CONTRACT",surface_override="ONEC_ONLY"); plan_time=time.perf_counter()-start
    start=time.perf_counter(); ledger=build_ledger(plan); ledger_time=time.perf_counter()-start
    start=time.perf_counter(); compact_bytes,queue=compact_size(plan,ledger); compact_time=time.perf_counter()-start
    total=time.perf_counter()-total_start

    return {
        "name":f"REAL_CORPUS_{count}","files":count,
        "phase_ms":{
            "hashing":round(hashing*1000,2),
            "inventory_including_internal_hashing":round(inventory*1000,2),
            "routing_trigger_scan":round(routing*1000,2),
            "review_plan":round(plan_time*1000,2),
            "full_ledger":round(ledger_time*1000,2),
            "compact_projection_with_release_reverification":round(compact_time*1000,2),
            "end_to_end_plan_ledger_compact":round(total*1000,2),
        },
        "compact_bytes":compact_bytes,
        "candidate_artifacts":len(plan.get("candidate_artifacts") or []),
        "ledger_bytes":len(json.dumps(ledger,ensure_ascii=False,separators=(",",":")).encode("utf-8")),
        "active_profiles":len(plan.get("active_profiles") or []),
        "verifier_status":queue.get("verifier",{}).get("status"),
        "peak_rss_kib_at_end":peak_rss_kib(),
        "hash_fingerprint":digest.hexdigest(),
    }


def main():
    failures=[]; rows=[]; large_rows=[]
    with tempfile.TemporaryDirectory() as td:
        temp=Path(td); r1=temp/"r1.bsl"; r1.write_text("Процедура Обработать()\n    Значение = 1;\nКонецПроцедуры\n",encoding="utf-8")
        cases=[
            ("R1",[r1],"R1_CONTRACT",None),
            ("R2",[ROOT/"TESTS/fixtures/transaction_bad.bsl"],"R2_STATEFUL_RUNTIME","ONEC_ONLY"),
            ("R3",[ROOT/"TESTS/fixtures/query_field_good.bsl",ROOT/"TESTS/fixtures/cleverence_graph_good.mslx"],"R3_CROSS_SYSTEM","CROSS_SYSTEM"),
            ("MAX_PROFILES",[ROOT/"TESTS/fixtures/all_onec_profile_activation.bsl",ROOT/"TESTS/fixtures/cleverence_graph_good.mslx"],"R3_CROSS_SYSTEM","CROSS_SYSTEM"),
        ]
        snapshots={}
        for args in cases:
            row,plan,ledger=run_case(*args); rows.append(row); snapshots[row["name"]]=(plan,ledger)
            if row["elapsed_ms"]/1000>MAX_SMALL_SECONDS:failures.append({"case":row["name"],"type":"TIME_LIMIT","actual_ms":row["elapsed_ms"]})
        if rows[0]["compact_bytes"]>MAX_R1_BYTES:failures.append({"case":"R1","type":"COMPACT_BUDGET","actual":rows[0]["compact_bytes"],"limit":MAX_R1_BYTES})
        if next(x for x in rows if x["name"]=="MAX_PROFILES")["active_profiles"]<5:failures.append({"case":"MAX_PROFILES","type":"PROFILE_ACTIVATION_TOO_SMALL"})

        # Retained non-work payload still must not inflate the compact projection.
        plan,base=snapshots["R1"]; large=copy.deepcopy(base); dep=large["candidate_artifacts"][0]
        for i in range(1000):
            large["evidence_registry"].append({"id":f"E:BENCH:{i}","kind":"SEMANTIC","ref":f"benchmark retained evidence {i}","dependencies":[{"kind":"CANDIDATE","id":dep["logical_path"],"fingerprint":dep["sha256"]}]})
        start=time.perf_counter(); large_size,_=compact_size(plan,large); large_elapsed=time.perf_counter()-start
        rows.append({"name":"LARGE_RETAINED_LEDGER","compact_bytes":large_size,"elapsed_ms":round(large_elapsed*1000,2),"ledger_bytes":len(json.dumps(large,ensure_ascii=False).encode("utf-8"))})
        if large_size-rows[0]["compact_bytes"]>1024:failures.append({"case":"LARGE_RETAINED_LEDGER","type":"COMPACT_GROWS_WITH_NONWORK_PAYLOAD","delta":large_size-rows[0]["compact_bytes"]})

        invalid=copy.deepcopy(base)
        for rule in invalid.get("rules") or []:
            rule["status"]="PASS"; rule["evidence"]=[]
            for check in rule.get("checks") or []:check["status"]="PASS"; check["evidence"]=[]
        start=time.perf_counter(); invalid_size,invalid_queue=compact_size(plan,invalid); invalid_elapsed=time.perf_counter()-start
        rows.append({"name":"MANY_UNCONFIRMED","compact_bytes":invalid_size,"elapsed_ms":round(invalid_elapsed*1000,2),"resolution_review_required":invalid_queue.get("counts",{}).get("resolution_review_required")})
        if invalid_size<=rows[0]["compact_bytes"]:failures.append({"case":"MANY_UNCONFIRMED","type":"UNRESOLVED_WORK_DID_NOT_GROW_QUEUE"})
        if not invalid_queue.get("counts",{}).get("resolution_review_required"):failures.append({"case":"MANY_UNCONFIRMED","type":"UNVERIFIED_TERMINAL_ROWS_HIDDEN"})

        sizes=[1000,10000]
        if os.environ.get("CI","").lower() in {"1","true","yes"}:sizes.append(20000)
        for count in sizes:
            row=benchmark_real_corpus(temp/f"corpus_{count}",count); large_rows.append(row)
            elapsed=row["phase_ms"]["end_to_end_plan_ledger_compact"]/1000
            if elapsed>LARGE_TOTAL_LIMITS[count]:failures.append({"case":row["name"],"type":"LARGE_CORPUS_TIME_LIMIT","actual_seconds":elapsed,"limit_seconds":LARGE_TOTAL_LIMITS[count]})
            if row["candidate_artifacts"]!=count:failures.append({"case":row["name"],"type":"CORPUS_INVENTORY_COUNT_DRIFT","actual":row["candidate_artifacts"],"expected":count})

    rss=peak_rss_kib()
    if rss is not None and rss>MAX_RSS_KIB:failures.append({"case":"PROCESS","type":"PEAK_RSS_LIMIT","actual_kib":rss,"limit_kib":MAX_RSS_KIB})
    report={
        "result":"PASS" if not failures else "FAIL","scenarios":rows,"real_corpus_scenarios":large_rows,
        "peak_rss_kib":rss,
        "peak_rss_measurement":"resource.getrusage(RUSAGE_SELF).ru_maxrss on Linux/macOS; unavailable (null, non-failing) on Windows",
        "thresholds":{"r1_compact_bytes":MAX_R1_BYTES,"max_small_seconds":MAX_SMALL_SECONDS,"max_rss_kib":MAX_RSS_KIB,"large_corpus_total_seconds":LARGE_TOTAL_LIMITS,"large_ledger_nonwork_delta_bytes":1024},
        "failures":failures,
        "proof_boundary":"Phase timings are reproducible process-level measurements, not production 1C/Cleverence runtime performance. inventory already performs internal hashing; the standalone hashing phase is reported separately as an independent cost reference.",
        "rule":"Compact output may grow with unresolved/verifier-rejected work, but not materially with retained full-ledger payload. Large-corpus cases use actual files and full plan/ledger/verifier projection.",
    }
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not failures else 2


if __name__=="__main__":
    raise SystemExit(main())
