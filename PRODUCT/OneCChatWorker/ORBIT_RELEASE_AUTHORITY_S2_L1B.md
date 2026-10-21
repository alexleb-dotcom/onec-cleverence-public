# S2-L1B — offline signed release authority and exact Git tree proof

**Status: DRAFT/OFF-PRODUCTION; not deployed, no production release authority
provisioned, not accepted by independent FA.** No network, publishing, WPF
background scheduler, downloader, installer, UPDATE or MIGRATE.

## Threat model and trust hierarchy

The operator-approved protected-main release commitment is the source of
release identity — never a new arbitrary GitHub commit, unsigned tag, Release,
mutable HEAD, downloaded public key, downloaded digest, or manifest alone.

1. The signing authority's RSA public-key identity (minimum 2048-bit) is
   independently provisioned in trusted installed product or OS-owned trust
   store with a protected key-rotation policy. Publisher keeps private key
   **outside** repository, release archive, product and CI fixtures. Test keys
   are synthetic, deterministic and never accepted for product use.
2. A separately ACL/OS-protected, rollback-resistant installed trust record
   supplies the minimum accepted release counter and separately trusted
   identity of installed package/EXE. Neither trust state nor key may be
   supplied by remote response or arbitrary user-editable receipt. Receipt
   creation, protection and tamper-resistant persistence are NOT built here.
3. Approved index schema ONEC_ORBIT_APPROVED_RELEASE_INDEX_V1 (unchanged S2-L1A)
   contains fixed repository, full 40-hex Git commit, monotonic counter,
   complete GUI SHA256, and canonical distribution snapshot SHA256.
4. Signed JSON envelope schema ONEC_ORBIT_SIGNED_RELEASE_AUTHORITY_V1 commits
   exact repository, exact protected-main full commit SHA, approved index SHA256,
   exact counter, and detached RSA PKCS#1 v1.5 SHA256 signature. Signed bytes
   are domain ONEC_ORBIT_RELEASE_AUTHORITY_V1 + NUL + canonical UTF8 JSON of
   the five fields, using sorted keys and compact separators. Duplicate and
   unexpected JSON keys are rejected. The key never comes from envelope.
5. The fixed repository's Git objects are verified *offline* against the
   signed exact main and exact release commits. Release must be an ancestor of
   the signed main. Shallow objects, missing commits, replacement refs and
   grafts are rejected. Every signed-main ancestry-path commit object's
   complete Git SHA-1 identity is recalculated with bounded count/size,
   not inferred solely from merge-base. Ancestry to a signed SHA alone
   does NOT show that SHA was actually operator-approved protected main;
   the publisher must verify
   GitHub branch protection and origin identity **before signing**, with an
   independent auditable publication receipt and protected signing policy.
6. All Git tree entries from the committed root and nested subdirectories are
   validated. Reject symlinks (120000), gitlinks/submodules (160000), abnormal
   file modes, dangerous Windows paths, duplicate NFC+casefold identities,
   extra/missing files and unsupported tree shapes. SHA-1 identities of the
   commit, tree and blob bytes are independently recalculated; every file
   SHA256 and byte size must match the canonical committed manifest. Canonical
   SHA256 digest of the entire inventory must equal BOTH the committed
   DISTRIBUTION_MANIFEST.json and the separately signed index digest.
   MANIFEST is not trusted alone; signature + Git object structure + all
   contents are required together. Individual blob reads are preflight
   size-checked (128 MiB maximum), with an aggregate 1 GiB cap.
7. verify_complete_release is the only composite PASS entry point in this
   prototype: signature -> Git ancestry -> exact tree + signed distribution
   digest. It returns no installer permission or side effects. S2-L1A
   readonly_discovery remains unchanged and non-mutating.

## Remaining acceptance/deployment dependencies

- Pin a real operator-owned trust key in protected production code/OS trust;
  enforce independently authenticated key rotation/revocation. No key is
  created, stored, published or accepted by this PR.
- Implement secure creation, separate storage, ACL and anti-rollback of the
  installed identity and monotonic counter, including Windows rollback tests.
  An integer argument from a caller is NOT yet trusted storage.
- Define an auditable protected-main release publication/sign-off ceremony
  binding GitHub provenance, signer identity, exact full commit, canonical
  distribution and immutable index location. Signing a random forged
  Git history with a compromised key is not ruled out by a Git ancestry check.
- Production WPF should use platform cryptographic verification APIs, not
  treat this standalone Python reference verifier as a deployed signer or
  install path.
- Independent adversarial FA, complete exact-head Fast/UI/Windows/Full hosted
  CI and separate operator merge permission are mandatory. No live install,
  network fetch, Worker/S4 or Source/Main/Incoming interaction here.

## Test coverage

run_orbit_release_authority_regression.py: offline synthetic signatures,
tampers, wrong/absent key, unsigned/counter rollback, missing Git commits,
ancestry. run_orbit_git_tree_regression.py: signed end-to-end fake-release
provenance, duplicate/missing pins, nested tree/blob modes, symlink,
submodule, extra files, unapproved manifest, Windows path safety. Tests create
only disposable fixture Git repositories; no user projects or installed
EXE are accessed.

Any absent/truncated/malformed/untrusted/offline authority: fail closed.
