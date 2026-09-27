# DOMAIN_VALIDATION

Use when changed code validates domain values, combinations of fields, ranges, sentinels, percentages, states, or applicability conditions.

## Core rule

Before writing or accepting an `Если`, establish which layer owns each invariant:

```text
platform/type/metadata guarantee
→ trust/input boundary
→ business invariant
→ persistence/runtime invariant
```

Do not blindly duplicate a state already impossible under the proven platform/type/metadata contract. Conversely, do not remove a defensive check merely because metadata normally prevents the value when the value can arrive through an external, legacy, migration, exchange, deserialization, privileged, or otherwise bypassing boundary.

## Mandatory checks

- state the complete value domain guaranteed by type/metadata/platform;
- identify every path that can bypass or predate that guarantee;
- distinguish defensive boundary validation from business validation;
- each condition must correspond to a reachable state or a documented defensive boundary;
- do not encode the same invariant independently in several layers without different trust/time ownership;
- for a rule involving multiple fields or piecewise cases, write an acceptance/rejection truth table before code;
- prove boundary cases: empty/default, zero, minimum/maximum, individually valid but jointly invalid, legacy/external input;
- keep the error message aligned with the actual business invariant rather than the lower-level type restriction.

## Status guidance

A redundant impossible-state check is a maintainability finding unless it masks a contradictory business rule. A missing check at a real trust boundary or an incorrectly encoded business truth table can be blocking.
