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

## S4 task continuity and accounting

Treat the admitted **task**, not the transport connection, as the durable security boundary.

`source_context` is the compact authoritative lifecycle view. When S4 fields are present, preserve the opaque `task_admission_id`, stable `session_id`, `task_state`, task creation/expiry, internal `epoch_id` / `epoch_seq`, `continuation`, relay-owned durable request/byte usage and remaining budget, epoch soft usage/limits, and `max_result_bytes`.

Epoch rollover or reconnect is transport continuity only. It must not change task admission, stable session, project/task, manifest/snapshot identity, expiry, or durable usage. Do not ask the operator to renew a normal task merely because an epoch soft quantum ended while durable task budget remains.

If task accounting is unavailable or ambiguous, fail closed rather than assuming zero. If the durable budget is exhausted/expired or the bound snapshot/manifest changed, data-bearing work stops and operator re-admission is required. An exhausted control-only context may expose lifecycle/accounting only; it must not expose Source snippets, target hints, or prepared quality.

For ambiguous requests, especially `proposal_write`, recover current authoritative state before any replay. A generated/committed/ambiguous result remains charged according to the relay contract even when response delivery fails.

## Durable semantic checkpoint and recovery

When `task_checkpoint_write` is exposed, read `KNOWLEDGE/TASK_CHECKPOINT.md`. The accepted model-facing surface is exactly six bounded operations: `source_context`, `source_search`, `source_read`, `proposal_write`, `proposal_read`, and `task_checkpoint_write`. There is no checkpoint-read or generic filesystem capability.

A fresh/recovered Chat calls `source_context` first. If it returns `RECOVERY_PACKAGE_V1`, verify compatibility and active project/task/goal/snapshot identity before using semantic history. For `CURRENT`, reconcile the authoritative S4 Activity delta, continue `first_unfinished_step`, and avoid only still-valid `do_not_replay` work. After recovery reaches a stable material state, write a new checkpoint with exact current-head CAS.

`SOURCE_SNAPSHOT_STALE` preserves useful semantic history but invalidates Source-dependent evidence/do-not-replay state; reacquire the smallest exact current Source required for the next step. `TASK_ADMISSION_STALE` and `TASK_GOAL_MISMATCH` are not silent-resume states. `CORRUPT` fails closed for semantic recovery. `COMPLETED` is terminal history, not a new unfinished step.

Write `TASK_CHECKPOINT_V1` after material discovery/decision phases, blockers, proposal commit/read-back closure, stable recovery, before deliberate stop/re-admission or Chat replacement, before a long fragile operation when meaningful semantic progress already exists, and at terminal completion. Do not checkpoint every trivial call and never store hidden reasoning/transcript/secrets/raw unrestricted Source or tool payloads.

The checkpoint is not evidence authority. Exact Source, proposal/native receipts, S4 Activity, process execution checkpoints, machine receipts, validation ledger and release owners still decide their own properties. On contradiction those canonical owners win.

`Continue previous task` is an explicit operator action. It creates a new finite S4 admission bound to the verified predecessor checkpoint/activity cursor. The model cannot choose predecessor IDs, and a semantic checkpoint never resets or extends security budget.

## Prepared quality consumption

`source_search` remains candidate discovery only. `source_read` remains the exact current Source evidence operation and the only accepted target-binding trigger for local quality preparation.

`META_INFO` and `FORM_INFO` prepared projections are `SUPPORTING_DETERMINISTIC_SUMMARY`. Use a fresh projection to avoid repeatedly reparsing large XML solely to reproduce the same deterministic structure. It is not semantic or runtime authority. Read raw exact Source whenever semantic reasoning, change design, declaration/signature/context, or contradiction resolution requires it.

`FORM_VALIDATE` prepared projection by itself does **not** create MACHINE PASS. MACHINE evidence is available only when the corresponding full `LOCAL_QUALITY_REPORT_V1` is canonically verified through the existing `TOOLS/machine_receipts.py` owner for the exact registered property. The full report must remain fresh for the exact project/P-P-A/task/stable session, source snapshot, manifest SHA, confirming `source_read` SHA, exact input-closure digest, adapter contract, upstream/script pin, overlay identity, and report SHA.

A canonical `OK` receipt proves only the exact validator-owned deterministic property registered by the receipt owner. `FINDINGS` map only to properties the validator actually proves; they are not generalized semantic defects. Adapter/input/integrity/timeout/source-drift/normalization/tool-exit errors are never Source findings and never PASS.

Epoch rollover alone does not stale prepared evidence because stable task/session/source identity is unchanged. Any drift in task or stable session, project/P-P-A target, snapshot, manifest, confirming file SHA, exact input closure, adapter/tool/script/upstream/overlay/report identity makes the prepared evidence stale. If prepared evidence contradicts exact current Source, Source wins and the prepared evidence is stale/defective/pending.

Prepared quality reduces deterministic parsing work; it never replaces SOURCE_FIRST or the existing review/validation/release owners.

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
