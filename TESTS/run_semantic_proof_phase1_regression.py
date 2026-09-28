#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import copy, hashlib, json, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"TOOLS"))

import semantic_proof_verifier as spv
from analyze_onec_bsl import analyze as analyze_onec
from analyze_changeset_architecture import analyze as analyze_changeset_architecture
from build_review_plan import build_plan
from build_validation_ledger import build_ledger
from implementation_intent import build_skeleton, validate_intent_map
from proof_contract import validate_obligation_evidence
from release_gate_core import evaluate as release_evaluate
from rule_registry import load_registry
from semantic_review import write_review_receipt, verify_review_receipt, _content_sha
from semantic_proof_verifier import validate_claim_policy, validate_independent_reviews
from validation_work_queue import build_work_queue

POLICY={"claim_class":"ARCHITECTURE_SEMANTIC","required_roles":["EXACT_SOURCE","INDEPENDENT_REVIEW"]}
results={}; errors=[]

def record(cid,ok,details=None):
    results[cid]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":cid,"details":details})

def types(rows):return {x.get("type") for x in rows or [] if isinstance(x,dict)}

def intent_row(artifact,target_kind="ARTIFACT",fragment=None,action="modify",entry_kind="ENTRYPOINT"):
    row={
        "requirement_id":"REQ:1","design_decision_id":"DD:1","artifact":artifact,
        "target_kind":target_kind,"action":action,
        "responsibility":"own requested behavior","necessity":"required by REQ:1",
        "existing_owner_disposition":"existing owner checked","existing_capability_claim_id":"RULE:ANALOG_BEFORE_INVENTION","platform_reuse_decision":"reuse existing owner",
        "acceptance_cases":["AC:1"],
        "nearest_smaller_alternative":{"alternative":"no change","rejection_reason":"does not satisfy REQ:1"},
        "verification_hooks":["phase1 regression"],
    }
    if fragment is not None:row["fragment"]=fragment
    if target_kind=="BSL_ROUTINE" and action!="delete":row["entrypoint"]={"kind":entry_kind,"ref":fragment}
    if target_kind=="MSLX_ACTION":
        row.update({"scenario_disposition":"scenario reviewed","writer_disposition":"writer reviewed","state_disposition":"state/re-entry reviewed"})
    if target_kind in {"CLEVERENCE_FIELD","MAPPING"}:
        row.update({"producer_disposition":"producer reviewed","consumer_disposition":"consumer reviewed","mapping_disposition":"mapping reviewed"})
    return row

def anchor_for(plan,logical,fragment=None):
    artifact=next(x for x in plan["candidate_artifacts"] if x["logical_path"]==logical)
    row={"logical_path":logical,"candidate_sha256":artifact["sha256"]}
    baseline=plan.get("baseline") or {}
    if baseline.get("kind")=="FILE" and baseline.get("path"):
        p=Path(baseline["path"])
        if p.is_file():row["baseline_sha256"]=hashlib.sha256(p.read_bytes()).hexdigest()
    if fragment:row["fragment"]=fragment
    return row

# FR-PRP-02 containment: deterministic detection must survive the real proof path.
_incident_fixture=ROOT/"TESTS/fixtures/query_surgery_short_bypass_bad.bsl"
_incident_analysis=analyze_onec(_incident_fixture)
_incident_types=types(_incident_analysis.get("findings"))
record("fr_prp02:short_query_surgery_detected",
       "HOMEGROWN_QUERY_STRUCTURE_PARSER" in _incident_types,_incident_analysis.get("findings"))

# The fixture is only a synthetic template. Proof-path candidate identity is bound
# to exact copied bytes outside TESTS/fixtures/** so trust-boundary checks exercise
# a production-like candidate artifact rather than accepting fixture provenance.
_incident_candidate_dir=Path(tempfile.mkdtemp(prefix="fr-prp02-semantic-candidate-"))
_incident_candidate=_incident_candidate_dir/_incident_fixture.name
_incident_candidate.write_bytes(_incident_fixture.read_bytes())
_incident_plan=build_plan([_incident_candidate],analysis_only=True)
_incident_query_route=next((x for x in _incident_plan.get("rules",[]) if x.get("id")=="QUERY"),{})
record("fr_prp02:query_owner_activated",
       bool(_incident_query_route.get("active")) and bool(_incident_query_route.get("detected_by")),_incident_query_route)

_incident_ledger=build_ledger(_incident_plan)
_incident_query=next((x for x in _incident_ledger.get("rules",[]) if x.get("id")=="QUERY"),{})
_incident_check=next((x for x in _incident_query.get("checks",[]) if x.get("id")=="HOMEGROWN_QUERY_GRAMMAR_PARSER"),{})
record("fr_prp02:ledger_contains_query_surgery_obligation",
       bool(_incident_check) and _incident_check.get("status")=="EVIDENCE_REQUIRED",_incident_check)

_incident_release=release_evaluate(_incident_plan,_incident_ledger,load_registry())
record("fr_prp02:release_verifier_blocks_unresolved_query_surgery",
       _incident_release.get("release_outcome")=="BLOCKED" and _incident_release.get("result")=="FAIL",
       _incident_release.get("errors"))

_incident_queue=build_work_queue(_incident_ledger)
_incident_queue_text=json.dumps(_incident_queue,ensure_ascii=False)
record("fr_prp02:compact_queue_preserves_query_surgery",
       "HOMEGROWN_QUERY_GRAMMAR_PARSER" in _incident_queue_text,_incident_queue)

_incident_generic=copy.deepcopy(_incident_ledger)
_generic_query=next(x for x in _incident_generic["rules"] if x["id"]=="QUERY")
_generic_check=next(x for x in _generic_query["checks"] if x["id"]=="HOMEGROWN_QUERY_GRAMMAR_PARSER")
_generic_check["status"]="PASS"
_generic_check["evidence"]=[{"kind":"SEMANTIC","ref":"self-authored generic semantic exception","claim_id":_generic_check["claim_id"]}]
_generic_release=release_evaluate(_incident_plan,_incident_generic,load_registry())
_generic_errors=_generic_release.get("errors") or []
record("fr_prp02:generic_semantic_exception_cannot_close_blocker",
       any(x.get("type") in {"EXACT_SOURCE_REQUIRED","INDEPENDENT_REVIEW_REQUIRED","PRIMARY_PROOF_MISSING"}
           and x.get("claim_id")==_generic_check.get("claim_id") for x in _generic_errors if isinstance(x,dict)),
       _generic_errors)

_public_reuse=analyze_changeset_architecture([ROOT/"TESTS/fixtures/owner_reuse_public_api_good"])
_public_types=types(_public_reuse.get("findings"))
record("fr_prp02:public_api_reuse_control_passes",
       "INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW" not in _public_types,_public_reuse)

_internal_reuse=analyze_changeset_architecture([ROOT/"TESTS/fixtures/owner_reuse_internal_pipeline_bad"])
_internal_findings=[x for x in _internal_reuse.get("findings",[]) if x.get("type")=="INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW"]
record("fr_prp02:internal_pipeline_reconstruction_requires_review",
       bool(_internal_findings)
       and _internal_findings[0].get("severity")=="REVIEW"
       and _internal_findings[0].get("suggested_reuse_classification")=="INTERNAL_PIPELINE_RECONSTRUCTION",
       _internal_findings)

# Self-authored/editable trust fields never close architecture semantics.
for cid,item in (
    ("phase1:self_authored_semantic_not_primary",{"kind":"SEMANTIC","ref":"self reasoning","claim_id":"CHECK:X:Y"}),
    ("phase1:edited_proof_role_not_primary",{"kind":"SEMANTIC","ref":"self reasoning","claim_id":"CHECK:X:Y","proof_role":"PRIMARY_VERIFIED_SOURCE"}),
    ("phase1:edited_verifier_role_not_primary",{"kind":"SEMANTIC","ref":"self reasoning","claim_id":"CHECK:X:Y","_verifier_proof_role":"PRIMARY_VERIFIED_SOURCE"}),
):
    local=[]
    out=validate_obligation_evidence([item],"CHECK:X:Y",["SEMANTIC"],local,"check","X:Y",require_primary=True,proof_policy=POLICY)
    record(cid,out["primary_count"]==0 and "PRIMARY_PROOF_MISSING" in types(local),local)

local=[]
role=validate_claim_policy(POLICY,[{"kind":"SOURCE_REQUIRED","ref":"source","claim_id":"CHECK:X:Y","_verifier_proof_role":"PRIMARY_VERIFIED_SOURCE"}],{},"CHECK:X:Y",local,"check","X:Y")
record("phase1:exact_source_without_independent_review_blocks",
       role["missing_roles"]==["INDEPENDENT_REVIEW"] and "INDEPENDENT_REVIEW_REQUIRED" in types(local),local)
record("phase1:missing_review_has_exact_blocker",
       any(x.get("type")=="INDEPENDENT_REVIEW_REQUIRED" and x.get("claim_id")=="CHECK:X:Y" for x in local),local)

with tempfile.TemporaryDirectory(prefix="semantic-proof-phase1-") as td:
    td=Path(td)
    baseline=td/"baseline.bsl"; candidate=td/"candidate.bsl"
    baseline.write_text("Процедура Обработать()\n\tЗначение = 1;\nКонецПроцедуры\n",encoding="utf-8")
    candidate.write_text("Процедура Обработать()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    plan=build_plan([candidate],baseline=baseline,analysis_only=True,risk_override="R1_CONTRACT")
    logical=plan["candidate_artifacts"][0]["logical_path"]
    anchor=[anchor_for(plan,logical,"Обработать")]
    receipt=td/"review.json"
    write_review_receipt(receipt,plan,author_execution_id="AUTHOR:1",reviewer_execution_id="REVIEWER:1",
        claim_id="CHECK:X:Y",rule_id="X",check_id="Y",source_anchors=anchor,reviewer_verdict="PASS",defects=[],
        limitations=["test procedural separation"])
    receipt_sha=hashlib.sha256(receipt.read_bytes()).hexdigest()

    vr=verify_review_receipt(receipt,expected_sha256=receipt_sha,plan=plan,expected_claim_id="CHECK:X:Y",
        expected_rule_id="X",expected_check_id="Y",expected_author_execution_id="AUTHOR:1")
    record("phase1:separated_review_positive_control",vr["integrity_result"]=="PASS" and vr["review_result"]=="PASS",vr.get("errors"))

    same=json.loads(receipt.read_text(encoding="utf-8"));same["reviewer_execution_id"]="AUTHOR:1";same["content_sha256"]=_content_sha(same)
    same_path=td/"same.json";same_path.write_text(json.dumps(same,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    vr=verify_review_receipt(same_path,expected_sha256=hashlib.sha256(same_path.read_bytes()).hexdigest(),plan=plan,
        expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y",expected_author_execution_id="AUTHOR:1")
    record("phase1:author_equals_reviewer_blocks","INDEPENDENT_REVIEW_AUTHOR_REVIEWER_SAME_EXECUTION" in types(vr["errors"]),vr["errors"])

    other_candidate=copy.deepcopy(plan);other_candidate["candidate_artifacts"][0]["sha256"]="0"*64
    vr=verify_review_receipt(receipt,expected_sha256=receipt_sha,plan=other_candidate,expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:review_other_candidate_blocks","INDEPENDENT_REVIEW_PLAN_BINDING_MISMATCH" in types(vr["errors"]),vr["errors"])

    other_baseline=copy.deepcopy(plan);other_baseline["baseline"]["sha256"]="1"*64
    vr=verify_review_receipt(receipt,expected_sha256=receipt_sha,plan=other_baseline,expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:review_other_baseline_blocks","INDEPENDENT_REVIEW_PLAN_BINDING_MISMATCH" in types(vr["errors"]),vr["errors"])

    other_req=copy.deepcopy(plan);other_req["requirements"]["sha256"]="2"*64
    vr=verify_review_receipt(receipt,expected_sha256=receipt_sha,plan=other_req,expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:review_old_requirements_blocks","INDEPENDENT_REVIEW_PLAN_BINDING_MISMATCH" in types(vr["errors"]),vr["errors"])

    other_plan=copy.deepcopy(plan);other_plan["routing"]["declared_risk"]="R2_STATEFUL_RUNTIME"
    vr=verify_review_receipt(receipt,expected_sha256=receipt_sha,plan=other_plan,expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:review_other_plan_blocks","INDEPENDENT_REVIEW_PLAN_BINDING_MISMATCH" in types(vr["errors"]),vr["errors"])

    vr=verify_review_receipt(receipt,expected_sha256=receipt_sha,plan=plan,expected_claim_id="CHECK:X:OTHER",expected_rule_id="X",expected_check_id="OTHER")
    record("phase1:review_other_claim_blocks",
        {"INDEPENDENT_REVIEW_CLAIM_MISMATCH","INDEPENDENT_REVIEW_CHECK_MISMATCH"}.issubset(types(vr["errors"])),vr["errors"])

    tampered=json.loads(receipt.read_text(encoding="utf-8"));tampered["limitations"].append("edited after review")
    tamper_path=td/"tamper.json";tamper_path.write_text(json.dumps(tampered,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    vr=verify_review_receipt(tamper_path,expected_sha256=hashlib.sha256(tamper_path.read_bytes()).hexdigest(),plan=plan,
        expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:review_receipt_mutation_blocks","INDEPENDENT_REVIEW_CONTENT_HASH_DRIFT" in types(vr["errors"]),vr["errors"])

    # PASS + defects is invalid and must be blocked by the actual release verifier path.
    defect_receipt=td/"defect-pass.json"
    write_review_receipt(defect_receipt,plan,author_execution_id="AUTHOR:DEFECT",reviewer_execution_id="REVIEWER:DEFECT",
        claim_id="CHECK:X:Y",rule_id="X",check_id="Y",source_anchors=anchor,reviewer_verdict="PASS",
        defects=[{"id":"D1","description":"material semantic defect found"}],limitations=["known test limitation"])
    defect_sha=hashlib.sha256(defect_receipt.read_bytes()).hexdigest()
    vr=verify_review_receipt(defect_receipt,expected_sha256=defect_sha,plan=plan,expected_claim_id="CHECK:X:Y",
        expected_rule_id="X",expected_check_id="Y",expected_author_execution_id="AUTHOR:DEFECT")
    record("phase1:pass_review_with_defects_receipt_invalid","INDEPENDENT_REVIEW_PASS_WITH_DEFECTS" in types(vr["errors"]),vr["errors"])
    defect_ledger=build_ledger(plan)
    defect_ledger["independent_reviews"]=[{
        "claim_id":"CHECK:X:Y","rule_id":"X","check_id":"Y","receipt_ref":str(defect_receipt),
        "receipt_sha256":defect_sha,"author_execution_id":"AUTHOR:DEFECT"
    }]
    release=release_evaluate(plan,defect_ledger,load_registry())
    nested=[
        e.get("detail",{}).get("type")
        for e in release.get("errors") or []
        if isinstance(e,dict) and e.get("type")=="INDEPENDENT_REVIEW_INVALID"
    ]
    record("phase1:pass_review_with_defects_release_verifier_blocks",
        release.get("result")=="FAIL" and "INDEPENDENT_REVIEW_PASS_WITH_DEFECTS" in nested,
        [e for e in release.get("errors") or [] if isinstance(e,dict) and e.get("type")=="INDEPENDENT_REVIEW_INVALID"])

    # No trusted adapter/root exists in Phase 1; editable external status cannot attest independence.
    external=json.loads(receipt.read_text(encoding="utf-8"));external["external_reviewer_status"]="EXTERNAL_REVIEWER_VERIFIED";external["content_sha256"]=_content_sha(external)
    external_path=td/"external.json";external_path.write_text(json.dumps(external,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    vr=verify_review_receipt(external_path,expected_sha256=hashlib.sha256(external_path.read_bytes()).hexdigest(),plan=plan,
        expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:external_reviewer_status_cannot_self_attest",
        "INDEPENDENT_REVIEW_EXTERNAL_VERIFICATION_UNSUPPORTED" in types(vr["errors"]),vr["errors"])

    # Multi-artifact review must cover all create/modify/delete artifacts.
    multi=td/"multi";multi.mkdir();(multi/"a.bsl").write_text("Процедура A()\nКонецПроцедуры\n",encoding="utf-8");(multi/"b.bsl").write_text("Процедура B()\nКонецПроцедуры\n",encoding="utf-8")
    two=build_plan([multi],analysis_only=True,risk_override="R1_CONTRACT")
    incomplete=td/"incomplete.json";first=two["candidate_artifacts"][0]
    write_review_receipt(incomplete,two,author_execution_id="AUTHOR:2",reviewer_execution_id="REVIEWER:2",
        claim_id="CHECK:X:Y",rule_id="X",check_id="Y",
        source_anchors=[{"logical_path":first["logical_path"],"candidate_sha256":first["sha256"]}],
        reviewer_verdict="PASS",defects=[],limitations=["coverage test"])
    vr=verify_review_receipt(incomplete,expected_sha256=hashlib.sha256(incomplete.read_bytes()).hexdigest(),plan=two,
        expected_claim_id="CHECK:X:Y",expected_rule_id="X",expected_check_id="Y")
    record("phase1:review_partial_changeset_blocks","INDEPENDENT_REVIEW_CHANGESET_COVERAGE_INCOMPLETE" in types(vr["errors"]),vr["errors"])

    rows=[{"claim_id":"CHECK:X:Y","rule_id":"X","check_id":"Y","receipt_ref":str(receipt),"receipt_sha256":receipt_sha,"author_execution_id":"AUTHOR:1"}]
    saved=spv.verify_review_receipt
    try:
        def boom(*args,**kwargs):raise RuntimeError("synthetic verifier unavailable")
        spv.verify_review_receipt=boom; local=[]; idx=validate_independent_reviews(rows,plan,local)
        record("phase1:review_verifier_unavailable_fail_closed",not idx and "INDEPENDENT_REVIEW_VERIFIER_UNAVAILABLE" in types(local),local)
    finally:spv.verify_review_receipt=saved

    # Existing modified owner: artifact + routine must both be represented with real actions.
    blank=build_skeleton(plan); ir=validate_intent_map(blank,plan)
    record("phase1:bsl_routine_without_intent_blocks","BSL_ROUTINE_WITHOUT_INTENT" in types(ir["errors"]),ir["errors"])
    good=build_skeleton(plan);good["rows"]=[
        intent_row(logical,"ARTIFACT",action="modify"),
        intent_row(logical,"BSL_ROUTINE","Обработать",action="modify"),
    ]
    ir=validate_intent_map(good,plan)
    record("phase1:minimal_existing_owner_intent_positive_control",ir["result"]=="PASS",ir["errors"])

    wrong_action=copy.deepcopy(good);wrong_action["rows"][1]["action"]="create"
    ir=validate_intent_map(wrong_action,plan)
    record("phase1:intent_action_mismatch_blocks","IMPLEMENTATION_INTENT_ACTION_MISMATCH" in types(ir["errors"]),ir["errors"])

    fbase=td/"fbase.bsl";fcand=td/"fcand.bsl"
    fbase.write_text("Процедура Вход()\nКонецПроцедуры\n",encoding="utf-8")
    fcand.write_text("Процедура Вход()\nКонецПроцедуры\n\nФункция НоваяФункция()\n\tВозврат 1;\nКонецФункции\n",encoding="utf-8")
    fp=build_plan([fcand],baseline=fbase,analysis_only=True,risk_override="R1_CONTRACT");fl=fp["candidate_artifacts"][0]["logical_path"]
    fmap=build_skeleton(fp);row=intent_row(fl,"BSL_ROUTINE","НоваяФункция",action="create");row.pop("entrypoint")
    fmap["rows"]=[intent_row(fl,"ARTIFACT",action="modify"),row]
    ir=validate_intent_map(fmap,fp)
    record("phase1:new_function_without_entrypoint_blocks",
        bool({"IMPLEMENTATION_INTENT_ENTRYPOINT_MISSING","NEW_FUNCTION_WITHOUT_REACHABILITY"} & types(ir["errors"])),ir["errors"])

    ecand=td/"export.bsl";ecand.write_text("Процедура Вход()\nКонецПроцедуры\n\nФункция НовыйAPI() Экспорт\n\tВозврат 1;\nКонецФункции\n",encoding="utf-8")
    ep=build_plan([ecand],baseline=fbase,analysis_only=True,risk_override="R1_CONTRACT");el=ep["candidate_artifacts"][0]["logical_path"]
    emap=build_skeleton(ep);emap["rows"]=[intent_row(el,"ARTIFACT",action="modify"),intent_row(el,"BSL_ROUTINE","НовыйAPI",action="create",entry_kind="HELPER_REACHABLE")]
    ir=validate_intent_map(emap,ep)
    record("phase1:new_export_without_api_contract_blocks","NEW_EXPORT_WITHOUT_API_CALLBACK_CONTRACT" in types(ir["errors"]),ir["errors"])

    outside=copy.deepcopy(good);outside["rows"].append(intent_row("unrelated.bsl","ARTIFACT",action="create"))
    ir=validate_intent_map(outside,plan)
    record("phase1:artifact_outside_change_surface_blocks","IMPLEMENTATION_INTENT_ARTIFACT_OUTSIDE_CHANGE_SURFACE" in types(ir["errors"]),ir["errors"])

    wrong=copy.deepcopy(good);wrong["binding"]["candidate_fingerprint_sha256"]="f"*64
    ir=validate_intent_map(wrong,plan)
    record("phase1:intent_map_other_candidate_blocks","IMPLEMENTATION_INTENT_BINDING_MISMATCH" in types(ir["errors"]),ir["errors"])

    # File/routine deletion obligations retain baseline-only facts.
    bdir=td/"delete-base";cdir=td/"delete-candidate";bdir.mkdir();cdir.mkdir()
    (bdir/"keep.bsl").write_text("Процедура Keep()\nКонецПроцедуры\n",encoding="utf-8")
    (cdir/"keep.bsl").write_text("Процедура Keep()\nКонецПроцедуры\n",encoding="utf-8")
    (bdir/"gone.bsl").write_text("Процедура Gone()\nКонецПроцедуры\n",encoding="utf-8")
    dp=build_plan([cdir],baseline=bdir,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(dp),dp)
    record("phase1:deleted_file_without_intent_blocks",
        any(x.get("type")=="MATERIAL_ARTIFACT_WITHOUT_INTENT" and x.get("artifact")=="gone.bsl" and x.get("expected_action")=="delete" for x in ir["errors"]),ir["errors"])

    rb=td/"routine-base";rc=td/"routine-candidate";rb.mkdir();rc.mkdir()
    (rb/"module.bsl").write_text("Процедура Keep()\nКонецПроцедуры\n\nПроцедура Gone()\nКонецПроцедуры\n",encoding="utf-8")
    (rc/"module.bsl").write_text("Процедура Keep()\nКонецПроцедуры\n",encoding="utf-8")
    rp=build_plan([rc],baseline=rb,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(rp),rp)
    record("phase1:deleted_bsl_routine_without_intent_blocks",
        any(x.get("type")=="BSL_ROUTINE_WITHOUT_INTENT" and x.get("fragment")=="Gone" and x.get("expected_action")=="delete" for x in ir["errors"]),ir["errors"])

    # MSLX full-body fingerprinting: opening tag unchanged, body changes.
    mb=td/"mslx-base";mc=td/"mslx-candidate";mb.mkdir();mc.mkdir()
    (mb/"Operation.mslx").write_text('<Operation><InputAction Id="Scan"><Text>A</Text></InputAction></Operation>',encoding="utf-8")
    (mc/"Operation.mslx").write_text('<Operation><InputAction Id="Scan"><Text>B</Text></InputAction></Operation>',encoding="utf-8")
    mp=build_plan([mc],baseline=mb,analysis_only=True,risk_override="R2_STATEFUL_RUNTIME")
    ir=validate_intent_map(build_skeleton(mp),mp)
    record("phase1:mslx_action_body_change_without_intent_blocks",
        any(x.get("type")=="MSLX_ACTION_WITHOUT_INTENT" and x.get("fragment")=="Scan" and x.get("expected_action")=="modify" for x in ir["errors"]),ir["errors"])

    adb=td/"action-delete-base";adc=td/"action-delete-candidate";adb.mkdir();adc.mkdir()
    (adb/"Operation.mslx").write_text('<Operation><InputAction Id="Scan"><Text>A</Text></InputAction></Operation>',encoding="utf-8")
    (adc/"Operation.mslx").write_text('<Operation></Operation>',encoding="utf-8")
    adp=build_plan([adc],baseline=adb,analysis_only=True,risk_override="R2_STATEFUL_RUNTIME")
    ir=validate_intent_map(build_skeleton(adp),adp)
    record("phase1:deleted_mslx_action_without_intent_blocks",
        any(x.get("type")=="MSLX_ACTION_WITHOUT_INTENT" and x.get("fragment")=="Scan" and x.get("expected_action")=="delete" for x in ir["errors"]),ir["errors"])

    # Cleverence field deletion + content modification and mapping modification/deletion.
    cb=td/"contract-base";cc=td/"contract-candidate";cb.mkdir();cc.mkdir()
    (cb/"Config.mslx").write_text(
        '<Configuration><Field Name="Gone"><Type>String</Type></Field><Field Name="Changed"><Type>String</Type></Field>'
        '<Mapping Name="MapChanged"><Source>A</Source><Target>B</Target></Mapping><Mapping Name="MapGone"><Source>X</Source><Target>Y</Target></Mapping></Configuration>',
        encoding="utf-8")
    (cc/"Config.mslx").write_text(
        '<Configuration><Field Name="Changed"><Type>Number</Type></Field>'
        '<Mapping Name="MapChanged"><Source>A</Source><Target>C</Target></Mapping></Configuration>',
        encoding="utf-8")
    cp=build_plan([cc],baseline=cb,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(cp),cp)
    err=ir["errors"]
    record("phase1:cleverence_field_delete_and_modify_are_obligations",
        any(x.get("type")=="CLEVERENCE_FIELD_WITHOUT_INTENT" and x.get("fragment")=="Gone" and x.get("expected_action")=="delete" for x in err)
        and any(x.get("type")=="CLEVERENCE_FIELD_WITHOUT_INTENT" and x.get("fragment")=="Changed" and x.get("expected_action")=="modify" for x in err),err)
    record("phase1:cleverence_mapping_delete_and_modify_are_obligations",
        any(x.get("type")=="CLEVERENCE_MAPPING_WITHOUT_INTENT" and x.get("fragment")=="MapGone" and x.get("expected_action")=="delete" for x in err)
        and any(x.get("type")=="CLEVERENCE_MAPPING_WITHOUT_INTENT" and x.get("fragment")=="MapChanged" and x.get("expected_action")=="modify" for x in err),err)

    # Compact queue must expose baseline-only delete obligations on a real release-verifier path.
    qplan=build_plan([rc],baseline=rb,analysis_only=False,risk_override="R1_CONTRACT")
    qledger=build_ledger(qplan)
    queue=build_work_queue(qledger)
    intent_blockers=queue.get("intent_blockers") or []
    record("phase1:new_delete_obligations_survive_compact_work_queue",
        any(x.get("type")=="BSL_ROUTINE_WITHOUT_INTENT" and x.get("fragment")=="Gone" for x in intent_blockers)
        and any(x.get("type")=="MATERIAL_ARTIFACT_WITHOUT_INTENT" and x.get("artifact")=="module.bsl" for x in intent_blockers),
        intent_blockers)

    # Duplicate semantic identities are ambiguity blockers, never last-write-wins deltas.
    dup_bsl_base=td/"dup-bsl-base";dup_bsl_candidate=td/"dup-bsl-candidate";dup_bsl_base.mkdir();dup_bsl_candidate.mkdir()
    (dup_bsl_base/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n\n"
        "Процедура Duplicate()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    (dup_bsl_candidate/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    dbp=build_plan([dup_bsl_candidate],baseline=dup_bsl_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(dbp),dbp);dup_errors=ir["errors"]
    record("phase1:duplicate_bsl_baseline_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="module.bsl" and x.get("side")=="baseline"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in dup_errors),dup_errors)

    dup_bsl_candidate_side=td/"dup-bsl-candidate-side";dup_bsl_candidate_side.mkdir()
    (dup_bsl_candidate_side/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n\n"
        "Процедура Duplicate()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    single_bsl_base=td/"single-bsl-base";single_bsl_base.mkdir()
    (single_bsl_base/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n",encoding="utf-8")
    dcp=build_plan([dup_bsl_candidate_side],baseline=single_bsl_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(dcp),dcp);dup_errors=ir["errors"]
    record("phase1:duplicate_bsl_candidate_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="module.bsl" and x.get("side")=="candidate"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in dup_errors),dup_errors)

    dup_field_base=td/"dup-field-base";dup_field_candidate=td/"dup-field-candidate";dup_field_base.mkdir();dup_field_candidate.mkdir()
    (dup_field_base/"Config.mslx").write_text(
        '<Configuration><Field Name="Duplicate"><Type>String</Type></Field>'
        '<Field Name="Duplicate"><Type>Number</Type></Field></Configuration>',encoding="utf-8")
    (dup_field_candidate/"Config.mslx").write_text(
        '<Configuration><Field Name="Duplicate"><Type>Number</Type></Field></Configuration>',encoding="utf-8")
    dfp=build_plan([dup_field_candidate],baseline=dup_field_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(dfp),dfp);dup_errors=ir["errors"]
    record("phase1:duplicate_cleverence_field_baseline_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="Config.mslx" and x.get("side")=="baseline"
            and x.get("kind")=="CLEVERENCE_FIELD" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in dup_errors),dup_errors)

    dup_field_candidate_side=td/"dup-field-candidate-side";dup_field_candidate_side.mkdir()
    (dup_field_candidate_side/"Config.mslx").write_text(
        '<Configuration><Field Name="Duplicate"><Type>String</Type></Field>'
        '<Field Name="Duplicate"><Type>Number</Type></Field></Configuration>',encoding="utf-8")
    single_field_base=td/"single-field-base";single_field_base.mkdir()
    (single_field_base/"Config.mslx").write_text(
        '<Configuration><Field Name="Duplicate"><Type>String</Type></Field></Configuration>',encoding="utf-8")
    dfcp=build_plan([dup_field_candidate_side],baseline=single_field_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(dfcp),dfcp);dup_errors=ir["errors"]
    record("phase1:duplicate_cleverence_field_candidate_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="Config.mslx" and x.get("side")=="candidate"
            and x.get("kind")=="CLEVERENCE_FIELD" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in dup_errors),dup_errors)

    dup_action_base=td/"dup-action-base";dup_action_candidate=td/"dup-action-candidate";dup_action_base.mkdir();dup_action_candidate.mkdir()
    (dup_action_base/"Operation.mslx").write_text(
        '<Operation><InputAction Id="Duplicate"><Text>A</Text></InputAction>'
        '<InputAction Id="Duplicate"><Text>B</Text></InputAction></Operation>',encoding="utf-8")
    (dup_action_candidate/"Operation.mslx").write_text(
        '<Operation><InputAction Id="Duplicate"><Text>B</Text></InputAction></Operation>',encoding="utf-8")
    dap=build_plan([dup_action_candidate],baseline=dup_action_base,analysis_only=True,risk_override="R2_STATEFUL_RUNTIME")
    ir=validate_intent_map(build_skeleton(dap),dap);dup_errors=ir["errors"]
    record("phase1:duplicate_mslx_action_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="Operation.mslx" and x.get("side")=="baseline"
            and x.get("kind")=="MSLX_ACTION" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in dup_errors),dup_errors)

    dup_mapping_base=td/"dup-mapping-base";dup_mapping_candidate=td/"dup-mapping-candidate";dup_mapping_base.mkdir();dup_mapping_candidate.mkdir()
    (dup_mapping_base/"Config.mslx").write_text(
        '<Configuration><Mapping Name="Duplicate"><Source>A</Source><Target>B</Target></Mapping>'
        '<Mapping Name="Duplicate"><Source>A</Source><Target>C</Target></Mapping></Configuration>',encoding="utf-8")
    (dup_mapping_candidate/"Config.mslx").write_text(
        '<Configuration><Mapping Name="Duplicate"><Source>A</Source><Target>C</Target></Mapping></Configuration>',encoding="utf-8")
    dmp=build_plan([dup_mapping_candidate],baseline=dup_mapping_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(dmp),dmp);dup_errors=ir["errors"]
    record("phase1:duplicate_cleverence_mapping_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="Config.mslx" and x.get("side")=="baseline"
            and x.get("kind")=="MAPPING" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in dup_errors),dup_errors)

    # The canonical release verifier and compact work queue must retain the exact ambiguity.
    qdup_plan=build_plan([dup_bsl_candidate],baseline=dup_bsl_base,analysis_only=False,risk_override="R1_CONTRACT")
    qdup_ledger=build_ledger(qdup_plan)
    qdup_release=release_evaluate(qdup_plan,qdup_ledger,load_registry())
    release_ambiguities=[
        x for x in qdup_release.get("errors") or []
        if isinstance(x,dict) and x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
    ]
    record("phase1:duplicate_identity_release_verifier_preserves_blocker",
        any(x.get("artifact")=="module.bsl" and x.get("side")=="baseline"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate" for x in release_ambiguities),
        release_ambiguities)
    qdup_queue=build_work_queue(qdup_ledger)
    queue_ambiguities=[
        x for x in qdup_queue.get("intent_blockers") or []
        if isinstance(x,dict) and x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
    ]
    record("phase1:duplicate_identity_ambiguity_survives_compact_queue",
        any(x.get("artifact")=="module.bsl" and x.get("side")=="baseline"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("occurrences")==2 for x in queue_ambiguities),
        queue_ambiguities)

    # BSL semantic identity is case-insensitive, aligned with call-signature indexing.
    case_bsl_base=td/"case-bsl-base";case_bsl_candidate=td/"case-bsl-candidate";case_bsl_base.mkdir();case_bsl_candidate.mkdir()
    (case_bsl_base/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n\n"
        "Процедура duplicate()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    (case_bsl_candidate/"module.bsl").write_text(
        "Процедура duplicate()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    cbp=build_plan([case_bsl_candidate],baseline=case_bsl_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(cbp),cbp);case_dup_errors=ir["errors"]
    record("phase1:case_variant_duplicate_bsl_baseline_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="module.bsl" and x.get("side")=="baseline"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("normalized_identity")=="duplicate"
            and x.get("spellings")==["Duplicate","duplicate"]
            and x.get("occurrences")==2 for x in case_dup_errors),case_dup_errors)

    case_bsl_candidate_side=td/"case-bsl-candidate-side";case_bsl_candidate_side.mkdir()
    case_single_base=td/"case-single-base";case_single_base.mkdir()
    (case_single_base/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n",encoding="utf-8")
    (case_bsl_candidate_side/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n\n"
        "Процедура duplicate()\n\tЗначение = 2;\nКонецПроцедуры\n",encoding="utf-8")
    ccp=build_plan([case_bsl_candidate_side],baseline=case_single_base,analysis_only=True,risk_override="R1_CONTRACT")
    ir=validate_intent_map(build_skeleton(ccp),ccp);case_dup_errors=ir["errors"]
    record("phase1:case_variant_duplicate_bsl_candidate_identity_blocks",
        any(x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
            and x.get("artifact")=="module.bsl" and x.get("side")=="candidate"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("normalized_identity")=="duplicate"
            and x.get("spellings")==["Duplicate","duplicate"]
            and x.get("occurrences")==2 for x in case_dup_errors),case_dup_errors)

    # Real release-verifier and compact-queue paths must preserve case-variant ambiguity evidence.
    qcase_plan=build_plan([case_bsl_candidate],baseline=case_bsl_base,analysis_only=False,risk_override="R1_CONTRACT")
    qcase_ledger=build_ledger(qcase_plan)
    qcase_release=release_evaluate(qcase_plan,qcase_ledger,load_registry())
    case_release_ambiguities=[
        x for x in qcase_release.get("errors") or []
        if isinstance(x,dict) and x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
    ]
    record("phase1:case_variant_duplicate_release_verifier_preserves_blocker",
        any(x.get("artifact")=="module.bsl" and x.get("side")=="baseline"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("normalized_identity")=="duplicate"
            and x.get("spellings")==["Duplicate","duplicate"] for x in case_release_ambiguities),
        case_release_ambiguities)

    qcase_queue=build_work_queue(qcase_ledger)
    case_queue_ambiguities=[
        x for x in qcase_queue.get("intent_blockers") or []
        if isinstance(x,dict) and x.get("type")=="IMPLEMENTATION_INTENT_SEMANTIC_IDENTITY_AMBIGUOUS"
    ]
    record("phase1:case_variant_duplicate_ambiguity_survives_compact_queue",
        any(x.get("artifact")=="module.bsl" and x.get("side")=="baseline"
            and x.get("kind")=="BSL_ROUTINE" and x.get("identity")=="Duplicate"
            and x.get("normalized_identity")=="duplicate"
            and x.get("spellings")==["Duplicate","duplicate"]
            and x.get("occurrences")==2 for x in case_queue_ambiguities),
        case_queue_ambiguities)

    # A case-only spelling change is one semantic routine modification, never delete+create.
    rename_base=td/"case-rename-base";rename_candidate=td/"case-rename-candidate";rename_base.mkdir();rename_candidate.mkdir()
    (rename_base/"module.bsl").write_text(
        "Процедура Duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n",encoding="utf-8")
    (rename_candidate/"module.bsl").write_text(
        "Процедура duplicate()\n\tЗначение = 1;\nКонецПроцедуры\n",encoding="utf-8")
    rnp=build_plan([rename_candidate],baseline=rename_base,analysis_only=True,risk_override="R1_CONTRACT")
    blank_rename=validate_intent_map(build_skeleton(rnp),rnp)
    rename_routine_rows=[
        x for x in blank_rename["errors"]
        if isinstance(x,dict) and x.get("type")=="BSL_ROUTINE_WITHOUT_INTENT"
    ]
    rmap=build_skeleton(rnp)
    rmap["rows"]=[
        intent_row("module.bsl","ARTIFACT",action="modify"),
        intent_row("module.bsl","BSL_ROUTINE","Duplicate",action="modify"),
    ]
    filled_rename=validate_intent_map(rmap,rnp)
    record("phase1:bsl_case_only_name_change_is_single_modify",
        len(rename_routine_rows)==1
        and rename_routine_rows[0].get("expected_action")=="modify"
        and rename_routine_rows[0].get("semantic_identity")=="duplicate"
        and filled_rename.get("result")=="PASS",
        {"missing":rename_routine_rows,"filled_errors":filled_rename.get("errors")})

    # Existing minimality/Cleverence behavioral controls.
    def minimality_violation(obs):
        return ((obs.get("existing_owner_satisfies_contract") and obs.get("new_parallel_helper_count",0)>0)
                or obs.get("unrelated_changed_artifacts",0)>0
                or (obs.get("loc_reduced") and obs.get("cohesion_lost")))
    record("phase1:extra_helper_near_existing_owner_rejected",minimality_violation({"existing_owner_satisfies_contract":True,"new_parallel_helper_count":1}))
    record("phase1:existing_owner_minimal_variant_accepted",not minimality_violation({"existing_owner_satisfies_contract":True,"new_parallel_helper_count":0}))
    record("phase1:opportunistic_refactoring_rejected",minimality_violation({"unrelated_changed_artifacts":1}))
    record("phase1:loc_reduction_with_cohesion_loss_rejected",minimality_violation({"loc_reduced":True,"cohesion_lost":True}))

    # Action/field disposition remains required even with exact structural delta.
    newbase=td/"new-action-base.mslx";newcand=td/"new-action.mslx"
    newbase.write_text("<Operation></Operation>",encoding="utf-8")
    newcand.write_text('<Operation><InputAction Id="NewScan"/></Operation>',encoding="utf-8")
    np=build_plan([newcand],baseline=newbase,analysis_only=True,risk_override="R2_STATEFUL_RUNTIME");nl=np["candidate_artifacts"][0]["logical_path"]
    nmap=build_skeleton(np);nmap["rows"]=[intent_row(nl,"ARTIFACT",action="modify"),intent_row(nl,"MSLX_ACTION","NewScan",action="create")]
    for field in ("scenario_disposition","writer_disposition","state_disposition"):nmap["rows"][1].pop(field)
    ir=validate_intent_map(nmap,np)
    record("phase1:mslx_action_without_scenario_writer_state_blocks","IMPLEMENTATION_INTENT_CLEVERENCE_ACTION_DISPOSITION_MISSING" in types(ir["errors"]),ir["errors"])

    fieldbase=td/"field-base.mslx";fieldcand=td/"field-candidate.mslx"
    fieldbase.write_text("<Configuration></Configuration>",encoding="utf-8")
    fieldcand.write_text('<Configuration><Field Name="НомерКороба"/></Configuration>',encoding="utf-8")
    fp2=build_plan([fieldcand],baseline=fieldbase,analysis_only=True,risk_override="R1_CONTRACT");fl2=fp2["candidate_artifacts"][0]["logical_path"]
    fmap2=build_skeleton(fp2);fr=intent_row(fl2,"CLEVERENCE_FIELD","НомерКороба",action="create")
    for field in ("producer_disposition","consumer_disposition","mapping_disposition"):fr.pop(field)
    fmap2["rows"]=[intent_row(fl2,"ARTIFACT",action="modify"),fr]
    ir=validate_intent_map(fmap2,fp2)
    record("phase1:cleverence_field_without_mapping_consumer_blocks",
        "IMPLEMENTATION_INTENT_CLEVERENCE_FIELD_MAPPING_DISPOSITION_MISSING" in types(ir["errors"]),ir["errors"])

    xp=build_plan([candidate],baseline=baseline,analysis_only=True,surface_override="CROSS_SYSTEM",risk_override="R3_CROSS_SYSTEM")
    xl=xp["candidate_artifacts"][0]["logical_path"];xmap=build_skeleton(xp);xmap["rows"]=[intent_row(xl,"ARTIFACT",action="modify"),intent_row(xl,"BSL_ROUTINE","Обработать",action="modify")]
    ir=validate_intent_map(xmap,xp)
    record("phase1:cross_system_incomplete_side_blocks","CROSS_SYSTEM_ONE_SIDED_SCOPE_UNPROVEN" in types(ir["errors"]),ir["errors"])

local=[]
role=validate_claim_policy(POLICY,[
    {"kind":"SOURCE_REQUIRED","ref":"source","claim_id":"CHECK:X:Y","_verifier_proof_role":"PRIMARY_VERIFIED_SOURCE"},
    {"kind":"MACHINE","ref":"machine","claim_id":"CHECK:X:Y","_verifier_machine_property_confirmed":True},
],{},"CHECK:X:Y",local,"check","X:Y")
record("phase1:generic_machine_pass_not_semantic_review","INDEPENDENT_REVIEW_REQUIRED" in types(local),local)

local=[]
out=validate_obligation_evidence([{"kind":"RUNTIME","ref":"runtime","claim_id":"CHECK:X:Y","property_id":"CHECK:X:OTHER"}],
    "CHECK:X:Y",["RUNTIME"],local,"check","X:Y",require_primary=True,proof_policy={"claim_class":"LEGACY_COMPATIBLE","required_roles":[]})
record("phase1:runtime_other_property_not_reused",
       "RUNTIME_EVIDENCE_CLAIM_PROPERTY_MISMATCH" in types(local) and out["primary_count"]==0,local)

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results,"cases":len(results),
     "proof_boundary":"CONTENT_SESSION_SEPARATED is procedural only; EXTERNAL_REVIEWER_UNVERIFIED remains mandatory without a trusted adapter/root. Structural deltas are not runtime/business proof."}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
