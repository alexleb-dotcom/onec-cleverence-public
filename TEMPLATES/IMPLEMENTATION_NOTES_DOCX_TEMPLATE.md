# Особенности реализации — source contract for separate DOCX

This file defines the artifact-specific content contract. It is not rendered verbatim.

## Trigger

Mandatory for every non-trivial implementation.

## Output

`Особенности реализации.docx`

Renderer:
`TOOLS/render_user_artifact_docx.py --artifact implementation_notes`

## Header — exact order

1. `Номер ТЗ`
2. `Проект`
3. `Задача`
4. `Версия платформы`
5. `Наименование и версия конфигурации`

Every value must be exact/evidenced. Do not invent a value only to complete the document.

## Table — exact columns and order

1. `Контейнер`
2. `ОбъектКонфигурации`
3. `Процедура/Функция`
4. `Статус`
5. `ОписаниеИзменений`

Rules:
- `Контейнер`: exact extension name or `ОсновнаяКонфигурация`;
- `ОбъектКонфигурации`: exact configuration object;
- `Процедура/Функция`: exact member when applicable, otherwise `—`;
- `Статус`: factual Russian status such as `Изменен`, `Создан`, `Удален` as applicable;
- `ОписаниеИзменений`: concise implemented functionality plus the applicable standard/rule;
- do not invent a standard/rule; if no applicable standard is evidenced, the upstream artifact must provide an explicit truthful disposition before rendering.

The renderer may use landscape orientation for readability. The five-column content contract is immutable.

## Proof boundary

This DOCX is user-facing documentation only. It does not upgrade application/deployment/runtime/release proof.
