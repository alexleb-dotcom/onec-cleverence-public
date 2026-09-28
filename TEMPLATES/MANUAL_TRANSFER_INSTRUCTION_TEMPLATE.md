# Инструкция по внедрению — source contract for separate DOCX

This file defines the artifact-specific source contract. Service rules in this file are **not rendered verbatim** to the customer.

## Trigger

Use when `MANUAL_TRANSFER_INSTRUCTION` is the selected implementation delivery mode.

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

## Visible R2 structure — exact order

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
- dependencies/order when material;
- `Было`: minimum sufficient exact source fragment locating the integration/replacement point;
- `Стало`: the same anchor/context with resulting code;
- concise `Обоснование`;
- applicable evidenced standard/rule when present.

Exact identifiers/code remain literal. The resulting `Стало` fragment must preserve the canonical Skill `AUTHOR_MARKER` when it is applicable upstream.

If DELETE is required, the removed object/property/code must be shown explicitly with rationale.

Do not leave a material design choice to the human executor.

## Conditional operational sections

After the three owner-approved primary blocks, render only when applicable:
- `Предусловия`;
- `Миграция / инициализация / одноразовые действия`;
- `Статическая проверка после внедрения`;
- `Проверка выполнения`;
- `Нерешённые выборы / блокеры`.

Always render:
- `Граница доказанности`.

## Boundary

A complete instruction does not prove target application, deployment/import or runtime behavior.

The R2 human-facing document is object-first. Do not render the previous generic STEP-first presentation as the primary customer structure.
