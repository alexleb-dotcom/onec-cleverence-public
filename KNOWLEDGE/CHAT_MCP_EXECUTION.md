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

## Capability availability and legacy fallback

Use this decision order for project Source acquisition/navigation:

1. Compatible bounded capabilities available: MUST use them. Do not ask the user to upload/provide the project module, file or archive as an alternative discovery path, and do not prefer attachments over the admitted project Source.
2. Wrong admitted project/artifact/scope: report/reroute the existing admission/project lifecycle gap. Do not ask for copied Source.
3. Capability absent/failing/error/timeout/schema mismatch: this is not authorization for legacy source requests. Report the exact capability blocker. If useful, ask only whether the user explicitly wants to continue without MCP; do not request Source yet.
4. Only after explicit user instruction that MCP cannot/should not be used may the legacy exact-source request/file/archive workflow run. Then request only the smallest sufficient material and preserve SOURCE_FIRST and MANUAL_SKILL_EXECUTION honesty.
5. If evidence still cannot be obtained, report the exact evidence gap.

If bounded read capabilities exist but proposal capabilities do not, read/evidence work must still use the bounded Source path. Proposal delivery may remain pending/manual; read capability never implies write capability.

Do not substitute unrelated unbounded execution or generic mutation capabilities for missing bounded source/proposal authority.

## Proof boundary

Context binds session identity. Search returns candidates. Exact read may support SOURCE_REQUIRED evidence when provenance matches the bound baseline. Proposal write/read-back proves proposal delivery state only. None of these operations by themselves establish release/runtime PASS beyond existing canonical owners.

A connector rename or namespace change does not alter this contract when equivalent bounded semantic capabilities and provenance/CAS guarantees remain present.
