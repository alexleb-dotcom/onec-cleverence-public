#!/usr/bin/env python3
"""Independent preconditions for final release verdicts.

This module closes trust-boundary holes that are unsafe to express as narrative
requirements only: non-proof evidence laundering, disappearance of exact source
bytes, free-text NOT_APPLICABLE on routed obligations, erased child checks, and
all-N/A adversarial validation.

It intentionally does not attempt to solve the later planner/receipt trust-model
work. The current plan is still an input; this layer only makes several known
ways of weakening that input fail closed.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import zipfile

from evidence_source_policy import validate_ledger as validate_evidence_source_policy
from rule_registry import RISK_RANK, rule_map


def _has_text(value):
    return isinstance(value,str) and bool(value.strip())


_PLACEHOLDER_REASON_RE=re.compile(
    r"^(?:n/?a|na|none|null|not\s+applicable|not\s+relevant|не\s+применимо|не\s+актуально|не\s+требуется|"
    r"reason|reason\s+here|template\s+reason|placeholder|todo|tbd|причина|указать\s+причину|"
    r"not\s+applicable\s+because\s+not\s+applicable)[\s.!_-]*$",
    re.I,
)


def is_substantive_reason(value):
    """Reject empty/template dispositions without pretending to judge business truth."""
    if not _has_text(value):
        return False
    text=str(value).strip()
    if len(text)<12 or _PLACEHOLDER_REASON_RE.match(text):
        return False
    if re.search(r"<[^>]*(?:reason|причин)[^>]*>|\{[^}]*(?:reason|причин)[^}]*\}",text,re.I):
        return False
    tokens=re.findall(r"[A-Za-zА-Яа-яЁё0-9]+",text)
    generic={"not","applicable","relevant","because","reason","here","не","применимо","актуально","требуется","причина"}
    informative=[x for x in tokens if x.casefold() not in generic]
    return len(informative)>=2


def _canon(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def route_fingerprint(route):
    material={
        "id":route.get("id"),
        "active":bool(route.get("active")),
        "activation_status":route.get("activation_status"),
        "detected_by":route.get("detected_by") or [],
        "reason":route.get("reason"),
        "surface":route.get("surface"),
        "risk_floor":route.get("risk_floor"),
    }
    return hashlib.sha256(_canon(material).encode("utf-8")).hexdigest()


def _read_origin(origin):
    if not _has_text(origin):
        return {"status":"MISSING_REF","ref":origin}
    text=str(origin)
    if "!/" in text:
        archive_name,entry=text.split("!/",1); archive=Path(archive_name)
        if not archive.is_file():return {"status":"MISSING_ARCHIVE","ref":text}
        try:
            with zipfile.ZipFile(archive) as z:data=z.read(entry)
        except KeyError:return {"status":"MISSING_ARCHIVE_ENTRY","ref":text}
        except zipfile.BadZipFile:return {"status":"BAD_ARCHIVE","ref":text}
        except OSError as exc:return {"status":"READ_ERROR","ref":text,"error":str(exc)}
        return {"status":"OK","ref":text,"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}
    path=Path(text)
    if not path.is_file():return {"status":"MISSING_FILE","ref":text}
    try:data=path.read_bytes()
    except OSError as exc:return {"status":"READ_ERROR","ref":text,"error":str(exc)}
    return {"status":"OK","ref":text,"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}


def _snapshot(path_value):
    if not _has_text(path_value):return {"status":"MISSING_REF","ref":path_value}
    path=Path(path_value)
    if path.is_file():
        try:data=path.read_bytes()
        except OSError as exc:return {"status":"READ_ERROR","ref":str(path),"error":str(exc)}
        return {"status":"OK","ref":str(path),"kind":"FILE","sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}
    if path.is_dir():
        digest=hashlib.sha256(); files=0; total=0
        try:
            children=sorted(x for x in path.rglob("*") if x.is_file())
            for item in children:
                rel=item.relative_to(path).as_posix(); data=item.read_bytes(); file_sha=hashlib.sha256(data).hexdigest()
                digest.update(rel.encode("utf-8")); digest.update(b"\0"); digest.update(file_sha.encode("ascii")); digest.update(b"\n")
                files+=1; total+=len(data)
        except OSError as exc:return {"status":"READ_ERROR","ref":str(path),"error":str(exc)}
        return {"status":"OK","ref":str(path),"kind":"DIRECTORY","sha256":digest.hexdigest(),"files":files,"size":total}
    return {"status":"MISSING_PATH","ref":str(path)}


def _validate_bound_file(scope, dep, path_key, portable_key, expected_key, errors):
    expected=dep.get(expected_key)
    primary=dep.get(path_key)
    if not _has_text(expected) or not _has_text(primary):return
    current=_read_origin(primary)
    if current.get("status")=="OK":
        if str(current.get("sha256")).lower()!=str(expected).lower():
            errors.append({"type":f"{scope}_SOURCE_DRIFT","path":primary,"expected":expected,"actual":current.get("sha256")})
        return
    portable=dep.get(portable_key)
    if _has_text(portable):
        replacement=_read_origin(portable)
        if replacement.get("status")=="OK":
            if str(replacement.get("sha256")).lower()!=str(expected).lower():
                errors.append({"type":f"{scope}_PORTABLE_SOURCE_DRIFT","path":portable,"expected":expected,"actual":replacement.get("sha256")})
            return
        errors.append({"type":f"{scope}_SOURCE_UNAVAILABLE","path":primary,"primary_state":current,"portable_path":portable,"portable_state":replacement})
        return
    errors.append({"type":f"{scope}_SOURCE_UNAVAILABLE","path":primary,"primary_state":current,"portable_path":None})


def _validate_current_sources(plan, errors):
    for row in plan.get("candidate_artifacts") or []:
        expected=row.get("sha256"); origin=row.get("origin")
        if not _has_text(expected) or not _has_text(origin):continue
        current=_read_origin(origin)
        if current.get("status")=="OK":
            if str(current.get("sha256")).lower()!=str(expected).lower():
                errors.append({"type":"CANDIDATE_SOURCE_DRIFT","logical_path":row.get("logical_path"),"origin":origin,"expected":expected,"actual":current.get("sha256")})
            continue
        portable=row.get("portable_origin")
        if _has_text(portable):
            replacement=_read_origin(portable)
            if replacement.get("status")=="OK":
                if str(replacement.get("sha256")).lower()!=str(expected).lower():
                    errors.append({"type":"CANDIDATE_PORTABLE_SOURCE_DRIFT","logical_path":row.get("logical_path"),"origin":portable,"expected":expected,"actual":replacement.get("sha256")})
                continue
            errors.append({"type":"CANDIDATE_SOURCE_UNAVAILABLE","logical_path":row.get("logical_path"),"origin":origin,"primary_state":current,"portable_origin":portable,"portable_state":replacement})
            continue
        errors.append({"type":"CANDIDATE_SOURCE_UNAVAILABLE","logical_path":row.get("logical_path"),"origin":origin,"primary_state":current,"portable_origin":None})

    baseline=plan.get("baseline")
    if isinstance(baseline,dict) and _has_text(baseline.get("path")) and _has_text(baseline.get("sha256")):
        current=_snapshot(baseline.get("path"))
        if current.get("status")=="OK":
            if current.get("sha256")!=baseline.get("sha256"):
                errors.append({"type":"BASELINE_SOURCE_DRIFT","path":baseline.get("path"),"expected":baseline.get("sha256"),"actual":current.get("sha256")})
        else:
            portable=baseline.get("portable_path")
            if _has_text(portable):
                replacement=_snapshot(portable)
                if replacement.get("status")=="OK":
                    if replacement.get("sha256")!=baseline.get("sha256"):
                        errors.append({"type":"BASELINE_PORTABLE_SOURCE_DRIFT","path":portable,"expected":baseline.get("sha256"),"actual":replacement.get("sha256")})
                else:errors.append({"type":"BASELINE_SOURCE_UNAVAILABLE","path":baseline.get("path"),"primary_state":current,"portable_path":portable,"portable_state":replacement})
            else:errors.append({"type":"BASELINE_SOURCE_UNAVAILABLE","path":baseline.get("path"),"primary_state":current,"portable_path":None})

    for scope,key in (("PROJECT_CONTEXT","project_context"),("REQUIREMENTS","requirements")):
        dep=plan.get(key) or {}
        _validate_bound_file(scope,dep,"path","portable_path","sha256",errors)


def _concrete_evidence(items):
    return bool(items) and all(isinstance(x,dict) and _has_text(x.get("kind")) and _has_text(x.get("ref")) for x in items)


def _untriggered_tier0_disposition(rule, route):
    return bool(rule.get("tier")==0 and not (route.get("detected_by") or []) and not str(route.get("reason") or "").startswith("derived:"))


def _validate_na_rules(plan, ledger, registry, errors):
    rules=rule_map(registry)
    routes={row.get("id"):row for row in (plan.get("rules") or []) if isinstance(row,dict) and _has_text(row.get("id"))}
    for row in ledger.get("rules") or []:
        if not isinstance(row,dict) or row.get("status")!="NOT_APPLICABLE":continue
        rid=row.get("id"); rule=rules.get(rid); route=routes.get(rid)
        if not rule or not route:continue
        if not is_substantive_reason(row.get("reason")):
            errors.append({"type":"NA_REASON_NOT_SUBSTANTIVE","scope":"rule","id":rid,"reason":row.get("reason")})

        expected_ids=[x.get("id") for x in rule.get("checks",[]) if _has_text(x.get("id"))]
        actual_rows=row.get("checks") or []
        actual_ids=[x.get("id") for x in actual_rows if isinstance(x,dict) and _has_text(x.get("id"))]
        if len(actual_ids)!=len(set(actual_ids)) or set(actual_ids)!=set(expected_ids):
            errors.append({"type":"NA_RULE_CHECK_STRUCTURE_DRIFT","id":rid,"missing":sorted(set(expected_ids)-set(actual_ids)),"extra":sorted(set(actual_ids)-set(expected_ids))})

        # An active/required parent N/A is a disposition, never a child-check bypass.
        # Every registered child must be explicitly N/A with a substantive reason.
        if route.get("activation_status")=="REQUIRED" or route.get("active"):
            for child in actual_rows:
                if not isinstance(child,dict):continue
                if child.get("status")!="NOT_APPLICABLE" or not is_substantive_reason(child.get("reason")):
                    errors.append({"type":"NA_RULE_CHILD_NOT_DISPOSED","rule":rid,"id":child.get("id"),"status":child.get("status"),"reason":child.get("reason")})

        # Untriggered Tier-0 disposition does not need a false-positive rebuttal,
        # but it still needs parent proof in release_gate_core and explicit child disposition.
        if _untriggered_tier0_disposition(rule,route):
            continue

        # A routed/derived N/A must rebut the exact routing signals.
        rebuttal=row.get("applicability_rebuttal")
        if not isinstance(rebuttal,dict):
            errors.append({"type":"ROUTED_RULE_NA_WITHOUT_REBUTTAL","id":rid,"activation_status":route.get("activation_status"),"detected_by":route.get("detected_by") or []})
            continue
        if rebuttal.get("status")!="FALSE_POSITIVE":errors.append({"type":"NA_REBUTTAL_STATUS_INVALID","id":rid,"status":rebuttal.get("status")})
        if rebuttal.get("route_fingerprint")!=route_fingerprint(route):errors.append({"type":"NA_REBUTTAL_ROUTE_FINGERPRINT_MISMATCH","id":rid})
        if not is_substantive_reason(rebuttal.get("reason")):errors.append({"type":"NA_REBUTTAL_REASON_MISSING","id":rid})
        if not _concrete_evidence(rebuttal.get("evidence")):errors.append({"type":"NA_REBUTTAL_EVIDENCE_MISSING","id":rid})
        detected=set(route.get("detected_by") or [])
        rebutted=set(rebuttal.get("rebutted_signals") or [])
        if detected and not detected.issubset(rebutted):errors.append({"type":"NA_REBUTTAL_SIGNAL_COVERAGE_INCOMPLETE","id":rid,"missing":sorted(detected-rebutted)})


def _validate_adversarial_attempt(plan, ledger, registry, errors):
    planned={row.get("gate"):row for row in (plan.get("gate_plan") or []) if isinstance(row,dict)}
    contract=registry.get("adversarial_case_contract") or {}
    risk=(plan.get("routing") or {}).get("risk"); min_risk=contract.get("min_risk","R1_CONTRACT")
    required=(
        (planned.get("ADVERSARIAL_VALIDATION") or {}).get("status")=="REQUIRED"
        and risk in RISK_RANK and min_risk in RISK_RANK and RISK_RANK[risk]>=RISK_RANK[min_risk]
        and (plan.get("routing") or {}).get("mode")!="ANALYSIS_ONLY"
    )
    if not required:return
    rows=[x for x in (ledger.get("adversarial_cases") or []) if isinstance(x,dict)]
    if rows and all(x.get("status")=="NOT_APPLICABLE" for x in rows):
        errors.append({"type":"ADVERSARIAL_CASE_ATTEMPT_MISSING","reason":"all adversarial cases are NOT_APPLICABLE"})


def validate_trust_boundary(plan, ledger, registry):
    errors=[]
    policy=validate_evidence_source_policy(ledger)
    errors.extend(policy.get("errors") or [])
    _validate_current_sources(plan,errors)
    _validate_na_rules(plan,ledger,registry,errors)
    _validate_adversarial_attempt(plan,ledger,registry,errors)
    return {
        "result":"PASS" if not errors else "FAIL",
        "errors":errors,
        "evidence_source_policy":policy.get("result"),
        "rule":"Final verdicts fail closed when non-proof evidence is laundered, exact bound bytes disappear, routed obligations are erased through free-text N/A, child checks disappear, or required adversarial validation is only N/A.",
    }
