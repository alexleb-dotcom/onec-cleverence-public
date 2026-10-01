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
- for `.Свойство(..., outVar)`, treat key presence and the out value domain as separate facts; before `Если outVar Тогда` / `Если НЕ outVar Тогда`, prove Boolean domain on every reachable path or normalize explicitly to a Boolean value

## Structure property out-parameter safety

For a Structure-like value, the two-argument `.Свойство(<key>, outVar)` form is a dynamic read. The method's presence result does not by itself prove that `outVar` is Boolean. The accepted platform contract for this stream also requires handling the absent-key path, where the out value is not a usable Boolean.

Safe patterns keep these facts separate:

- use one-argument `.Свойство(<key>)` when only presence is needed;
- after a two-argument read, normalize the value to an explicit Boolean before a later bare Boolean condition; or
- guard the exact consumption path with a simple proven Boolean type contract, such as `ТипЗнч(value) = Тип("Булево")`.

A prior variable name, a presence check, or an initialization that does not survive the method result is not Boolean-domain proof. Ambiguous aliases/interprocedural contracts remain semantic review; the deterministic analyzer only blocks the bounded high-confidence local pattern.

Supporting typification guidance is indexed as `V8_CODE_STYLE_TYPIFICATION` in `KNOWLEDGE/EXTERNAL_SOURCE_CATALOG.json`. It is supporting guidance, not a replacement for the actual platform/Syntax Assistant method contract.

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.
