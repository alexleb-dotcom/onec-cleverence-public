#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"TOOLS"))

from build_review_plan import build_plan, compact_summary as compact_plan
from build_validation_ledger import build_ledger
import validation_work_queue as vwq
from evidence_receipt import prepare_receipt, apply_receipt
from rule_registry import load_registry, rule_map
from release_gate_core import evaluate as release_evaluate

errors=[]; results={}


def record(name,ok,details=None):
    results[name]={"pass":bool(ok)}
    if details is not None:results[name]["details"]=details
    if not ok:errors.append({"case":name,"details":details})


def queued_rule(queue,rule_id):
    return next((x for x in queue.get("work_queue",{}).get("rules",[]) if isinstance(x,dict) and x.get("id")==rule_id),None)


def queued_check(queue,rule_id,check_id):
    rule=queued_rule(queue,rule_id)
    if not rule:return None
    for item in rule.get("checks") or []:
        if item==check_id:return {"id":check_id,"state":"UNRESOLVED"}
        if isinstance(item,dict) and item.get("id")==check_id:return item
    return None


def queued_id(rows,rid):
    return next((x for x in rows or [] if x==rid or (isinstance(x,dict) and x.get("id")==rid)),None)


def exact_check_verdict(report,rule_id,check_id):
    return next((x for x in report.get("resolution_verdicts") or [] if x.get("scope")=="check" and x.get("rule_id")==rule_id and x.get("id")==check_id),None)


def has_attach_only_error(report,rule_id,check_id):
    rid=f"{rule_id}:{check_id}"
    return any(x.get("type") in {"ATTACH_ONLY_EVIDENCE_CANNOT_CLOSE_CLAIM","PRIMARY_PROOF_MISSING"} and x.get("scope")=="check" and x.get("id")==rid for x in report.get("errors") or [])


def set_check_pass(document,rule_id,claim_id):
    row=next(x for x in document["rules"] if x["id"]==rule_id)
    check=next(x for x in row["checks"] if x["claim_id"]==claim_id)
    check["status"]="PASS"; check["reason"]="manual status declaration after evidence attachment"
    return check


def binding(claim,anchor,reason="This exact source observation is attached to the declared claim for reviewer verification"):
    return {
        "claim_id":claim,
        "observation":f"source contains anchor {anchor!r}",
        "source_anchors":[{"type":"TEXT","value":anchor}],
        "applicability_reason":reason,
        "assertion":{"mode":"TEXT_CONTAINS","value":anchor},
    }


def write_zip(path,rows):
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in rows:z.writestr(name,data)


skill=(ROOT/"SKILL.md").read_text(encoding="utf-8-sig")
progressive=skill.split("## Progressive loading",1)[1] if "## Progressive loading" in skill else ""
record("llm_does_not_load_full_registry","RULES/rule_registry.json\nrouted profile(s)" not in progressive and "LLM must not load the full registry" in skill)

with tempfile.TemporaryDirectory() as td:
    temp=Path(td)
    source=temp/"small_r1.bsl"; source_text="Процедура Обработать()\n    Значение = 1;\nКонецПроцедуры\n"; source.write_text(source_text,encoding="utf-8")
    plan=build_plan([str(source)],analysis_only=True,risk_override="R1_CONTRACT")
    ledger=build_ledger(plan); ledger_text=json.dumps(ledger,ensure_ascii=False,indent=2)+"\n"
    ledger_sha=hashlib.sha256(ledger_text.encode("utf-8")).hexdigest()
    queue=vwq.build_work_queue(ledger,ledger_sha)
    compact_plan_text=json.dumps(compact_plan(plan),ensure_ascii=False,separators=(",",":"))+"\n"
    work_queue_text=json.dumps(queue,ensure_ascii=False,separators=(",",":"))+"\n"
    compact_plan_bytes=len(compact_plan_text.encode("utf-8"))
    work_queue_bytes=len(work_queue_text.encode("utf-8"))
    compact_bytes=compact_plan_bytes+work_queue_bytes
    efficiency_metrics={
        "skill_utf8_bytes":len((ROOT/"SKILL.md").read_bytes()),
        "skill_lines":len(skill.splitlines()),
        "compact_plan_bytes":compact_plan_bytes,
        "work_queue_bytes":work_queue_bytes,
        "combined_compact_bytes":compact_bytes,
        "active_profile_count":len(compact_plan(plan).get("active_profiles") or []),
        "active_delivery_count":len(compact_plan(plan).get("active_deliveries") or []),
        "active_support_reference_count":len(plan.get("active_supporting_artifacts") or []),
        "context_reference_count":len((compact_plan(plan).get("context_load_plan") or {}).get("references") or []),
        "compact_limit_bytes":12*1024,
    }
    record("small_r1_compact_plan_plus_ledger_within_12kb",compact_bytes<=12*1024,{"bytes":compact_bytes,"limit":12*1024,"verifier":queue.get("verifier")})
    record("efficiency_metrics_are_visible",all(isinstance(efficiency_metrics.get(key),int) for key in (
        "skill_utf8_bytes","skill_lines","compact_plan_bytes","work_queue_bytes","combined_compact_bytes",
        "active_profile_count","active_delivery_count","active_support_reference_count"
    )),efficiency_metrics)
    all_capabilities={d.get("capability_id") for rule in load_registry().get("rules",[]) for d in rule.get("delivery",[]) if isinstance(d,dict)}
    compact_capabilities={d.get("capability_id") for d in compact_plan(plan).get("active_deliveries",[]) if isinstance(d,dict)}
    full_active_capabilities={d.get("capability_id") for d in plan.get("active_deliveries",[]) if isinstance(d,dict)}
    record("compact_plan_contains_only_active_delivery_bindings",compact_capabilities==full_active_capabilities and compact_capabilities < all_capabilities,{"active":sorted(compact_capabilities),"all_count":len(all_capabilities)})
    compact_by_capability={d["capability_id"]:d for d in compact_plan(plan).get("active_deliveries",[]) if isinstance(d,dict)}
    full_by_capability={d["capability_id"]:d for d in plan.get("active_deliveries",[]) if isinstance(d,dict)}
    routing_preserved=compact_capabilities==set(compact_by_capability) and all(compact_by_capability[c].get("enforcement")==full_by_capability[c].get("enforcement") for c in full_active_capabilities)
    routing_preserved=routing_preserved and all(compact_by_capability[c].get("proof_owner")==full_by_capability[c]["proof_binding"].get("owner") for c in full_active_capabilities if full_by_capability[c].get("enforcement")=="GATING")
    record("compact_delivery_projection_preserves_enforcement_and_gating_proof_owner",routing_preserved)
    record("full_plan_preserves_canonical_delivery_proof_binding",all(full_by_capability[c].get("proof_binding")==next((d for rule in load_registry().get("rules",[]) for d in rule.get("delivery",[]) if d.get("capability_id")==c),{}).get("proof_binding") for c in full_active_capabilities))

    registry=load_registry(); registered=rule_map(registry)
    expected=[]
    for route in plan.get("rules") or []:
        spec=registered[route["id"]]
        if spec.get("tier")==0 or route.get("active"):expected.append(spec["id"])
    ledger_by={x["id"]:x for x in ledger.get("rules") or []}; coverage_errors=[]
    for rid in expected:
        spec=registered[rid]; actual=ledger_by.get(rid)
        if not actual:coverage_errors.append({"rule":rid,"missing":True});continue
        if {x["id"] for x in spec.get("checks") or []}!={x["id"] for x in actual.get("checks") or []}:coverage_errors.append({"rule":rid,"check_drift":True})
    record("full_ledger_preserves_all_routed_rules_and_checks",set(expected)==set(ledger_by) and not coverage_errors,{"rules":len(expected),"errors":coverage_errors})

    system_rows=[x for x in ledger.get("gates") or [] if x.get("resolution_source")=="SYSTEM" and x.get("status") in {"PASS","NOT_APPLICABLE"}]
    system_ids={x["id"] for x in system_rows}
    queued_gate_ids={x if isinstance(x,str) else x.get("id") for x in queue.get("work_queue",{}).get("gates",[])}
    record("terminal_rows_omitted_only_with_explicit_verdict",queue.get("verifier",{}).get("status")=="AVAILABLE" and not(system_ids & queued_gate_ids),{"system":sorted(system_ids),"queued":sorted(x for x in queued_gate_ids if x),"verifier":queue.get("verifier")})

    source_rule=ledger_by["SOURCE_FIRST"]; c1,c2=source_rule["checks"][:2]; claim1=c1["claim_id"]; claim2=c2["claim_id"]

    # Existing fail-closed status regressions.
    bad=copy.deepcopy(ledger); target=next(x for x in bad["rules"] if x["id"]=="SOURCE_FIRST")["checks"][0]; target["status"]="PASS"; target["evidence"]=[]
    q=vwq.build_work_queue(bad); item=queued_check(q,"SOURCE_FIRST",target["id"]); rel=release_evaluate(plan,bad,registry)
    record("pass_without_evidence_stays_in_queue_and_blocks",bool(item and item.get("state")=="RESOLUTION_REVIEW_REQUIRED") and rel["result"]=="FAIL" and any(x["type"]=="PASS_WITHOUT_EVIDENCE" for x in rel["errors"]),item)

    bad=copy.deepcopy(ledger); target=next(x for x in bad["rules"] if x["id"]=="SOURCE_FIRST")["checks"][0]; target["status"]="PASS"; target["evidence"]=[{"kind":"SEMANTIC","ref":str(source),"claim_id":target["claim_id"]}]
    q=vwq.build_work_queue(bad); item=queued_check(q,"SOURCE_FIRST",target["id"]); rel=release_evaluate(plan,bad,registry)
    record("pass_with_inappropriate_evidence_stays_in_queue",bool(item and item.get("state")=="RESOLUTION_REVIEW_REQUIRED") and rel["result"]=="FAIL",item)

    for name,reason in (("na_without_reason",""),("na_template_reason","not applicable")):
        bad=copy.deepcopy(ledger); target=next(x for x in bad["rules"] if x["id"]=="SOURCE_FIRST")["checks"][0]
        target["status"]="NOT_APPLICABLE"; target["reason"]=reason; target["evidence"]=[]
        q=vwq.build_work_queue(bad); item=queued_check(q,"SOURCE_FIRST",target["id"]); rel=release_evaluate(plan,bad,registry)
        record(name,bool(item and item.get("state")=="RESOLUTION_REVIEW_REQUIRED") and rel["result"]=="FAIL",item)

    bad=copy.deepcopy(ledger); rule=next(x for x in bad["rules"] if x["id"]=="SOURCE_FIRST"); rule["status"]="NOT_APPLICABLE"; rule["reason"]="Exact source is intentionally outside this synthetic rule scenario"
    for child in rule["checks"]:child["status"]="EVIDENCE_REQUIRED"; child["reason"]=""; child["evidence"]=[]
    q=vwq.build_work_queue(bad); rel=release_evaluate(plan,bad,registry)
    record("required_rule_na_does_not_skip_children",queued_rule(q,"SOURCE_FIRST") is not None and any(x["type"]=="REQUIRED_RULE_NA_WITHOUT_PROOF" for x in rel["errors"]) and any(x["type"]=="CHECK_BLOCKING_OR_UNRESOLVED" for x in rel["errors"]))

    # P0 verifier-unavailable/protocol regressions.
    terminal=copy.deepcopy(ledger); tcheck=next(x for x in terminal["rules"] if x["id"]=="SOURCE_FIRST")["checks"][0]; tcheck["status"]="PASS"; tcheck["evidence"]=[]
    terminal_na=copy.deepcopy(ledger); ncheck=next(x for x in terminal_na["rules"] if x["id"]=="SOURCE_FIRST")["checks"][0]; ncheck["status"]="NOT_APPLICABLE"; ncheck["reason"]="Synthetic non-applicability declaration awaiting deterministic verification"
    system_gate=system_rows[0]["id"] if system_rows else None

    no_intake=copy.deepcopy(terminal); no_intake.pop("release_intake",None); q=vwq.build_work_queue(no_intake)
    record("missing_release_intake_keeps_terminal_rows",q.get("verifier",{}).get("status")=="UNAVAILABLE" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None and q.get("global_blocker") is not None)

    invalid_manifest=copy.deepcopy(terminal); invalid_manifest["release_intake"]={"manifest":"not-an-object"}; q=vwq.build_work_queue(invalid_manifest)
    record("invalid_release_intake_manifest_keeps_terminal_rows",q.get("verifier",{}).get("status")=="UNAVAILABLE" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None)

    original_builder=vwq.build_plan_from_intake
    try:
        def broken_builder(_):raise RuntimeError("synthetic plan rebuild failure")
        vwq.build_plan_from_intake=broken_builder; q=vwq.build_work_queue(terminal)
        record("plan_rebuild_exception_keeps_terminal_rows",q.get("verifier",{}).get("status")=="UNAVAILABLE" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None)
    finally:vwq.build_plan_from_intake=original_builder

    original_verifier=vwq.release_evaluate
    try:
        def broken_verifier(*args,**kwargs):raise RuntimeError("synthetic release verifier failure")
        vwq.release_evaluate=broken_verifier; q=vwq.build_work_queue(terminal)
        record("release_verifier_exception_keeps_terminal_rows",q.get("verifier",{}).get("status")=="UNAVAILABLE" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None)
    finally:vwq.release_evaluate=original_verifier

    try:
        vwq.release_evaluate=lambda *args,**kwargs:{"result":"FAIL","errors":[],"resolution_verifier":{"status":"UNAVAILABLE"},"resolution_verdicts":[]}
        q=vwq.build_work_queue(terminal)
        record("reported_unavailable_keeps_terminal_rows",q.get("verifier",{}).get("status")=="UNAVAILABLE" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None)
    finally:vwq.release_evaluate=original_verifier

    try:
        def future_global(*args,**kwargs):
            report=copy.deepcopy(original_verifier(*args,**kwargs)); report["errors"].append({"type":"FUTURE_UNKNOWN_GLOBAL_ERROR"})
            return report
        vwq.release_evaluate=future_global; q=vwq.build_work_queue(terminal)
        record("unknown_global_error_is_fail_closed",q.get("verifier",{}).get("status")=="DEGRADED" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None and q.get("global_blocker") is not None)
    finally:vwq.release_evaluate=original_verifier

    try:
        def future_unmatched(*args,**kwargs):
            report=copy.deepcopy(original_verifier(*args,**kwargs)); report["errors"].append({"type":"FUTURE_UNMATCHED_CHECK_ERROR","id":tcheck["id"]})
            return report
        vwq.release_evaluate=future_unmatched; q=vwq.build_work_queue(terminal)
        record("new_unmatched_error_is_fail_closed",q.get("verifier",{}).get("status")=="DEGRADED" and queued_check(q,"SOURCE_FIRST",tcheck["id"]) is not None)
    finally:vwq.release_evaluate=original_verifier

    no_intake_na=copy.deepcopy(terminal_na); no_intake_na.pop("release_intake",None); q=vwq.build_work_queue(no_intake_na)
    record("formal_na_never_disappears_when_verifier_unavailable",queued_check(q,"SOURCE_FIRST",ncheck["id"]) is not None)

    no_intake_system=copy.deepcopy(ledger); no_intake_system.pop("release_intake",None); q=vwq.build_work_queue(no_intake_system)
    record("system_row_requires_reverification",bool(system_gate and queued_id(q.get("work_queue",{}).get("gates"),system_gate)))

    # Receipt baseline.
    ledger_path=temp/"ledger.json"; ledger_path.write_text(ledger_text,encoding="utf-8"); receipt_path=temp/"receipt.json"

    try:prepare_receipt(ledger_path,receipt_path,"E:MISSING","SOURCE_REQUIRED",str(temp/"missing.bsl"),[claim1]); missing_rejected=False
    except ValueError:missing_rejected=True
    record("receipt_missing_source_rejected",missing_rejected)

    prepare_receipt(ledger_path,receipt_path,"E:GENERIC","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать")])
    generic_out=temp/"generic.json"; generic=apply_receipt(ledger_path,receipt_path,generic_out); generic_ledger=json.loads(generic_out.read_text(encoding="utf-8"))
    generic_check=next(x for x in next(r for r in generic_ledger["rules"] if r["id"]=="SOURCE_FIRST")["checks"] if x["claim_id"]==claim1)
    generic_evidence=generic_check["evidence"][0]
    record("generic_source_receipt_is_attach_only",
        generic_check["status"]=="EVIDENCE_REQUIRED"
        and claim1 in generic["attached_claim_ids"]
        and not generic["passed_claim_ids"]
        and generic_evidence.get("proof_role")=="SUPPORTING_ONLY"
        and generic_evidence.get("supporting_only") is True
        and generic_evidence.get("verification_mode")=="ATTACH_ONLY"
        and bool(generic_evidence.get("receipt_id"))
        and bool(generic_evidence.get("receipt_provenance_id"))
        and bool(generic_ledger.get("receipt_evidence_provenance")),
        generic)

    # Third-audit P0: attach-only evidence + manual PASS must stay rejected.
    manual=copy.deepcopy(generic_ledger); manual_check=set_check_pass(manual,"SOURCE_FIRST",claim1)
    manual_release=release_evaluate(plan,manual,registry); manual_verdict=exact_check_verdict(manual_release,"SOURCE_FIRST",manual_check["id"]); manual_queue=vwq.build_work_queue(manual)
    record("manual_pass_after_attach_only_t01_rejected",
        manual_release["result"]=="FAIL"
        and manual_verdict is not None and manual_verdict.get("verdict")=="REJECTED"
        and has_attach_only_error(manual_release,"SOURCE_FIRST",manual_check["id"])
        and (queued_check(manual_queue,"SOURCE_FIRST",manual_check["id"]) or {}).get("state")=="RESOLUTION_REVIEW_REQUIRED",
        {"verdict":manual_verdict,"queue":queued_check(manual_queue,"SOURCE_FIRST",manual_check["id"]),"errors":[x for x in manual_release["errors"] if x.get("id")==f"SOURCE_FIRST:{manual_check['id']}"]})

    # Removing/editing any receipt trust field cannot promote the same evidence.
    for case,mutation in (
        ("receipt_evidence_without_verification_mode_stays_supporting",lambda e:e.pop("verification_mode",None)),
        ("receipt_evidence_without_supporting_only_stays_supporting",lambda e:e.pop("supporting_only",None)),
        ("receipt_evidence_without_proof_role_stays_supporting",lambda e:e.pop("proof_role",None)),
        ("receipt_evidence_without_receipt_id_stays_supporting",lambda e:e.pop("receipt_id",None)),
        ("receipt_evidence_changed_mode_stays_supporting",lambda e:e.__setitem__("verification_mode","DETERMINISTIC_SOURCE_FACT")),
    ):
        altered=copy.deepcopy(generic_ledger); altered_check=set_check_pass(altered,"SOURCE_FIRST",claim1); mutation(altered_check["evidence"][0])
        altered_release=release_evaluate(plan,altered,registry); altered_verdict=exact_check_verdict(altered_release,"SOURCE_FIRST",altered_check["id"]); altered_queue=vwq.build_work_queue(altered)
        record(case,
            altered_release["result"]=="FAIL"
            and altered_verdict is not None and altered_verdict.get("verdict")=="REJECTED"
            and has_attach_only_error(altered_release,"SOURCE_FIRST",altered_check["id"])
            and (queued_check(altered_queue,"SOURCE_FIRST",altered_check["id"]) or {}).get("state")=="RESOLUTION_REVIEW_REQUIRED",
            {"verdict":altered_verdict,"errors":[x.get("type") for x in altered_release["errors"] if x.get("id")==f"SOURCE_FIRST:{altered_check['id']}"]})

    # Even deleting the separate receipt provenance registry does not turn a stripped
    # SOURCE_REQUIRED receipt into direct primary proof: direct source proof now needs
    # verifier-owned CURRENT_CORPUS provenance.
    stripped=copy.deepcopy(generic_ledger); stripped_check=set_check_pass(stripped,"SOURCE_FIRST",claim1)
    stripped["receipt_evidence_provenance"]=[]
    for field in ("receipt_id","receipt_ref","receipt_sha256","receipt_schema_version","receipt_provenance_id","verification_mode","proof_role","supporting_only","source_fingerprint"):
        stripped_check["evidence"][0].pop(field,None)
    stripped_release=release_evaluate(plan,stripped,registry); stripped_verdict=exact_check_verdict(stripped_release,"SOURCE_FIRST",stripped_check["id"])
    record("stripped_receipt_cannot_masquerade_as_direct_source_primary",
        stripped_release["result"]=="FAIL"
        and stripped_verdict is not None and stripped_verdict.get("verdict")=="REJECTED"
        and any(x.get("type")=="SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED" and x.get("id")==f"SOURCE_FIRST:{stripped_check['id']}" for x in stripped_release["errors"]),
        {"verdict":stripped_verdict,"errors":[x for x in stripped_release["errors"] if x.get("id")==f"SOURCE_FIRST:{stripped_check['id']}"]})

    # Positive control: a non-receipt SOURCE_REQUIRED row with independently
    # recomputed current-corpus provenance remains a valid primary proof candidate.
    direct=copy.deepcopy(ledger); direct_check=set_check_pass(direct,"SOURCE_FIRST",claim1); candidate=plan["candidate_artifacts"][0]
    direct_check["evidence"]=[{
        "kind":"SOURCE_REQUIRED","ref":candidate["origin"],"claim_id":claim1,
        "source_provenance":{"type":"CURRENT_CORPUS","verifier":"release_gate_core.source_identity","version":1,"source_sha256":candidate["sha256"]},
    }]
    direct_release=release_evaluate(plan,direct,registry); direct_verdict=exact_check_verdict(direct_release,"SOURCE_FIRST",direct_check["id"])
    record("verified_direct_source_primary_still_supported",
        direct_verdict is not None and direct_verdict.get("verdict")=="ACCEPTED"
        and not any(x.get("type") in {"SOURCE_EVIDENCE_PROVENANCE_UNVERIFIED","ATTACH_ONLY_EVIDENCE_CANNOT_CLOSE_CLAIM","PRIMARY_PROOF_MISSING"} and x.get("id")==f"SOURCE_FIRST:{direct_check['id']}" for x in direct_release["errors"]),
        {"verdict":direct_verdict,"errors":[x for x in direct_release["errors"] if x.get("id")==f"SOURCE_FIRST:{direct_check['id']}"]})

    prepare_receipt(ledger_path,receipt_path,"E:T01","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать","A very long formally substantive applicability explanation that still cannot prove temporal source-read ordering")])
    out1=temp/"t01.json"; r1=apply_receipt(ledger_path,receipt_path,out1); l1=json.loads(out1.read_text(encoding="utf-8")); st1=next(x for x in next(r for r in l1["rules"] if r["id"]=="SOURCE_FIRST")["checks"] if x["claim_id"]==claim1)["status"]
    record("arbitrary_text_cannot_close_source_first_t01",st1=="EVIDENCE_REQUIRED" and not r1["passed_claim_ids"])

    prepare_receipt(ledger_path,receipt_path,"E:T02","SOURCE_REQUIRED",str(source),bindings=[binding(claim2,"Значение = 1","Another long reason cannot prove that no implementation detail was inferred from narrative")])
    out2=temp/"t02.json"; r2=apply_receipt(ledger_path,receipt_path,out2); l2=json.loads(out2.read_text(encoding="utf-8")); st2=next(x for x in next(r for r in l2["rules"] if r["id"]=="SOURCE_FIRST")["checks"] if x["claim_id"]==claim2)["status"]
    record("arbitrary_text_cannot_close_source_first_t02",st2=="EVIDENCE_REQUIRED" and not r2["passed_claim_ids"])
    manual2=copy.deepcopy(l2); manual2_check=set_check_pass(manual2,"SOURCE_FIRST",claim2)
    manual2_release=release_evaluate(plan,manual2,registry); manual2_verdict=exact_check_verdict(manual2_release,"SOURCE_FIRST",manual2_check["id"]); manual2_queue=vwq.build_work_queue(manual2)
    record("manual_pass_after_attach_only_t02_rejected",
        manual2_release["result"]=="FAIL"
        and manual2_verdict is not None and manual2_verdict.get("verdict")=="REJECTED"
        and has_attach_only_error(manual2_release,"SOURCE_FIRST",manual2_check["id"])
        and (queued_check(manual2_queue,"SOURCE_FIRST",manual2_check["id"]) or {}).get("state")=="RESOLUTION_REVIEW_REQUIRED",
        {"verdict":manual2_verdict,"queue":queued_check(manual2_queue,"SOURCE_FIRST",manual2_check["id"])})

    prepare_receipt(ledger_path,receipt_path,"E:UNRELATED","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Значение = 1","The anchor exists but is semantically unrelated to the source-read-before-claims obligation")])
    unrelated_out=temp/"unrelated.json"; unrelated=apply_receipt(ledger_path,receipt_path,unrelated_out); unrelated_ledger=json.loads(unrelated_out.read_text(encoding="utf-8"))
    unrelated_check=next(x for x in next(r for r in unrelated_ledger["rules"] if r["id"]=="SOURCE_FIRST")["checks"] if x["claim_id"]==claim1)
    record("semantically_unrelated_anchor_never_creates_pass",unrelated_check["status"]=="EVIDENCE_REQUIRED" and not unrelated["passed_claim_ids"])

    # Receipt tampering cannot raise trust.
    prepare_receipt(ledger_path,receipt_path,"E:TAMPER","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать")])
    payload=json.loads(receipt_path.read_text(encoding="utf-8")); payload["bindings"][0]["verification_mode"]="DETERMINISTIC_SOURCE_FACT"; receipt_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    tamper=apply_receipt(ledger_path,receipt_path,temp/"tamper-mode.json")
    record("manual_verification_mode_escalation_rejected",tamper["result"]=="PARTIAL" and any(x["error"]=="RECEIPT_VERIFICATION_MODE_NOT_CANONICAL" for x in tamper["rejected"]),tamper)

    prepare_receipt(ledger_path,receipt_path,"E:OBS","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать")])
    payload=json.loads(receipt_path.read_text(encoding="utf-8")); payload["bindings"][0]["verified_observation"]["anchors_verified"]=False; receipt_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    obs=apply_receipt(ledger_path,receipt_path,temp/"tamper-obs.json")
    record("manual_verified_observation_change_rejected",obs["result"]=="PARTIAL" and any(x["error"]=="RECEIPT_VERIFIED_OBSERVATION_DRIFT" for x in obs["rejected"]),obs)

    prepare_receipt(ledger_path,receipt_path,"E:ANCHOR-EDIT","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать")])
    payload=json.loads(receipt_path.read_text(encoding="utf-8")); payload["bindings"][0]["source_anchors"][0]["value"]="Значение = 1"; receipt_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    anchor_edit=apply_receipt(ledger_path,receipt_path,temp/"tamper-anchor.json"); anchor_ledger=json.loads((temp/"tamper-anchor.json").read_text(encoding="utf-8"))
    anchor_status=next(x for x in next(r for r in anchor_ledger["rules"] if r["id"]=="SOURCE_FIRST")["checks"] if x["claim_id"]==claim1)["status"]
    record("manual_anchor_change_cannot_raise_status",anchor_status=="EVIDENCE_REQUIRED" and not anchor_edit["passed_claim_ids"])

    # Drift after prepare.
    prepare_receipt(ledger_path,receipt_path,"E:DRIFT","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать")])
    source.write_text(source_text+"// drift\n",encoding="utf-8")
    try:apply_receipt(ledger_path,receipt_path,temp/"drift.json"); drift_rejected=False
    except ValueError:drift_rejected=True
    record("receipt_source_drift_rejected",drift_rejected); source.write_text(source_text,encoding="utf-8")

    try:prepare_receipt(ledger_path,receipt_path,"E:ANCHOR","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"ABSENT_ANCHOR_123")]); anchor_rejected=False
    except ValueError:anchor_rejected=True
    record("receipt_missing_anchor_rejected",anchor_rejected)

    # Multi-claim evidence is explicit fan-out only, never fan-out PASS.
    prepare_receipt(ledger_path,receipt_path,"E:MULTI","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать"),binding(claim2,"Значение = 1")])
    multi_out=temp/"multi.json"; multi=apply_receipt(ledger_path,receipt_path,multi_out); multi_ledger=json.loads(multi_out.read_text(encoding="utf-8")); multi_rule=next(x for x in multi_ledger["rules"] if x["id"]=="SOURCE_FIRST"); multi_by={x["claim_id"]:x for x in multi_rule["checks"]}
    record("multi_claim_receipt_attaches_without_pass",set(multi["attached_claim_ids"])=={claim1,claim2} and not multi["passed_claim_ids"] and multi_by[claim1]["status"]=="EVIDENCE_REQUIRED" and multi_by[claim2]["status"]=="EVIDENCE_REQUIRED",multi)
    multi_manual=copy.deepcopy(multi_ledger)
    mc1=set_check_pass(multi_manual,"SOURCE_FIRST",claim1); mc2=set_check_pass(multi_manual,"SOURCE_FIRST",claim2)
    multi_release=release_evaluate(plan,multi_manual,registry)
    mv1=exact_check_verdict(multi_release,"SOURCE_FIRST",mc1["id"]); mv2=exact_check_verdict(multi_release,"SOURCE_FIRST",mc2["id"])
    record("multi_claim_manual_passes_remain_rejected",
        multi_release["result"]=="FAIL"
        and mv1 is not None and mv1.get("verdict")=="REJECTED"
        and mv2 is not None and mv2.get("verdict")=="REJECTED"
        and has_attach_only_error(multi_release,"SOURCE_FIRST",mc1["id"])
        and has_attach_only_error(multi_release,"SOURCE_FIRST",mc2["id"]),
        {"t01":mv1,"t02":mv2})

    one_receipt=temp/"one.json"; prepare_receipt(ledger_path,one_receipt,"E:ONE","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать")]); one_out=temp/"one-out.json"; one=apply_receipt(ledger_path,one_receipt,one_out); one_ledger=json.loads(one_out.read_text(encoding="utf-8")); one_rule=next(x for x in one_ledger["rules"] if x["id"]=="SOURCE_FIRST"); one_by={x["claim_id"]:x for x in one_rule["checks"]}
    record("receipt_only_attaches_explicit_claim",bool(one_by[claim1]["evidence"]) and not one_by[claim2]["evidence"] and one_by[claim2]["status"]=="EVIDENCE_REQUIRED")

    prepare_receipt(ledger_path,receipt_path,"E:PARTIAL","SOURCE_REQUIRED",str(source),bindings=[binding(claim1,"Процедура Обработать"),binding(claim2,"Значение = 1")])
    payload=json.loads(receipt_path.read_text(encoding="utf-8")); payload["bindings"][1]["source_anchors"][0]["value"]="MISSING_AFTER_PREPARE"; receipt_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    partial_out=temp/"partial.json"; partial=apply_receipt(ledger_path,receipt_path,partial_out); partial_ledger=json.loads(partial_out.read_text(encoding="utf-8")); partial_rule=next(x for x in partial_ledger["rules"] if x["id"]=="SOURCE_FIRST"); partial_by={x["claim_id"]:x for x in partial_rule["checks"]}
    record("partial_receipt_only_attaches_verified_claims",partial["result"]=="PARTIAL" and bool(partial_by[claim1]["evidence"]) and not partial_by[claim2]["evidence"] and partial_by[claim1]["status"]=="EVIDENCE_REQUIRED" and partial_by[claim2]["status"]=="EVIDENCE_REQUIRED",partial)

    # SEMANTIC receipt evidence is subject to the same supporting-only boundary.
    semantic_target=None
    for rule_row in ledger["rules"]:
        spec=registered.get(rule_row["id"]) or {}
        if "SEMANTIC" in {str(x).upper() for x in spec.get("evidence_modes") or []} and rule_row.get("checks"):
            semantic_target=(rule_row,rule_row["checks"][0]); break
    if semantic_target:
        sem_rule,sem_check=semantic_target; sem_receipt=temp/"semantic-receipt.json"; sem_out=temp/"semantic-ledger.json"
        prepare_receipt(ledger_path,sem_receipt,"E:SEMANTIC","SEMANTIC",str(source),bindings=[binding(sem_check["claim_id"],"Процедура Обработать")])
        sem_apply=apply_receipt(ledger_path,sem_receipt,sem_out); sem_ledger=json.loads(sem_out.read_text(encoding="utf-8"))
        sem_manual_check=set_check_pass(sem_ledger,sem_rule["id"],sem_check["claim_id"])
        sem_release=release_evaluate(plan,sem_ledger,registry); sem_verdict=exact_check_verdict(sem_release,sem_rule["id"],sem_manual_check["id"])
        record("semantic_attach_only_manual_pass_rejected",
            sem_apply["result"]=="PASS"
            and sem_verdict is not None and sem_verdict.get("verdict")=="REJECTED"
            and has_attach_only_error(sem_release,sem_rule["id"],sem_manual_check["id"]),
            {"rule":sem_rule["id"],"check":sem_manual_check["id"],"verdict":sem_verdict})
    else:
        record("semantic_attach_only_manual_pass_rejected",False,{"reason":"no active semantic-capable check"})

    rejected_kinds=[]
    for kind in ("MACHINE","RUNTIME"):
        try:prepare_receipt(ledger_path,temp/f"{kind}.json",f"E:{kind}",kind,str(source),[claim1])
        except ValueError:rejected_kinds.append(kind)
    record("receipt_cannot_create_machine_or_runtime_proof",set(rejected_kinds)=={"MACHINE","RUNTIME"},rejected_kinds)

    predicates=[(r.get("id"),c.get("id")) for r in registry.get("rules") or [] for c in r.get("checks") or [] if c.get("receipt_predicate")]
    record("no_rule_owned_auto_pass_predicates_currently_declared",not predicates,{"predicates":predicates})

    release=release_evaluate(plan,multi_ledger,registry)
    record("receipt_does_not_weaken_release_semantics",release["result"]=="FAIL" and release["release_outcome"]=="BLOCKED",{"outcome":release["release_outcome"]})

    # P1 exact archive-entry and directory corpus.
    archive=temp/"evidence.zip"; allowed_text=source_text.encode("utf-8"); write_zip(archive,[("allowed.bsl",allowed_text),("sibling.txt",b"not inventoried evidence")])
    archive_plan=build_plan([str(archive)],analysis_only=True,risk_override="R1_CONTRACT"); archive_ledger=build_ledger(archive_plan); archive_ledger_path=temp/"archive-ledger.json"; archive_ledger_path.write_text(json.dumps(archive_ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    archive_claim=next(r for r in archive_ledger["rules"] if r["id"]=="SOURCE_FIRST")["checks"][0]["claim_id"]
    allowed_candidate=next(x for x in archive_plan["candidate_artifacts"] if x["logical_path"].endswith("allowed.bsl")); allowed_ref=allowed_candidate["origin"]
    ar=temp/"archive-receipt.json"; prepare_receipt(archive_ledger_path,ar,"E:ARCHIVE","SOURCE_REQUIRED",allowed_ref,bindings=[binding(archive_claim,"Процедура Обработать")],source_type="ARCHIVE_ENTRY")
    archive_out=temp/"archive-out.json"; archive_apply=apply_receipt(archive_ledger_path,ar,archive_out); prepared=json.loads(ar.read_text(encoding="utf-8"))["source"]
    record("exact_archive_entry_allowed",archive_apply["result"]=="PASS" and archive_claim in archive_apply["attached_claim_ids"] and all(prepared.get(k) for k in ("archive_path","archive_sha256","entry_path","entry_sha256")),prepared)

    sibling_ref=f"{str(archive)}!/sibling.txt"
    try:prepare_receipt(archive_ledger_path,temp/"sibling.json","E:SIBLING","SOURCE_REQUIRED",sibling_ref,[archive_claim],source_type="ARCHIVE_ENTRY"); sibling_rejected=False
    except ValueError:sibling_rejected=True
    record("archive_sibling_outside_plan_rejected",sibling_rejected)

    prepare_receipt(archive_ledger_path,ar,"E:ENTRY-DRIFT","SOURCE_REQUIRED",allowed_ref,bindings=[binding(archive_claim,"Процедура Обработать")],source_type="ARCHIVE_ENTRY")
    write_zip(archive,[("allowed.bsl",allowed_text+b"// changed\n"),("sibling.txt",b"not inventoried evidence")])
    try:apply_receipt(archive_ledger_path,ar,temp/"entry-drift.json"); entry_drift=False
    except ValueError:entry_drift=True
    record("archive_entry_change_rejected",entry_drift)

    write_zip(archive,[("allowed.bsl",allowed_text),("sibling.txt",b"not inventoried evidence")])
    prepare_receipt(archive_ledger_path,ar,"E:ARCHIVE-REPLACE","SOURCE_REQUIRED",allowed_ref,bindings=[binding(archive_claim,"Процедура Обработать")],source_type="ARCHIVE_ENTRY")
    write_zip(archive,[("allowed.bsl",allowed_text),("sibling.txt",b"replacement changes archive bytes"),("extra.txt",b"x")])
    try:apply_receipt(archive_ledger_path,ar,temp/"archive-replace.json"); archive_replaced=False
    except ValueError:archive_replaced=True
    record("archive_replacement_rejected_even_when_entry_same",archive_replaced)

    duplicate=temp/"duplicate.zip"
    with zipfile.ZipFile(duplicate,"w") as z:
        z.writestr("dup.bsl",allowed_text); z.writestr("./dup.bsl",allowed_text)
    duplicate_ledger=copy.deepcopy(ledger); duplicate_ledger["candidate_artifacts"].append({"logical_path":"dup.bsl","origin":f"{duplicate}!/dup.bsl","sha256":hashlib.sha256(allowed_text).hexdigest(),"size":len(allowed_text),"onec":True,"cleverence":False})
    duplicate_path=temp/"duplicate-ledger.json"; duplicate_path.write_text(json.dumps(duplicate_ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    try:prepare_receipt(duplicate_path,temp/"dup.json","E:DUP","SOURCE_REQUIRED",f"{duplicate}!/dup.bsl",[claim1],source_type="ARCHIVE_ENTRY"); duplicate_rejected=False
    except ValueError:duplicate_rejected=True
    record("ambiguous_duplicate_archive_entry_rejected",duplicate_rejected)

    directory=temp/"corpus"; directory.mkdir(); inventoried=directory/"inventoried.bsl"; inventoried.write_text(source_text,encoding="utf-8")
    dir_plan=build_plan([str(directory)],analysis_only=True,risk_override="R1_CONTRACT"); dir_ledger=build_ledger(dir_plan); dir_path=temp/"dir-ledger.json"; dir_path.write_text(json.dumps(dir_ledger,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    dir_claim=next(r for r in dir_ledger["rules"] if r["id"]=="SOURCE_FIRST")["checks"][0]["claim_id"]; late=directory/"late.bsl"; late.write_text(source_text,encoding="utf-8")
    try:prepare_receipt(dir_path,temp/"late.json","E:LATE","SOURCE_REQUIRED",str(late),[dir_claim]); late_rejected=False
    except ValueError:late_rejected=True
    record("directory_file_absent_from_inventory_rejected",late_rejected)

    # CLI preserves full artifacts and compact stdout.
    plan_out=temp/"plan.cli.json"; p=subprocess.run([sys.executable,str(ROOT/"TOOLS/build_review_plan.py"),str(source),"--analysis-only","--risk","R1_CONTRACT","--output",str(plan_out)],cwd=ROOT,capture_output=True,text=True)
    plan_stdout=json.loads(p.stdout) if p.returncode==0 else {}
    record("review_plan_output_defaults_to_compact_stdout",p.returncode==0 and plan_out.is_file() and "rules" not in plan_stdout and "active_profiles" in plan_stdout,{"stdout_bytes":len(p.stdout.encode("utf-8"))})

    ledger_out=temp/"ledger.cli.json"; p=subprocess.run([sys.executable,str(ROOT/"TOOLS/build_validation_ledger.py"),"--plan",str(plan_out),"--output",str(ledger_out)],cwd=ROOT,capture_output=True,text=True)
    ledger_stdout=json.loads(p.stdout) if p.returncode==0 else {}
    record("validation_ledger_output_defaults_to_work_queue",p.returncode==0 and ledger_out.is_file() and ledger_stdout.get("projection")=="VALIDATION_WORK_QUEUE",{"stdout_bytes":len(p.stdout.encode("utf-8"))})
    record("compact_stdout_omits_full_intent_and_review_receipts",
        p.returncode==0 and "implementation_intent_map" not in ledger_stdout and "independent_reviews" not in ledger_stdout,
        {"stdout_keys":sorted(ledger_stdout)})

    p=subprocess.run([sys.executable,str(ROOT/"TOOLS/build_validation_ledger.py"),"--plan",str(plan_out),"--output",str(temp/"ledger.full.json"),"--full-json"],cwd=ROOT,capture_output=True,text=True)
    full_stdout=json.loads(p.stdout) if p.returncode==0 else {}
    record("explicit_full_json_flag_preserves_diagnostic_access",
        p.returncode==0 and isinstance(full_stdout.get("rules"),list)
        and "implementation_intent_map" in full_stdout and "independent_reviews" in full_stdout
        and len(full_stdout["rules"])==len(json.loads((temp/"ledger.full.json").read_text(encoding="utf-8"))["rules"]))

    cleverence_source=temp/"compact-cleverence.mslx"
    cleverence_source.write_text('<?xml version="1.0" encoding="utf-8"?><Operation><InputAction Id="Scan"/></Operation>',encoding="utf-8")
    cleverence_plan=build_plan([str(cleverence_source)],analysis_only=True,risk_override="R2_STATEFUL_RUNTIME")
    cleverence_ledger=build_ledger(cleverence_plan)
    cleverence_queue=vwq.build_work_queue(cleverence_ledger)
    proof_claims={
        claim
        for group in cleverence_queue.get("proof_requirements") or []
        for claim in group.get("claims") or []
    }
    routed_cleverence={
        row["id"] for row in cleverence_plan.get("rules") or []
        if row.get("active") and row.get("id") in {"CLEVERENCE_MSLX","CLEVERENCE_CONFIGURATION","CLEVERENCE_INTEGRATION"}
    }
    expected_cleverence_claims={
        row.get("claim_id")
        for row in cleverence_ledger.get("rules") or []
        if row.get("id") in routed_cleverence and (row.get("proof_policy") or {}).get("claim_class")=="ARCHITECTURE_SEMANTIC"
    }
    expected_cleverence_claims.update(
        check.get("claim_id")
        for row in cleverence_ledger.get("rules") or []
        if row.get("id") in routed_cleverence and (row.get("proof_policy") or {}).get("claim_class")=="ARCHITECTURE_SEMANTIC"
        for check in row.get("checks") or []
    )
    expected_cleverence_claims.discard(None)
    record("compact_queue_preserves_cleverence_semantic_claims",
        bool(routed_cleverence) and expected_cleverence_claims<=proof_claims,
        {"routed":sorted(routed_cleverence),"expected_claims":len(expected_cleverence_claims),"queued_claims":len(expected_cleverence_claims & proof_claims)})

p=subprocess.run([sys.executable,str(ROOT/"TOOLS/rule_registry.py"),"--rule","SOURCE_FIRST"],cwd=ROOT,capture_output=True,text=True)
narrow=json.loads(p.stdout) if p.returncode==0 else {}
record("registry_query_is_narrow_single_rule_projection",p.returncode==0 and narrow.get("rule",{}).get("id")=="SOURCE_FIRST" and "rules" not in narrow)

out={"result":"PASS" if not errors else "FAIL","efficiency_metrics":efficiency_metrics,"results":results,"errors":errors}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
