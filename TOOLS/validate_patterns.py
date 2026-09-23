#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ROLE = {
    "role": "ILLUSTRATIVE_PATTERN",
    "evidence_role": "NONE",
    "copy_policy": "ADAPT_ONLY",
    "proves_api": False,
    "proves_runtime": False,
    "requires_exact_source": True,
}


def validate(root: Path = ROOT) -> dict:
    errors = []
    index_path = root / "PATTERNS/INDEX.json"
    readme_path = root / "PATTERNS/README.md"
    if not index_path.is_file():
        return {"result": "FAIL", "errors": [{"type": "PATTERN_INDEX_MISSING"}]}
    if not readme_path.is_file():
        return {"result": "FAIL", "errors": [{"type": "PATTERN_README_MISSING"}]}

    payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != 1:
        errors.append({"type": "PATTERN_SCHEMA_UNSUPPORTED", "value": payload.get("schema_version")})
    contract = payload.get("contract", {})
    for key, expected in REQUIRED_ROLE.items():
        if contract.get(key) != expected:
            errors.append({"type": "PATTERN_GLOBAL_CONTRACT_DRIFT", "field": key, "expected": expected, "actual": contract.get(key)})

    ids = set(); indexed_files = set(); counts = {"ONEC": 0, "CLEVERENCE": 0}
    for row in payload.get("patterns", []):
        pid = row.get("id")
        if not pid or pid in ids:
            errors.append({"type": "PATTERN_ID_INVALID_OR_DUPLICATE", "id": pid})
            continue
        ids.add(pid)
        platform = row.get("platform")
        if platform not in counts:
            errors.append({"type": "PATTERN_PLATFORM_INVALID", "id": pid, "platform": platform})
        else:
            counts[platform] += 1
        if not row.get("summary") or not row.get("intent_terms") or not row.get("profiles"):
            errors.append({"type": "PATTERN_ROUTING_METADATA_INCOMPLETE", "id": pid})
        if not row.get("exact_source_required_for"):
            errors.append({"type": "PATTERN_EXACT_SOURCE_GATE_MISSING", "id": pid})
        for kind in ("good", "bad"):
            rel = row.get(kind)
            if not rel or not rel.startswith("PATTERNS/") or "TESTS/fixtures" in rel:
                errors.append({"type": "PATTERN_PATH_INVALID", "id": pid, "kind": kind, "path": rel})
                continue
            indexed_files.add(rel)
            path = root / rel
            if not path.is_file():
                errors.append({"type": "PATTERN_FILE_MISSING", "id": pid, "kind": kind, "path": rel})
                continue
            text = path.read_text(encoding="utf-8-sig")
            sentinel = "ILLUSTRATIVE_PATTERN: NOT EVIDENCE"
            if sentinel not in text:
                errors.append({"type": "PATTERN_SENTINEL_MISSING", "id": pid, "kind": kind, "path": rel})
            if "REFERENCE/SOURCES" in text or "TESTS/fixtures" in text:
                errors.append({"type": "PATTERN_FORBIDDEN_DEPENDENCY", "id": pid, "kind": kind, "path": rel})
        good = root / row.get("good", "")
        bad = root / row.get("bad", "")
        if good.is_file() and bad.is_file() and good.read_bytes() == bad.read_bytes():
            errors.append({"type": "PATTERN_GOOD_BAD_IDENTICAL", "id": pid})

    code_files = {p.relative_to(root).as_posix() for p in (root / "PATTERNS").rglob("*") if p.is_file() and p.suffix.lower() in {".bsl", ".mslx"}}
    unindexed = sorted(code_files - indexed_files)
    if unindexed:
        errors.append({"type": "PATTERN_CODE_UNINDEXED", "paths": unindexed})

    readme = readme_path.read_text(encoding="utf-8-sig")
    for required in ("evidence_role = NONE", "TESTS/fixtures/**", "NEVER implementation precedent", "ADAPT_ONLY"):
        if required not in readme:
            errors.append({"type": "PATTERN_POLICY_TEXT_MISSING", "token": required})

    if counts["ONEC"] < 8 or counts["CLEVERENCE"] < 2 or len(ids) < 10:
        errors.append({"type": "PATTERN_MINIMUM_COVERAGE_NOT_MET", "counts": counts, "total": len(ids)})

    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "pattern_count": len(ids),
        "counts": counts,
        "indexed_code_files": len(indexed_files),
        "rule": "Canonical patterns are a bounded illustrative layer, never evidence. Every code example is indexed, labeled NOT EVIDENCE and requires exact target source before adaptation."
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    report = validate(Path(args.root).resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
