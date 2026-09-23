# PROJECT CONTEXT LIFECYCLE — durable decisions without stale truth

`PROJECT_CONTEXT` is durable project state, but durable does not mean immutable or eternally true. A later explicit user decision, newer authoritative target evidence, changed baseline/version, or expired temporary approximation can supersede or invalidate an earlier project decision.

This contract applies to **project-specific mutable decisions/facts**. It is separate from `KNOWLEDGE/SKILL_FRESHNESS.md`, which tracks the version of the universal skill itself.

## Core invariant

A historical decision must never remain silently active after stronger/newer project evidence contradicts it.

```text
new explicit user decision / newer authoritative source
→ detect conflict with current decision_key
→ SUPERSEDE or INVALIDATE old decision
→ keep history as provenance
→ use only the current evidenced decision in new work
```

Do not solve this by deleting history. The objective is to distinguish **current truth** from **historical provenance**.

## Decision record

For every material project decision likely to be reused across tasks, keep a record equivalent to:

```json
{
  "id": "PROJECT_DECISION_001",
  "decision_key": "warehouse.osu.applicability",
  "claim": "Business statement used by later tasks",
  "status": "ACTIVE",
  "scope": "where this statement is valid",
  "established_by": [
    {"kind": "USER_DECISION", "ref": "conversation/task reference"}
  ],
  "evidence_dependencies": [
    {"kind": "SOURCE", "id": "target-baseline", "fingerprint": "..."}
  ],
  "decision_dependencies": [],
  "supersedes": [],
  "superseded_by": null,
  "temporary_reason": null,
  "replacement_criterion": null,
  "revalidation_triggers": [],
  "status_reason": null,
  "last_revalidated": null
}
```

Use one stable `decision_key` for one mutable topic. This allows a newer decision to replace an older decision without confusing differently worded statements as unrelated facts.

## Status model

Allowed statuses:

```text
ACTIVE
TEMPORARY
REVALIDATION_REQUIRED
SUPERSEDED
INVALIDATED
```

### ACTIVE

Current evidenced project decision. It may be relied on inside its stated scope while its evidence dependencies remain valid.

### TEMPORARY

A consciously accepted approximation/proxy/constraint. It is current only within its explicit scope and must contain:

- `temporary_reason`;
- `replacement_criterion`;
- at least one `revalidation_trigger`;
- the known risk or scope distortion in the claim/scope/reason.

Examples of temporary decisions include using a broader technical condition because the authoritative business signal is not yet available, or freezing a workaround until a target vendor version changes.

`TEMPORARY` must never be normalized to `ACTIVE` merely because it survived several chats or releases.

### REVALIDATION_REQUIRED

The previous statement may still be correct, but one of its dependencies changed or a trigger fired. Do not use it as current proof until revalidated.

### SUPERSEDED

A newer decision for the same topic replaces it. Keep the old record for provenance and link both directions:

```text
old.superseded_by = new.id
new.supersedes contains old.id
```

A superseded decision is not active project context.

### INVALIDATED

Evidence proves the old statement wrong or no longer applicable and no direct replacement is established. `status_reason` is mandatory.

## Conflict and precedence handling

When a new material statement conflicts with existing project context:

1. identify the same `decision_key`/business topic;
2. compare evidence authority and recency;
3. never keep two conflicting `ACTIVE`/`TEMPORARY` decisions for the same key;
4. if the new statement replaces the old one, mark the old one `SUPERSEDED` and link the records;
5. if the old statement is disproved without a replacement, mark it `INVALIDATED`;
6. if decisive dependency evidence changed but the answer is not yet known, mark the current decision `REVALIDATION_REQUIRED`;
7. update downstream decisions that explicitly depend on the changed decision.

A newer chat message does not automatically outrank target source for a platform/runtime fact. Evidence authority still follows the skill hierarchy. Conversely, an explicit user decision **does** control project business policy when it is the authoritative source for that policy.

## Evidence dependency invalidation

A mutable project decision should name the evidence whose change can make it stale.

When an evidence dependency with the same `{kind,id}` gets a different fingerprint/version:

```text
ACTIVE/TEMPORARY decision
→ REVALIDATION_REQUIRED
→ invalidate only dependent project claims/proof
→ inspect the new evidence
→ restore ACTIVE/TEMPORARY, SUPERSEDE or INVALIDATE
```

Do not re-bootstrap the entire project because an unrelated source changed.

## Temporary approximation discipline

A temporary technical proxy is not a business invariant.

Forbidden transformation:

```text
"for now use DocumentTypeName/BP name/route X"
→ later chat
→ "project rule is X"
```

Required representation:

```text
business rule: authoritative meaning
technical approximation: what is currently used
status: TEMPORARY
known mismatch/broader/narrower scope
replacement criterion
revalidation trigger
```

This applies to route IDs/names, document-type names, hard-coded version checks, temporary mappings, fallback constants, manually maintained lists and other proxies.

## Business predicate vs technical route

A Business Process ID/name, document type, operation/action ID, UI route or handler identity proves **where code is executing**, not automatically **why the business behavior applies**.

If a technical route is used as the business applicability predicate, exact project requirements/source must prove the equivalence and lifecycle. Otherwise keep the two concepts separate:

```text
business applicability decision
→ technical route consumes decision
```

For cross-system behavior, name the authoritative owner/source of a derived business decision. Prefer transmitting the explicit decision or authoritative raw inputs. If 1C and Cleverence recompute the same derived predicate independently, prove input parity, semantic equivalence, boundary cases and revalidation dependencies.

## Resume / refresh behavior

Before a substantive task that relies on durable project decisions:

- use only `ACTIVE`/properly scoped `TEMPORARY` decisions;
- do not use `SUPERSEDED`/`INVALIDATED` as current facts;
- resolve `REVALIDATION_REQUIRED` decisions before relying on them;
- inspect newer explicit user/project evidence that conflicts with the current decision;
- refresh only affected decision keys/dependencies, not the whole project context.

## Anti-bypass invariants

```text
TEMPORARY_COMPROMISE_PROMOTED_TO_INVARIANT
  a temporary proxy silently becomes permanent project truth

STALE_PROJECT_CONTEXT_REUSE
  an older decision continues to drive new work after its evidence/decision was superseded or invalidated

CONFLICTING_PROJECT_FACT_COEXISTENCE
  mutually incompatible current decisions remain ACTIVE/TEMPORARY for one decision_key

TECHNICAL_ROUTE_AS_BUSINESS_PREDICATE
  BP/document/operation identity is treated as business applicability without evidence of equivalence

CROSS_SYSTEM_PREDICATE_REIMPLEMENTATION
  the same derived business decision is independently reimplemented across systems without an authoritative owner or equivalence proof
```

The correct optimization is **targeted decision supersession/invalidation**, not forgetting history and not treating every past project statement as forever current.
