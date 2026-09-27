# PROFILE — DUPLICATION_INVARIANT

## Detection

- `same business rule in form/common module`
- `repeated dedup/normalization/validation`

## Triggered standards

- `std440`

## Mandatory checks

- single owner for business relation/invariant with explicit `established_by`, `relied_on_by`, `defensively_rechecked_by` and `reason_for_recheck`
- caller postcondition vs callee repeated work
- intentional duplication documented
- optimized duplicate path covered by equivalence tests

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.

This profile owns repeated establishment/checking of an invariant. Structural similarity between implementations in distinct changed objects is separately routed to `CROSS_OBJECT_DUPLICATION_REVIEW`; do not rely on the lexical triggers above to cover the whole change-set.
