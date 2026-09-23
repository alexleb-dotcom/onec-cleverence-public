# Requirements artifact integrity

This contract applies when the task is to analyze, create, refine or approve an LT/TZ/specification/requirements artifact. `ANALYSIS_ONLY` is not an exemption: a wrong requirement can propagate into architecture, code and acceptance even when no source code is changed in the current task.

## Claim provenance

Every material statement that can change behavior, ownership, scope or acceptance must keep its provenance instead of being flattened into prose:

- `USER_CONFIRMED` — explicitly confirmed by the user/process owner in the current evidence chain;
- `SOURCE_OBSERVED` — directly observed in the supplied/current project source or artifact;
- `TYPICAL_RELEASE_PROVEN` — proven against the relevant official firm-1C release under `ONEC_TERMINOLOGY_CONTRACT.md`;
- `DERIVED_WITH_EVIDENCE` — derived from concrete evidence, with the derivation kept visible;
- `PROPOSED_SOLUTION` — a design/UX/technical proposal, not a requirement;
- `OPEN` — unresolved and not safe to state as agreed behavior.

A proposed button, register, form, field, handler, query, integration route or other implementation choice stays `PROPOSED_SOLUTION` until independently confirmed as a requirement or accepted design decision. Rephrasing a proposal as “the system must” does not change its provenance.

## Blocking material uncertainty

An unresolved decision is blocking when it can change quantity, money, tax, business identity, relation cardinality, match key, source of truth, rights, state transition, an irreversible/external side effect, an external contract or compliance behavior. Such a decision cannot be downgraded to a non-blocking assumption merely because implementation could proceed under one convenient interpretation.

Presentation-only preferences may remain non-blocking when they do not change business behavior, data ownership, acceptance or technical feasibility.

## Match-key completeness

When behavior depends on matching one business object/row to another, the requirement must define the exact matching dimensions or explicitly leave the decision blocking/open. It must also define the allowed relation cardinality and deterministic behavior for `0`, `1` and `N` matches where those states are possible.

Phrases such as “and other available analytics”, “etc.”, “by available fields” or “take the first suitable row” are not a complete business matching contract when the chosen match affects quantity, price, tax, ownership or another material result.

## Requirement correction invalidation

A correction to an upstream requirement invalidates every derived claim that depends on the old statement until each dependent claim is revalidated or explicitly invalidated. Editing one paragraph is not enough when old conclusions survive in field mappings, restrictions, acceptance cases, UI behavior or technical proposals.

Keep correction/revision events with the changed claim ids, dependent claims invalidated or revalidated, reason and evidence. A superseded claim is historical evidence, not current truth.

## Requirements-level adversarial validation

Before a non-trivial requirements artifact is called ready, try to falsify the functional contract itself. Use concrete counterexamples appropriate to the task, for example:

- no matching source, exactly one match, several matches;
- the same business fact selected/consumed twice;
- source/context changes between selection and write/use;
- two source rows are equally eligible but lead to different material results;
- repeat/re-entry after a partial result;
- an alternative or reverse path reaches a different owner/state.

The purpose is not to invent edge cases. It is to expose material choices that the current wording leaves ambiguous.

## Readiness boundary

A requirements artifact may be described as complete/ready only when the requirements gate is ready and all material claims are either proven requirements, evidence-backed derivations, explicitly separated proposals, or resolved/non-blocking gaps. Blocking `OPEN`, proposal-to-requirement laundering, vague material match keys, unresolved correction fallout and missing required adversarial cases keep the artifact blocked.

The readiness chain is:

`fact/evidence -> claim provenance -> agreed/derived requirement -> acceptance -> only then proposed solution/design`.

This contract defines evidence discipline. It does not prove concrete 1C/BSP/Cleverence API behavior or target-release behavior; those still require the existing source/evidence gates.
