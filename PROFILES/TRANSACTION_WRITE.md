# PROFILE — TRANSACTION_WRITE

`RULES/rule_registry.json` is the executable owner. This file explains the routed review.

## Detection

- `НачатьТранзакцию`
- `Записать()`
- `НаборЗаписей`
- `БлокировкаДанных`
- object lifecycle handlers `ОбработкаПроверкиЗаполнения`, `ПередЗаписью`, `ПриЗаписи`, `ОбработкаПроведения`

## Triggered standards

- `std783`
- `std792`
- `std463` — `ОбработкаПроверкиЗаполнения` lifecycle/transaction boundary
- `std464` — object `ПередЗаписью`

When object/document validation participates in the write lifecycle, also read `KNOWLEDGE/ONEC_OBJECT_WRITE_VALIDATION_LIFECYCLE.md`.

## Mandatory checks

- transaction pairing
- same-method transaction ownership
- try/catch placement
- no DB access after failed transaction before rollback
- transaction duration/scope
- external resources outside transaction
- responsible read/locking
- TOCTOU between validation and write
- write/register-set inside loop
- batch size/idempotency/retry
- required mutation-channel matrix before selecting a validation event
- actual event coverage for interactive/programmatic write and posting; `ОбработкаПроверкиЗаполнения` is not a universal write guard
- one authoritative business predicate when both early UX validation and transactional integrity are needed
- explicit `ОбменДанными.Загрузка` / exchange bypass disposition
- runtime acceptance across every required write channel

## Completion rule

Every applicable check must be classified with source/official/runtime evidence or explicit non-applicability. A passing interactive save does not prove programmatic-write or posting coverage.
