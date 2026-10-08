# Q108 HTTPS Pull: candidate acceptance and matched rollout

Authority: [public #59](https://github.com/alexleb-dotcom/onec-cleverence-public/issues/59), including the accepted FA P1–P8/R1–R10 clarification. Reuses the mailbox state machine and fixtures from [draft #58](https://github.com/alexleb-dotcom/onec-cleverence-public/pull/58). No production deployment or Nendo live PASS is claimed here.

## Transport and state ownership

ChatGPT uses the unchanged six MCP tools. The existing Worker forwards to the existing `RelaySession` SQLite Durable Object. The admitted S4 helper makes outbound HTTPS POSTs to `/helper/pull/hello`, `/helper/pull/claim`, and `/helper/pull/result`. No persistent WebSocket is required for the active S4 transport. Legacy helper admissions retain their previous transport.

The accepted DO migration, namespace, `task:<admission>` rows, S4 functions, task/session/snapshot bindings, caps and TTL are preserved. Asynchronous KV is backed by the existing SQLite `__cf_kv` table; this is not a second database. See [Cloudflare storage documentation](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/).

An MCP invocation enqueues one bounded PENDING job with **no reserve**. Claim runs the real `reserveRequest`, internal checkpoint/context cursor enrichment and lease persistence in one storage transaction. Repeated claims return the same request ID/token, without reserve or execution. Result acceptance atomically stores the shaped MCP result, `commitRequest`, the actual sealed activity receipt, and a bounded ACK digest. The original accounting receipt fences old IDs even after transport retention ends.

An unclaimed deadline drops args and spends zero S4. A claimed deadline charges the reserved bytes once with `chargeAmbiguousRequest` and seals the real receipt chain. Hello validates every existing binding/cap through `reconcileTaskHello` on a validation copy; a live Pull reservation remains owned by its persisted lease. Genuine old orphan reservations use the existing fail-closed recovery/sealing functions.

The helper uses its existing processed-result file and `persistAndSendProcessed`. It persists execution intent before execution and the processed result before POST. After restart, a persisted result is replayed; an intent without a persisted result is reported as ambiguous and never reexecuted. Neither retry path changes admission/session/snapshot or resets accounting.

## Authentication and bounds

Private routes require the existing enrolled helper credential in an Authorization header, plus HMAC-SHA256 over method, path, timestamp, nonce and body digest. No new operator secret is created. The DO checks the full admission/session/snapshot/manifest/project/task tuple and the persisted helper instance ID. The instance ID is an internal identifier in the existing state file, not an operator-entered credential. Nonces are durable, one-use and bounded to 128 live entries. They remain stored through the complete signed timestamp validity window, including allowed clock skew (at most 120 seconds); business retries use fresh nonces and the same lease. Result ACKs require the exact identity/token/digest, including after a DO wake. URL credentials and query parameters are rejected on the new routes.

Only one active mailbox job and one active poll exist per DO. Public argument limits are unchanged: the prototype's 4096-byte argument default remains fixture-only, while production accepts a 262144-byte serialized argument envelope. Private claim/result bodies are capped at 12288 bytes, result payloads retain the existing 3000-byte S4 cap, and body/response reads have finite time and byte bounds. At most eight ACK digests are retained for 60 seconds; args disappear on terminal transition, and the terminal mailbox result is removed after 60 seconds. Authoritative S4 receipts are not removed.

MCP keeps its original 15-second deadline, starting at relay receipt and clipped to the existing task expiry. Poll holds at most 8 seconds, helper HTTP wait at most 9 seconds, idle pause 250 ms and network backoff 250–2000 ms. Result POST has at most four attempts bounded by the original lease deadline, with one finite late ACK query. Empty polls do not execute tools, reserve or charge S4, rewrite unchanged S4, or rewrite an unchanged mailbox. An alarm settles expiry and removes only transport retention.

Worst-case idle estimate for one helper: approximately 5237 polls per 12-hour admitted task, one nonce/liveness mailbox write per poll and up to 27 KV row reads per held poll (approximately 141399 row reads per task). Duration billing remains material: continuous polling can keep the DO active, so budget up to 128 MB times admitted active seconds rather than claiming hibernation savings. At 24h/day this is up to 331776 GB-s and approximately 314200 HTTP polls per 30 days, before model calls. Apply the account's shared included allocations and actual Worker/SQLite usage using [Cloudflare pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/). These are bounds/estimates, not a production bill measurement.

## Pre-install evidence

`TESTS/run_https_pull_native_regression.py` installs integrity-locked test packages in an OS temporary directory and executes native workerd with actual SQLite persistence. Its temporary worker adds isolated seed/inspect/fault routes; those routes are not in the production worker. Local network endpoints, provider config, Source/Output fixture and state files stay outside SHAREABLE_CORE. The harness executes the actual MCP handler, relay, helper execution/processed-cache code, filesystem provider and checkpoint store.

| FA gate | Candidate test evidence |
| --- | --- |
| P1 | Accepted-main SHA comparison of the complete six-tool definitions, plus native tools/list equality |
| P2 | All six actual MCP/relay/helper/provider/Output/checkpoint paths over Pull |
| P3 | 8192-byte proposal COMMITTED, exact bounded read-back/hash/provenance; bounded checkpoint file |
| P4 | Distinct IDs for identical model reads; duplicate claim/POST; semantic mutation replay/conflict and checkpoint CAS |
| P5 | 21-line structured INVALID_READ_ARGS, followed by successful context |
| P6 | Actual SQLite rollback, restart/wake, persisted cache, missing result, lost claim/ACK, stale lease, client disconnect, wrong identities, expiry |
| P7 | 9-second claim-response loss recovery, 151-second real idle, internal poll zero S4, per-call latency distribution |
| P8 | Existing transport/S4/activity/checkpoint and Product gates; exact-head Public Fast/UI/Full |

Run the security/S4 unit suite with `node PRODUCT/OneCChatWorker/tests/https-pull-security-regression.mjs`. The native acceptance entry is registered in Public Full. A green native test does not prove Windows process/UAC/reader-password or live Nendo behavior.

## RP/operator rollout boundary

1. Independently review the PR and exact-head Fast/UI/Full receipts. Check the candidate runtime lock, distribution digest, LF identities and unchanged accepted S4 module/migration/OAuth/tool definitions.
2. Before an approved matched deployment, read back current admission/session/snapshot/manifest, task expiry, accounting/activity cursor and one known Source SHA. Retain a secure rollback copy of the installed helper state/cache and the current exact helper/relay pair. Never publish those local files or credentials.
3. Stop new model calls and drain existing work. Require no unresolved RESERVED receipt. Do not STOP/START the Nendo task, mint an admission, clear cache, or reset S4 to install this transport.
4. Only after separate RP deployment approval, an authorized operator installs the matched helper+relay artifacts pinned in `runtime.lock.json`. Keep the existing namespace, SQLite migration, secret, OAuth configuration, admission and state files. Resolve genuine Windows elevation/reader credential prompts through the normal operator UI; Codex does not automate that boundary. The helper derives HTTPS from its existing admitted relay URL.
5. Verify authenticated Pull hello, unchanged lifecycle, internal poll readiness and zero idle S4 usage before live model calls. A missing accounting row during RPC/claim is fail-closed. Normal first/subsequent enrollment uses the same authenticated helper hello and real `createTaskRecord`/`reconcileTaskHello` owner as before: input identity must come from the existing operator-issued admission, prior rows are retained, and no active job can be displaced. The helper never manufactures a new admission, extends expiry, or automatically renews a task to make installation pass.
6. Run the accepted FA R1–R10 smoke once: exact six tools, context, one narrow search, four sequential 20-line reads on the former failing path, two contexts, >=150s idle and repeat read, safe 21-line error then context, one small Output canary write/read, and one fresh ordinary Chat context. Nominal budget: 13 current-chat calls plus one fresh-chat context. Check Source/snapshot/expiry and monotonic accounting/activity throughout. STOP on first failure and preserve evidence; no destructive packet-loss/cap/expiry tests on production.

## Safe rollback and remaining risks

Rollback is a separately authorized **matched helper+relay** rollback, never an automatic WebSocket fallback after a claimed request. Stop new calls, settle any current lease once, and wait for transport retention/alarm cleanup before restoring the prior pair. Preserve the exact existing DO/task rows, admission, credential and processed cache. The prior relay's normal hello recovery handles genuine unresolved old reservations; never delete them or replay uncertain writes blindly. The accepted main baseline was `fe8f96d177471371d277901c6a2eb010ca8c0717`; prior relay/helper hashes are recoverable from that commit's runtime lock. No merge/deploy/rollback is executed by this PR.

Remaining risks: live Cloudflare scheduling and network latency; actual Windows disk/process persistence and reader performance; account-wide duration/SQLite costs; prolonged outages exceeding the finite lease; hard failure between execution intent and cache persistence (deliberate fail-closed ambiguous charge); and disappearance/corruption of the enrolled helper's state file (requires operator recovery, no silent identity replacement). The unchanged checkpoint owner's 1350-byte recovery envelope can return `RECOVERY_PACKAGE_HARD_CAP` for unusually large mandatory summaries; this existing application limit is not widened or silently hidden by transport. The bounded checkpoint integration case uses near-cap optional semantic fields, whose normal truncation is supported by the existing recovery owner. Hard DO restart can terminate the in-flight client's HTTP connection while the durable lease/result remains recoverable. True exactly-once network delivery is not promised. Nendo functional PASS requires the independently approved live smoke after installation.
