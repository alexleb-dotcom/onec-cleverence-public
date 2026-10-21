# S2-L1B / ADR-01 — Release authority, publisher ceremony, anti-rollback

Status: **PROPOSED / OFF-PRODUCTION / DESIGN CHALLENGE**, not an operational
release mechanism. Control: private #115. Base protected main:
`4a0fb72a52e8188465c58e48a5f0024708dbff4d`. The independently accepted
`release_authority.py` and `release_git_tree.py` are offline reference
verifiers. This ADR creates no keys, release, installer, network call, or
installed-state trust record.

## Trust boundary and release identity

**Operator source of authority is NOT GitHub Release, an API response, a
downloaded JSON, a mutable branch, a self-hash, or the release publisher's own
metadata.** All positive discovery requires three *independently established*
inputs before interpreting an index: (1) initially trusted signer identity,
(2) operator-controlled protected-main approval, (3) trusted installed identity
and a monotonic minimum release counter. The existing composite verifier checks
cryptographic and Git-byte consistency **after** those inputs are established.
The runtime may not infer or bootstrap them from an untrusted response.

1. Initial key pin: operator supplies an independently validated trust bundle
   at first trusted installation, authenticated by a reviewed installer and
   separately pinned publisher identity. The bundle fixes repository, signing
   key ID, public RSA modulus/exponent (>=2048 bits), algorithm, and policy
   generation. There is no runtime download/install of signing key from the
   candidate release. Prefer OS CNG signature verification for deployed Windows
   product; Python reference remains off-production.
2. Private signing key: non-exportable, independently owner-controlled
   HSM/OS-protected signer kept outside GitHub repo, workflows, user projects
   and product distribution. A *synthetic* RSA key in tests is not a credential.
   Publisher CI cannot generate a trusted signature merely from successful
   build artifacts.
3. Protected-main release ceremony: an authorized human/operator reviews exact
   protected-main full SHA, release SHA ancestry, exact committed
   DISTRIBUTION_MANIFEST inventory, GUI EXE SHA256, and strictly increasing
   counter. A separate auditable approval record binds this context and the
   authorized approver. Signing service must verify a separate authenticated
   approval channel and protected-main origin evidence **before** signing.
   Merely querying GitHub API or checking Git ancestry cannot establish human
   approval or protected branch governance. Signed envelope uses the existing
   ONEC_ORBIT_SIGNED_RELEASE_AUTHORITY_V1 domain and exact approved-index bytes.
4. Publication: store immutable exact-byte signed envelope and approved index
   addressed by digest. Transport discovery is untrusted and may be unavailable;
   no response-derived signer root, minimum counter, or proof of main. No
   positive status if approval/attestation or chain proof is absent.
5. Rotation/revocation: a new key must be authorized by an authenticated
   already-pinned root plus an operator-approved policy-generation increment,
   before it can validate a release. Missing prior-root authentication,
   counter conflict, replay, revoked key, unknown policy generation, or a
   downgrade must return HOLD. Offline revocation freshness cannot be
   guaranteed from a stale downloaded list: define an OS-protected or online
   trusted freshness witness **before** enabling unattended release discovery.

## Installed high-water mark: explicit unsolved security decision

The installed baseline stores exact EXE SHA, commit SHA, canonical snapshot SHA,
release counter, signer key ID and trust policy generation. All are checked
against the actual installed image before even showing CURRENT. User-writable
preferences, local caches and signed release bundles do not own this baseline.

- Windows ACL + DPAPI protects against an unprivileged actor but **does not**
  prevent privileged disk-image restore or rollback of the entire state.
  Do NOT label this arrangement cryptographic monotonic anti-rollback.
- For strong rollback resistance evaluate platform-provisioned TPM NV monotonic
  state (with explicit provisioning, authorization, resource limits, lost/cleared
  TPM, backup/restore and power-loss recovery), **or** a separately authenticated
  remote high-water witness with verifiable receipts, availability policy and
  anti-replay. Neither is implemented or assumed universally available.
- If anti-rollback witness is unavailable, tampered, cleared, contradictory,
  lower than a previously witnessed generation, or cannot be authenticated:
  **HOLD / NO UPDATE**. Do not silently fall back to DPAPI/ACL and call it PASS.
- Crash-safe progression must verify the installed target and recorded release
  after an update *before* committing a new high-water mark. A restart after a
  partially applied installer must report ambiguous/recovery, never CURRENT.
- Product upgrade may not overwrite trust root or lower counter as a side
  effect. Recovery requires an explicit authenticated operator ceremony, not
  a user-editable 'reset' file.

## Fail-closed observable states

| Condition | User-facing state | Installer allowed |
|---|---|---|
| No pinned signer / no publisher attestation | RELEASE_UNKNOWN | No |
| Valid schema but failed signature/Git tree/EXE identity | HOLD | No |
| Unknown or stale policy / revoked key / rollback witness missing | HOLD | No |
| Current EXE bytes contradict independently protected installed pin | REPAIR_REQUIRED | No |
| Installed and approved authenticated identity equal | CURRENT | No |
| Higher independently approved release, full proof, trusted anti-rollback | UPDATE_DETECTED | Still no; separate S2-L2 user-approved install gate |

No UI timer, network transport, download, install, UAC, Worker action, project
I/O, rollback/migration, or active S4 operations are authorized by this ADR.

## Work slices & evidence required for production

A. Operator signs off exact source and delivery of the root public-key bundle,
signer lifecycle/rotation, audit logs and emergency revocation policy. Independent
red-team: self-signed index, substituted/unknown key, compromised transport,
fake Git main and replayed old generation.
B. Design and prototype anti-rollback witness strictly on *disposable Windows
fixtures* (not real TPM/provisioning without explicit owner authorization).
Independent red-team: copied/rolled-back disk snapshot, journal truncation,
state pair mismatch, denied ACL, privilege boundaries, lost witness, crash,
concurrent installs and signer rotation.
C. Design immutable publication ceremony, approver roles, protected-main proof
and signed attestation. A fabricated local Git graph is not authoritative
protected-main provenance. Independent red-team: wrong branch, unsigned
approver, replayed approval, out-of-order counter, package/GUI mismatch.
D. Only when A–C pass, integrate with S2-L1A and Windows native CNG in separate
PR(s), with exact-head 4/4 CI and independent FA, then separately gate S2-L1C
read-only periodic discovery and S2-L2 install/UAC and image-in-use handoff.

**ACCEPTANCE:** Architectural review of this ADR may PASS as a decision record;
it cannot be counted as real key issuance, anti-rollback enforcement,
protected-main publication, operational S2-L1B, or a license to install.
