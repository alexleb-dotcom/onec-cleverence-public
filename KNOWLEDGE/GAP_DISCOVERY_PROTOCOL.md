# Evidence-bounded gap discovery

Purpose: search for material omissions that are not already named by an active rule,
without allowing free-form model suspicion to become a defect or a release claim.

## Core boundary

Discovery produces **hypotheses**, not findings. A hypothesis cannot establish PASS,
cannot become a universal rule and cannot trigger a destructive/refactoring action by
itself. It may only widen review, request evidence or identify a testable counterexample.

Every hypothesis must contain:

```text
source_anchors  — exact changed artifact/contract/runtime observation;
statement       — one falsifiable possible failure;
counterexample  — concrete input/path/state that would expose it;
falsifier       — evidence that would disprove it;
status          — fail-closed disposition;
```

Unanchored concerns such as “there may be another handler” are discarded. A source
anchor may expose an unresolved boundary; it is not proof of what exists beyond that
boundary.

## Bounded expansion and stall

Gap discovery may widen the current evidence path only for a source-anchored dependency necessary to the already accepted outcome, with a finite exit condition. A newly interesting but outcome-independent mechanism is recorded as a follow-up candidate instead of silently growing scope.

Active investigation normally keeps one causal question in focus; a second may be active only to discriminate between competing explanations. This focus does not discard required writers, lenses, paired flows, routed obligations or acceptance checks: they remain in the existing work queue and are handled sequentially.

Repeated non-progress triggers source/strategy reassessment and at most one bounded discriminating retrace for the same claim. If that retrace still does not change the accepted uncertainty/next engineering choice, preserve the unresolved disposition and return the smallest exact evidence/input/experiment request while completing independent work. Do not create a universal tool-call/iteration stop rule.

## Independent lenses

Run the lenses independently from routed profiles and machine findings:

1. `CHANGESET_COHERENCE` — responsibilities/invariants duplicated or split across changed objects;
2. `BOUNDARY_CONTRACT` — caller/callee, client/server, producer/consumer and trust-boundary mismatches; also declared/static shape versus actual runtime data shape (for example metadata object existence versus membership of a form/container value);
3. `TEMPORAL_STATE` — later writers, repeat/re-entry, ordering, stale state and lifecycle ownership;
4. `IDENTITY_CARDINALITY` — identity/representation, join/merge/split cardinality and conservation;
5. `REACHABILITY_DELIVERY` — entrypoint-to-behavior and delivery/deployment dependency closure;
6. `FAILURE_NEGATIVE_PATH` — rollback, partial completion, retry/idempotency, cancel/error and recovery;
7. `STANDARD_PIPELINE` — semantic loss versus a parallel source of truth;
8. `REQUIREMENTS_ACCEPTANCE` — behavior or acceptance branch not proved by the functional contract.

Each lens receives evidence-backed `PASS`, reasoned `NOT_APPLICABLE` or a pending /
blocking status. A clean known-rule analyzer is not evidence that these lenses were run.

## Standard pipeline closure projection

For a non-trivial standard-document transformation, reuse the existing `STANDARD_PIPELINE_SEMANTIC_PRESERVATION` ledger evidence rather than creating a `MECHANISM_TRACE` state/artifact. The minimum useful projection is:

- source/business identity;
- entry/caller;
- target initialization;
- every material selection/reselection stage that can rebuild the set;
- standard-owned fields;
- requirement-owned fields;
- later writers/finalizers/post-process.

A business filter or identity proven only at an early/header stage does not close the obligation when a later stage reselects the data. `QUERY_REQUIRED_FACT_RETENTION` and the standard-pipeline stage closure must cover the later rebuild as well.

For material fields, project `target field -> requirement/source-of-truth -> typical producer -> final owner/finalizer`. Preserve standard-owned technical/business fields. Apply requirement-owned values as an overlay on the Typical skeleton whenever possible.

After a standard fill creates rows, destructive clear/rebuild is a blocking semantic concern until all required standard fields and stable row identity are proven restored. Preferred shape: **Typical skeleton + requirement-owned overlay** / **Preserve Typical Row Identity**.

## Hypothesis lifecycle

Allowed resolved statuses:

```text
COVERED_BY_EXISTING_RULE — route to an existing registry owner and prove its ledger row;
DISPROVED                — falsifier evidence was obtained;
NOT_MATERIAL             — impact is bounded with evidence and a reason;
FIXED_REVALIDATED        — defect was fixed and the dependency closure was rerun.
```

Unresolved statuses:

```text
EVIDENCE_REQUIRED — request the smallest sufficient artifact/test;
CONFIRMED_DEFECT  — evidence proves a defect that is not yet fixed;
COVERAGE_GAP      — evidence proves the registry/workflow cannot own a material class;
RUNTIME_PENDING   — static evidence cannot decide and a named runtime case remains.
```

`EVIDENCE_REQUIRED`, `CONFIRMED_DEFECT` and `COVERAGE_GAP` block release.
`RUNTIME_PENDING` permits at most `READY_FOR_RUNTIME_TEST` and must reference a named
`runtime_cases` row. `EVIDENCE_REQUIRED` names the missing evidence; `COVERAGE_GAP`
records the existing-registry search that failed to find an owner.

When runtime acceptance disproves the causal/design hypothesis behind a patch, invalidate that hypothesis and dependent readiness before another patch to the same symptom. Retrace the exact owner/dependency/lifecycle path and reuse only evidence whose dependencies remain valid.

## Hallucination controls

- start only from actual deltas, unresolved calls/data flows, contradictory evidence,
  missing consumers/writers, or a concrete counterexample;
- search the current registry before declaring a coverage gap;
- separate observation from inference in every hypothesis;
- for a changed path/member access `A.B`, ask what exact producer/type/composition evidence proves that `B` exists in the runtime value of `A` at that point; a same-named metadata object, field in another schema or global catalog entry is not membership evidence;
- prefer one discriminating falsifier over a long list of generic risks;
- deduplicate equivalent hypotheses and keep only material ones;
- calibrate new deterministic heuristics on positive and negative fixtures plus a
  known-working corpus before making them blocking;
- promote a new universal rule only after a reproduced failure or authoritative
  contract, generalization beyond the project, independent counterexample and full
  activation/enforcement/release coverage.

## Whole-change-set relation

Run `TOOLS/analyze_changeset_architecture.py` for multi-BSL change-sets. Its output is
machine evidence for candidate pairs only. Even zero candidates does not close
`CHANGESET_COHERENCE`; the semantic pass must still map changed responsibilities and
owners across objects.
