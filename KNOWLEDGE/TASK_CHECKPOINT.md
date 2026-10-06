# Durable semantic task checkpoint

TASK_CHECKPOINT_V1 is the product-owned semantic handoff for one logical project_id + task_id. It is separate from Source, Output proposals, S4 security accounting, local process execution checkpoints, machine receipts, validation ledgers, and hidden assistant reasoning.

## Canonical owners

- Semantic handoff storage: %ProgramData%\OneCChatWorker\task-state\<project_id>\<task_id>\.
- S4 request/result accounting and Activity: the existing relay task record and request_receipts.
- Current Source truth: accepted ProjectManifest snapshot / P-P-A / source_read.
- Proposal truth: admitted Output task plus proposal provenance/read-back.
- Local long-running command recovery: TOOLS/execution_checkpoint.py.

No second Activity journal, second Durable Object/storage namespace, database, daemon, transcript store, or generic checkpoint filesystem tool is permitted.

## Storage, privacy, and bounds

Each logical task has head.json and immutable checkpoints/<seq>-<hash>.json. The model never supplies a native destination path or canonical identity fields.

Hard bounds:
- canonical checkpoint <= 4096 UTF-8 bytes;
- model-authored semantic payload <= 2048 bytes;
- progress summary <= 640 bytes;
- first unfinished step <= 320 bytes;
- individual text item <= 192 bytes;
- completed steps <= 6;
- decisions/constraints <= 6;
- unresolved questions <= 4;
- do-not-replay items <= 6;
- assumptions requiring confirmation <= 4;
- source/proposal/machine refs combined <= 12;
- max committed versions retained per task = 16;
- default completed/abandoned retention = 30 days;
- retained payload target <= 64 KiB.

Store concise factual handoff state only. Never persist chain-of-thought, scratch reasoning, transcript text, token/logprob traces, secrets/credentials, unrestricted Source, unrestricted MCP payloads, or invented Chat identity.

## Write contract

task_checkpoint_write is the only model-facing checkpoint mutation. The model may author idempotency_key, expected_seq, expected_predecessor_sha256, bounded semantic state, and bounded identity-only Source/proposal/machine refs. Active admission injects project/task/goal/admission/session/snapshot/manifest identity. The relay injects the authoritative S4 Activity cursor immediately before the checkpoint request.

Write semantics:
1. validate active S4 admission and semantic caps;
2. acquire the authoritative pre-request S4 cursor;
3. bind a request fingerprint;
4. recover same-key prior state before mutation;
5. serialize local head mutation;
6. verify exact CAS head;
7. atomically commit one immutable checkpoint;
8. read back exact schema/hash/size;
9. atomically advance head.json;
10. read back head;
11. return a compact receipt.

First write uses expected_seq=0 and no predecessor hash. Every later write requires the exact current head seq/hash. There is no last-write-wins.

Same idempotency key plus same fingerprint returns the original receipt. Same key plus different fingerprint is IDEMPOTENCY_KEY_REUSE.

Interrupted writes are recover-first:
- no checkpoint file: exact retry may proceed;
- file committed/head not advanced: the same idempotent request may finalize only while the predecessor is still current;
- head advanced/response lost: return the original committed receipt;
- later head already exists: never move head backward;
- corrupt/ambiguous chain: CHECKPOINT_STATE_CORRUPT and fail closed.

## S4 Activity cursor and delta

The canonical Activity owner is the accepted S4 relay task record/request_receipts. The same owner may carry monotonic activity_seq, bounded safe request/result metadata, and receipt-integrity chaining. There is no parallel journal.

A recoverable checkpoint requires S4_ACTIVITY_CURSOR_V1 for its admission. A cursor-less semantic checkpoint cannot become recovery authority.

Activity metadata is safe identity/operation state only: admitted relative target/query identity, charged bytes, proposal commit/read-back state, error/recovery class, epoch, and receipt integrity. It never stores semantic checkpoint body, raw Source, raw unrestricted tool payload, or hidden reasoning.

## Recovery package

A fresh/recovered Chat calls source_context first. Recovery is:

latest verified compatible TASK_CHECKPOINT_V1
+
authoritative S4 Activity delta after its checkpoint cursor
=
RECOVERY_PACKAGE_V1

Compatibility values are CURRENT, SOURCE_SNAPSHOT_STALE, TASK_ADMISSION_STALE, TASK_GOAL_MISMATCH, SUPERSEDED, CORRUPT, and COMPLETED.

Within the hard result bound, preserve this priority:
1. active identity/accounting;
2. recovery compatibility and checkpoint;
3. critical Activity delta;
4. prepared quality if it still fits;
5. target hints if they still fit.

Prepared quality and hints may be dropped. Compatibility/stale reason, first unfinished step, and recovery_complete/truncated must not be silently omitted.

Source drift invalidates Source-dependent evidence and matching do-not-replay claims; it does not erase unrelated semantic history. Historical checkpoint statements are never current Source proof. Exact current Source/receipt/Activity owners win on contradiction.

For CURRENT, reconcile post-checkpoint Activity, continue first_unfinished_step, honor only still-valid do_not_replay items, and write a stable new checkpoint after recovery reaches a material state.

For SOURCE_SNAPSHOT_STALE, keep useful semantic history but reacquire the smallest invalidated exact Source and never reuse stale Source evidence as current proof.

TASK_ADMISSION_STALE and TASK_GOAL_MISMATCH are not silent-resume states. CORRUPT fails closed for semantic recovery. COMPLETED is terminal history. With no checkpoint, continue normal fresh-task flow.

Do not ask the operator to paste the old conversation when valid local recovery exists.

## Explicit Continue previous task

A logical task may outlive one finite S4 admission only through the explicit operator action Continue previous task. The model cannot choose predecessor IDs. Worker/Core verifies the current local checkpoint and creates a new finite S4 admission with the same project/task/goal and an explicit predecessor checkpoint/activity binding.

If Source identity is unchanged, the verified checkpoint may recover as CURRENT. If Source changed, recover as SOURCE_SNAPSHOT_STALE. If TaskGoal changed, do not treat it as the same task.

A semantic checkpoint never resets or extends S4 security budget. Every continuation admission has a new finite budget.

If required predecessor Activity is no longer retained, set recovery_complete=false with PREDECESSOR_ACTIVITY_UNAVAILABLE; do not invent a local Activity copy.

## Cadence and proof boundary

Write a checkpoint after material discovery/decision phases, blocker classification, proposal commit/read-back closure, stable recovery, before deliberate stop/re-admission or Chat replacement, before a long fragile operation when meaningful progress exists, and at terminal completion. Do not checkpoint every trivial call.

Pilot soft trigger: if semantic state changed since the last checkpoint, roughly 24 authoritative MCP activities, 24,000 charged result bytes, or 20 minutes of material work may trigger a checkpoint.

A checkpoint is a handoff note, not proof. It cannot establish current Source truth, MACHINE PASS, runtime PASS, release proof, or proposal-applied state. Referenced evidence remains owned by its canonical owner.
