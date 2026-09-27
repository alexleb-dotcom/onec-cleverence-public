# PROFILE — DOCUMENTATION_CONTRACT

## Detection

- changed/added comment;
- comments before changed procedures/functions;
- exported/public interface change;
- non-obvious invariant, platform/vendor limitation or deliberate deviation.

## Triggered standards

- `std453`
- `std641`
- `COMMENTING_POLICY`

## Comment classes

- `AUTHOR_MARKER` — project-specific attribution of a typical/vendor change;
- `TECHNICAL_COMMENT` — reason, invariant, limitation or non-obvious algorithmic contract;
- `PUBLIC_INTERFACE_COMMENT` — parameters, result, allowed values, side effects, execution context and limitations.

Author-marker syntax belongs to project context and must not be inferred as a universal format.

## Mandatory checks

- comment matches current responsibility
- parameter/return schema current
- no stale performance/ownership claims
- technical comment explains why/invariant/constraint instead of restating code
- project marker is separate from technical/public documentation
- read `KNOWLEDGE/COMMENTING_POLICY.md`

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Static routing cannot prove comment quality. Unknown material behavior is not PASS.
