#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "PATTERNS/INDEX.json"


def tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[A-Za-zА-Яа-яЁё0-9_]+", value.lower()) if len(x) > 1}


def load_index(root: Path = ROOT) -> dict:
    return json.loads((root / "PATTERNS/INDEX.json").read_text(encoding="utf-8-sig"))


def locate(intent: str, platform: str | None = None, limit: int = 5, root: Path = ROOT) -> dict:
    payload = load_index(root)
    query_tokens = tokens(intent)
    rows = []
    for row in payload.get("patterns", []):
        if platform and row.get("platform") != platform:
            continue
        corpus = " ".join([row.get("id", ""), row.get("summary", ""), *row.get("intent_terms", []), *row.get("profiles", [])])
        corpus_tokens = tokens(corpus)
        overlap = sorted(query_tokens & corpus_tokens)
        phrase_hits = [term for term in row.get("intent_terms", []) if term.lower() in intent.lower()]
        score = len(overlap) + 3 * len(phrase_hits)
        if not score:
            continue
        rows.append({
            "id": row["id"],
            "platform": row["platform"],
            "score": score,
            "matched_terms": sorted(set(overlap + phrase_hits)),
            "summary": row["summary"],
            "good": row["good"],
            "bad": row["bad"],
            "role": "ILLUSTRATIVE_PATTERN",
            "evidence_role": "NONE",
            "copy_policy": "ADAPT_ONLY",
            "proves_api": False,
            "proves_runtime": False,
            "requires_exact_source": True,
            "exact_source_required_for": row.get("exact_source_required_for", []),
            "proof_gate": "Pattern shape may guide design; exact target/user-authorized source must prove the real contract before implementation is called ready."
        })
    rows.sort(key=lambda x: (-x["score"], x["id"]))
    return {
        "result": "CANDIDATES" if rows else "NO_MATCH",
        "intent": intent,
        "platform": platform,
        "candidates": rows[:limit],
        "rule": "PATTERNS are illustrative only and carry no API/runtime evidence. TESTS/fixtures are never implementation precedent."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Find small illustrative implementation patterns by intent without treating them as evidence.")
    parser.add_argument("--intent", required=True)
    parser.add_argument("--platform", choices=("ONEC", "CLEVERENCE"))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(locate(args.intent, args.platform, args.limit), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
