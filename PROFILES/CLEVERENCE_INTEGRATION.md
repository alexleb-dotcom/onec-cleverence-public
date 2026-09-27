# PROFILE — CLEVERENCE_INTEGRATION

## Detection

- 1C ↔ Cleverence field mapping
- Cleverence Business Process settings
- Core/Integration hooks
- loader/writer/grouping/search rules
- document header/line contract
- CurrentItems exported back to 1C
- a business applicability decision is inferred from Business Process/document/operation/action identity
- the same derived business Boolean/classification is computed independently in 1C and Cleverence

## Mandatory checks

- when loader/writer/router/BP behavior is uncertain, inspect the nearest stock Cleverence implementation before custom integration logic;
- determine effective active BP, not merely files present in export;
- trace producer → exact field declaration/name/type → mapping → Mobile field → mutation/writer → export → grouping/search → 1C consumer;
- compare field identifiers exactly. Similar spelling, transliteration or Cyrillic/Latin confusables do not establish the same contract;
- preserve native types and identity fields;
- verify one-plan-line-to-many-fact-lines behavior;
- verify repeat load/retry/partial failure;
- prove all **applicable** Mobile writer paths for a changed exported fact field, not only one writer found during source search;
- search standard Cleverence Core/Integration hook before full custom path;
- name the authoritative business applicability decision/source separately from the technical route that consumes it. A Business Process ID/name, `DocumentTypeName`, Operation/Action identity or UI route proves execution/routing context, not automatically business applicability. Treat route identity as the business predicate only when exact requirements/target source prove that equivalence and its lifecycle;
- when the same derived business decision is needed in 1C and Cleverence, name its authoritative owner/source. Prefer transmitting the explicit decision or authoritative raw inputs through the existing supported integration contract. If both systems recompute it, prove input parity, semantic equivalence, boundary/default cases and which source/version change forces revalidation;
- keep project-specific mapping decisions in project context, while universal contract rules remain in skill.

## Business predicate ownership model

Preferred shapes:

```text
authoritative business source
→ derive decision once
→ map/transport decision
→ technical route consumes it
```

or, when recomputation is justified:

```text
authoritative source inputs
→ 1C predicate implementation
→ semantic-equivalence contract
→ Cleverence predicate implementation
→ shared acceptance matrix + dependency/revalidation triggers
```

Do not use this shortcut without evidence:

```text
"this Business Process/document/operation currently handles the scenario"
→ therefore
"its ID/name is the business rule"
```

A route may change while business applicability stays the same, or multiple routes may implement the same business scenario.

## Completion rule

Cross-system tasks are incomplete if only the 1C side, only the MSLX side, or only the field declaration was validated. The same exact field/decision must be traced through the effective producer/writer/BP/consumer chain, and any derived cross-system business predicate must have an explicit authoritative owner or proven semantic-equivalence contract.
