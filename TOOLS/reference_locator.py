#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "REFERENCE" / "CATALOGS"
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]+")


def _tokens(value: str) -> set[str]:
    return {x.casefold() for x in TOKEN_RE.findall(value or "") if len(x) >= 2}


def load_catalogs(root: Path = CATALOG_ROOT) -> list[dict]:
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        payload["_catalog_path"] = str(path)
        rows.append(payload)
    return rows


def _request_candidates(catalog: dict, entry: dict) -> tuple[list[str], list[str], list[dict]]:
    explicit = entry.get("request_candidates") or []
    if explicit:
        candidates = []
        names = []
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

    legacy_modules = list(entry.get("candidate_modules") or [])
    names = list(entry.get("candidate_names") or legacy_modules)
    request_template = entry.get("request_path_template")
    if request_template is None:
        request_template = catalog.get("request_path_template")
    request_object_type = entry.get("request_object_type") or catalog.get("request_object_type")
    if not request_object_type:
        request_object_type = "CommonModule" if (request_template or "").replace("\\", "/").startswith("CommonModules/") else "UNKNOWN"

    candidates = []
    for name in names:
        candidates.append({
            "object_type": request_object_type,
            "name": name,
            "suggested_path": request_template.format(module=name, name=name) if request_template else None,
        })
    return names, legacy_modules, candidates


def locate(query: str, catalogs: list[dict] | None = None, limit: int = 10) -> dict:
    catalogs = load_catalogs() if catalogs is None else catalogs
    query_tokens = _tokens(query)
    matches = []

    for catalog in catalogs:
        for entry in catalog.get("entries", []):
            terms = list(entry.get("intent_terms") or [])
            names, legacy_modules, request_candidates = _request_candidates(catalog, entry)
            haystack_tokens = _tokens(" ".join([entry.get("id", ""), *terms, *names]))
            overlap = query_tokens & haystack_tokens
            phrase_hits = [term for term in terms if term.casefold() in query.casefold() or query.casefold() in term.casefold()]
            if not overlap and not phrase_hits:
                continue

            score = len(overlap) * 2 + len(phrase_hits) * 3
            matches.append({
                "catalog_id": catalog.get("catalog_id"),
                "source_family": catalog.get("source_family"),
                "entry_id": entry.get("id"),
                "score": score,
                "matched_tokens": sorted(overlap),
                "matched_terms": phrase_hits,
                "candidate_names": names,
                "candidate_modules": legacy_modules,
                "request_candidates": request_candidates,
                "role": catalog.get("role", "DISCOVERY_ONLY"),
                "proof_rule": catalog.get("rule"),
                "proof_required_after_locator_match": entry.get("proof_required_after_locator_match") or catalog.get("proof_required_after_locator_match") or [],
            })

    matches.sort(key=lambda row: (-row["score"], row.get("entry_id") or ""))
    matches = matches[: max(1, limit)]
    return {
        "result": "MATCHES" if matches else "NO_MATCH",
        "query": query,
        "matches": matches,
        "rule": "Locator matches identify likely evidence to request. They are never API/signature/behavior proof and must not be promoted to a callable contract without exact source evidence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Search shareable discovery catalogs for likely exact source to request.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--catalog-root", default=str(CATALOG_ROOT))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output")
    args = parser.parse_args()

    report = locate(args.query, load_catalogs(Path(args.catalog_root)), args.limit)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
