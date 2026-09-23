# PROFILE — STATEFUL_UI_MODE

Read `KNOWLEDGE/DATA_STATE_VERSION_CONTRACTS.md`.

## Mandatory checks

- explicit states/transitions or equivalent invariant;
- state/selection/transient-input owner;
- success reset;
- cancel/error/invalid/no-data reset;
- row/selection change semantics;
- repeated activation/re-entry;
- close/reopen behavior and next ordinary action.

## Completion rule

Happy-path success is insufficient. Every material exit/re-entry path must disposition transient state.
