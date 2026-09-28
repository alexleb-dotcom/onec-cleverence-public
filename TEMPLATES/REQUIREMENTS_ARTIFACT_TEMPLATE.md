# Функциональная спецификация — source contract for separate DOCX

This file defines the artifact-specific source contract. Service rules in this file are **not rendered verbatim** to the customer.

## Trigger

Use when the user/project requires a human-readable requirements / LT / TZ / functional specification artifact.

## Output

Separate file:

`Функциональная спецификация.docx`

Renderer:

`TOOLS/render_user_artifact_docx.py --artifact requirements`

The executable requirements contract and `TOOLS/requirements_gate.py` remain the semantic/readiness authority.

## Visible document model

Compact metadata:
- `Проект: <exact>`
- `Задача: <exact>`

Then:
1. `Потребность / проблема`
2. `Целевой результат`
3. `Границы`
   - `Входит`
   - `Не входит`
4. `Функциональное поведение и материальные правила`
5. `Источник истины / идентичность / данные` — only when materially applicable
6. `Процесс / состояния / повтор / ошибки` — only when materially applicable
7. `Интеграционный контракт` — only when materially applicable
8. `Приемка`
9. `Открытые вопросы / блокеры` — when any remain; mandatory when requirements are blocked
10. `Допущения` — only when present
11. `Предлагаемое решение` — only when present and visibly separate from agreed requirements
12. `Основания и граница доказанности`
13. localized readiness wording plus exact canonical readiness token.

Truly empty conditional sections are omitted.

## Acceptance table

Exact columns:
- `Случай`
- `Предусловия`
- `Действие`
- `Ожидаемый результат`
- `Оракул`

## Language / identity

For a Russian project/user, all human-facing labels/explanations are Russian.

Exact identifiers, paths, code, API names, hashes and machine tokens required for traceability remain literal.

## Readiness boundary

The DOCX cannot create or upgrade requirements readiness.

`REQUIREMENTS_BLOCKED` must stay visibly blocked and must expose its material open questions.

Internal authoring invariants, renderer instructions and tool names are not part of the rendered customer body.
