# ITS GAP DISCOVERY PROTOCOL

Purpose: catch unknown-unknown 1C problems after the internal skill review.

Internal profiles can only detect classes already known to the skill. Therefore every non-trivial 1C change must have an independent official-ITS discovery pass before delivery.

## When mandatory

Mandatory when at least one of these is true:
- a BSL/query/form/DynamicList mechanism changed;
- a new or materially rewritten query exists;
- generated/dynamic code or query text exists;
- client/server boundaries changed;
- transaction/write/security/platform behavior is involved;
- runtime found an error not predicted by the internal review;
- the mechanism profile is new or has unresolved `COVERAGE_GAP`/`NEEDS_REVISION`.

Tiny comment/label-only changes may record `NOT_APPLICABLE`.

## Pass A — mechanism search

For every detected 1C platform mechanism, search the current official 1C/ITS standards independently of the embedded trigger map. In addition, use the `v8std` project (`https://v8std.ru/`, `https://github.com/zeegin/v8std`) as a supporting discovery/index layer when it can expose related standards, diagnostics or coverage gaps. Read `KNOWLEDGE/V8STD_SOURCE_POLICY.md` for the trust boundary.
Batch searches by mechanism and reuse the opened official source within the current task. After a code fix, repeat external discovery only for newly activated mechanisms or changed version/freshness dependencies; unchanged hash/revision-bound evidence remains valid for the logical rerun.

Use several search axes, for example:

```text
site:its.1c.ru/db/content/v8std <mechanism> неправильно правильно
site:its.1c.ru/db/content/v8std <mechanism> ограничения производительность
site:its.1c.ru/db/content/v8std <exact construct/API name>
site:its.1c.ru/db/content/v8std <mechanism> "См. также"
```


Supporting discovery axes may also include:

```text
site:v8std.ru <mechanism>
site:v8std.ru <stdNNN or diagnostic code>
site:github.com/zeegin/v8std <mechanism or stdNNN>
```

If an environment exposes the v8std MCP (`https://ai.v8std.ru/mcp`), it may be used for retrieval. Do not send confidential project code to a public snippet-explanation service; prefer mechanism names, diagnostic codes or sanitized minimal examples.

`v8std` discovery is not by itself normative proof. For blocking conclusions, current official 1C/ITS text wins when available.

Examples of exact constructs:
```text
ВыполнитьПакет
СтрЗаменить текст запроса
ДинамическийСписок ТекстЗапроса
НаСервереБезКонтекста
ДанныеФормыКоллекция
ПолучитьОбъект
ПОМЕСТИТЬ временная таблица
ОБЪЕДИНИТЬ ВСЕ
```

Search intent is **not** “confirm my solution”. Search intent is “what classes of mistakes exist around this mechanism?”.

## Pass B — good/bad example extraction

For relevant standards, explicitly inspect:
- `ПРАВИЛЬНО` / `НЕПРАВИЛЬНО` examples;
- prohibitions/recommendations;
- performance notes;
- version/application scope;
- `См. также` links.

Follow relevant `См. также` links at least one level when they address the same changed mechanism.

## Pass C — exact-code challenge

Compare the final generated code against discovered examples, including final runtime-generated variants.

For dynamic query text:
```text
BSL syntax PASS
!=
final generated query syntax PASS
```

Materialize every meaningful branch/variant and verify:
- fragment boundaries;
- semicolons/package separators;
- aliases and ambiguous fields;
- markers replaced exactly once/as expected;
- each independently designed fragment can be opened/validated by query tooling where applicable;
- final variant runtime-parses in 1C before acceptance.

## Pass D — freshness

For non-trivial work, inspect the official “Новые и измененные разделы” standards page or equivalent official update source.

Question:
```text
Has a relevant standard changed since the embedded catalog/profile was written?
```

If yes, current official text wins and embedded knowledge must be updated.

## Pass E — knowledge assimilation

Every newly discovered reusable class must result in all applicable actions:
1. fix current code;
2. update mechanism profile/core trigger;
3. add/update official standard catalog;
4. add a machine or semantic regression case;
5. re-run internal review;
6. re-run ITS discovery on the changed mechanism;
7. record official URL/revision evidence and current candidate hashes in the task validation ledger.

A web search result that does not change or explicitly confirm coverage is not considered completed review.

## Status

Allowed statuses:
```text
PASS_NO_NEW_GAPS
PASS_NEW_RULES_ASSIMILATED
NEEDS_REVISION
RUNTIME_RETEST_REQUIRED
EXTERNAL_DISCOVERY_NOT_RUN
WEB_UNAVAILABLE
```

`EXTERNAL_DISCOVERY_NOT_RUN`/`WEB_UNAVAILABLE` means the code may still be delivered only when the user explicitly accepts the coverage limitation; it cannot be described as fully standards-reviewed.
