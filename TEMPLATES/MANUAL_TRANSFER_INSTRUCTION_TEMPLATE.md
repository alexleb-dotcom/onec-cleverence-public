# Инструкция по внедрению — source contract for separate DOCX

This file defines the artifact-specific source contract. Service rules in this file are **not rendered verbatim** to the customer.

## Trigger

Use when `MANUAL_TRANSFER_INSTRUCTION` is the selected implementation delivery mode.

This artifact is mandatory for that mode. Chat-only code is supporting explanation, not a complete manual-transfer delivery.

## Output

Separate file:

`Инструкция по внедрению.docx`

Renderer:

`TOOLS/render_user_artifact_docx.py --artifact manual_transfer`

`ChangePackage` remains the machine delivery/proof-boundary owner.

## Compact metadata

- `Проект: <exact>`
- `Задача: <exact>`
- `Целевая база / артефакт: <exact baseline/candidate identity>`

## Purpose and boundaries

Always render:
- `Назначение и границы` — concise purpose plus exact implementation boundaries;
- `Не изменять / не делать` only when a material negative boundary exists.

The renderer must not invent a negative boundary just to populate the section.

## Visible object-first structure — exact core order

### 1. Создаваемые объекты

For every created object show:
- `Объект: <exact configuration object>`;
- all material properties required for manual creation;
- exact/evidenced values;
- `Обоснование`;
- `Применимый стандарт/правило` when an applicable evidenced rule exists.

Do not invent a rule merely to fill the field.

### 2. Изменяемые объекты

For every modified object show:
- `Объект: <exact configuration object>`;
- only material changed properties;
- exact `Было` / `Стало` values;
- enough object identity to avoid applying the change to another object;
- `Обоснование`;
- applicable evidenced standard/rule when present.

### 3. Код

For every changed procedure/function/handler show:
- exact `Объект`;
- exact `Изменения: <procedure/function/handler>`;
- exact `Якорь / место изменения`;
- dependencies/order when material;
- `Было`: minimum sufficient exact source fragment locating the integration/replacement point;
- `Стало`: the same anchor/context with resulting code;
- concise `Обоснование`;
- `Пояснение` when placement/behavior can reasonably be misunderstood;
- applicable evidenced standard/rule when present.

Exact identifiers/code remain literal. The resulting `Стало` fragment must preserve the canonical Skill `AUTHOR_MARKER` when it is applicable upstream.

If DELETE is required, the removed object/property/code must be shown explicitly with rationale.

Do not leave a material design choice to the human executor.

## Execution and acceptance closure

For every complete manual-transfer instruction always render:

### Порядок внедрения

An explicit ordered deployment sequence. The human executor must not have to infer action order from object layout alone.

### Матрица проверки

A verification/acceptance matrix with:
- `Действие / сценарий`;
- `Ожидаемый результат`.

Use exact expected behavior. Do not upgrade unobserved runtime/deployment proof.

### Финальный статический контроль

A concise checklist that can be completed after transfer and before runtime/deployment claims are made.

### Карта изменённых объектов

A final inventory mapping each changed object to the material implemented change.

## Conditional operational sections

Render only when applicable:
- `Предусловия`;
- `Миграция / инициализация / одноразовые действия`;
- `Статическая проверка после внедрения`;
- `Проверка выполнения`;
- `Нерешённые выборы / блокеры`.

When `Миграция / инициализация / одноразовые действия` replaces a prior failed manual attempt, it must:
- bind the exact current target block before giving replacement steps;
- identify and remove only the exact prior-attempt fragment;
- restore the evidenced base fragment when the final change depends on that restoration;
- apply the final replacement against the current block;
- preserve unrelated valid changes already present in the target;
- state execution order and post-transfer verification.

A vague instruction such as “rollback the previous change” is insufficient when it could remove unrelated work or assume stale target bytes.

Always render:
- `Граница доказанности`.

## Boundary

A complete instruction does not prove target application, deployment/import or runtime behavior.

The human-facing document remains object-first: purpose/boundaries frame the task, the core implementation is `Создаваемые объекты → Изменяемые объекты → Код`, and execution/acceptance closure follows. Do not render the previous generic STEP-first presentation as the primary customer structure.
