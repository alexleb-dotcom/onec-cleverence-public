#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from final_docx_set import validate_final_docx_set
from render_user_artifact_docx import ARTIFACTS, render_artifact

errors = []
cases = {}


def record(case: str, ok: bool, details=None):
    cases[case] = {"pass": bool(ok)}
    if details is not None:
        cases[case]["details"] = details
    if not ok:
        errors.append({"case": case, "details": details})


def error_types(receipt: dict) -> set[str]:
    return {row.get("type") for row in receipt.get("errors") or []}


BASE_CONTEXT = {
    "phase": "POST_RENDER_POST_PUBLISH_PRE_DELIVERY",
    "task_id": "TASK-53",
    "candidate_sha256": "a" * 64,
    "package_binding_sha256": "b" * 64,
    "change_items_sha256": "c" * 64,
    "result_mode": "DIRECT_SOURCE_CHANGESET",
    "nontrivial_implementation": True,
    "requirements_artifact_required": False,
    "line_by_line_requested": False,
    "combined_alternate_requested": False,
}


def binding(context: dict) -> dict:
    return {
        key: context[key]
        for key in (
            "task_id",
            "candidate_sha256",
            "package_binding_sha256",
            "change_items_sha256",
            "result_mode",
        )
    }


def payload(kind: str, context: dict) -> dict:
    common = {"delivery_binding": binding(context)}
    if kind == "implementation_notes":
        return {
            **common,
            "tz_number": "ТЗ-53",
            "project": "Проект А",
            "task": "Проверка финальных DOCX",
            "platform_version": "8.3.27.1234",
            "configuration_name_version": "УТ 11.5.20",
            "rows": [{
                "container": "Расширение Поставка",
                "configuration_object": "ОбщийМодуль.ПоставкаСервер",
                "procedure_function": "Выполнить",
                "status": "Изменен",
                "description": "Добавлена проверка финального пакета.",
                "standard_rule": "RESULT_DELIVERY",
            }],
        }
    if kind == "manual_transfer":
        return {
            **common,
            "project": "Проект А",
            "task": "ТЗ-53",
            "target_identity": "Расширение Поставка candidate a",
            "purpose": "Перенести подтвержденное изменение.",
            "implementation_boundaries": ["Только расширение Поставка."],
            "do_not_change": ["Основную конфигурацию не изменять."],
            "created_objects": [],
            "modified_objects": [{
                "object": "ОбщийМодуль.ПоставкаСервер",
                "properties": [{"name": "Сервер", "before": "Ложь", "after": "Истина"}],
                "rationale": "Серверное выполнение.",
                "standard_rule": "RESULT_DELIVERY",
            }],
            "code_changes": [{
                "object": "ОбщийМодуль.ПоставкаСервер",
                "member": "Выполнить",
                "anchor": "перед возвратом результата",
                "before": "Возврат Результат;",
                "after": "Проверить();\nВозврат Результат;",
                "rationale": "Проверка обязательного результата.",
                "explanation": "Проверка выполняется до возврата.",
                "standard_rule": "RESULT_DELIVERY",
            }],
            "preconditions": ["Создать резервную копию."],
            "migration": ["Не требуется."],
            "deployment_sequence": ["Открыть расширение.", "Изменить модуль.", "Проверить синтаксис."],
            "static_verification": ["Синтаксическая проверка успешна."],
            "verification_matrix": [{"action": "Выполнить сценарий", "expected": "Результат получен."}],
            "runtime_verification": ["Выполнить контрольный сценарий."],
            "final_control_checklist": ["Изменен только разрешенный объект."],
            "changed_object_map": [{"object": "ОбщийМодуль.ПоставкаСервер", "change": "Добавлена проверка."}],
            "blocking_choices": ["Нет."],
            "proof_boundary": "Применение в целевой базе не наблюдалось.",
        }
    if kind == "requirements":
        return {
            **common,
            "project": "Проект А",
            "task": "ТЗ-53",
            "need_problem": "Проверять итоговые DOCX.",
            "target_outcome": "Обязательные документы доказаны по финальным байтам.",
            "scope_in": ["Итоговая поставка"],
            "scope_out": ["Runtime"],
            "functional_rules": ["Финальный файл проверяется после публикации."],
            "acceptance": [{
                "case": "Финальный DOCX",
                "preconditions": "Файл опубликован",
                "action": "Проверить",
                "expected": "Хэш и OOXML валидны",
                "oracle": "PASS",
            }],
            "proof_boundary": "Семантическая корректность документа требует review.",
            "requirements_status": "REQUIREMENTS_READY",
        }
    if kind == "line_by_line":
        return {
            **common,
            "explicit_user_request": True,
            "tz_number": "ТЗ-53",
            "project": "Проект А",
            "task": "Проверка финальных DOCX",
            "purpose": "Показать точный материал изменения.",
            "objects": [{
                "object": "ОбщийМодуль.ПоставкаСервер",
                "changes": [{
                    "member": "Выполнить",
                    "status": "Изменен",
                    "task_relation": "ТЗ-53",
                    "location": "перед возвратом",
                    "reason": "Добавить проверку.",
                    "what_changed": "Добавлен вызов.",
                    "behavior_impact": "Проверка выполняется до возврата.",
                    "diff": "+Проверить();",
                }],
            }],
        }
    raise AssertionError(kind)


def render_kinds(root: Path, context: dict, kinds: list[str]) -> dict:
    out = root / "Output"
    artifacts = {}
    for kind in kinds:
        path = render_artifact(kind, payload(kind, context), out)
        rel = path.relative_to(root).as_posix()
        artifacts[kind] = {
            "path": rel,
            "publication": {"kind": "LOCAL_FILE", "path": rel},
        }
    return artifacts


def manifest(context: dict, artifacts: dict) -> dict:
    return {
        "schema_version": 1,
        "context": copy.deepcopy(context),
        "artifacts": copy.deepcopy(artifacts),
    }


def validate_case(root: Path, context: dict, artifacts: dict) -> dict:
    return validate_final_docx_set(manifest(context, artifacts), root)


with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "positive-notes"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    arts = render_kinds(root, ctx, ["implementation_notes"])
    receipt = validate_case(root, ctx, arts)
    record(
        "positive_nontrivial_requires_and_verifies_notes",
        receipt.get("result") == "PASS"
        and receipt.get("required_kinds") == ["implementation_notes"]
        and receipt["artifacts"]["implementation_notes"]["ooxml_valid"] is True,
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "positive-manual"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["result_mode"] = "MANUAL_TRANSFER_INSTRUCTION"
    arts = render_kinds(root, ctx, ["implementation_notes", "manual_transfer"])
    receipt = validate_case(root, ctx, arts)
    record(
        "positive_manual_primary_requires_separate_notes_and_instruction",
        receipt.get("result") == "PASS"
        and receipt.get("required_kinds") == ["implementation_notes", "manual_transfer"]
        and len({row["sha256"] for row in receipt["artifacts"].values()}) == 2,
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "positive-combined-alternate"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["result_mode"] = "MANUAL_TRANSFER_INSTRUCTION"
    ctx["combined_alternate_requested"] = True
    arts = render_kinds(root, ctx, ["implementation_notes", "manual_transfer"])
    receipt = validate_case(root, ctx, arts)
    record(
        "positive_combined_alternate_preserves_required_separate_docs",
        receipt.get("result") == "PASS"
        and receipt.get("combined_alternate_requested") is True
        and receipt.get("required_kinds") == ["implementation_notes", "manual_transfer"],
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "positive-triggered-optionals"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["requirements_artifact_required"] = True
    ctx["line_by_line_requested"] = True
    arts = render_kinds(root, ctx, ["implementation_notes", "requirements", "line_by_line"])
    receipt = validate_case(root, ctx, arts)
    record(
        "positive_existing_requirements_and_line_by_line_triggers_preserved",
        receipt.get("result") == "PASS"
        and receipt.get("required_kinds") == ["implementation_notes", "requirements", "line_by_line"],
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "route-e2e"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    arts = render_kinds(root, ctx, ["implementation_notes"])
    arts["implementation_notes"]["publication"] = {
        "kind": "PLATFORM_ATTACHMENT",
        "ref": "attachment:opaque-final-notes",
    }
    receipt = validate_case(root, ctx, arts)
    record(
        "platform_attachment_identity_is_explicit_route_e2e",
        receipt.get("result") == "PASS"
        and receipt.get("route_e2e_required") == ["publication:implementation_notes"]
        and receipt["proof_boundary"]["platform_attachment_identity"] == "REQUIRES_ROUTE_E2E",
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "missing-notes"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    receipt = validate_case(root, ctx, {})
    record(
        "negative_missing_implementation_notes",
        "FINAL_DOCX_REQUIRED_ARTIFACT_MISSING" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "missing-manual"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["result_mode"] = "MANUAL_TRANSFER_INSTRUCTION"
    arts = render_kinds(root, ctx, ["implementation_notes"])
    receipt = validate_case(root, ctx, arts)
    record(
        "negative_missing_manual_transfer_instruction",
        any(
            row.get("type") == "FINAL_DOCX_REQUIRED_ARTIFACT_MISSING"
            and row.get("kind") == "manual_transfer"
            for row in receipt.get("errors") or []
        ),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "zero"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    arts = render_kinds(root, ctx, ["implementation_notes"])
    (root / arts["implementation_notes"]["path"]).write_bytes(b"")
    receipt = validate_case(root, ctx, arts)
    record("negative_zero_byte_docx", "FINAL_DOCX_ZERO_BYTE_FILE" in error_types(receipt), receipt)

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "renamed-text"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    arts = render_kinds(root, ctx, ["implementation_notes"])
    (root / arts["implementation_notes"]["path"]).write_text("plain text, not docx", encoding="utf-8")
    receipt = validate_case(root, ctx, arts)
    record("negative_arbitrary_text_renamed_docx", "DOCX_NOT_ZIP_CONTAINER" in error_types(receipt), receipt)

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "broken-ooxml"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    arts = render_kinds(root, ctx, ["implementation_notes"])
    path = root / arts["implementation_notes"]["path"]
    temp_zip = root / "broken.zip"
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temp_zip, "w") as target:
        for info in source.infolist():
            if info.filename != "word/document.xml":
                target.writestr(info, source.read(info.filename))
    shutil.move(temp_zip, path)
    receipt = validate_case(root, ctx, arts)
    record(
        "negative_missing_ooxml_mandatory_part",
        any(
            row.get("type") == "DOCX_MANDATORY_PART_MISSING:word/document.xml"
            for row in receipt.get("errors") or []
        ),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "duplicate"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["result_mode"] = "MANUAL_TRANSFER_INSTRUCTION"
    arts = render_kinds(root, ctx, ["implementation_notes", "manual_transfer"])
    notes_path = root / arts["implementation_notes"]["path"]
    manual_path = root / arts["manual_transfer"]["path"]
    manual_path.write_bytes(notes_path.read_bytes())
    receipt = validate_case(root, ctx, arts)
    record(
        "negative_duplicate_bytes_for_distinct_required_kinds",
        "FINAL_DOCX_REQUIRED_KINDS_DUPLICATE_BYTES" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "wrong-mapping"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["result_mode"] = "MANUAL_TRANSFER_INSTRUCTION"
    arts = render_kinds(root, ctx, ["implementation_notes", "manual_transfer"])
    arts["implementation_notes"]["path"] = arts["manual_transfer"]["path"]
    receipt = validate_case(root, ctx, arts)
    record(
        "negative_wrong_kind_path_mapping",
        "FINAL_DOCX_KIND_PATH_MAPPING_INVALID" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "stale-candidate"
    root.mkdir()
    old = copy.deepcopy(BASE_CONTEXT)
    old["candidate_sha256"] = "d" * 64
    arts = render_kinds(root, old, ["implementation_notes"])
    receipt = validate_case(root, BASE_CONTEXT, arts)
    record(
        "negative_stale_candidate_binding",
        "FINAL_DOCX_BINDING_MISMATCH" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "stale-task"
    root.mkdir()
    old = copy.deepcopy(BASE_CONTEXT)
    old["task_id"] = "TASK-OLD"
    arts = render_kinds(root, old, ["implementation_notes"])
    receipt = validate_case(root, BASE_CONTEXT, arts)
    record(
        "negative_stale_task_binding",
        "FINAL_DOCX_BINDING_MISMATCH" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "stale-change-items"
    root.mkdir()
    old = copy.deepcopy(BASE_CONTEXT)
    old["change_items_sha256"] = "e" * 64
    arts = render_kinds(root, old, ["implementation_notes"])
    receipt = validate_case(root, BASE_CONTEXT, arts)
    record(
        "negative_changed_anchor_with_stale_document_evidence",
        "FINAL_DOCX_BINDING_MISMATCH" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "publication-mismatch"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    arts = render_kinds(root, ctx, ["implementation_notes"])
    published = root / "Published" / ARTIFACTS["implementation_notes"]
    published.parent.mkdir()
    published.write_bytes(b"different publication bytes")
    arts["implementation_notes"]["publication"] = {
        "kind": "LOCAL_FILE",
        "path": published.relative_to(root).as_posix(),
    }
    receipt = validate_case(root, ctx, arts)
    record(
        "negative_mismatched_final_publication_reference",
        "FINAL_DOCX_PUBLICATION_BYTES_MISMATCH" in error_types(receipt),
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "combined-substitute"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["result_mode"] = "MANUAL_TRANSFER_INSTRUCTION"
    ctx["combined_alternate_requested"] = True
    combined = root / "Output" / "Combined.docx"
    combined.parent.mkdir()
    combined.write_bytes(b"combined alternate cannot close separate docs")
    receipt = validate_case(
        root,
        ctx,
        {
            "combined": {
                "path": "Output/Combined.docx",
                "publication": {"kind": "LOCAL_FILE", "path": "Output/Combined.docx"},
            }
        },
    )
    missing = [
        row.get("kind")
        for row in receipt.get("errors") or []
        if row.get("type") == "FINAL_DOCX_REQUIRED_ARTIFACT_MISSING"
    ]
    record(
        "negative_combined_alternate_cannot_replace_required_separate_docs",
        sorted(missing) == ["implementation_notes", "manual_transfer"],
        receipt,
    )

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "pre-render-phase"
    root.mkdir()
    ctx = copy.deepcopy(BASE_CONTEXT)
    ctx["phase"] = "PRE_RENDER_RELEASE"
    arts = render_kinds(root, ctx, ["implementation_notes"])
    receipt = validate_case(root, ctx, arts)
    record(
        "negative_pre_render_receipt_cannot_qualify_final_bytes",
        "FINAL_DOCX_PHASE_INVALID" in error_types(receipt),
        receipt,
    )

result = {
    "result": "PASS" if not errors else "FAIL",
    "errors": errors,
    "cases": cases,
    "case_count": len(cases),
}
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
