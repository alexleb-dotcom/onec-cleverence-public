# Requirements Discovery / Functional Contract

This layer exists **before technical design**. It is derived from real requirement-review practice, but it is adapted for development: no 0–100 scoring, no formal LT report, no mandatory “business vs IT customer” question.

## Goal

A technically correct implementation of the wrong/underspecified behavior is still a defect. Before BSP/typical-code discovery, reconstruct enough of the functional contract that two competent implementers would not choose materially different business behavior.

```text
TASK / SOURCE EVIDENCE
→ REQUIREMENTS CONTRACT
→ REQUIREMENTS GATE
→ only then TECHNICAL DISCOVERY / DESIGN
```

## Functional contract spine

Trace:

```text
need / problem
→ observable target outcome
→ target behavior + rules
→ process / actors / states when relevant
→ data lifecycle + source of truth
→ scope / assumptions
→ acceptance oracle
```

For cross-system work extend it to:

```text
trigger
→ input source + semantics
→ mapping / method / message
→ response/output semantics
→ validation/transformation
→ persisted/consumed use
→ retry/idempotency/partial failure
→ final state in every system
→ acceptance
```

A named API/endpoint/method plus a field list is not a complete functional requirement.

## Evidence-first questioning

Do not turn discovery into a generic questionnaire. First infer from:

1. current user/task text;
2. actual source/metadata/process implementation;
3. already-proven project context;
4. typical/vendor behavior when the requirement explicitly relies on it.

Then ask only `OPEN` questions that can materially change behavior, ownership, scope or acceptance. Prefer a small batch of precise questions such as:

- “On repeated import, replace the existing result or merge with it?”
- “Is packaging part of business identity or only quantity representation?”

Do not ask “clarify roles/process/data” when a concrete gap can be named.

## Risk-scaled depth

### R0_LOCAL

Require only:

- need/target change;
- what must not change;
- observable acceptance.

### R1_CONTRACT

Add:

- business/system invariant;
- source of truth;
- stable identity where relevant;
- scope and assumptions;
- acceptance matrix/cases.

### R2_STATEFUL_RUNTIME

Add:

- initiator/roles/rights;
- trigger/preconditions;
- states/transitions;
- repeat/re-entry;
- concurrency when material;
- lifecycle/data ownership;
- errors/alternative paths.

### R3_CROSS_SYSTEM

Add the complete integration functional contract:

- producer/input source;
- mapping and semantic transformations;
- receiver/output use;
- authorization/pagination/async/timeouts when material;
- retry/idempotency/partial failure;
- final state in all systems;
- end-to-end acceptance.

## Analogy rule

Technical analogs are mandatory evidence when implementation behavior is uncertain. But “make it like X” is **not itself a business requirement**.

For an analogy state:

- what exactly is reused (input, rule, UI, result, data/error contract);
- what differs;
- what adaptations are required;
- whether the current source exposes the same required data.

## Obligation / artifact separation

When one task statement names several platform effects, keep them as separate obligations until each is traced to its own observable artifact/acceptance. Similar wording or visual proximity is not equivalence. For example:

```text
metadata/subsystem membership
≠ command/navigation visibility
≠ form group placement
≠ form data binding
≠ persistence of the edited value
```

A change that satisfies one row must not silently close the others. During technical discovery map each obligation to the actual owning artifact/mechanism, then prove all rows in acceptance/delivery closure. This is especially important for extension work, where metadata overlay, inherited form structure and runtime form data may belong to different serialized/runtime contracts.

## Acceptance oracle

Acceptance proves correctness, not merely execution.

Every important case should have:

```text
preconditions + test data
→ actions
→ observable result
→ independent correctness oracle
```

For piecewise/multi-field rules use a truth/case matrix before BSL/MSLX code. Acceptance cases should later become runtime/regression cases where possible.

## Scope and assumptions

An algorithm-affecting restriction is a contract, not a comment. Record in-scope/out-of-scope behavior, material versions/contours/dependencies and assumptions.

Unknown business decisions may not silently become technical assumptions. An assumption must have:

- statement;
- impact;
- validation plan;
- explicit classification as non-blocking.

If the assumption decides business behavior, the requirements gate remains blocked.

## Data lifecycle questions

For each significant datum prove as applicable:

- source and semantic meaning;
- owner/source of truth;
- plan/fact/derived/representation role;
- stable business identity;
- transformations;
- storage/transmission/consumption;
- later writers;
- behavior on source change/repeat;
- duplicate/conflict resolution.

This directly complements `BUSINESS_IDENTITY`, `POST_WRITE_STANDARD_OVERWRITE`, `INVARIANT_SINGLE_OWNER` and Cleverence plan/fact rules.

## Do not over-specify requirements

Do not force module/procedure/query/internal call structure into the business/functional contract unless it changes an agreed obligation. If an unchanged typical mechanism has unambiguous behavior and the expected result is stated, its internals do not need to be restated as requirements.

## Outcomes

`TOOLS/requirements_gate.py` returns:

- `REQUIREMENTS_BLOCKED` — a blocking business/functional gap remains;
- `REQUIREMENTS_READY_WITH_ASSUMPTIONS` — only explicit non-blocking uncertainty remains;
- `REQUIREMENTS_READY` — functional contract is sufficiently evidenced for technical design.

These outcomes do not prove the technical design. They only authorize moving into it.

## Missing source evidence

Requirements discovery must distinguish a business question from a source-evidence gap. If an unanswered requirement can be resolved by a concrete existing artifact (document, metadata object, integration mapping, current operation/BP, handler source, protocol/log), inspect available sources first and then request the smallest missing artifact instead of asking the user to restate facts already encoded in the system.

A blocking source-evidence request remains `REQUIREMENTS_BLOCKED` until provided or independently resolved. If unavailable, preserve the limitation explicitly; never convert it into an assumption when it determines behavior, scope, ownership or acceptance. The core functional spine (`need`, `target_outcome`, `target_behavior`, `acceptance_cases`) is never `NOT_APPLICABLE`; exact task text stays hash-bound, accessible source files are rehashed at gate time, and a contract must cover the effective technical surface/risk before it can authorize design.

## Requirements artifacts are provenance-bearing deliverables

When the output itself is an LT/TZ/specification/requirements document, use purpose `REQUIREMENTS_ARTIFACT` and read `REQUIREMENTS_ARTIFACT_INTEGRITY.md`. Analysis-only mode does not relax the gate. Preserve the difference between observed/confirmed facts, evidence-backed derivations, unresolved choices and analyst/model proposals.

A concrete implementation idea is not automatically a requirement. Keep it as `PROPOSED_SOLUTION` until the current evidence chain independently confirms it. Likewise, an unresolved decision that can change quantity, money, tax, identity, cardinality, matching, source-of-truth, rights, state transition, external/irreversible side effects or compliance is blocking by materiality rather than by whoever happened to mark a Boolean flag.

If a user/source correction changes a material upstream claim, revalidate or invalidate dependent claims instead of editing only the visible paragraph. For R1+ requirements artifacts, attempt at least one structured counterexample against the functional contract before calling the artifact ready.
