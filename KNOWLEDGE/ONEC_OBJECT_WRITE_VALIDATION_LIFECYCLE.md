# 1C object write validation lifecycle

## Purpose

Use this contract when a requirement says that an object/document **must not be written, persisted or posted** unless a business rule holds, or when implementation places a blocking check in one of the standard object lifecycle handlers.

The core rule is:

> A validation handler is sufficient only when its proven lifecycle coverage contains every mutation channel that the requirement says must be blocked.

Do not choose a handler only because its name contains `ПроверкиЗаполнения` or because it works in one interactive scenario.

## Normative 1C evidence

Official 1C development standards are normative for the platform lifecycle semantics used here:

- `std463` — `ОбработкаПроверкиЗаполнения`: https://its.1c.ru/db/content/v8std/src/200/400/i8100463.htm
- `std464` — `ПередЗаписью`: https://its.1c.ru/db/content/v8std/src/200/400/i8100464.htm

Material points from `std463`:

1. `ОбработкаПроверкиЗаполнения` is intended for fill/correctness checks and is executed outside the object write transaction.
2. It is **not called for every object write**, in particular when the write was initiated programmatically.
3. Checks that must guarantee consistent object/dependent-data state must be located in write-transaction events such as `ПередЗаписью`, `ПриЗаписи`, or `ОбработкаПроведения` for documents.

Material point from `std464`:

- object-module `ПередЗаписью` is the standard place for value-correctness/state checks that belong to the object write lifecycle; the standard also requires explicit handling of `ОбменДанными.Загрузка` semantics.

These standards establish event semantics. Exact target behavior still requires source/runtime evidence for the concrete configuration and requirement.

## Required mutation-channel matrix

Before deciding where the guard belongs, derive the required channels from the requirement and project context. At minimum consider:

```text
INTERACTIVE_WRITE
PROGRAMMATIC_WRITE
POSTING
EXCHANGE_OR_IMPORT_WRITE
BACKGROUND_OR_INTEGRATION_WRITE
```

Only channels that are materially possible/required in the current task need to be enforced, but omitted channels require a reasoned `NOT_APPLICABLE` or explicit scope statement.

Examples:

```text
"Пользователь не должен провести документ"
→ POSTING may be the only required mutation channel.

"Документ нельзя записать или провести без X"
→ INTERACTIVE_WRITE + PROGRAMMATIC_WRITE + POSTING must be covered;
  exchange/integration channels must be dispositioned separately.

"Поле обязательно только при интерактивном вводе пользователем"
→ a pre-transaction fill check may be sufficient if persistence integrity is not claimed.
```

## Event semantics and selection

### `ОбработкаПроверкиЗаполнения`

Good fit:

- user-facing fill validation;
- conditional required fields;
- inexpensive pre-transaction validation;
- early feedback before write transaction.

Not sufficient as the only guard when the requirement claims that invalid state **cannot be persisted by any required write path**. Programmatic write is the canonical counterexample from `std463`.

### Object `ПередЗаписью`

Use when the invariant must be enforced for object writes across interactive/programmatic paths that reach object write lifecycle. For a requirement of the form "cannot be written or posted", it is usually the common object-level guard point, subject to actual project/extension interception and exchange semantics.

Do not blindly copy the standard `ОбменДанными.Загрузка` early return if the business invariant is required during exchange/import as well. First disposition whether exchange loading is allowed to bypass the rule.

### `ПриЗаписи`

May be appropriate for checks/actions that specifically belong later in the write transaction. Do not select it merely as a stronger-sounding replacement; prove that its timing/cancellation semantics match the requirement and target configuration.

### `ОбработкаПроведения`

Posting-specific. It can enforce a rule that matters only when posting, but it does not by itself guarantee plain document write restrictions.

## Avoid duplicated business logic

If both user-friendly pre-validation and persistence integrity are needed, do not implement two divergent rule copies.

Prefer:

```text
single business predicate / validation routine
→ optional ОбработкаПроверкиЗаполнения adapter for early UX feedback
→ transactional object guard for required persistence channels
```

The adapters may format messages differently, but the material business predicate must have one owner unless the target configuration proves another established pattern.

## Audit rule

When the accepted requirement says invalid data must not be written/persisted and the implementation contains the blocking rule only in `ОбработкаПроверкиЗаполнения`:

```text
PROGRAMMATIC_WRITE required or possible
+ no proven transactional/object write guard
→ blocking lifecycle coverage defect
```

Do not mark this defect merely because the handler exists. First bind:

1. the requirement's required mutation channels;
2. the source location of the validation rule;
3. the actual handler/event coverage;
4. any extension/subscription/interception that may provide another guard;
5. runtime evidence when behavior is runtime-visible.

## Runtime acceptance

For a guard that claims to prohibit write/posting, runtime acceptance must exercise every material required channel, not only the original UI path.

Typical matrix:

```text
interactive Save/Write with invalid state → rejected
programmatic Object.Write() with invalid state → rejected
posting with invalid state → rejected
valid object through the same channels → accepted
exchange/import/background path → test or explicit NOT_APPLICABLE according to scope
```

A breakpoint in `ОбработкаПроверкиЗаполнения` not being hit during one write is useful target-runtime evidence for that path, but the reusable platform rule is grounded in the official standard, not in the breakpoint observation alone.

## Review anti-pattern

Forbidden shortcut:

```text
"Есть ОбработкаПроверкиЗаполнения + Отказ = Истина"
→ therefore any invalid document cannot be recorded
```

Correct review question:

```text
Which mutation channels must be blocked?
→ which lifecycle events are actually reached for those channels?
→ where is the authoritative business predicate enforced?
→ are all required channels proven by source/runtime evidence?
```
