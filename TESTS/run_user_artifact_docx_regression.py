#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

import docx
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from render_user_artifact_docx import ARTIFACTS, render_artifact

errors=[]

def require(ok, name, details=None):
    if not ok:
        errors.append({"case":name,"details":details})

require(getattr(docx,"__version__","")=="1.2.0","dependency_pinned",getattr(docx,"__version__",None))

requirements={
 "project":"Проект А","task":"ТЗ-42","need_problem":"Исключить повторную фиксацию.",
 "target_outcome":"Повтор безопасен.","scope_in":["Приёмка"],"scope_out":["Продажи"],
 "functional_rules":["Одна операция — один подтверждённый факт."],
 "acceptance":[{"case":"Повтор","preconditions":"Факт есть","action":"Повторить","expected":"Дубликата нет","oracle":"Ровно один факт"}],
 "proof_boundary":"Точный runtime не наблюдался.","requirements_status":"REQUIREMENTS_READY"
}
marker="// ИвановИИ, ПервыйБит, 28.09.2026, ТЗ-42"
manual={
 "project":"Проект А","task":"ТЗ-42","target_identity":"Расширение Приемка baseline abc",
 "purpose":"Внедрить защиту от повторной фиксации без изменения сторонней логики.",
 "implementation_boundaries":["Изменяется только расширение Приемка.","Основная конфигурация не изменяется."],
 "do_not_change":["Не переносить изменение в основную конфигурацию."],
 "preconditions":["Выполнить резервную копию."],
 "migration":["Заполнить существующие ключи при необходимости."],
 "deployment_sequence":["Открыть расширение Приемка.","Изменить общий модуль.","Выполнить статическую проверку."],
 "static_verification":["Проверить синтаксис модуля."],
 "verification_matrix":[{"action":"Повторить уже зафиксированную операцию.","expected":"Второй факт не создаётся."}],
 "runtime_verification":["Выполнить контрольный повтор операции."],
 "final_control_checklist":["AUTHOR_MARKER сохранён.","Изменён только разрешённый объект."],
 "changed_object_map":[{"object":"ОбщийМодуль.ИнтеграцияCleverenceСервер","change":"Добавлена защита от повторной фиксации."}],
 "blocking_choices":["Нет нерешённых выборов."],
 "created_objects":[{"object":"РегистрСведений.ОбработанныеОперации","properties":[{"name":"Периодичность","value":"Непериодический"}],"rationale":"Хранить бизнес-ключ.","standard_rule":"Проектное правило IDEMPOTENCY"}],
 "modified_objects":[{"object":"ОбщийМодуль.ИнтеграцияCleverenceСервер","properties":[{"name":"Сервер","before":"Ложь","after":"Истина"}],"rationale":"Выполнение на сервере.","standard_rule":"Клиент-серверный контракт"}],
 "code_changes":[{"object":"ОбщийМодуль.ИнтеграцияCleverenceСервер","member":"Процедура ОбработатьРезультатПриемки","anchor":"перед фиксацией результата","before":"Контекст();","after":"Контекст();\n"+marker+"\nПроверитьПовтор();","rationale":"Идемпотентность.","explanation":"Проверка должна выполняться до записи результата.","standard_rule":"Проектное правило IDEMPOTENCY"}],
 "proof_boundary":"Перенос в целевой базе не наблюдался."
}
notes={
 "tz_number":"ТЗ-42","project":"Проект А","task":"Идемпотентность",
 "platform_version":"8.3.27.1234","configuration_name_version":"УТ 11.5.20",
 "rows":[{"container":"Расширение Приемка","configuration_object":"ОбщийМодуль.ИнтеграцияCleverenceСервер","procedure_function":"ОбработатьРезультатПриемки","status":"Изменен","description":"Добавлена защита от повторной фиксации.","standard_rule":"Проектное правило IDEMPOTENCY"}]
}
line={
 "explicit_user_request":True,"tz_number":"ТЗ-42","project":"Проект А","task":"Идемпотентность",
 "purpose":"Объяснить материал изменения.",
 "objects":[{"object":"ОбщийМодуль.ИнтеграцияCleverenceСервер","changes":[{"member":"ОбработатьРезультатПриемки","status":"Изменен","task_relation":"ТЗ-42 п.1.2","location":"перед фиксацией","reason":"Исключить дубль.","what_changed":"Добавлена проверка.","behavior_impact":"Повтор не создаёт второй факт.","diff":" Контекст();\n+ПроверитьПовтор();\n Записать();"}]}]
}

with tempfile.TemporaryDirectory() as td:
    out=Path(td)
    paths={
      "requirements":render_artifact("requirements",requirements,out),
      "manual_transfer":render_artifact("manual_transfer",manual,out),
      "implementation_notes":render_artifact("implementation_notes",notes,out),
      "line_by_line":render_artifact("line_by_line",line,out),
    }
    require({p.name for p in paths.values()}==set(ARTIFACTS.values()),"four_separate_default_filenames",[p.name for p in paths.values()])
    require(len(list(out.glob("*.docx")))==4,"no_accidental_combined_docx",list(map(str,out.glob("*.docx"))))

    req=Document(paths["requirements"])
    req_text="\n".join(p.text for p in req.paragraphs)
    require("Проект: Проект А" in req_text and "Задача: ТЗ-42" in req_text,"requirements_compact_metadata")
    require("Интеграционный контракт" not in req_text and "Допущения" not in req_text,"requirements_empty_conditionals_omitted",req_text)
    require("requirements_gate.py" not in req_text and "Инварианты готовности" not in req_text,"requirements_internal_invariants_not_rendered",req_text)

    man=Document(paths["manual_transfer"])
    headings=[p.text for p in man.paragraphs if p.style and p.style.name.startswith("Heading")]
    require(all(x in headings for x in ["Создаваемые объекты","Изменяемые объекты","Код"]),"manual_primary_headings",headings)
    require(headings.index("Создаваемые объекты")<headings.index("Изменяемые объекты")<headings.index("Код"),"manual_owner_order",headings)
    h1=[p.text for p in man.paragraphs if p.style and p.style.name=="Heading 1"]
    expected_h1=[
      "Назначение и границы",
      "Не изменять / не делать",
      "Создаваемые объекты",
      "Изменяемые объекты",
      "Код",
      "Предусловия",
      "Миграция / инициализация / одноразовые действия",
      "Порядок внедрения",
      "Статическая проверка после внедрения",
      "Матрица проверки",
      "Проверка выполнения",
      "Финальный статический контроль",
      "Карта изменённых объектов",
      "Нерешённые выборы / блокеры",
      "Граница доказанности",
    ]
    require(h1==expected_h1,"manual_full_owner_order_with_conditionals",h1)
    man_text="\n".join(p.text for p in man.paragraphs)
    require("STEP-001" not in man_text,"manual_not_step_first",man_text)
    require(marker in man_text,"author_marker_literal_preserved",man_text)
    table_text=["|".join(cell.text for cell in row.cells) for table in man.tables for row in table.rows]
    require(any("Свойство|Было|Стало" in row for row in table_text),"manual_before_after_properties",table_text)
    require(any("Действие / сценарий|Ожидаемый результат" in row for row in table_text),"manual_verification_matrix",table_text)
    require(any("Объект|Изменение" in row for row in table_text),"manual_changed_object_map",table_text)
    for token in ["Якорь / место изменения: перед фиксацией результата","Пояснение: Проверка должна выполняться до записи результата.","Основная конфигурация не изменяется.","Не переносить изменение в основную конфигурацию."]:
        require(token in man_text,"manual_quality_token:"+token,man_text)

    missing_closure=dict(manual)
    missing_closure.pop("deployment_sequence")
    try:
        render_artifact("manual_transfer",missing_closure,out)
        require(False,"manual_transfer_requires_execution_closure")
    except ValueError:
        pass

    impl=Document(paths["implementation_notes"])
    impl_text=[p.text for p in impl.paragraphs]
    labels=["Номер ТЗ: ","Проект: ","Задача: ","Версия платформы: ","Наименование и версия конфигурации: "]
    positions=[next((i for i,v in enumerate(impl_text) if v.startswith(label)),-1) for label in labels]
    require(positions==sorted(positions) and all(i>=0 for i in positions),"implementation_notes_header_order",positions)
    require(len(impl.tables)==1,"implementation_notes_one_table",len(impl.tables))
    header=[c.text for c in impl.tables[0].rows[0].cells]
    require(header==["Контейнер","ОбъектКонфигурации","Процедура/Функция","Статус","ОписаниеИзменений"],"implementation_notes_exact_columns",header)
    require("Стандарт/правило:" in impl.tables[0].rows[1].cells[4].text,"implementation_notes_rule_in_description")
    require(impl.sections[0].orientation==1,"implementation_notes_landscape",int(impl.sections[0].orientation))

    lbd=Document(paths["line_by_line"])
    ltext="\n".join(p.text for p in lbd.paragraphs)
    for token in ["Назначение документа","Правила чтения","Причина изменения","Что изменено","Влияние на поведение","+ПроверитьПовтор();"]:
        require(token in ltext,"line_by_line_token:"+token,ltext)

    denied=dict(line)
    denied["explicit_user_request"]=False
    try:
        render_artifact("line_by_line",denied,out)
        require(False,"line_by_line_requires_explicit_request")
    except ValueError:
        pass

    blocked=dict(requirements)
    blocked["requirements_status"]="REQUIREMENTS_BLOCKED"
    try:
        render_artifact("requirements",blocked,out)
        require(False,"blocked_requirements_requires_open_questions")
    except ValueError:
        pass

    bad=dict(requirements)
    bad["filename"]="Функциональная спецификация final.docx"
    try:
        render_artifact("requirements",bad,out)
        require(False,"pseudo_version_filename_rejected")
    except ValueError:
        pass

contract=json.loads((ROOT/"WORKFLOW/RESULT_DELIVERY_CONTRACT.json").read_text(encoding="utf-8"))
fmt=contract.get("user_artifact_format") or {}
require(fmt.get("default_container")=="DOCX" and fmt.get("separate_file_default") is True,"contract_separate_docx_default",fmt)
require(fmt.get("renderer")=="TOOLS/render_user_artifact_docx.py","contract_renderer_binding",fmt)
impl_contract=contract["profiles"]["IMPLEMENTATION_DELIVERY"]
require(impl_contract["implementation_notes"].get("filename_ru")=="Особенности реализации.docx","contract_mandatory_notes_filename")
require(impl_contract["line_by_line_justification"].get("trigger")=="EXPLICIT_USER_REQUEST_ONLY","contract_optional_line_by_line")
require(contract["profiles"]["REQUIREMENTS_ARTIFACT"]["artifact_output"].get("separate_file") is True,"requirements_separate_file")
require(impl_contract["manual_transfer_artifact_output"].get("separate_file") is True,"manual_separate_file")
require(impl_contract["manual_transfer_artifact_output"].get("required") is True,"manual_required_for_manual_mode")
require(impl_contract["manual_transfer_artifact_output"].get("chat_only_code_complete") is False,"manual_chat_only_incomplete")
require(impl_contract["implementation_notes"].get("required") is True and "deterministically applicable" in impl_contract["implementation_notes"].get("trigger_contract",""),"implementation_notes_deterministic_required")
require(impl_contract["delivery_mode_selection"].get("must_precede_final_artifact_construction") is True,"delivery_mode_before_artifact")

print(json.dumps({"result":"PASS" if not errors else "FAIL","errors":errors,"cases":29},ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
