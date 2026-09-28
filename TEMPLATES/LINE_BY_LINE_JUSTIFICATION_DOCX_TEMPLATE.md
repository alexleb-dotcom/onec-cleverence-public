# Построчное обоснование изменений — source contract for separate optional DOCX

This file defines the artifact-specific content contract. It is not rendered verbatim.

## Trigger

OPTIONAL. Generate only on explicit user request.

## Output

`Построчное обоснование изменений.docx`

Renderer:
`TOOLS/render_user_artifact_docx.py --artifact line_by_line`

The payload must contain `explicit_user_request=true`; otherwise generation fails closed.

## Required structure

At the beginning:
- document/task identity;
- `Номер ТЗ` when available;
- `Проект`;
- `Задача`;
- `Назначение документа`;
- `Правила чтения`.

Group content:
1. by exact configuration object;
2. within object, by exact procedure/function/handler/change unit.

For every change unit:
- status: created / changed / deleted as applicable;
- relation to task/TZ when available;
- exact source location / line range / equivalent anchor when available;
- `Причина изменения`;
- `Что изменено`;
- `Влияние на поведение`;
- exact diff-like fragment.

Diff rules:
- removed lines start with `-`;
- added lines start with `+`;
- unchanged lines are context without change marker;
- exact identifiers/code remain literal.

The document must let a reviewer understand WHAT changed, WHY it changed and WHAT behavior is affected.

## Boundary

This artifact explains validated changes. It does not become a code/proof/release owner.
