# Result delivery contract

`WORKFLOW/RESULT_DELIVERY_CONTRACT.json` is the canonical machine-readable owner of the final user-facing result shape for non-trivial skill work. This document explains how to apply it without turning the final answer into another internal validation artifact.

## Why this layer exists

The skill already has strict contracts for requirements, evidence, review, release and technical delivery. Those contracts answer **whether a result is justified** and **what bytes/instructions are delivered**. They do not by themselves guarantee that two equally well-validated tasks are presented to the user consistently.

The final response therefore has its own presentation contract. It does not create proof and it must never strengthen a gate outcome.

## Stable outer shape

For non-trivial work the user should normally see, in this order:

1. **Итог** — the direct result and strongest justified readiness statement.
2. **Результат** — the substantive profile-specific payload.
3. **Проверка** — only the material checks/evidence that change confidence in the result.
4. **Граница доказанности** — only when runtime/deployment/source/application remains unobserved or evidence is still partial/blocking.
5. **Артефакты** — only when files, patches, PRs, reports or packages were produced.
6. **Что нужно от пользователя** — only when a concrete user action remains.

Empty sections are omitted. Trivial factual answers are exempt; the contract is not permission to turn a one-line technical answer into a formal report.

## Analysis report profile

For architectural/code review, group observations by root cause/owner rather than repeating the same defect for every occurrence. Each material finding uses the shape:

```text
Где
Как сейчас
Проблема
Рекомендуется
Обоснование
Доказательство / граница
```

When exact source is available and a concrete replacement materially helps, add:

```text
Старый код
Рекомендуемый код
```

Do not manufacture a replacement fragment when the missing dependency means the exact code cannot be justified.

## Implementation delivery profile

For implemented changes, summarize by responsibility rather than by changed line:

```text
Что изменено
Изменённые объекты / файлы
Ключевые решения
Поставка
Проверка
```

The selected result mode still controls the technical delivery shape (`DIRECT_SOURCE_CHANGESET`, `MANUAL_TRANSFER_INSTRUCTION`, `PATCH_DIFF`, `IMPORTABLE_ARTIFACT`, `FULL_COMPARE_SET`, etc.). `ChangePackage` remains the machine delivery envelope; this Result Delivery contract controls how that delivery is presented to the person.

### Особенности реализации

Every non-trivial implementation must finish with a human-readable `Особенности реализации` section. `Проект` and `Задача` are mandatory one-time section fields above the table and are not repeated in each row:

```text
Проект: <bound project name>
Задача: <bound task name or identifier>
```

The table then uses exactly these five base columns:

| Контейнер | Объект конфигурации | Процедура / функция | Статус | Описание изменения |
|---|---|---|---|---|
| <exact container> | <exact configuration object> | <exact routine/member/event> | <factual status> | <factual change description> |

Both parts of the base format are immutable. The labels/order of `Проект` and `Задача` and the five table columns must not be changed: do not rename, remove, merge, split or reorder them. Do not repeat `Проект`/`Задача` as table columns, and do not add extra columns to the base table. In particular, keep `Объект конфигурации` as one field; do not replace it with separate `Тип объекта конфигурации` + `Имя объекта конфигурации` columns.

- `Проект` and `Задача` come only from bound Project Context/requirements and appear once above the table.
- Create one row per material implementation change/decision at the most precise practical object/member level. The same configuration object may appear in several rows when different procedures/functions/members have separate statuses or descriptions.
- `Контейнер` is the exact source container identity, for example `Расширение <имя>` or `Основная конфигурация <имя>`.
- `Объект конфигурации` is the exact human-readable configuration object identity in one field.
- `Процедура / функция` contains the exact changed routine/member/event; multiple exact members are allowed in the cell when one status/description genuinely applies to the group.
- `Статус` is factual and grammatically appropriate, for example `Создана`, `Добавлена`, `Изменена`, `Удалена`, `Удалены`, `Оставлена без изменения`, `Удалена привязка`.
- `Описание изменения` concisely states what changed or was deliberately retained and how the resulting behavior/mechanism works.
- Do not collapse equal object names from the main configuration, an extension or different extensions. Do not invent objects, members, statuses or changes, and do not omit material implementation rows.
- Additional rationale, evidence, risks, performance notes, verification or links may be added after/below the mandatory header+table as supplementary material. They never replace, rename or extend the two header fields or five table columns.
- Cleverence and other non-1C artifacts may be documented additionally with their own system/artifact identity, but that supplementary representation must not mutate the mandatory 1C format.

If manual transfer is primary, the compact user summary must not replace the exact ordered transfer specification required by the ChangePackage contract.

### Performance Review

When the canonical exact-candidate plan routes `COLLECTION_ALGORITHM`, add a compact `Performance Review` projection **outside** the mandatory `Проект`/`Задача` header and five-column `Особенности реализации` table. It is supplementary presentation of already validated evidence; it cannot create or upgrade proof.

Show the current and proposed algorithms with passes over primary data, nested searches, loop I/O, asymptotic time, memory/materialized copies, client/server/DB topology, reviewed scale, preservation of result/order/rounding/side effects/error semantics, and runtime profiling status.

- For `STRUCTURAL_ONLY`, structural/asymptotic improvement may be described, but the projection must include the exact statement: `Измеренное ускорение не доказано.`
- For `MEASURED`, render the measured claim only when the canonical verifier accepted an exact-candidate runtime case backed by `RUNTIME_ADAPTER` evidence.
- `NOT_APPLICABLE` is verifier-owned: it is valid only when the exact candidate has `COLLECTION_ALGORITHM` inactive and no activation trigger was detected.
- Missing, stale, wrong-candidate, generic-PASS/prose or otherwise invalid Performance Review remains visibly blocked/incomplete; omitting it must never make the delivery appear ready.
- The projection cannot change `implementation_readiness` or the final `release_outcome`.

## Requirements artifact profile

For a specification/technical assignment/resulting requirements artifact, the result must distinguish:

- agreed scope/outcome;
- material rules and acceptance criteria;
- unresolved assumptions/open questions;
- the produced artifact.

A requirements gate that is still blocked must be visible in the outcome/proof boundary. Do not bury it in an appendix while describing the artifact as complete.

## Blocked or partial profile

This profile takes precedence whenever a material blocker remains. Present:

```text
Что удалось завершить
Что блокирует / какого доказательства не хватает
Что именно нужно предоставить
Что можно продолжать без этого
```

Request the smallest concrete artifact or answer that can close the blocker. Do not make the user repeat already available task context.

## Readiness language

The response uses the readiness outcome owned by the relevant gate/validator. In particular:

- `BLOCKED` cannot become «готово»;
- `READY_FOR_RUNTIME_TEST` cannot become «проверено в работе»;
- `ANALYSIS_COMPLETE` means analysis coverage, not deployment/runtime proof;
- `PROVEN` is scoped exactly to what the release gate proved;
- `ProjectSnapshot ACCEPTED` proves package/request/plan/configuration binding, not source semantics by itself;
- a validated ChangePackage does not prove that the target system was changed, deployed or executed unless that was observed separately.

## What not to expose by default

Do not dump the whole requirements contract, routing table, validation ledger, rule list, gate inventory or every machine report into the final response unless the user explicitly asks for those internals. The final answer should be a compact, traceable projection of the validated result, not a second copy of the proof system.
