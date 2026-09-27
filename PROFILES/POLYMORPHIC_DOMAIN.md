# PROFILE — POLYMORPHIC_DOMAIN

## Detection

- `ТипЗнч`
- `ССЫЛКА Документ`
- `composite reference`

## Triggered standards

- `std654`
- `std728`

## Mandatory checks

- validate allowed type before value enters downstream collection
- explicit unsupported-type policy
- no domain-contract leakage before branching
- all supported types have equivalent semantics
- unexpected type cannot partially execute

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.
