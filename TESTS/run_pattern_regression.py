#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))
from validate_patterns import validate
from pattern_locator import locate

errors = []
results = {}


def record(case, ok, details):
    results[case] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": case, "details": details})


validation = validate(ROOT)
record("pattern_contract_validation", validation.get("result") == "PASS", validation)

cases = [
    ("hook orchestration обработчик расширение", "HOOK_ORCHESTRATION"),
    ("derive validate mutate добавить строку ключ", "DERIVE_VALIDATE_MUTATE"),
    ("sentinel empty reference bulk mode пустая ссылка", "QUERY_SENTINEL_EXPLICIT_BRANCH"),
    ("form collection client loop server коллекция формы", "FORM_COLLECTION_SERVER"),
    ("DeclaredItems CurrentItems BindedLine plan fact", "PLAN_FACT_IDENTITY"),
    ("scan re-entry repeat barcode сканирование", "SCAN_REENTRY"),
]
for query, expected in cases:
    report = locate(query, root=ROOT)
    ids = [x["id"] for x in report.get("candidates", [])]
    record(f"locator:{expected}", expected in ids, {"query": query, "ids": ids})
    if report.get("candidates"):
        safe = all(
            row.get("role") == "ILLUSTRATIVE_PATTERN"
            and row.get("evidence_role") == "NONE"
            and row.get("copy_policy") == "ADAPT_ONLY"
            and row.get("proves_api") is False
            and row.get("proves_runtime") is False
            and row.get("requires_exact_source") is True
            and row.get("exact_source_required_for")
            for row in report["candidates"]
        )
        record(f"locator_proof_gate:{expected}", safe, report["candidates"])

policy = (ROOT / "PATTERNS/README.md").read_text(encoding="utf-8-sig")
record(
    "fixtures_never_precedent",
    "TESTS/fixtures/**" in policy and "NEVER implementation precedent" in policy,
    {"policy": "PATTERNS/README.md"},
)

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
