#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from analyze_onec_bsl import analyze
from rule_registry import load_registry, proof_policy_for, rule_map, regex_hits
from build_validation_ledger import machine_finding_mapping
from release_gate_core import (
    _validate_machine_findings,
    SOURCE_PROVENANCE_VERIFIER_ID,
    SOURCE_PROVENANCE_VERSION,
)

FINDING = "STRUCTURE_PROPERTY_OUT_PARAM_UNSAFE_BOOLEAN"
REVIEW_FINDING = "STRUCTURE_PROPERTY_RECEIVER_TYPE_REVIEW"
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
    return (
        [row for row in report.get("findings", []) if row.get("type") == FINDING],
        [row for row in report.get("findings", []) if row.get("type") == REVIEW_FINDING],
        report,
    )


negative = {
    "basic_bare_boolean": """
        Процедура Тест()
            Параметры = Новый Структура;
            Параметры.Свойство("Признак", Флаг);
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "negated_bare_boolean": """
        Процедура Тест()
            Параметры = Новый Структура;
            Параметры.Свойство("Признак", Флаг);
            Если НЕ Флаг Тогда
                Сообщить("Нет");
            КонецЕсли;
        КонецПроцедуры
    """,
    "undefined_initialized_then_overwritten": """
        Процедура Тест()
            Параметры = Новый Структура;
            Флаг = Неопределено;
            Параметры.Свойство("Признак", Флаг);
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "presence_does_not_prove_value_domain": """
        Процедура Тест()
            Параметры = Новый Структура;
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
            Параметры = Новый Структура;
            Параметры.Свойство("Признак", Флаг);
            ЛокальныйФлаг = Флаг;
            Если ЛокальныйФлаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "incoming_structure_exact_type_guard": """
        Процедура Тест(Параметры)
            Если ТипЗнч(Параметры) = Тип("Структура") Тогда
                Параметры.Свойство("Признак", Флаг);
                Если Флаг Тогда
                    Сообщить("Да");
                КонецЕсли;
            КонецЕсли;
        КонецПроцедуры
    """,
}

positive = {
    "presence_only": """
        Процедура Тест()
            Параметры = Новый Структура;
            Если Параметры.Свойство("Ключ") Тогда
                Сообщить("Есть");
            КонецЕсли;
        КонецПроцедуры
    """,
    "explicit_boolean_normalization": """
        Процедура Тест()
            Параметры = Новый Структура;
            Параметры.Свойство("Признак", Флаг);
            Флаг = ?(ТипЗнч(Флаг) = Тип("Булево"), Флаг, Ложь);
            Если Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецПроцедуры
    """,
    "simple_boolean_type_guard": """
        Процедура Тест()
            Параметры = Новый Структура;
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
            Параметры = Новый Структура;
            Если Параметры.Свойство("Признак", Значение) И ТипЗнч(Значение) = Тип("Булево") Тогда
                Если Значение Тогда
                    Сообщить("Да");
                КонецЕсли;
            КонецЕсли;
        КонецПроцедуры
    """,
    "unrelated_out_use": """
        Процедура Тест()
            Параметры = Новый Структура;
            Параметры.Свойство("Код", Значение);
            Сообщить(Строка(Значение));
        КонецПроцедуры
    """,
}

for name, source in negative.items():
    rows, review_rows, report = finding_rows(source)
    record(
        "negative:" + name,
        len(rows) == 1 and len(review_rows) == 0,
        {"findings": rows, "review_findings": review_rows, "summary": report.get("summary")},
    )

for name, source in positive.items():
    rows, review_rows, report = finding_rows(source)
    record(
        "positive:" + name,
        len(rows) == 0,
        {"findings": rows, "review_findings": review_rows, "summary": report.get("summary")},
    )

unrelated_source = """
    Процедура Тест(Сервис)
        Сервис.Свойство("Признак", Флаг);
        Если Флаг Тогда
            Сообщить("Да");
        КонецЕсли;
    КонецПроцедуры
"""
unrelated_rows, unrelated_review, unrelated_report = finding_rows(unrelated_source)
record(
    "unrelated_receiver_is_review_not_structure_block",
    len(unrelated_rows) == 0
    and len(unrelated_review) == 1
    and unrelated_review[0].get("receiver_proof") == "UNRESOLVED",
    {
        "findings": unrelated_rows,
        "review_findings": unrelated_review,
        "summary": unrelated_report.get("summary"),
    },
)

boolean_guard_else_source = """
    Процедура Тест()
        Параметры = Новый Структура;
        Параметры.Свойство("Признак", Флаг);
        Если ТипЗнч(Флаг) = Тип("Булево") Тогда
            Сообщить("Булево");
        Иначе
            Если Флаг Тогда
                Сообщить("Опасно");
            КонецЕсли;
        КонецЕсли;
    КонецПроцедуры
"""
rows, review_rows, report = finding_rows(boolean_guard_else_source)
record(
    "boolean_guard_does_not_leak_into_else",
    len(rows) == 1 and len(review_rows) == 0,
    {"findings": rows, "review_findings": review_rows, "summary": report.get("summary")},
)

structure_guard_else_source = """
    Процедура Тест(Получатель)
        Если ТипЗнч(Получатель) = Тип("Структура") Тогда
            Сообщить("Структура");
        Иначе
            Получатель.Свойство("Признак", Флаг);
            Если Флаг Тогда
                Сообщить("Неизвестный API");
            КонецЕсли;
        КонецЕсли;
    КонецПроцедуры
"""
rows, review_rows, report = finding_rows(structure_guard_else_source)
record(
    "structure_guard_does_not_leak_into_else",
    len(rows) == 0
    and len(review_rows) == 1
    and review_rows[0].get("receiver_proof") == "UNRESOLVED",
    {"findings": rows, "review_findings": review_rows, "summary": report.get("summary")},
)

boolean_guard_elseif_source = """
    Процедура Тест()
        Параметры = Новый Структура;
        Параметры.Свойство("Признак", Флаг);
        Если ТипЗнч(Флаг) = Тип("Булево") Тогда
            Сообщить("Булево");
        ИначеЕсли Истина Тогда
            Если Флаг Тогда
                Сообщить("Опасно");
            КонецЕсли;
        КонецЕсли;
    КонецПроцедуры
"""
rows, review_rows, report = finding_rows(boolean_guard_elseif_source)
record(
    "boolean_guard_does_not_leak_into_elseif",
    len(rows) == 1 and len(review_rows) == 0,
    {"findings": rows, "review_findings": review_rows, "summary": report.get("summary")},
)

structure_guard_elseif_source = """
    Процедура Тест(Получатель)
        Если ТипЗнч(Получатель) = Тип("Структура") Тогда
            Сообщить("Структура");
        ИначеЕсли Истина Тогда
            Получатель.Свойство("Признак", Флаг);
            Если Флаг Тогда
                Сообщить("Неизвестный API");
            КонецЕсли;
        КонецЕсли;
    КонецПроцедуры
"""
rows, review_rows, report = finding_rows(structure_guard_elseif_source)
record(
    "structure_guard_does_not_leak_into_elseif",
    len(rows) == 0
    and len(review_rows) == 1
    and review_rows[0].get("receiver_proof") == "UNRESOLVED",
    {"findings": rows, "review_findings": review_rows, "summary": report.get("summary")},
)

registry = load_registry()
rules = rule_map(registry)
structured = rules["STRUCTURED_CONTRACT"]
mapping = machine_finding_mapping(registry)
owner = mapping.get(FINDING)
record(
    "machine_owner_mapping",
    bool(owner and owner[0] == "STRUCTURED_CONTRACT" and owner[1] == "STRUCTURED_CONTRACT_P07"),
    {"owner": owner[:2] if owner else None},
)

incoming_source = textwrap.dedent(negative["incoming_structure_exact_type_guard"]).strip()
record(
    "incoming_structure_type_guard_routes_owner",
    bool(regex_hits(structured, incoming_source)),
    {"hits": regex_hits(structured, incoming_source)},
)
record(
    "unrelated_method_name_does_not_activate_structure_owner",
    not regex_hits(structured, textwrap.dedent(unrelated_source).strip()),
    {"hits": regex_hits(structured, textwrap.dedent(unrelated_source).strip())},
)

policy = proof_policy_for(structured, registry)
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

with tempfile.TemporaryDirectory() as td:
    contract_path = Path(td) / "ExactBooleanContract.bsl"
    contract_bytes = (
        "// Exact source/API contract for this candidate: property Признак is Boolean.\n"
        "// This evidence closes only the exact machine-finding claim; it is not a generic suppression.\n"
    ).encode("utf-8")
    contract_path.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    plan = {
        "candidate_artifacts": [
            {
                "logical_path": "ExactBooleanContract.bsl",
                "origin": str(contract_path),
                "sha256": contract_sha,
            }
        ]
    }
    exact_source_evidence = {
        "kind": "SOURCE_REQUIRED",
        "ref": str(contract_path),
        "claim_id": "MF:test",
        "source_provenance": {
            "type": "CURRENT_CORPUS",
            "verifier": SOURCE_PROVENANCE_VERIFIER_ID,
            "version": SOURCE_PROVENANCE_VERSION,
            "source_sha256": contract_sha,
        },
    }
    resolved_errors = []
    resolved_pending = []
    _validate_machine_findings(
        [
            {
                **expected_row,
                "status": "PASS",
                "reason": "Exact current source/API contract proves this out value is Boolean.",
                "evidence": [exact_source_evidence],
            }
        ],
        {"MF:test": expected_row},
        rules,
        resolved_errors,
        resolved_pending,
        {},
        [],
        plan,
        {},
        "R1_CONTRACT",
    )
record(
    "exact_boolean_source_contract_resolves_finding",
    not resolved_errors and not resolved_pending,
    {"errors": resolved_errors, "pending": resolved_pending, "proof_policy": policy},
)

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
