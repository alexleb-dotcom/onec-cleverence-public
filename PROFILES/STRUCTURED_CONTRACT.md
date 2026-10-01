# PROFILE — STRUCTURED_CONTRACT

## Detection

- `Новый Структура`
- `ТаблицаЗначений as API value`
- `Соответствие as API value`
- Structure-like `.Свойство(..., outVar)` reads where the out value can later enter a Boolean condition

## Triggered standards

- `std693`
- `std641`
- `std453`

## Mandatory checks

- <=3 constructor values or explicit filling
- fixed schema initialized once
- no dynamic property drift
- export API documents fields/types
- caller/callee contract names match
- service fields survive transformations
- before manually assembling a non-trivial subsystem-owned DTO/structure, resolve the standard constructor/factory, inspect at least one exact real call site, and prove mandatory runtime fields/initialization semantics
- for `.Свойство(..., outVar)`, treat key presence and the out value domain as separate facts; before direct Boolean consumption, prove Boolean domain on every reachable path or normalize explicitly to a Boolean value
- for a locally proven `ТаблицаЗначений` column consumed as a bare Boolean, prove both the Boolean domain and row initialization/normalization, or use an explicit comparison/type guard; an untyped/uninitialized column may carry `Неопределено`

## Structure property out-parameter safety

For a Structure-like value, the two-argument `.Свойство(<key>, outVar)` form is a dynamic read. The method's presence result does not by itself prove that `outVar` is Boolean. The accepted platform contract for this stream also requires handling the absent-key path, where the out value is not a usable Boolean.

Safe patterns keep these facts separate:

- use one-argument `.Свойство(<key>)` when only presence is needed;
- after a two-argument read, normalize the value to an explicit Boolean before a later bare Boolean condition; or
- guard the exact consumption path with a simple proven Boolean type contract, such as `ТипЗнч(value) = Тип("Булево")`.

A prior variable name, a presence check, or an initialization that does not survive the method result is not Boolean-domain proof. The deterministic HIGH finding applies only when the receiver is mechanically Structure-like through a local `Новый Структура` value or an active exact `ТипЗнч(receiver) = Тип("Структура")` guard. A generic API method named `.Свойство` does not inherit the platform Structure contract from its name; unresolved receiver type is review-only. If exact current source/API evidence proves that the specific out value is Boolean, resolve the exact machine-finding claim through the existing SOURCE_REQUIRED/SEMANTIC proof path rather than adding a new suppression/state mechanism. Ambiguous aliases/interprocedural contracts remain semantic review.

Supporting typification guidance is indexed as `V8_CODE_STYLE_TYPIFICATION` in `KNOWLEDGE/EXTERNAL_SOURCE_CATALOG.json`. It is supporting guidance, not a replacement for the actual platform/Syntax Assistant method contract.

## ValueTable tri-state Boolean safety

The deterministic `VALUE_TABLE_TRI_STATE_BOOLEAN` finding is deliberately local. It requires a table created locally as `Новый ТаблицаЗначений`, a column declared through `Колонки.Добавить`, a row variable from `Для Каждого row Из table Цикл`, and direct Boolean consumption of `row.column`.

Safe bounded routes include explicit Boolean column type plus proven initialization for all locally added rows, Boolean normalization before the condition, an exact comparison/type guard on the reachable branch, or an exact current source/API contract resolving the exact machine-finding claim. This detector does not infer a contract for arbitrary object properties and is not a generic BSL type engine.

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.
