# PROFILE — DECISION_DEPENDENCY_INVALIDATION

Read `KNOWLEDGE/BUSINESS_STATE_AND_RELATION_CONTRACTS.md`.

## Mandatory checks

- name the derived decision and all mutable dependencies;
- name authoritative current values/sources;
- define invalidation/revalidation for every dependency change;
- prove the boundary before a cached decision is consumed again;
- cover existing-row behavior after context changes;
- runtime acceptance before/after at least one dependency change.

## Completion rule

A decision proved under context A is not reusable under context B until freshness or revalidation is proven.
