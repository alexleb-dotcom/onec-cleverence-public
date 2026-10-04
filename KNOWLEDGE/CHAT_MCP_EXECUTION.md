# Capability-based bounded Chat execution

Use this conditional owner when the runtime exposes bounded project source and/or proposal capabilities. Route by semantic capability, not by connector/app/namespace name. Example operation names describe semantics; an equivalent bounded connector may use different names.

This adapter does not replace SOURCE_FIRST, Project Context, requirements/release gates, result delivery, or MANUAL_SKILL_EXECUTION.

## Read flow

1. Call source_context (or equivalent bounded context capability) first.
2. Verify active project, participant, artifact/source roots, source snapshot/baseline, admitted task, status and caps.
3. Preserve that identity on every later evidence claim.
4. source_search is narrow candidate discovery only; a hit is not proof.
5. source_read supplies exact current evidence. Keep reads narrow and preserve returned provenance.
6. Respect caps rather than widening reads to bypass targeted evidence acquisition.

If the active project/session is wrong, stop this path and return to the existing manager/admission/project lifecycle. Never invent an arbitrary project/root switch.

## Proposal flow

Source remains immutable. Proposal capability is Output delivery, not permission to mutate Source.

1. proposal_write may target only the currently admitted Output task.
2. First create uses a stable semantic idempotency key.
3. Replace/update requires the exact prior returned SHA-256 or equivalent expected-hash/CAS identity.
4. An ambiguous or interrupted write leaves completion UNKNOWN. Use proposal_read/native recovery inspection first; never blind-replay the write.
5. Every successful or possibly-successful write is followed by proposal_read read-back verification.
6. Verify machine provenance, proposal hash/identity, and binding to the exact source_snapshot/participant/artifact/task.
7. PROPOSAL_NOT_APPLIED means the proposal was not applied/deployed to business Source.

## Capability absence

- If bounded tools are absent, do not pretend they ran. Use MANUAL_SKILL_EXECUTION or report an explicit execution-capability blocker; machine/runtime proof remains pending.
- If bounded reads exist but proposal capabilities do not, read/evidence work may proceed while proposal delivery remains pending/manual.
- Do not substitute unrelated unbounded execution or generic mutation capabilities for missing bounded source/proposal authority.

## Proof boundary

Context binds session identity. Search returns candidates. Exact read may support SOURCE_REQUIRED evidence when provenance matches the bound baseline. Proposal write/read-back proves proposal delivery state only. None of these operations by themselves establish release/runtime PASS beyond existing canonical owners.

A connector rename or namespace change does not alter this contract when equivalent bounded semantic capabilities and provenance/CAS guarantees remain present.
