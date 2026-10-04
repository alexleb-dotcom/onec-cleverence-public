#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, json, re

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "REFERENCE" / "CATALOGS"
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")
BSP_STATUSES = {"EXACT", "RANGE_ONLY", "UNKNOWN", "NOT_DETECTED"}

def _tokens(value):
    return {x.casefold() for x in TOKEN_RE.findall(value or "") if len(x) >= 2}

def _version_tuple(value):
    if not value:
        return None
    parts = re.findall(r"\d+", str(value))
    return tuple(int(x) for x in parts) if parts else None

def classify_bsp_identity(*, exact_marker_value=None, unique_reference_version=None, bounded_range=None, bsp_detected=None, baseline_identity=None):
    if bsp_detected is False:
        status, version, rng, method = "NOT_DETECTED", None, None, "NO_BSP_EVIDENCE"
    elif exact_marker_value:
        status, version, rng, method = "EXACT", exact_marker_value, None, "EXACT_CURRENT_SOURCE_VERSION_MARKER"
    elif unique_reference_version:
        status, version, rng, method = "EXACT", unique_reference_version, None, "UNIQUE_AUTHORIZED_REFERENCE_FINGERPRINT"
    elif bounded_range and (bounded_range.get("min_inclusive") or bounded_range.get("max_exclusive")):
        status, version, rng, method = "RANGE_ONLY", None, bounded_range, "BOUNDED_VERSION_EVIDENCE"
    else:
        status, version, rng, method = "UNKNOWN", None, None, "UNPROVABLE"
    return {
        "status": status, "version": version, "range": rng,
        "detection_method": method, "baseline_identity": baseline_identity,
        "rule": "EXACT requires exact current-source marker value or unique authorized reference fingerprint; one module/API presence is never sufficient.",
    }

def bsp_identity_valid(identity, baseline_identity):
    return bool(identity and baseline_identity and identity.get("baseline_identity") == baseline_identity)

def load_catalogs(root=CATALOG_ROOT, catalog_id=None):
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if catalog_id and payload.get("catalog_id") != catalog_id:
            continue
        payload["_catalog_path"] = str(path)
        rows.append(payload)
    return rows

def _request_candidates(catalog, entry):
    explicit = entry.get("request_candidates") or []
    if explicit:
        candidates, names = [], []
        for raw in explicit:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            row = {
                "object_type": raw.get("object_type") or entry.get("request_object_type") or catalog.get("request_object_type") or "UNKNOWN",
                "name": raw["name"],
                "suggested_path": raw.get("suggested_path"),
            }
            candidates.append(row)
            names.append(row["name"])
        return names, [], candidates

    legacy = list(entry.get("candidate_modules") or [])
    names = list(entry.get("candidate_names") or legacy)
    template = entry.get("request_path_template")
    if template is None:
        template = catalog.get("request_path_template")
    object_type = entry.get("request_object_type") or catalog.get("request_object_type")
    if not object_type:
        object_type = "CommonModule" if (template or "").replace("\\", "/").startswith("CommonModules/") else "UNKNOWN"
    candidates = [{
        "object_type": object_type,
        "name": name,
        "suggested_path": template.format(module=name, name=name) if template else None,
    } for name in names]
    return names, legacy, candidates

def _version_match(entry, identity):
    support = entry.get("version_support") or {}
    if not identity or identity.get("status") in {None, "UNKNOWN", "RANGE_ONLY", "NOT_DETECTED"}:
        return "UNKNOWN"
    if identity.get("status") != "EXACT":
        return "POSSIBLE"
    version = _version_tuple(identity.get("version"))
    if not version or not support:
        return "POSSIBLE"
    min_v = _version_tuple(support.get("min_inclusive"))
    max_v = _version_tuple(support.get("max_exclusive"))
    if min_v and version < min_v:
        return "INCOMPATIBLE_PROVEN"
    if max_v and version >= max_v:
        return "INCOMPATIBLE_PROVEN"
    return "MATCH"

def locate(query, catalogs=None, limit=5, capability_id=None, bsp_identity=None):
    catalogs = load_catalogs() if catalogs is None else catalogs
    query_tokens = _tokens(query)
    matches = []
    for catalog in catalogs:
        for entry in catalog.get("entries", []):
            if capability_id and entry.get("id") != capability_id:
                continue
            terms = list(entry.get("intent_terms") or [])
            names, legacy, requests = _request_candidates(catalog, entry)
            hints = entry.get("candidate_api_hints") or []
            api_names = [str(x.get("name") or "") for x in hints if isinstance(x, dict)]
            haystack_tokens = _tokens(" ".join([entry.get("id", ""), entry.get("purpose", ""), *terms, *names, *api_names]))
            overlap = query_tokens & haystack_tokens
            phrase_hits = [term for term in terms if term.casefold() in query.casefold() or query.casefold() in term.casefold()]
            if not capability_id and not overlap and not phrase_hits:
                continue
            version_match = _version_match(entry, bsp_identity)
            if version_match == "INCOMPATIBLE_PROVEN":
                continue
            score = len(overlap) * 2 + len(phrase_hits) * 3 + (2 if version_match == "MATCH" else 0)
            matches.append({
                "catalog_id": catalog.get("catalog_id"),
                "source_family": catalog.get("source_family"),
                "entry_id": entry.get("id"),
                "purpose": entry.get("purpose"),
                "score": score,
                "matched_tokens": sorted(overlap),
                "matched_terms": phrase_hits,
                "version_match": version_match,
                "candidate_names": names,
                "candidate_modules": legacy,
                "candidate_api_hints": hints,
                "request_candidates": requests,
                "version_evidence_refs": entry.get("version_evidence_refs") or [],
                "discovery_probes": entry.get("discovery_probes") or [],
                "caveats": entry.get("caveats") or [],
                "role": catalog.get("role", "DISCOVERY_ONLY"),
                "proof_rule": catalog.get("rule"),
                "proof_required_after_locator_match": entry.get("proof_required_after_locator_match") or catalog.get("proof_required_after_locator_match") or [],
            })
    matches.sort(key=lambda row: (-row["score"], row.get("entry_id") or ""))
    matches = matches[:max(1, min(limit, 20))]
    return {
        "result": "MATCHES" if matches else "NO_MATCH",
        "query": query,
        "capability_id": capability_id,
        "bsp_identity": bsp_identity,
        "matches": matches,
        "rule": "DISCOVERY_ONLY. Current Source is final authority. Candidate/API hints are not callable until exact current source proves module/path, declaration/signature, execution context and availability for the exact participant/artifact/baseline.",
    }

def main():
    parser = argparse.ArgumentParser(description="Search shareable discovery catalogs for likely exact source to request.")
    parser.add_argument("--query", default="")
    parser.add_argument("--catalog-root", default=str(CATALOG_ROOT))
    parser.add_argument("--catalog")
    parser.add_argument("--capability-id")
    parser.add_argument("--bsp-version")
    parser.add_argument("--bsp-status", choices=sorted(BSP_STATUSES))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    identity = None
    if args.bsp_status or args.bsp_version:
        status = args.bsp_status or "EXACT"
        identity = {"status": status, "version": args.bsp_version if status == "EXACT" else None}
    report = locate(args.query, load_catalogs(Path(args.catalog_root), args.catalog), args.limit, args.capability_id, identity)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
