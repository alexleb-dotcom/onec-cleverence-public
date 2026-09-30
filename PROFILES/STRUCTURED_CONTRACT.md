# PROFILE — STRUCTURED_CONTRACT

## Detection

- `Новый Структура`
- `ТаблицаЗначений as API value`
- `Соответствие as API value`

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

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.
