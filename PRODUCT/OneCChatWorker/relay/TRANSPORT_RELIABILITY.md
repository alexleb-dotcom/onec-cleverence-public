# Relay/helper transport reliability (Q108)

Candidate from accepted PR #56 merge
`7af5073a23e4be8e86ac04c42fb6db427d491bd7`. No candidate deployment or
production reliability PASS is implied by this document.

## Evidence and confidence

**Proven defect:** after sending a durably cached result the helper awaits
RESULT log append in its execution message pump. UI projection writes and
HELLO_ACK logging occupy that same pump. The relay returns a successful context
while advisory disk I/O still holds the pump. The next application ping queues
behind that I/O, expires at 2500ms, and closes a healthy transport with
HELPER_OFFLINE before reserving the next read.

The production-handler regression first failed `503 != 200` with delayed RESULT
logging after context. UI projection delay reproduced the same mechanism.
Local workerd plus native Node WebSocket reproduced both failures on exact #56
code with 2600ms advisory stalls. The candidate reads return HTTP 200 during
both stalls. This proves a mechanism rather than assuming the timeout is short.

**Attribution to the production incident remains unproven.** Existing sanitized
receipts show a read RESERVED, helper OK result in about 1093ms, then
AMBIGUOUS_CHARGED / RECONNECT_WITH_UNRESOLVED_RESERVATION. Earlier and following
context receipts are COMMITTED. Zero-reserve probe failure cannot explain that
read's charge. Installed helper SHA matches #56; one helper process was found.
No correlated relay trace proves where the dispatched result was lost or
whether another invocation produced the reported HELPER_OFFLINE. No additional
S4-consuming production calls were made in this iteration.

Confidence is high in the reproduced queue/listener defects, limited in their
attribution to this incident. This PR does not claim to cure every lost-result
case. RP must correlate live probe, dispatch, helper result and terminal receipt.
Do not label the existing ambiguous charge a pre-reservation violation or refund it.

## Correction and invariants

- Move advisory RESULT/CONNECTED/HELLO logging and UI projection writes onto
  one ordered best-effort helper lane shared across reconnects. Advisory failure
  cannot poison execution; a delayed projection can leave the UI temporarily
  stale while authoritative receipts remain in relay storage. Retain at most
  64 queued log entries and one latest pending projection; coalesce superseded
  projections and drop excess best-effort logs under sustained disk delay.
- Keep requests, cached replay, execution, processed-state persistence and
  ping/pong in the original serialized execution lane. A pong still waits for
  authoritative execution/persistence. Persistence failure still stops the
  connection via the existing fatal/fail-closed path.
- Install message/close/error listeners before hello or CONNECTED logging so
  immediate ACK, probe, request or close cannot be missed during disk I/O.
- Mark failed-probe attachment `ready:false` before retiring the socket. If
  close throws and the host socket remains OPEN, wake cannot restore old readiness.
- Correlate probe_started/ready/expired/not_ready/disconnected/send_failed using
  the existing 12-hex opaque request key, generation and elapsed time. No nonce,
  credentials, URLs, Source paths/content, request args or results enter traces.

Retain Hibernation acceptance/class callbacks and attachment recovery, RPC lane
ownership through commit, 409 reconnect refusal while owned, exact socket/
generation/request matching, 2500ms probe, 15s deadline and bounded identical
frame retries. Actual shutdown retains durable orphan recovery. S4 policy,
limits, TTL, admission/session/snapshot, Source acquisition/immutability,
AuthZ/OAuth and the public MCP schema remain unchanged.

Cloudflare references:
- https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/api/state/

## Verification

`python TESTS/run_relay_helper_transport_regression.py`: 21 lifecycle, 6 retry,
6 telemetry, 8 persistence, 36 S4 and 18 checkpoint checks. Public Full runs this
deterministic suite without live helper or Source. New cases cover delayed
advisory I/O after context, immediate messages during CONNECTED logging,
authoritative persistence holding pong, delayed/late pong, reconnect during
probe, failed-close attachment wake and advisory rejection/order across reconnects.
The advisory-backlog case proves bounded buffering and latest-projection retention.
Existing cases preserve single reserve/charge, cache, orphan recovery, storage
failure protection, expiry and identities.

An opt-in host integration runs the production relay class/helper handler in
local workerd, native Node WebSocket, SQLite fixture storage and synthetic
execution. Install dependencies in a separate scratch directory:

```powershell
npm install --prefix <scratch> miniflare@5.20261006.0-alpha esbuild@0.28.2 --no-audit --no-fund
node TESTS/run_relay_helper_workerd_regression.mjs <scratch> --baseline
node TESTS/run_relay_helper_workerd_regression.mjs <scratch>
```

Pinned Miniflare is an alpha test dependency, not a deployed component; workerd
is `1.20261006.1`, compatibility date `2026-10-01`. Baseline PASS means expected
reproduction of HTTP 503 on both stalls; candidate PASS requires HTTP 200.
Five host checks include context/read/context, 12s idle with a persisted test-only
constructor counter proving reconstruction, and reconnect with retained cache
and no RESERVED. This opt-in integration is separate from standard Public gates.

## Independent RP rollout and rollback

This candidate authorizes no merge, deploy, installation, restart, STOP/START,
reset or admission remint. RP reviews exact head/green CI, then separately
approves a matched helper/relay maintenance window.

1. Verify runtime lock/distribution identities against staged Git LF bytes.
   Build the normal package from exact accepted candidate. Record actual helper
   hash and new Worker Version ID from rollout receipts.
2. Verify current rollback pair afresh: #56 helper SHA256
   `1835dc673f902c9682d1f2b9747fcef96415c8df81798d70b358cb63de5d6343`,
   Worker `onec-g1q1-relay`, Version ID
   `18d1a864-b461-4302-aaa5-9ed6a32d06a8`. Preserve credentials, runtime state,
   processed cache, admission/session/snapshot/expiry and Durable Object records.
3. At approved idle maintenance verify no pending RPC or canonical RESERVED
   receipt. Cached UI projection cannot prove current absence of RESERVED; use
   the existing authorized canonical status/receipt owner. Resolve orphan only
   through normal fail-closed hello recovery. Use canonical package
   `UPDATE -SkipDependencies`, relaunch under existing reader identity with
   human-only credentials/UAC as needed, then deploy matched accepted relay via
   existing Wrangler. Do not START/CONTINUE or change identities for smoke.
4. Verify one helper, expected hashes, HELLO_ACK and Worker version. Old #56
   helper is pong-compatible but retains the queue defect; relay-only rollout
   does not install this correction.
5. On rollback, inspect receipts at approved idle boundary, restore exact #56
   relay Version ID and helper package using existing release/installer flow,
   then reconnect normally. Restore code only; never overwrite runtime state
   with older backup, clear cache/DO records, refund or recreate admission.
   Human credentials remain local. Record both rollback generation receipts.

## Exact live smoke after separately approved installation

Before EACH call confirm ACTIVE, same admission/session/snapshot, unexpired
TTL, remaining caps, monotonic accounting and no unresolved RESERVED. The task
may expire before acceptance; no silent renewal. Capture allowlisted correlation
through existing authorized observability without changing settings or exposing secrets.

1. One `source_context`: tool/HTTP OK, helper_online not false, control_only
   not true; record identities, expiry, usage and activity cursor. Offline control
   context alone does not prove transport readiness.
2. Four sequential `source_read` calls on the same currently admitted module:
   lines 1–20, 21–40, 41–60, 61–80. Obtain canonical path from the active task,
   never synthetic or widened scope. Each invocation gets one receipt and +1
   request; resends must not get extra reserves.
3. Two `source_context` calls; at least 150s idle then one bounded read; a
   brand-new ordinary chat `source_context` on the SAME task/admission without
   STOP/START. Compare identities, expiry, monotonic chain, usage and retained cache.
4. On HELPER_OFFLINE, HELPER_TIMEOUT, ACCOUNTING_ERROR or uncertain receipt,
   stop spending S4. Preserve last context/receipt and bounded correlation:
   probe key/generation/outcome -> dispatch -> helper RESULT -> matched/unmatched
   frame -> deadline/reconnect/terminal receipt. Expired probe means zero reserve;
   lost dispatched result means one fail-closed ambiguous charge. Continue local
   engineering; no mass retry, reset/remint, refund or automatic production PASS.

Only RP grants real acceptance after smoke. Remaining risks: network/process/DO
shutdown after pong, Windows stalls in authoritative persistence, storage failure
and stale advisory UI. Local workerd does not prove production placement or the
precise original lost-result cause.
