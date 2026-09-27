#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED_STATUSES = {
    "ACTIVE",
    "TEMPORARY",
    "REVALIDATION_REQUIRED",
    "SUPERSEDED",
    "INVALIDATED",
}
CURRENT_STATUSES = {"ACTIVE", "TEMPORARY"}


def _dep_key(row: dict) -> tuple[str, str]:
    return str(row.get("kind") or ""), str(row.get("id") or "")


def validate_lifecycle(data: dict, changed_dependencies: list[dict] | None = None) -> dict:
    decisions = data.get("decisions") or []
    errors: list[dict] = []
    warnings: list[dict] = []
    by_id: dict[str, dict] = {}
    current_by_key: dict[str, list[str]] = {}

    for index, row in enumerate(decisions):
        did = str(row.get("id") or "").strip()
        key = str(row.get("decision_key") or "").strip()
        claim = str(row.get("claim") or "").strip()
        status = str(row.get("status") or "").strip()
        where = did or f"index:{index}"

        if not did:
            errors.append({"type": "DECISION_ID_MISSING", "decision": where})
            continue
        if did in by_id:
            errors.append({"type": "DECISION_ID_DUPLICATE", "decision": did})
            continue
        by_id[did] = row

        if not key:
            errors.append({"type": "DECISION_KEY_MISSING", "decision": did})
        if not claim:
            errors.append({"type": "DECISION_CLAIM_MISSING", "decision": did})
        if status not in ALLOWED_STATUSES:
            errors.append({"type": "DECISION_STATUS_INVALID", "decision": did, "status": status})
            continue

        if status in CURRENT_STATUSES and key:
            current_by_key.setdefault(key, []).append(did)

        if status == "TEMPORARY":
            if not str(row.get("temporary_reason") or "").strip():
                errors.append({"type": "TEMPORARY_REASON_MISSING", "decision": did})
            if not str(row.get("replacement_criterion") or "").strip():
                errors.append({"type": "TEMPORARY_REPLACEMENT_CRITERION_MISSING", "decision": did})
            if not (row.get("revalidation_triggers") or []):
                errors.append({"type": "TEMPORARY_REVALIDATION_TRIGGER_MISSING", "decision": did})

        if status == "SUPERSEDED" and not str(row.get("superseded_by") or "").strip():
            errors.append({"type": "SUPERSEDED_LINK_MISSING", "decision": did})
        if status in {"INVALIDATED", "REVALIDATION_REQUIRED"} and not str(row.get("status_reason") or "").strip():
            errors.append({"type": "STATUS_REASON_MISSING", "decision": did, "status": status})

        dep_seen: set[tuple[str, str]] = set()
        for dep in row.get("evidence_dependencies") or []:
            dkey = _dep_key(dep)
            if not all(dkey):
                errors.append({"type": "EVIDENCE_DEPENDENCY_IDENTITY_MISSING", "decision": did, "dependency": dep})
                continue
            if dkey in dep_seen:
                errors.append({"type": "EVIDENCE_DEPENDENCY_DUPLICATE", "decision": did, "dependency": dkey})
            dep_seen.add(dkey)
            if not str(dep.get("fingerprint") or "").strip():
                errors.append({"type": "EVIDENCE_DEPENDENCY_FINGERPRINT_MISSING", "decision": did, "dependency": dkey})

    for key, ids in current_by_key.items():
        if len(ids) > 1:
            errors.append({"type": "CONFLICTING_CURRENT_DECISIONS", "decision_key": key, "decisions": sorted(ids)})

    # Link integrity after all IDs are known.
    for did, row in by_id.items():
        status = row.get("status")
        if status == "SUPERSEDED":
            successor_id = str(row.get("superseded_by") or "").strip()
            successor = by_id.get(successor_id)
            if successor_id and successor is None:
                errors.append({"type": "SUPERSEDED_SUCCESSOR_NOT_FOUND", "decision": did, "superseded_by": successor_id})
            elif successor is not None and did not in set(successor.get("supersedes") or []):
                errors.append({"type": "SUPERSESSION_LINK_NOT_BIDIRECTIONAL", "decision": did, "successor": successor_id})

        for old_id in row.get("supersedes") or []:
            old = by_id.get(str(old_id))
            if old is None:
                errors.append({"type": "SUPERSEDED_PREDECESSOR_NOT_FOUND", "decision": did, "predecessor": old_id})
            elif old.get("status") != "SUPERSEDED" or str(old.get("superseded_by") or "") != did:
                errors.append({"type": "SUPERSESSION_PREDECESSOR_STATE_INVALID", "decision": did, "predecessor": old_id})

        for dependency_id in row.get("decision_dependencies") or []:
            dependency = by_id.get(str(dependency_id))
            if dependency is None:
                errors.append({"type": "DECISION_DEPENDENCY_NOT_FOUND", "decision": did, "dependency": dependency_id})
            elif row.get("status") in CURRENT_STATUSES and dependency.get("status") in {"SUPERSEDED", "INVALIDATED"}:
                errors.append({"type": "CURRENT_DEPENDS_ON_STALE_DECISION", "decision": did, "dependency": dependency_id, "dependency_status": dependency.get("status")})

    changed_map = {_dep_key(row): str(row.get("fingerprint") or "") for row in (changed_dependencies or []) if all(_dep_key(row))}
    revalidation_required: list[dict] = []
    for did, row in by_id.items():
        if row.get("status") not in CURRENT_STATUSES:
            continue
        for dep in row.get("evidence_dependencies") or []:
            key = _dep_key(dep)
            if key not in changed_map:
                continue
            old_fp = str(dep.get("fingerprint") or "")
            new_fp = changed_map[key]
            if new_fp and new_fp != old_fp:
                revalidation_required.append({
                    "decision": did,
                    "decision_key": row.get("decision_key"),
                    "dependency": {"kind": key[0], "id": key[1]},
                    "old_fingerprint": old_fp,
                    "new_fingerprint": new_fp,
                })
                break

    if revalidation_required:
        warnings.append({
            "type": "PROJECT_CONTEXT_REVALIDATION_REQUIRED",
            "decisions": [x["decision"] for x in revalidation_required],
            "rule": "Do not rely on these ACTIVE/TEMPORARY decisions until the changed evidence dependency is revalidated.",
        })

    active = sorted(did for did, row in by_id.items() if row.get("status") in CURRENT_STATUSES)
    stale = sorted(did for did, row in by_id.items() if row.get("status") in {"SUPERSEDED", "INVALIDATED"})
    pending = sorted(set(did for did, row in by_id.items() if row.get("status") == "REVALIDATION_REQUIRED") | {x["decision"] for x in revalidation_required})

    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "decisions": len(decisions),
            "active_or_temporary": active,
            "historical_stale": stale,
            "revalidation_required": pending,
        },
        "revalidation_required": revalidation_required,
        "rule": "Use only one current decision per decision_key; temporary decisions remain explicitly temporary; superseded/invalidated history is provenance, not current truth.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate project-context decision lifecycle and detect stale evidence dependencies.")
    parser.add_argument("context", help="JSON file containing a decisions array")
    parser.add_argument("--changed-dependencies", help="Optional JSON file containing a dependencies array or list")
    args = parser.parse_args()

    data = json.loads(Path(args.context).read_text(encoding="utf-8-sig"))
    changed = []
    if args.changed_dependencies:
        payload = json.loads(Path(args.changed_dependencies).read_text(encoding="utf-8-sig"))
        changed = payload.get("dependencies", []) if isinstance(payload, dict) else payload
    report = validate_lifecycle(data, changed)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
