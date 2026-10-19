# #113 selected first-time EXTENSION ADD (off-production)

Implemented in the existing PREPARE_SOURCE_UPDATE / ACCEPT_SOURCE_UPDATE owner.
No installed Worker/Helper, real source, credentials, Cloudflare, deployment,
installation, push, or live full APPLY was used. Initial Git HEAD was
2dcfd1bd092c3b09e43f278173c24f372ba9c0b9 on
`ta/arch-20261019-q113-selected-new-extension`.

## Behavior and proof

- A selection such as `do|EXTENSION|bitdo` resolves a new artifact only from the
  current active catalog, for an exact existing accepted participant.
- Catalog drift is still visible until publication. The original manifest is
  proved against its original catalog identity; old fingerprint inventory bytes
  are verified as metadata. All prior active artifacts must remain present with
  their exact canonical identity. Main and unselected source paths cannot change.
- Only explicitly selected new extension topology is allowed. Duplicate/case
  identities, reserved Windows names, existing targets (file or directory),
  aliases, source overlap, removals and unrelated topology changes fail closed.
- ADD validates/hashes only the selected sealed slot, constructs its manifest row
  and fingerprint entry from that validation, and reuses all old unselected rows.
  There is no required old fingerprint entry for a first-time artifact.
- Same-volume promotion uses the existing zero-copy owner and manifest-last atomic
  publication. ADD never detaches an existing target. ADD requires eligible local
  zero-copy paths; the copy fallback refuses ADD before creating a marker.
- Recovery distinguishes ADD from UPDATE. Before manifest commit it returns a
  promoted ADD to its slot and discards that intake generation; after commit it
  finalizes the published snapshot. Physical slot/target evidence covers a rename
  before its journal phase write. Both present or both missing is contradictory
  and preserves the recovery marker. Rollback waits for active admission to end.
- Existing UPDATE generations need no new state fields. The regression also uses
  a real filled UPDATE generation produced by the unmodified baseline Core.

## Tests and limitations

Run in Windows PowerShell 5.1 with the repository Node runtime available:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ./PRODUCT/OneCChatWorker/tests/run_selected_extension_add_regression.ps1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ./PRODUCT/OneCChatWorker/tests/run_selected_catalog_update_regression.ps1
```

The ADD suite accepts optional `-BaselineCorePath`: an unmodified baseline Core
saved under a distinct module filename in the package's `core` directory. The
recorded compatibility run used the exact HEAD blob, SHA-256
`0a1966f49ec3701651bbc8cbe3dd02bc3fc36c53f3a0cd77d1d2e345b0346eb9`.
No product installation is needed for this compatibility check.

ADD suite with baseline compatibility: 189 checks passed.

The ADD suite holds exclusive handles on every file in both accepted and external
Main fixtures throughout PREPARE, ACCEPT and recovery, asserts zero Main content
read/hash/copy, compares exact old Main and un/bit manifest/snapshot identities,
and runs full integrity verification after releasing the handles. It exercises
admission, stale generation/catalog/manifest, seal drift, alias/duplicate/path
collisions, target appearance, fallback refusal, recovery-first and contradictory
recovery cases. Only admin/account/ACL integration is stubbed; real catalog,
Node validation, hashing, moves, fingerprint publication and recovery execute.
Actual Windows account provisioning and ACL enforcement were not exercised.

Existing selected catalog UPDATE regression: 50 checks passed. Generation wire
regression: 12 checks passed. Supplementary snapshot fast-path regression fails
at `helper_manifest_hash_mismatch` because its copied helper fixture omits
`helper-https-pull.mjs`; the same failure was reproduced using the untouched
baseline Core and runtime. That unrelated fixture was left unchanged.

The first ADD test attempt exceeded a legacy .NET path length in its own long
scratch location; the fixture now uses a short checkout-local directory. An
initial optional baseline import shadowed module commands; baseline and current
modules are now imported separately before executing the test. Both harness
issues were corrected. A supplementary batch runner also timed out after omitting
its mandatory report-path argument; the wire test passed when rerun noninteractively
with an explicit report path.

## Future operational sequence (not performed)

1. Review this change and package integrity pins; separately authorize any later
   installation/update. Ensure the executing Core is this reviewed version: the
   launcher prefers an already installed Core for ordinary modes. Do not bypass
   its package hash check. Use explicit WorkerRoot and ProgramDataRoot throughout.
2. End active admission. If a promotion marker exists, run
   `Recover-SourceUpdatePromotion` with those explicit roots and the provisioned
   operator identity before PREPARE or ACCEPT. Inspect recovery's old/new outcome.
3. Register the exact new extension using `Add-WorkerExtension` (or launcher mode
   ADD_EXTENSION): ProjectId RetailGroup, ParticipantId do, ExtensionId bitdo,
   SourcePath the intended extension export root, and the explicit WorkerRoot.
   Do not use ReplaceExisting for a first-time ADD. Catalog drift is expected.
4. Call `Prepare-SourceUpdate` with Selections `@('do|EXTENSION|bitdo')`, explicit
   roots and OperatorIdentity. Record the returned generation_id and slot_path.
   Export only that extension into that slot; retain the recorded generation.
5. Call `Accept-SourceUpdate` with ProjectId RetailGroup,
   ExpectedGenerationId the recorded generation, ExpectedArtifactKey
   `'do|EXTENSION|bitdo'`, and the same roots/identity. The launcher equivalents
   are PREPARE_SOURCE_UPDATE with ArtifactSelection `'do|EXTENSION|bitdo'`, then
   ACCEPT_SOURCE_UPDATE with those explicit expected identity parameters.
6. If admission is active, keep the SEALED_VALIDATED generation and retry the same
   expected identity after admission ends. Do not re-PREPARE or refill a sealed
   generation. On stale identity or catalog errors, investigate before retrying.
   After pre-commit rollback, expect the original manifest and CATALOG_DRIFT;
   prepare a fresh ADD generation and refill only its selected slot.
7. Confirm READY/ACCEPTED, one publication-generation increment, the new extension
   inventory, and unchanged Main/un/bit identities. Full VERIFY reads Main and is
   a separate explicit deep-integrity operation; it is not required by selected
   ADD. Do not use full APPLY or detach Main to resolve drift.

For an existing filled legacy UPDATE generation, keep its original generation,
key and filled slot; ACCEPT it with that exact identity without another PREPARE.
One-command quicksync is deferred to a #113 follow-up.
