# PROFILE — EXTERNAL_SIDE_EFFECT_IDENTITY

Read `KNOWLEDGE/DATA_STATE_VERSION_CONTRACTS.md`.

## Mandatory checks

- identity immediately before external effect;
- exact external payload/projection;
- confirmed success boundary;
- post-success identity mutation timing;
- failure/retry/idempotency/correlation;
- downstream pre/post identity ownership;
- independent reverse/refund/cancel trace;
- auditable mapping between external result and transformed internal state.

## Completion rule

External and later internal identities may differ only with explicit temporal ownership and runtime-verifiable correlation.
