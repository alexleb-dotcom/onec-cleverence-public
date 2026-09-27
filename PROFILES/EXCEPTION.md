# PROFILE — EXCEPTION

## Detection

- `Попытка`
- `Исключение`
- `ВызватьИсключение`

## Triggered standards

- `std499`
- `std783`

## Mandatory checks

- catch is necessary and local
- exception not swallowed
- original diagnostics preserved
- no parsing of exception text
- transaction rollback first
- user vs admin diagnostics

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.
