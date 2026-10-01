#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import textwrap

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"TOOLS"))

from analyze_onec_bsl import analyze
from rule_registry import load_registry, proof_policy_for, rule_map
from build_validation_ledger import machine_finding_mapping
from release_gate_core import _validate_machine_findings, SOURCE_PROVENANCE_VERIFIER_ID, SOURCE_PROVENANCE_VERSION

TRI="VALUE_TABLE_TRI_STATE_BOOLEAN"
REWRITE="STANDARD_FILL_DESTRUCTIVE_REWRITE_REVIEW"
errors=[]
results={}

def record(case,ok,details):
    results[case]={"pass":bool(ok),"details":details}
    if not ok:
        errors.append({"case":case,"details":details})

def run(source):
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"Module.bsl"
        p.write_text(textwrap.dedent(source).strip()+"\n",encoding="utf-8")
        return analyze(p)

negative={
"untyped_uninitialized":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Колонки.Добавить("Флаг");
    СтрокаНовая = Таблица.Добавить();
    Для Каждого Строка Из Таблица Цикл
        Если Строка.Флаг Тогда
            Сообщить("Да");
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры
""",
"typed_but_uninitialized":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Колонки.Добавить("Флаг", Новый ОписаниеТипов("Булево"));
    СтрокаНовая = Таблица.Добавить();
    Для Каждого Строка Из Таблица Цикл
        Если НЕ Строка.Флаг Тогда
            Сообщить("Нет");
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры
"""
}
positive={
"typed_initialized":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Колонки.Добавить("Флаг", Новый ОписаниеТипов("Булево"));
    СтрокаНовая = Таблица.Добавить();
    СтрокаНовая.Флаг = Ложь;
    Для Каждого Строка Из Таблица Цикл
        Если Строка.Флаг Тогда
            Сообщить("Да");
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры
""",
"normalized_in_loop":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Колонки.Добавить("Флаг");
    СтрокаНовая = Таблица.Добавить();
    Для Каждого Строка Из Таблица Цикл
        Строка.Флаг = ?(ТипЗнч(Строка.Флаг) = Тип("Булево"), Строка.Флаг, Ложь);
        Если Строка.Флаг Тогда
            Сообщить("Да");
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры
""",
"explicit_comparison":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Колонки.Добавить("Флаг");
    СтрокаНовая = Таблица.Добавить();
    Для Каждого Строка Из Таблица Цикл
        Если Строка.Флаг = Истина Тогда
            Сообщить("Да");
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры
""",
"type_guard":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Колонки.Добавить("Флаг");
    СтрокаНовая = Таблица.Добавить();
    Для Каждого Строка Из Таблица Цикл
        Если ТипЗнч(Строка.Флаг) = Тип("Булево") Тогда
            Если Строка.Флаг Тогда
                Сообщить("Да");
            КонецЕсли;
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры
""",
"unrelated_object_property":"""
Процедура Тест(Объект)
    Если Объект.Флаг Тогда
        Сообщить("Не ValueTable");
    КонецЕсли;
КонецПроцедуры
"""
}

for name,src in negative.items():
    report=run(src)
    hits=[x for x in report.get("findings",[]) if x.get("type")==TRI]
    record("tri_negative:"+name,len(hits)==1,{"hits":hits})
for name,src in positive.items():
    report=run(src)
    hits=[x for x in report.get("findings",[]) if x.get("type")==TRI]
    record("tri_positive:"+name,len(hits)==0,{"hits":hits})

report=run("""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    СтандартноеЗаполнение.ЗаполнитьТаблицу(Таблица);
    Таблица.Очистить();
КонецПроцедуры
""")
hits=[x for x in report.get("findings",[]) if x.get("type")==REWRITE]
record("rewrite_review:standard_fill_then_clear",len(hits)==1 and hits[0].get("severity")=="REVIEW",{"hits":hits})

for name,src in {
"generic_clear":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    Таблица.Очистить();
КонецПроцедуры
""",
"custom_fill":"""
Процедура Тест()
    Таблица = Новый ТаблицаЗначений;
    МойСервис.ЗаполнитьТаблицу(Таблица);
    Таблица.Очистить();
КонецПроцедуры
"""
}.items():
    report=run(src)
    hits=[x for x in report.get("findings",[]) if x.get("type")==REWRITE]
    record("rewrite_review:"+name,not hits,{"hits":hits})

registry=load_registry()
rules=rule_map(registry)
mapping=machine_finding_mapping(registry)
owner=mapping.get(TRI)
record("tri_machine_owner",bool(owner and owner[0]=="STRUCTURED_CONTRACT" and owner[1]=="STRUCTURED_CONTRACT_P08"),{"owner":owner[:2] if owner else None})

policy=proof_policy_for(rules["STRUCTURED_CONTRACT"],registry)
expected={
    "id":"MF:tri","claim_id":"MF:tri","rule_id":"STRUCTURED_CONTRACT","check_id":"STRUCTURED_CONTRACT_P08",
    "finding_type":TRI,"artifact":"Module.bsl","candidate_sha256":"a"*64,"report_id":"report:tri",
    "report_output_sha256":"b"*64,"finding_sha256":"c"*64,"proof_policy":policy
}
blocked_errors=[]
blocked_pending=[]
_validate_machine_findings(
    [{**expected,"status":"EVIDENCE_REQUIRED","reason":"","evidence":[]}],
    {"MF:tri":expected},rules,blocked_errors,blocked_pending,{},[],{},{}, "R1_CONTRACT"
)
record("tri_unresolved_blocks_release",any(x.get("type")=="MACHINE_FINDING_BLOCKING_OR_UNRESOLVED" for x in blocked_errors),{"errors":blocked_errors})

with tempfile.TemporaryDirectory() as td:
    path=Path(td)/"BooleanContract.bsl"
    raw=b"// exact current source contract: target ValueTable field is Boolean\n"
    path.write_bytes(raw)
    sha=hashlib.sha256(raw).hexdigest()
    plan={"candidate_artifacts":[{"logical_path":"BooleanContract.bsl","origin":str(path),"sha256":sha}]}
    evidence={"kind":"SOURCE_REQUIRED","ref":str(path),"claim_id":"MF:tri","source_provenance":{"type":"CURRENT_CORPUS","verifier":SOURCE_PROVENANCE_VERIFIER_ID,"version":SOURCE_PROVENANCE_VERSION,"source_sha256":sha}}
    ok_errors=[]
    ok_pending=[]
    _validate_machine_findings(
        [{**expected,"status":"PASS","reason":"Exact current source contract proves Boolean domain for this bounded value.","evidence":[evidence]}],
        {"MF:tri":expected},rules,ok_errors,ok_pending,{},[],plan,{}, "R1_CONTRACT"
    )
record("tri_exact_source_contract_resolves_same_finding",not ok_errors and not ok_pending,{"errors":ok_errors,"pending":ok_pending})

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results,"case_count":len(results)}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
