# PROFILE — REFERENCE_DATA_FRESHNESS

Read `KNOWLEDGE/DATA_STATE_VERSION_CONTRACTS.md`.

## Mandatory checks

- authoritative owner and semantic validity;
- observable freshness/version/fingerprint;
- source → exchange → server/base/cache → device/client propagation;
- controlled refresh diagnostic before code change when stale data is plausible;
- technically valid but business-invalid mappings;
- runtime acceptance after source change/refresh.

## Completion rule

A data mismatch is not a code defect until relevant source and downstream snapshots are proven current.
