# PROFILE — POST_WRITE_STANDARD_OVERWRITE

## Detection

Route this profile from **field-aware temporal flow**, not module-wide keyword co-occurrence:

- a meaningful field is assigned;
- the same object/row flows into a statically reachable later local writer of that same field, or into a later unresolved lifecycle-like external call that may write it;
- dynamic callbacks/subscriptions/dispatch that cannot be statically resolved remain review evidence, not “safe”.

`same module` ≠ `same execution path` and `contains Пересчитать/Заполнить` ≠ `writes this field`.

Run `TOOLS/analyze_onec_field_flow.py` for the deterministic first pass.

## Mandatory lifecycle proof

Trace the complete effective scenario for the exact field:

```text
custom write Field X
→ reachable subsequent calls/handlers
→ writers of Field X
→ reset/default/re-entry/reselection
→ before-write/write hooks
→ final persisted/consumed Field X
```

For each relevant field record:

```text
written_at
writer
field
reachable_from
execution_order
reason
final_owner
```

## Mandatory checks

- distinguish direct reachable same-field writes from unrelated writers elsewhere in the module;
- resolve local call argument → parameter flow where possible;
- inspect actual source of unresolved standard/BSP/vendor lifecycle calls before PASS;
- include dynamic callbacks/subscriptions as `EVIDENCE_REQUIRED` until the execution edge is proven;
- prove event/call order, not procedure-name similarity;
- validate the final value after the complete runtime scenario, not immediately after assignment.

## Completion rule

A machine finding is a routing/evidence signal, not automatic proof of a business defect.

- unrelated routine: no overwrite finding;
- reachable later writer of the same field: semantic ownership review required;
- proven later writer that violates the required final value: `BLOCKING_DEFECT`;
- unresolved dynamic/external writer: `EVIDENCE_REQUIRED`;
- runtime acceptance must inspect the final persisted/consumed value.
