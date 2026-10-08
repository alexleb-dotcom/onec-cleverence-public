# Relay/helper transport reliability (Q108)

This candidate addresses public issue #55 on baseline
`e73b5e60d0f79f65e71573af9aba581441bbae74`. It is not deployed and has
not passed a production live smoke.

## Evidence and choice

Production observations include both a completed helper result missing at the
relay and a request missing at the helper. The exact lost half-hop remains
unproven. Same-socket retransmission in PR #54 failed live smoke, so it cannot
establish that an idle connection is usable.

The baseline uses standard `WebSocket.accept()` and JS event listeners with a
memory-only helper reference. Cloudflare documents idle eviction of
non-hibernatable objects and termination of sockets at shutdown. The Hibernation
API preserves idle server sockets and runs class callbacks after reconstruction;
attachments survive that reconstruction. An active HTTP request and scheduled
timers prevent ordinary hibernation, so active RPC promises are not restored
from attachments. Actual shutdown still uses existing durable S4 orphan recovery.

References:
- https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/
- https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- https://developers.cloudflare.com/durable-objects/api/state/

Chosen solution:
- Accept with `state.acceptWebSocket`; handle message/close/error on the DO class.
  Restore only socket generation and successful-hello readiness from attachment.
  Do not reconcile admissions or replay hello on hibernation wake.
- Before S4 reserve, send a fresh application-level `transport_ping` nonce and
  require its `transport_pong` on that exact socket and generation within 2.5s.
  This exercises the helper message pump; a protocol-level automatic pong cannot
  prove that the application can receive/respond. No periodic heartbeat runs.
  Missing readiness fails with zero reserve, usage, activity or task renewal.
  Only this pre-reservation failure may retire the stale socket.
- Keep one RPC lane through probe, reserve, dispatch and durable accounting
  completion. Refuse replacement upgrades with HTTP 409 while it is owned.
  Ignore duplicate hello during that interval. Match results against socket,
  generation and request ID, including legacy transport.
- Keep the existing 15s post-dispatch deadline and the existing bounded identical
  frame retries. Send/close/error after reserve cancels timers and takes the
  existing ambiguous charge path once. An unsettled durable RESERVED receipt
  blocks another reserve until existing hello orphan recovery settles it.
- Helper answers the internal challenge in its existing serialized message pump.
  Request execution, processed-result persistence-before-send, caps and replay
  remain unchanged. OAuth, helper authentication, public MCP schema, S4 policy,
  Source acquisition, session/snapshot and TTL are unchanged.

## Verification

Run `python TESTS/run_relay_helper_transport_regression.py`. It runs production
relay/helper handlers with mocked Cloudflare facilities and virtual timers, plus
the existing retry, telemetry, helper persistence, S4 and checkpoint regressions.
The Public Full inventory executes this runner and fails if Node is unavailable.
The fixture provider never opens Source or contacts an installed helper.

The deterministic cases cover repeated idle reconstruction and sequential reads,
missing hello/pong, half-open/closed transport, stale nonce and generation,
wrong-socket/request-ID results, cached replay after request/result loss,
reconnect refusal while RESERVED and while committing, send/close/error failure,
timer cancellation, durable orphan recovery, commit-storage failure, unchanged
expiry/session and zero application/state work for transport probes.

## RP installation and live acceptance

RP must independently review the exact candidate commit and Public Fast/UI/Full
results. This document authorizes no deployment, installation, restart, merge,
new admission or change to credentials. A separate RP-approved rollout is needed.

1. Verify the candidate runtime lock and distribution manifest against Git LF
   bytes. Build the normal accepted distribution from this exact commit. Keep
   the previous accepted helper/relay generation and current helper state for
   rollback. Do not delete or recreate Durable Object storage or helper state.
2. At a separately approved maintenance boundary, confirm there is no pending
   RPC or RESERVED receipt. Install the matching helper candidate using the
   normal maintainer-approved package/update flow, then release the matching
   relay under RP authority. The new relay needs the probe-capable helper;
   an old helper fails before reserve instead of consuming S4 budget.
3. Preserve the existing authorized task/session/snapshot. Do not mint an
   admission for this smoke. If it is expired/exhausted, report that prerequisite
   to RP; do not silently renew it. Record accepted generation hashes, expiry,
   usage and activity cursor before testing. Allow existing orphan recovery to
   settle any earlier ambiguous receipt; never refund it.
4. After HELLO_ACK, run four sequential bounded `source_read` calls, then one
   `source_context`. Repeat a bounded read after at least 150s idle. In a new chat,
   request `source_context` and verify continuity on the same admission. Verify
   no HELPER_TIMEOUT, exactly one accounting receipt per executed call, a
   monotonic receipt chain, unchanged task expiry and unchanged Source snapshot.
   Approved offline/half-open negative testing must fail before reserve with
   unchanged usage; reconnect must preserve processed cache and existing charges.
5. Save correlated allowlisted relay/helper evidence without credentials or
   Source contents. Only this real smoke can support production PASS. On failure,
   stop further reads and let RP roll back the helper/relay pair at an idle
   boundary, preserving storage, session, admission and cache; do not reset S4.

## Remaining risks

Mocked lifecycle tests do not prove Cloudflare placement/network behavior or a
Windows rollout. A connection can fail after a successful probe; this still
charges ambiguously and fails closed. The probe adds one round trip and can fail
under helper queue delay; its 2.5s wait does not extend task TTL or the 15s RPC
deadline. Busy reconnect attempts receive 409 and use the existing helper
reconnect loop. Mixed helper/relay generations require a coordinated RP rollout.
True DO shutdown or durable storage failure may require existing orphan recovery.
