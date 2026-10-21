# OneC Orbit #115 — S2-L1A trusted, read-only update decision gate

This is a foundation for automatic checks, NOT automatic checking in the running WPF UI yet.
It does not fetch GitHub, implement a background timer, install a program, move worker/data
roots, ask UAC, stop S4, or create/accept release metadata for the operator.

The file update/readonly_discovery.py is an offline pure byte-based decision engine.
A future background source obtains an out-of-band operator-approved immutable
index SHA-256, exact index bytes, a trusted installed identity and proof
that the release commit is reachable from approved protected main.
These authorities cannot be derived from arbitrary GitHub HEAD,
a downloaded package or a locally editable receipt. Unauthenticated network
input, absent authority, missing ancestry evidence, or missing installed pin
means hold/unknown for release status. Exception: independently provable
local EXE drift remains REPAIR_REQUIRED even if a separate snapshot pin is
missing. A newer main commit is not itself an approved update.

Index schema ONEC_ORBIT_APPROVED_RELEASE_INDEX_V1:
- exact repository alexleb-dotcom/onec-cleverence-public;
- immutable 40-character Git SHA-1 release_commit_sha;
- monotonic integer release_counter (no downgrade);
- gui_exe_sha256 and distribution_snapshot_sha256, full 64-hex SHA-256;
- no extra fields. Authenticate the exact whole index bytes against
  a separately trusted digest before parsing any fields.
  A client cannot derive its trust digest from its network response.

Independent decisions:
- Installed EXE differs from separately trusted installed EXE pin:
  REPAIR_REQUIRED / LOCAL_IMAGE_DRIFT, even if installed distribution
  snapshot pin is missing; never UPDATE_DETECTED. If EXE bytes are
  unavailable, HOLD/INSTALLED_IMAGE_UNAVAILABLE (no unproven repair claim).
- No approved index, invalid schema, digest mismatch or offline:
  RELEASE_UNKNOWN or HOLD; never UPDATE_DETECTED.
- Exact valid index equals installed trusted counter/commit/SHA AND
  the separately supplied release Git ancestry proof is exactly true:
  CURRENT **only when the separately trusted installed full-distribution
  snapshot SHA-256 also exactly matches the approved index snapshot identity**.
  A different approved snapshot with identical counter/commit/EXE means
  SAME_COUNTER_CONFLICT/HOLD, not CURRENT.
- If the independently trusted installed distribution snapshot SHA-256 is
  missing or malformed, HOLD: never claim CURRENT or UPDATE_DETECTED.
- Newer approved counter + different immutable commit and GUI image,
  PLUS proven approved chain: UPDATE_DETECTED status only.
- Release chain absent/unproven: HOLD for CURRENT and UPDATE_DETECTED,
  not just newer releases; exact byte-index digest alone is insufficient.
- Active operation/admission: DEFERRED, no install.
- Counter rollback, same-counter conflict, same-commit counter change,
  non-proven release ancestry: HOLD.

All results contain installation_permitted=false, update_invoked=false,
worker_or_s4_touched=false, even when UPDATE_DETECTED.

Tests use FAKE executable bytes/digests, never read installed EXE or
contact GitHub, and never inspect user projects. Native Windows CI must
run the tests without executing installer or updater.

Next gates:
- S2-L1B: define operator-approved release-publication/signature trust
  and protected-channel anchor rotation; no blind trust in branch HEAD.
- S2-L1C: wire startup + periodic background checks into WPF, with
  backoff/offline handling, compact RU/EN and accessible GUI status.
  Authenticate installed identity from access-controlled trust, not a
  user-writable receipt. Never hash Source, Main, Incoming, Output.
- S2-L2: detached exclusive update coordinator, multi-instance admission,
  graceful close, UAC cancellation, journal and rollback, adjacent
  verified launcher/Core, post-install exact readback. The current GUI
  UPDATE button is not a trusted self-updater.

NO permission for updating the user's installed OneC Orbit or
migrating C:\OneCChatWorker to C:\OneCOrbit.
