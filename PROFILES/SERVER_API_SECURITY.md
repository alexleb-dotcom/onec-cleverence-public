# PROFILE — SERVER_API_SECURITY

## Detection

- `ServerCall=true`
- `Привилегированный`
- `ВыполнитьБезПроверкиПрав`
- `external input reaches server export`

## Triggered standards

- `std467`

## Mandatory checks

- minimal exported surface
- no unnecessary ServerCall
- no unnecessary privileged mode
- authorization/trust-boundary validation
- external identifiers do not select arbitrary methods/metadata
- input size/domain constrained

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.
