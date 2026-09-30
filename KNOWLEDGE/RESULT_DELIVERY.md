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

For implemented changes, the chat summary remains compact and evidence-bound, while every applicable user-facing documentation artifact is delivered as its own Word file through `KNOWLEDGE/USER_ARTIFACT_DOCX.md` and `TOOLS/render_user_artifact_docx.py`.

`ChangePackage` remains the machine delivery envelope and proof owner. DOCX files are human-facing projections only.

### Primary delivery mode is decided first

Resolve the primary implementation delivery mode **before** constructing the final implementation artifact. Base the choice on the explicit user request, project modification policy, target/source topology, actually available mutation/import mechanism, exact validation boundary and whether a human is expected to apply the change.

Technical ability to construct XML does not establish `IMPORTABLE_ARTIFACT`. For an accepted 1C human/Configurator or extension-application route where direct target mutation is unavailable/not authorized and no exact importable artifact mechanism is proven and validated, use `MANUAL_TRANSFER_INSTRUCTION` as the default primary mode. XML remains valid when the selected proven route actually requires it.

### Инструкция по внедрению

When `MANUAL_TRANSFER_INSTRUCTION` is primary, generate the separate mandatory `Инструкция по внедрению.docx` from `TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md`. Chat-only code may preview/support the transfer but is not a complete manual-transfer delivery.

The visible R2 order is fixed:

1. `Создаваемые объекты`;
2. `Изменяемые объекты`;
3. `Код`.

Start from the exact target/baseline, purpose and implementation boundaries, including material “do not change / do not do” constraints when applicable. Created objects show exact material properties plus concise rationale/applicable evidenced rule. Modified objects show material property changes as `Было / Стало`. Code changes show exact object/member, placement anchor and minimum sufficient exact `Было / Стало` fragments with the same integration context; add concise explanation when placement/behavior could be misunderstood. Preserve exact code and the canonical AUTHOR_MARKER when applicable. Finish with an ordered deployment sequence, verification matrix with expected results, final static-control checklist and changed-object map. Do not leave a material implementation decision to the human executor.

### Особенности реализации

Every non-trivial implementation produces a **separate mandatory** `Особенности реализации.docx` from `TEMPLATES/IMPLEMENTATION_NOTES_DOCX_TEMPLATE.md`. This obligation is deterministic for non-trivial implementation and must not depend on an extra model judgment that “user-facing documentation is applicable”.

The header is exact and ordered:

1. `Номер ТЗ`;
2. `Проект`;
3. `Задача`;
4. `Версия платформы`;
5. `Наименование и версия конфигурации`.

The document contains one table with exactly these columns and order:

| Контейнер | ОбъектКонфигурации | Процедура/Функция | Статус | ОписаниеИзменений |
|---|---|---|---|---|

`ОписаниеИзменений` contains concise implemented functionality plus the applicable evidenced standard/rule. Exact container/object/member identity is preserved. The document does not upgrade application/deployment/runtime/release proof.

### Построчное обоснование изменений

Generate the separate `Построчное обоснование изменений.docx` **only on explicit user request**, using `TEMPLATES/LINE_BY_LINE_JUSTIFICATION_DOCX_TEMPLATE.md`.

It is grouped by exact object and then procedure/function/change unit, contains `Причина изменения`, `Что изменено`, `Влияние на поведение`, and an exact diff-like fragment where `-` marks removed lines, `+` marks added lines and unmarked lines are context.

Do not silently combine requirements, manual-transfer, implementation-notes or line-by-line artifacts into one Word file unless the user explicitly requests a combined/alternate format.

### Performance Review

When the canonical exact-candidate plan routes `COLLECTION_ALGORITHM`, add a compact `Performance Review` projection **outside** the mandatory `Проект`/`Задача` header and five-column `Особенности реализации` table. It is supplementary presentation of already validated evidence; it cannot create or upgrade proof.

Show the current and proposed algorithms with passes over primary data, nested searches, loop I/O, asymptotic time, memory/materialized copies, client/server/DB topology, reviewed scale, preservation of result/order/rounding/side effects/error semantics, and runtime profiling status.

- For `STRUCTURAL_ONLY`, structural/asymptotic improvement may be described, but the projection must include the exact statement: `Измеренное ускорение не доказано.`
- For `MEASURED`, render the measured claim only when the canonical verifier accepted an exact-candidate runtime case backed by `RUNTIME_ADAPTER` evidence.
- `NOT_APPLICABLE` is verifier-owned: it is valid only when the exact candidate has `COLLECTION_ALGORITHM` inactive and no activation trigger was detected.
- Missing, stale, wrong-candidate, generic-PASS/prose or otherwise invalid Performance Review remains visibly blocked/incomplete; omitting it must never make the delivery appear ready.
- The projection cannot change `implementation_readiness` or the final `release_outcome`.

## Requirements artifact profile

When a human-readable requirements / LT / TZ / functional specification artifact is applicable, generate the separate `Функциональная спецификация.docx` through `TEMPLATES/REQUIREMENTS_ARTIFACT_TEMPLATE.md` and `TOOLS/render_user_artifact_docx.py`.

Use compact `Проект` / `Задача` metadata, Russian user-facing labels for a Russian project/user, and omit truly empty conditional technical sections. Internal authoring rules are not rendered to the customer.

The executable requirements contract/gate remains authoritative. The DOCX must preserve agreed requirements, material `OPEN` items, explicit assumptions and proposed solution as distinct classes, and must never upgrade a blocked gate. A blocked requirements artifact must visibly retain the blocker and proof boundary.

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
