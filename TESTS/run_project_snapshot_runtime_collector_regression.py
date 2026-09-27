#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Ext/ObjectModule.bsl"
LEGACY_DUPLICATE = ROOT / "COLLECTOR/ONEC_RUNTIME/ProjectSnapshotRuntimeCollector.bsl"
PROFILE = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_RUNTIME_V1_CAPABILITIES.json"
ANALYZER = ROOT / "TOOLS/analyze_onec_bsl.py"


def main() -> int:
    errors: list[str] = []
    if LEGACY_DUPLICATE.exists():
        errors.append("duplicate_runtime_collector_source_must_not_exist")
    text = SOURCE.read_text(encoding="utf-8-sig")
    profile = json.loads(PROFILE.read_text(encoding="utf-8-sig"))

    required_tokens = [
        "Функция СобратьПоПлану(ТекстПланаJSON) Экспорт",
        "Функция СформироватьJSONРезультата(РезультатСбора) Экспорт",
        'ВыбранныйBackend <> "RUNTIME_METADATA"',
        'Категория = "METADATA_PROPERTIES"',
        'Категория = "SCHEDULED_JOBS"',
        'Результат.Вставить("runtime_proven", Ложь)',
        'СтрокаРезультата.Вставить("status", "PARTIAL")',
        'Возврат Метаданные.Документы.Найти(Имя)',
        'Возврат Метаданные.Справочники.Найти(Имя)',
        'Возврат Метаданные.РегистрыСведений.Найти(Имя)',
        'Возврат Метаданные.РегистрыНакопления.Найти(Имя)',
        'Возврат Метаданные.РегламентныеЗадания.Найти(Имя)',
    ]
    for token in required_tokens:
        if token not in text:
            errors.append(f"runtime_collector_missing_contract_token:{token}")

    forbidden_patterns = {
        "query_against_business_data": r"\bНовый\s+Запрос\b",
        "transaction_start": r"\bНачатьТранзакцию\s*\(",
        "transaction_commit": r"\bЗафиксироватьТранзакцию\s*\(",
        "transaction_rollback": r"\bОтменитьТранзакцию\s*\(",
        "dynamic_execute": r"\bВыполнить\s*\(",
        "dynamic_evaluate": r"\bВычислить\s*\(",
        "object_write": r"\.Записать\s*\(",
        "catalog_create": r"\.СоздатьЭлемент\s*\(",
        "document_create": r"\.СоздатьДокумент\s*\(",
        "recordset_create": r"\.СоздатьНаборЗаписей\s*\(",
    }
    for name, pattern in forbidden_patterns.items():
        if re.search(pattern, text, flags=re.IGNORECASE):
            errors.append(f"runtime_collector_read_only_violation:{name}")

    if profile.get("profile") != "RUNTIME_V1":
        errors.append("runtime_profile_id_drift")
    if profile.get("backend") != "RUNTIME_METADATA":
        errors.append("runtime_profile_backend_drift")
    if profile.get("runtime_proven") is not False:
        errors.append("runtime_profile_must_remain_not_proven_without_runtime_evidence")
    implemented = set((profile.get("implemented_categories") or {}).keys())
    if implemented != {"METADATA_PROPERTIES", "SCHEDULED_JOBS"}:
        errors.append(f"runtime_v1_category_contract_drift:{sorted(implemented)}")

    analyzer = subprocess.run(
        [sys.executable, str(ANALYZER), str(SOURCE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if analyzer.returncode != 0:
        errors.append(f"runtime_collector_bsl_analyzer_failed:{analyzer.stderr or analyzer.stdout}")

    out = {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "collector": str(SOURCE.relative_to(ROOT)),
        "runtime_proven": profile.get("runtime_proven"),
        "implemented_categories": sorted(implemented),
        "bsl_analyzer_returncode": analyzer.returncode,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
