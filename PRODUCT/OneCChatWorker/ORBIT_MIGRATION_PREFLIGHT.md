# OneC Orbit migration: bounded read-only preflight (Phase C0)

**Status:** OFF-PRODUCTION EXPERIMENT ONLY. This is not a migration implementation, a safe-to-install verdict, or authorization to alter any existing Windows installation.

## Purpose

Before designing the separately authorized `OneCChatWorker` -> `OneCOrbit` cutover, require a deterministic metadata-only refusal gate. The accompanying `tests/Inspect-OrbitMigrationReadOnly.ps1` has four mandatory explicit roots; it has no production defaults. It rejects standard installed paths unless an *explicit* read-only inspection switch is passed (this switch never authorizes migration). It returns a machine-readable decision with `migration_permitted=false` in **all** states.

The gate does not read/hash/traverse/copy Source, Main or Incoming, inspect project source content, stop any helper, manipulate any active S4 session, mutate ACLs, install an app, edit registry or create output files.

## Reasons and interpretations

| Reason | Status | Meaning |
| --- | --- | --- |
| ROOT_COLLISION / REPARSE_ANCESTOR | BLOCKED | Nested or equal roots, including duplicate physical DOS-device paths, or reparse ancestors |
| PHYSICAL_ROOT_IDENTITY_UNVERIFIED | BLOCKED | Cannot prove a canonical attached local DOS device; SUBST, UNC/mapped/virtual drives, NTFS 8.3 aliases and other unproven namespace forms refused |
| PRODUCTION_INSPECTION_NOT_AUTHORIZED | BLOCKED | Standard live roots cannot be inspected by off-production tests |
| LEGACY_ROOT_MISSING / INCOMPLETE_LEGACY_INSTALL | BLOCKED | Legacy root or required marker missing; no reconstruction |
| ORBIT_DESTINATION_OCCUPIED | BLOCKED | Pre-existing Orbit destination, including partial installation, must be adjudicated |
| ADMISSION_MARKER_PRESENT | BLOCKED | Any saved admission marker, even offline/expired/unknown, must be adjudicated before migration |
| HELPER_STATE_UNADJUDICATED | BLOCKED | Presence of helper state is not proof that helper exited |
| OPERATION_STATE_UNADJUDICATED | BLOCKED | Current operation evidence may represent recovery/source transition |
| METADATA_INSPECTION_FAILED | BLOCKED | Access denied, malformed path, or other uncertainty fails closed |
| PROJECT_SOURCE_S4_ATTESTATION_REQUIRED | OWNER_ATTESTATION_REQUIRED | Basic markers are clean; **not** permission to copy, rebind or install |

## Deferred owner-controlled migration gates

1. Explicit read-only inventory of project catalogue and absolute path references, with bounded input and redacted report. Confirm each registered project's immutable source snapshot and external project roots. Never infer safety from empty admission/operation markers alone.
2. Owner/S4 evidence: no ACTIVE/STARTING task, no active-but-helper-offline admission, no helper process, no pending source update or recovery, no snapshot mutation. Requires independent live authority, not just a local filename check. Do not auto STOP/START.
3. ACL/owner/share/reparse validation, storage quota/free-space assessment, backup/readback of bounded **metadata only** and intentional no-deep-copy/rebind plan for large existing Source roots. A project's Source/Main must not be duplicated or hashed while active.
4. Transaction design with immutable journal, preimage hashes for metadata, private staging, durable commit markers, explicit operator confirm/UAC; atomic project catalogue/shortcut/startup cutover only after verification. Preserve old paths and admissions, no old-root deletion.
5. Crash injection and rollback at each staging/cutover boundary; interrupted migration must recover without mixed roots. Denial/cancel cannot produce false success. All tests use disposable roots before any real operator downtime decision.
6. Exact packaged WPF GUI and launcher integration, RU/EN, dark/light, 100/125/150% DPI, 4/4 hosted CI and independent FA on an immutable PR head. A subsequent **separate** live migration authorization is mandatory.

No public "migration available" or "install ready" UI status may be derived from this Phase C0 result. The previous Phase A `MIGRATION_REQUIRED` default-root hold remains unchanged.

## Isolated test evidence

`tests/run_orbit_migration_readonly_preflight_regression.ps1` constructs only disposable `%TEMP%` roots. It checks missing/partial legacy roots, clean-marker owner-review status, ACTIVE admission marker, helper/operation markers, occupied destination, root collision, production inspection guard, unchanged marker bytes, no source content access and `migration_permitted=false` on every branch. The adversarial Windows matrix also creates and removes an actual disposable `SUBST` drive (same directory alias and parent/child alias), a disposable NTFS junction removed with a non-recursive directory unlink, a local unprovable device namespace, a denied-ACL temporary directory restored in `finally`, and a synthetic NTFS 8.3 spelling. No network path is probed.
