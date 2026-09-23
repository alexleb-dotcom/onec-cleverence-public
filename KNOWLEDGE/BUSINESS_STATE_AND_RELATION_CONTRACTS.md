# Business state, relation and fact contracts

This chapter captures reusable failure classes from real 1C/Cleverence work. It defines proof obligations, not project-specific implementations or API signatures.

## Decision dependency invalidation

A derived business decision is valid only for the dependency snapshot under which it was computed. Examples include eligibility, permission, classification, routing, price applicability and regulatory checks. Name every material dependency and define what happens when it changes: immediate revalidation, lazy revalidation before consumption, or an explicitly accepted no-revalidation limitation.

A context change must not silently preserve a stale row-level/cache/UI decision. Acceptance must exercise the decision before and after changing at least one dependency and state what happens to already existing rows/results.

## Business relation cardinality

Object/document relations are business contracts, not artifacts of test-data shape. For every material relation, state the allowed multiplicity (`0`, `1`, `N`) and deterministic behavior for zero, singleton and multiple matches. `ПЕРВЫЕ 1`, `НайтиПервый` or a sample database with one row never proves a 1:1 invariant.

When several sources can contribute to one target or one source can split into several targets, define merge/split identity, duplicate prevention and ambiguity handling.

## Field-level source ownership

A target row often has no single upstream owner. Quantity/fact, item identity, series/marking, commercial conditions, tax properties and derived totals may legitimately come from different sources. Use a field-level ownership matrix:

`target field → semantic role → authoritative source → match key → calculation owner`.

Do not copy an entire row from whichever source supplied one important field. Derived values should remain owned by the standard/vendor calculation pipeline when that pipeline is authoritative.

## Composite row grain and correlation

Field-level ownership is insufficient unless contributing source rows are correlated at the same target grain. State the target row/object stable business identity and the complete cross-source match tuple before combining sources. Two valid 1:N relations joined only by a coarser key can create an accidental N×M product that fabricates row combinations and multiplies additive fact.

For each many-side source, either reduce it to the required target grain before composition, join with a complete correlation tuple that proves the intended pairing, or explicitly widen the target grain and acceptance contract. Preserve material measures with an explicit invariant where applicable. `DISTINCT`, `GROUP BY`, `МАКСИМУМ`, `МИНИМУМ` or first-found selection is not a repair for an under-specified join unless semantic equivalence and measure preservation are independently proven.

## Fact-preserving reallocation

Changing where a fact is allocated is not the same operation as creating or deleting the fact. Separate the conserved fact/measure from its current allocation dimension (box, container, series, project, warehouse, department, activity or another analytic).

State a conservation invariant such as `Σ fact before = Σ fact after`. If temporary `UNASSIGNED` state is allowed, define its lifetime and transitions. Completion must reject duplicated, over-allocated or required-but-unassigned fact. Retry/re-entry must remain idempotent with respect to both fact and allocation identity.

## Compatibility with existing customizations

Correctness against a clean standard/vendor baseline is insufficient for an already customized project. Before changing a business path, map existing extensions, event subscriptions, overrides and other customizations touching the same events, mutable state or data. Prove call order, ownership and interaction with the new change.

The strict terminology contract still applies: standard/typical code and project customizations are different provenance classes. Existing customizations are not promoted to typical merely because they are old or widespread in the project.

## Legacy behavior and residual risk

An old system/release is evidence of AS-IS behavior, not an automatic TO-BE specification. For each material legacy behavior classify it as `REQUIRED_AS_IS`, `INTENTIONAL_CHANGE`, `KNOWN_LIMITATION_ACCEPTED` or `UNKNOWN`.

A consciously accepted limitation remains a residual-risk contract, not PASS. Record its trigger condition, consequence, acceptance owner, effect on acceptance criteria and whether the new change must preserve, mitigate or leave it explicitly unresolved.

## Evidence boundary

These contracts do not prove concrete 1C/BSP/Cleverence APIs, target-release behavior or project facts. Exact target/typical/BSP/vendor source and runtime evidence remain required where the existing skill gates require them.
