# PROFILE — FACT_PRESERVING_REALLOCATION

Read `KNOWLEDGE/BUSINESS_STATE_AND_RELATION_CONTRACTS.md`.

## Mandatory checks

- separate conserved fact from allocation analytics;
- state conservation invariant;
- define any temporary unassigned state;
- prevent duplicate/over-allocation;
- block completion when required fact remains unallocated;
- prove repeated move/re-entry idempotency and runtime conservation.

## Completion rule

Reallocation may change ownership/analytics, but must not change total fact unless the business action explicitly creates or removes fact.
