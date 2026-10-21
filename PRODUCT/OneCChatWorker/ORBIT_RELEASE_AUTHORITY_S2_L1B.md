# S2-L1B — signed release authority prototype (not deployment)

Scope: **offline, fail-closed provenance verifier** on disposable inputs. No live
publication, no GitHub fetch, no trusted signing key distributed to users, no
background polling, no INSTALL/UPDATE/MIGRATE.

## Authority contract
1. Approval publisher holds a separately secured RSA private key (minimum
   2048-bit). Product must obtain the matching modulus/exponent from a
   protected, operator-approved distribution/OS trust store; NEVER an index,
   envelope, download, or a user-writable data file.
2. Detached envelope JSON schema ONEC_ORBIT_SIGNED_RELEASE_AUTHORITY_V1
   contains exact repository, protected-main 40-hex commit, SHA256 of exact
   approved index bytes, monotonic release_counter, signature_hex. Signature is
   PKCS#1 v1.5 SHA256 over ASCII domain ONEC_ORBIT_RELEASE_AUTHORITY_V1 followed
   by NUL, then canonical UTF8 JSON of the other five fields (sort_keys=True,
   separators=(',', ':')). No extra/duplicate fields.
3. Approved index must meet the accepted L1A schema and fixed repository. Its
   counter must equal the signed counter. Minimum counter is from a separately
   protected, rollback-resistant installed trust record, not the response.
4. Offline Git verification checks exact signed main commit and exact release
   commit, complete ancestry, and rejects shallow/grafted/replaced histories.
   An observed mutable branch HEAD is NOT a trust anchor.
5. The L1A status-only gate receives validated index bytes and the verified
   ancestry boolean only AFTER BOTH separate conditions pass. A missing key,
   signed approval, full Git graph, or installed trust state fails closed.

The RSA public-key identity and protected installed release record are
**dependencies not yet provisioned**. No product code currently calls the
prototype; no release is approved by this change. The separate distribution
byte inventory still requires a verified Git-tree-to-manifest binding,
including blob identity, file modes, symlinks, directory paths and nested trees;
this is not yet established by this module. Do not promote this prototype to
S2-L1B final PASS until those proofs, external key provenance, CI, and
independent FA acceptance are complete.

## Tests
run_orbit_release_authority_regression.py constructs disposable deterministic
synthetic RSA keys (NEVER production keys), signed fake releases and temporary
local Git commits. It checks signed approval, wrong key, tampering, downgrade,
missing input, forged signature, schema collision, accepted ancestry,
unverified ancestry and missing object. No network or live worker access.

Forbidden: trusting downloaded public keys, self-computed network digest as
trust proof, automatic installation, production writes, or using manifest
content alone to establish release identity.
