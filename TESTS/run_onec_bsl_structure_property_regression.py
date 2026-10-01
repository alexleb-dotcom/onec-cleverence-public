#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from analyze_onec_bsl import analyze
from rule_registry import load_registry, proof_policy_for, rule_map
from build_validation_ledger import machine_finding_mapping
from release_gate_core import _validate_machine_findings

FINDING = "STRUCTURE_PROPERTY_OUT_PARAM_UNSAFE_BOOLEAN"
errors = []
results = {}


def record(case, ok, details):
    results[case] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": case, "details": details})


def finding_rows(source):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "Module.bsl"
        path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")
        report = analyze(path)
    return [row for row in report.get("findings", []) if row.get("type") == FINDING], report


negative = {
    "basic_bare_boolean": """
        Процедура Тест()
            Параметры.Свойство("Признак", Флаг);
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "negated_bare_boolean": """
        Процедура Тест()
            Параметры.Свойство("Признак", Флаг);
            Если НЕ Флаг Тогда
                Сообщить("Нет");
            КонецЕсли;
        КонецПроцедуры
    """,
    "undefined_initialized_then_overwritten": """
        Процедура Тест()
            Флаг = Неопределено;
            Параметры.Свойство("Признак", Флаг);
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "presence_does_not_prove_value_domain": """
        Процедура Тест()
            Если Параметры.Свойство("Признак", Флаг) Тогда
                Сообщить("Ключ есть");
            КонецЕсли;
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "simple_alias": """
        Процедура Тест()
            Параметры.Свойство("Признак", Флаг);
            ЛокальныйФлаг = Флаг;
            Если ЛокальныйФлаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
}

positive = {
    "presence_only": """
        Процедура Тест()
            Если Параметры.Свойство("Ключ") Тогда
                Сообщить("Есть");
            КонецЕсли;
        КонецПроцедуры
    """,
    "explicit_boolean_normalization": """
        Процедура Тест()
            Параметры.Свойство("Признак", Флаг);
            Флаг = ?(ТипЗнч(Флаг) = Тип("Булево"), Флаг, Ложь);
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "simple_boolean_type_guard": """
        Процедура Тест()
            Параметры.Свойство("Признак", Флаг);
            Если ТипЗнч(Флаг) = Тип("Булево") Тогда
                Если Флаг Тогда
                    Сообщить("Да");
                КонецЕсли;
            КонецЕсли;
        КонецПроцедуры
    """,
    "presence_plus_exact_type_guard": """
        Процедура Тест()
            Если Параметры.Свойство("Признак", Значение) И ТипЗнч(Значение) = Тип("Булево") Тогда
                Если Значение Тогда
                    Сообщить("Да");
                КонецЕсли;
            КонецЕсли;
        КонецПроцедуры
    """,
    "unrelated_out_use": """
        Процедура Тест()
            Параметры.Свойство("Код", Значение);
            Сообщить(Строка(Значение));
        КонецПроцедуры
    """,
}

for name, source in negative.items():
    rows, report = finding_rows(source)
    record("negative:" + name, len(rows) == 1, {"findings": rows, "summary": report.get("summary")})

for name, source in positive.items():
    rows, report = finding_rows(source)
    record("positive:" + name, len(rows) == 0, {"findings": rows, "summary": report.get("summary")})

registry = load_registry()
rules = rule_map(registry)
mapping = machine_finding_mapping(registry)
owner = mapping.get(FINDING)
record(
    "machine_owner_mapping",
    bool(owner and owner[0] == "STRUCTURED_CONTRACT" and owner[1] == "STRUCTURED_CONTRACT_P07"),
    {"owner": owner[:2] if owner else None},
)

policy = proof_policy_for(rules["STRUCTURED_CONTRACT"], registry)
expected_row = {
    "id": "MF:test",
    "claim_id": "MF:test",
    "rule_id": "STRUCTURED_CONTRACT",
    "check_id": "STRUCTURED_CONTRACT_P07",
    "finding_type": FINDING,
    "artifact": "Module.bsl",
    "candidate_sha256": "a" * 64,
    "report_id": "report:test",
    "report_output_sha256": "b" * 64,
    "finding_sha256": "c" * 64,
    "proof_policy": policy,
}
errors_probe = []
pending_probe = []
_validate_machine_findings(
    [{**expected_row, "status": "EVIDENCE_REQUIRED", "reason": "", "evidence": []}],
    {"MF:test": expected_row},
    rules,
    errors_probe,
    pending_probe,
    {},
    [],
    {},
    {},
    "R1_CONTRACT",
)
record(
    "unresolved_machine_finding_blocks_release",
    any(row.get("type") == "MACHINE_FINDING_BLOCKING_OR_UNRESOLVED" for row in errors_probe),
    {"errors": errors_probe},
)

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
