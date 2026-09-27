#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from analyze_changeset_architecture import analyze as analyze_changeset_architecture
from analyze_onec_bsl import analyze as analyze_onec_bsl
from analyze_onec_xml import analyze as analyze_onec_xml
from build_review_plan import build_plan, compact_summary

EPF_ROOT = ROOT / "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE"
ROOT_XML = EPF_ROOT / "ProjectSnapshotCollector.xml"
FORM_META = EPF_ROOT / "ProjectSnapshotCollector/Forms/MainForm.xml"
FORM_XML = EPF_ROOT / "ProjectSnapshotCollector/Forms/MainForm/Ext/Form.xml"
FORM_MODULE = EPF_ROOT / "ProjectSnapshotCollector/Forms/MainForm/Ext/Form/Module.bsl"
OBJECT_MODULE = EPF_ROOT / "ProjectSnapshotCollector/Ext/ObjectModule.bsl"
BUILD_SCRIPT = ROOT / "COLLECTOR/ONEC_RUNTIME/build_epf.ps1"

MD = {"m": "http://v8.1c.ru/8.3/MDClasses", "xr": "http://v8.1c.ru/8.3/xcf/readable"}
LF = {"f": "http://v8.1c.ru/8.3/xcf/logform", "v8": "http://v8.1c.ru/8.1/data/core"}

FORBIDDEN_COMMON = [
    r"\bНовый\s+Запрос\b",
    r"\bНачатьТранзакцию\s*\(",
    r"\bЗафиксироватьТранзакцию\s*\(",
    r"\bОтменитьТранзакцию\s*\(",
    r"\.СоздатьЭлемент\s*\(",
    r"\.СоздатьДокумент\s*\(",
    r"\.СоздатьНаборЗаписей\s*\(",
    r"\bВыполнить\s*\(",
    r"\bВычислить\s*\(",
]

FORBIDDEN_DESIGNER_MUTATIONS = [
    "/LoadConfigFromFiles",
    "/LoadCfg",
    "/UpdateDBCfg",
    "/RestoreIB",
    "/DumpIB",
]

# 1C parser rejects a method call directly on a freshly constructed object
# inside an Если expression, for example:
#     Если Новый Файл(Имя).Существует() Тогда
# The constructed object must first be assigned to a variable.
CONSTRUCTOR_METHOD_IN_IF = re.compile(
    r"^\s*Если\b.*\b(?:Не\s+)?Новый\s+[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*"
    r"\s*\([^\n;]*\)\s*\.",
    re.IGNORECASE,
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def run_self_hosting_gate(routing_inputs: list[Path], bsl_paths: list[Path], xml_root: Path | None = None) -> dict:
    blockers: list[dict] = []
    warnings: list[dict] = []

    try:
        plan = build_plan(routing_inputs, analysis_only=True)
    except Exception as exc:
        return {
            "result": "FAIL",
            "blockers": [{"type": "SELF_HOST_REVIEW_PLAN_FAILED", "error": str(exc)}],
            "warnings": [],
            "proof_boundary": {
                "platform_bsl_compile": "RUNTIME_PENDING",
                "epf_build_open": "RUNTIME_PENDING",
                "runtime_behavior": "RUNTIME_PENDING",
            },
        }

    surface = (plan.get("routing") or {}).get("surface")
    if surface not in {"ONEC_ONLY", "CROSS_SYSTEM"}:
        blockers.append({"type": "SELF_HOST_SOURCE_NOT_ROUTED_AS_ONEC", "surface": surface})

    bsl_reports = []
    for path in bsl_paths:
        try:
            report = analyze_onec_bsl(path)
        except Exception as exc:
            blockers.append({"type": "SELF_HOST_BSL_ANALYZER_FAILED", "path": str(path), "error": str(exc)})
            continue
        findings = report.get("findings", [])
        high = [row for row in findings if row.get("severity") == "HIGH"]
        review = [row for row in findings if row.get("severity") != "HIGH"]
        for row in high:
            blockers.append({"type": "SELF_HOST_BSL_HIGH_FINDING", "path": str(path), "finding": row})
        if review:
            warnings.append({"type": "SELF_HOST_BSL_REVIEW_FINDINGS", "path": str(path), "findings": review})
        bsl_reports.append({
            "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "sha256": report.get("sha256"),
            "summary": report.get("summary", {}),
            "high_findings": len(high),
            "review_findings": len(review),
        })

    xml_report = None
    if xml_root is not None:
        try:
            xml_report = analyze_onec_xml(xml_root)
        except Exception as exc:
            blockers.append({"type": "SELF_HOST_XML_ANALYZER_FAILED", "path": str(xml_root), "error": str(exc)})
        else:
            high = [row for row in xml_report.get("findings", []) if row.get("severity") == "HIGH"]
            review = [row for row in xml_report.get("findings", []) if row.get("severity") != "HIGH"]
            for row in high:
                blockers.append({"type": "SELF_HOST_XML_HIGH_FINDING", "path": str(xml_root), "finding": row})
            if review:
                warnings.append({"type": "SELF_HOST_XML_REVIEW_FINDINGS", "path": str(xml_root), "findings": review})

    changeset_report = None
    if len(bsl_paths) > 1:
        try:
            changeset_report = analyze_changeset_architecture(bsl_paths)
        except Exception as exc:
            blockers.append({"type": "SELF_HOST_CHANGESET_ANALYZER_FAILED", "error": str(exc)})
        else:
            if changeset_report.get("analysis_coverage") != "COMPLETE_FOR_SUPPLIED_CHANGESET":
                blockers.append({"type": "SELF_HOST_CHANGESET_COVERAGE_INCOMPLETE", "details": changeset_report})
            elif changeset_report.get("findings"):
                warnings.append({
                    "type": "SELF_HOST_CHANGESET_REVIEW_FINDINGS",
                    "findings": changeset_report.get("findings"),
                })

    gate_passed = not blockers
    return {
        "result": "PASS" if gate_passed else "FAIL",
        "readiness": "STATIC_SELF_HOST_PASS_RUNTIME_PENDING" if gate_passed else "SELF_HOST_BLOCKED",
        "review_plan": compact_summary(plan),
        "bsl_analysis": bsl_reports,
        "xml_analysis": {
            "result": xml_report.get("result"),
            "files": xml_report.get("files"),
            "artifact_kinds": xml_report.get("artifact_kinds"),
            "summary": xml_report.get("summary"),
        } if xml_report is not None else None,
        "changeset_analysis": changeset_report,
        "blockers": blockers,
        "warnings": warnings,
        "proof_boundary": {
            "routing": "STATIC_PROVEN",
            "deterministic_source_analysis": "STATIC_PROVEN" if gate_passed else "FAILED_OR_UNRESOLVED",
            "platform_bsl_compile": "RUNTIME_PENDING",
            "epf_build_open": "RUNTIME_PENDING",
            "runtime_behavior": "RUNTIME_PENDING",
            "rule": (
                "Self-hosting PASS proves deterministic analysis of maintained source only. "
                "It does not upgrade missing 1C platform compilation, EPF build/open, or runtime execution evidence to PASS."
            ),
        },
    }


def main() -> int:
    errors: list[str] = []

    for path in [ROOT_XML, FORM_META, FORM_XML, FORM_MODULE, OBJECT_MODULE, BUILD_SCRIPT]:
        if not path.exists():
            errors.append(f"missing_file:{path.relative_to(ROOT)}")

    if errors:
        print("\n".join(errors))
        return 2

    try:
        root_tree = ET.parse(ROOT_XML)
        form_meta_tree = ET.parse(FORM_META)
        form_tree = ET.parse(FORM_XML)
    except ET.ParseError as exc:
        print(f"xml_parse_error:{exc}")
        return 2

    processor = root_tree.getroot().find("m:ExternalDataProcessor", MD)
    if processor is None:
        errors.append("root_external_data_processor_missing")
    else:
        name = processor.findtext("m:Properties/m:Name", namespaces=MD)
        default_form = processor.findtext("m:Properties/m:DefaultForm", namespaces=MD)
        forms = [node.text for node in processor.findall("m:ChildObjects/m:Form", MD)]
        if name != "ProjectSnapshotCollector":
            errors.append(f"processor_name:{name}")
        expected_form = "ExternalDataProcessor.ProjectSnapshotCollector.Form.MainForm"
        if default_form != expected_form:
            errors.append(f"default_form:{default_form}")
        if forms != ["MainForm"]:
            errors.append(f"child_forms:{forms}")

    form_meta = form_meta_tree.getroot().find("m:Form", MD)
    if form_meta is None:
        errors.append("form_metadata_missing")
    else:
        if form_meta.findtext("m:Properties/m:Name", namespaces=MD) != "MainForm":
            errors.append("form_metadata_name")
        if form_meta.findtext("m:Properties/m:FormType", namespaces=MD) != "Managed":
            errors.append("form_type_not_managed")

    form_root = form_tree.getroot()
    attrs = {node.attrib.get("name") for node in form_root.findall("f:Attributes/f:Attribute", LF)}
    for required in {"Объект", "ПланJSON", "РезультатJSON", "Статус"}:
        if required not in attrs:
            errors.append(f"form_attribute_missing:{required}")

    commands = {node.attrib.get("name") for node in form_root.findall("f:Commands/f:Command", LF)}
    for required in {"ЗагрузитьПлан", "Собрать", "СохранитьРезультат", "Очистить"}:
        if required not in commands:
            errors.append(f"form_command_missing:{required}")

    data_paths = {node.text for node in form_root.findall(".//f:DataPath", LF)}
    for required in {"ПланJSON", "РезультатJSON", "Статус"}:
        if required not in data_paths:
            errors.append(f"form_datapath_missing:{required}")

    form_xml = text(FORM_XML)
    if "Собрать пакет" not in form_xml:
        errors.append("package_action_not_primary_in_form")

    object_module = text(OBJECT_MODULE)
    form_module = text(FORM_MODULE)

    for bsl_path in sorted(EPF_ROOT.rglob("*.bsl")):
        for line_number, line in enumerate(text(bsl_path).splitlines(), start=1):
            if CONSTRUCTOR_METHOD_IN_IF.search(line):
                errors.append(
                    "constructor_method_call_in_if:"
                    f"{bsl_path.relative_to(ROOT)}:{line_number}:{line.strip()}"
                )

    for export_name in ["СобратьПоПлану", "СформироватьJSONРезультата"]:
        marker = re.compile(rf"\bФункция\s+{re.escape(export_name)}\s*\([^)]*\)\s+Экспорт", re.IGNORECASE)
        if not marker.search(object_module):
            errors.append(f"embedded_export_missing:{export_name}")

    for anchor in [
        '"METADATA_PROPERTIES"',
        '"SCHEDULED_JOBS"',
        '"runtime_proven", Ложь',
        '"SKIPPED_OTHER_BACKEND"',
    ]:
        if anchor not in object_module:
            errors.append(f"embedded_semantic_anchor_missing:{anchor}")

    for path, source in [(OBJECT_MODULE, object_module), (FORM_MODULE, form_module)]:
        for pattern in FORBIDDEN_COMMON:
            if re.search(pattern, source, re.IGNORECASE):
                errors.append(f"read_only_violation:{path.relative_to(ROOT)}:{pattern}")

    if re.search(r"\.Записать\s*\(", object_module, re.IGNORECASE):
        errors.append("read_only_violation:object_module_write")

    required_package_anchors = [
        "СформироватьProjectSnapshotПакет",
        "ВыполнитьSourceExport",
        "/DumpConfigToFiles",
        "-listFile ",
        "-Format Hierarchical",
        "source-objects.txt",
        "ПолучитьИмяОбъектаДляDesigner",
        'Возврат "ОбщийМодуль." + Имя',
        'Возврат "Документ." + Имя',
        'Возврат "Справочник." + Имя',
        "СтрокаСоединенияИнформационнойБазы()",
        "КаталогПрограммы() + \"1cv8.exe\"",
        "ЗапуститьПриложение(",
        "Новый ЗаписьZipФайла",
        "РежимОбработкиПодкаталоговZIP.ОбрабатыватьРекурсивно",
        'ВРег(ЭлементКонтракта.category) <> "MODULE_SOURCE"',
        '"PROJECT_SNAPSHOT_EVIDENCE"',
        '"SOURCE_EXPORT"',
        '"MODULE_FILE"',
        '"REQUESTED_SOURCE_OWNERS_READ_ONLY"',
        '"REQUESTED_MODULE_FILES_ONLY"',
        '"source_file"',
        '"config_dump_info_present"',
        '"expected_module_paths"',
        '"found_module_paths"',
        '"diagnostics", SourceКонтракт.Диагностика',
        "ProjectSnapshotPackage_",
        "ProjectSnapshotDesigner_",
        "ОчиститьВременныйКаталог(КаталогВыгрузкиDesigner)",
        "ОчиститьВременныйКаталог(РабочийКаталог)",
        "УдалитьФайлы(ИмяКаталога);",
    ]
    for anchor in required_package_anchors:
        if anchor not in form_module:
            errors.append(f"package_contract_missing:{anchor}")

    if 'Возврат "ERROR_NO_SOURCE_DUMP"' in form_module:
        errors.append("config_dump_info_must_not_block_concrete_module_file_evidence")
    if "РежимОбработкиПодкаталоговZIP.Обрабатывать)" in form_module:
        errors.append("invalid_zip_subdirectory_enum_regression")
    if "УдалитьФайлы(ИмяКаталога, Истина)" in form_module:
        errors.append("cleanup_must_not_pass_boolean_as_delete_files_mask")
    if '"exported_objects", SourceКонтракт.Объекты' in form_module:
        errors.append("manifest_must_not_treat_requested_objects_as_exported_objects")
    if "ProjectSnapshotDesigner_" not in form_module or "ProjectSnapshotPackage_" not in form_module:
        errors.append("designer_dump_must_be_physically_separate_from_package_root")
    if "РабочийКаталог + \"\\designer-source\"" in form_module:
        errors.append("designer_dump_must_never_live_under_package_root")

    for forbidden in FORBIDDEN_DESIGNER_MUTATIONS:
        if forbidden.lower() in form_module.lower():
            errors.append(f"designer_mutation_command_forbidden:{forbidden}")

    for handler in [
        "КомандаЗагрузитьПлан",
        "КомандаСобрать",
        "КомандаСохранитьРезультат",
        "КомандаОчистить",
        "СобратьНаСервере",
        "СформироватьProjectSnapshotПакет",
        "ВыполнитьSourceExport",
        "ПолучитьИмяОбъектаДляDesigner",
        "ПолучитьОтносительныйПутьМодуля",
        "ОчиститьВременныйКаталог",
    ]:
        if handler not in form_module:
            errors.append(f"form_handler_missing:{handler}")

    build = text(BUILD_SCRIPT)
    for anchor in [
        "/LoadExternalDataProcessorOrReportFromFiles",
        "ProjectSnapshotCollector.epf",
        "Start-Process",
        "-Wait",
        "-PassThru",
        "Specify -FileBase or -ServerBase",
    ]:
        if anchor not in build:
            errors.append(f"build_contract_missing:{anchor}")
    if "& $OneCExe @arguments" in build:
        errors.append("build_must_wait_for_designer_process")

    operational_bsl = sorted((ROOT / "COLLECTOR").rglob("*.bsl"))
    self_host = run_self_hosting_gate(
        [EPF_ROOT],
        operational_bsl,
        EPF_ROOT,
    )
    if self_host.get("result") != "PASS":
        for blocker in self_host.get("blockers", []):
            errors.append(f"self_host_blocker:{blocker}")

    # Negative control: the gate must really reject a HIGH finding from the
    # skill's own BSL analyzer instead of merely reporting that it ran.
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "BadModule.bsl"
        bad.write_text(
            "Процедура ПлохойПример()\n"
            "    Для Каждого Элемент Из Элементы Цикл\n"
            "        Результат = Запрос.Выполнить();\n"
            "    КонецЦикла;\n"
            "КонецПроцедуры\n",
            encoding="utf-8",
        )
        negative = run_self_hosting_gate([bad], [bad])
        negative_types = {row.get("type") for row in negative.get("blockers", [])}
        if negative.get("result") != "FAIL" or "SELF_HOST_BSL_HIGH_FINDING" not in negative_types:
            errors.append("self_host_negative_control_failed")

    result = "PASS" if not errors else "FAIL"
    print({
        "result": result,
        "errors": errors,
        "self_hosting": self_host,
        "proof_boundary": {
            "platform_bsl_compile": "RUNTIME_PENDING",
            "epf_build_open": "RUNTIME_PENDING",
            "runtime_behavior": "RUNTIME_PENDING",
        },
    })
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
