# PROFILE — BUSINESS_RELATION_CARDINALITY

Read `KNOWLEDGE/BUSINESS_STATE_AND_RELATION_CONTRACTS.md`.

## Mandatory checks

- state 0/1/N cardinality for every material relation;
- prove any claimed uniqueness from metadata/business invariant;
- define behavior for zero, one and many related objects;
- define merge/split identity and duplicate rules;
- test 0/1/N rather than only singleton sample data.

## Completion rule

First-found logic or current sample cardinality cannot establish a 1:1 business contract.
