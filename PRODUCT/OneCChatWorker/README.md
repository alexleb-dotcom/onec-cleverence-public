# OneCChatWorker turnkey product

This directory contains the 1C-first turnkey OneCChatWorker product defined by control thread #44. It packages the accepted hosted-MCP read/proposal contour behind one deterministic Windows lifecycle manager. Cleverence remains deferred.

## One visible entry point

Run OneCChatWorker.ps1.

With no arguments it is the normal guided operator UI. It derives the current state from installed-state, local enrollment, projects.json, the bounded accepted-snapshot state check, and active-admission/helper state, then presents one recommended next action. A normal user does not need to know the internal ADD_PROJECT / ADD_PARTICIPANT / SET_MAIN / APPLY / VERIFY / START order.

The default guided presentation follows Windows CurrentUICulture deterministically: ru-* cultures use Russian labels/help/errors, while other cultures use the canonical English fallback. Technical CLI modes and Advanced lifecycle/diagnostic wording remain unchanged.

INSTALL is also the package update/reinstall path. When INSTALL is launched from a complete package, its adjacent package core is authoritative for bootstrap even if an older installed core already exists. The installer then refreshes the installed launcher/core/runtime lock to the package hashes while retaining the project catalog, managed Source/Output data, enrollment secret, and the bounded operator ACL contract. A failed package-integrity/update step is reported as a recoverable guided error; do not uninstall or wipe project roots to recover from version skew.

The default state path is: install -> connect ChatGPT -> add local project -> complete setup -> ready -> start work. When work is running, the default view offers status, stop and Output. Interrupted work is recover-first; reinstall is not the ordinary recovery recommendation.

Add local project is a wizard. Every field explains what it is, why it is needed, the accepted format, an example, whether it is required, and a safe default when one can be derived. Type ? or help at a prompt to repeat the explanation. Invalid input is re-prompted in place without losing previous answers. Project/system/task technical ids are derived automatically in the guided view. Main and extension folders are validated immediately and must contain Configuration.xml directly in the selected root.

Before setup is committed, the wizard shows a plain-language summary with Confirm, Back/Edit and Cancel. Setup can resume from an existing draft without replaying already-completed project/system steps. The guided completion action records APPLY as the durable publication operation and then confirms readiness with FAST_STATE_CHECK_V1. It does not run an implicit deep VERIFY; explicit VERIFY remains available under Advanced.

Guided project completion exposes five plain-language stages over the durable APPLY publication plus a bounded accepted-snapshot state check. The presentation polls only the existing operation receipt/process state and emits elapsed-time heartbeats while a stage is still running; it does not calculate a fake percentage, run implicit deep VERIFY, or add a second full-tree scan for UI progress. Russian ru-* and canonical English fallback use the same stage order. Advanced explicit VERIFY remains the long full-integrity operation.

Expected user-input failures in the default UI are shown as FAIL / Next / Details guidance rather than uncaught PowerShell stack traces. Full technical lifecycle controls, raw operation details, diagnostics and manual APPLY/VERIFY remain available under Advanced.

The same launcher exposes deterministic CLI modes for support and automation. Normal output is human-readable; -Json is an explicit automation/support option. There is one manager/core owner: guided UI and Advanced mode call the same lifecycle implementation rather than maintaining a second state machine.

## First run

From a repository/release checkout:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PRODUCT\OneCChatWorker\OneCChatWorker.ps1 -Mode PRECHECK
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PRODUCT\OneCChatWorker\OneCChatWorker.ps1 -Mode INSTALL

INSTALL self-elevates when needed. It verifies runtime.lock.json, installs/reuses the exact pinned Node.js and ripgrep builds, verifies their SHA-256 values, installs the hash-locked product components, creates/adopts the restricted local reader identity, applies ACLs, initializes projects.json, and leaves the helper OFF.

Each component is reported as an explicit disposition such as REUSED, INSTALLED, UPDATED, SKIPPED_NOT_REQUIRED, or a classified failure/operator checkpoint.

Python is not a product runtime dependency. Cloudflare CLI / Wrangler is not a product runtime dependency. They may be engineering tools in development, but the new-machine installer does not install them.

The default restricted identity is OneCSourceReader; -ReaderName can select another safe local name. The worker root and ProgramData runtime root are parameterized as -WorkerRoot and -ProgramDataRoot.

INSTALL captures the normal Windows operator identity before UAC elevation and reconciles ACLs idempotently. The operator receives Modify only on the managed WorkerRoot tree, operation journal, provider-config surface, and runtime admission surface. The installed launcher, provider integration binary, helper/product files, and runtime ripgrep binary remain read/execute only for the operator; the helper enrollment secret is not readable by the operator. REPAIR re-runs the same bounded ACL reconciliation before operation journaling.

### Remote authorization

There is one unavoidable remote-auth checkpoint:

1. connect the stable private MCP app in ChatGPT to https://onec-g1q1-relay.alex-lebad1.workers.dev/mcp;
2. complete the app OAuth flow in ChatGPT;
3. locally enroll the machine helper secret with:

    .\OneCChatWorker.ps1 -Mode SETTINGS

The helper secret is entered locally. Its value is not written to operation logs, the catalog, diagnostics, or the repository. The stable hosted endpoint is not recreated per project.

## Project catalog and canonical topology

C:\OneCChatWorker\projects.json is the one human-editable desired-state catalog. JSON is intentional: no YAML runtime dependency is required.

Each applied project receives generated normalized runtime state at:

    C:\OneCChatWorker\<project>\
      ProjectManifest\project.json
      Participants\<participant>\Target\Main\Configuration.xml
      Participants\<participant>\Target\Extensions\<extension-id>\Configuration.xml
      Output\<task>\...
      Detached\...

For ordinary unpacked 1C exports the artifact directory is the source root. There is no Main\Main or <extension-id>\<extension-id> wrapper.

ProjectManifest\project.json records the exact catalog SHA-256 used to generate it. Manifest schema v2 also records ACCEPTED_SNAPSHOT_V1 identity: deterministic source_snapshot_id, publication generation, per-artifact P/P/A identity, canonical path, files/bytes/tree SHA-256, Configuration.xml SHA-256, proof basis, and subordinate fingerprint-inventory identity/state. Catalog/manifest mismatch is a fail-closed CATALOG_DRIFT state; runtime never silently guesses desired state. A qualifying v1 manifest can be adopted to v2 from durable post-publication READY/RECOVERED evidence without recopying or re-hashing the artifact tree; insufficient evidence returns DEEP_VERIFY_REQUIRED.

APPLY reports safe metadata for every artifact: operator source input path, participant/artifact identity, canonical target path, COPIED / REUSED / REPLACED_DETACHED / DEACTIVATED_DETACHED, and detached path when applicable.

APPLY materialization is failure-atomic. Each artifact copy has an explicit CREATED -> COPYING -> VERIFIED -> COMMITTED staging lifecycle under the bounded WorkerRoot staging area. A failure before commit removes the incomplete stage where possible; if normal cleanup cannot complete, the residue is moved/classified under the project's Recovery\ApplyResidue area. FAST_STATE_CHECK_V1 reports INCOMPLETE_APPLY_RESIDUE before replay, explicit VERIFY remains available for full integrity evidence, and REPAIR resolves residue first. Residue cleanup does not delete a committed canonical Target, Detached evidence, Output, or the authoritative external Source.

Durable operation receipts keep a stable error_class plus bounded safe error_message, error_phase, error_path and cleanup_status fields when available. Human operation-log timestamps are explicitly labeled UTC. Guided mode turns APPLY failures into localized FAIL / Reason / Stage / Cleanup / Next / Details guidance instead of exposing a raw PowerShell stack.

External business Source is never edited. A full publication enumerates Source metadata once, streams each file into bounded staging while computing its SHA-256, builds the aggregate tree digest from those collected rows without rereading stage, performs a metadata-only Source stability recheck, then commits staging and publishes fingerprint inventory + manifest last. SOURCE_CHANGED_DURING_SYNC aborts publication.

## Safe removal

REMOVE means deactivate, not purge.

Replacements and deactivations move managed copies to Detached rather than recursively destroying them. Deactivating a required 1C Main is allowed as desired state so the old managed copy can be detached, but the bounded state classifier no longer reports ACCEPTED and START refuses the incomplete project until a valid Main is set again.

No PURGE action exists in this release.

## START / STOP

START performs exactly one FAST_STATE_CHECK_V1 for the selected project, then writes one manager-owned active-admission.json binding exactly one project, one task, the accepted source_snapshot_id, and the exact manifest SHA-256. New-Admission consumes that accepted identity and does not run a second deep VERIFY. The selected relay/helper endpoint is also fixed before helper launch. The model cannot switch project, root, task, or snapshot.

The helper runs under the restricted local identity and connects outbound-only. Before connection it verifies the exact manifest SHA-256 and source_snapshot_id from admission against manifest v2. Its session recovery is bound to that snapshot; a changed manifest cannot silently reuse an older helper session.

STOP ends the local helper/admission and does not delete catalog, Participants, Output, Detached, or external Source.

## Model-facing execution boundary

The hosted app contract is exactly five semantic tools:

- source_context
- source_search
- source_read
- proposal_write
- proposal_read

There is no model-facing source write, delete, shell, process, browser, arbitrary URL, project switch, root switch, or task switch.

Participants are read-only to the restricted helper. Output is writable only for bounded proposal delivery. _proposal_provenance.json binds proposal artifacts to the admitted source snapshot. PROPOSAL_NOT_APPLIED means the proposal was delivered to Output but was not applied/deployed to authoritative business Source.

### Bounded local quality preparation

The five-tool surface does not grow. After, and only after, a successful admitted source_read, the helper may deterministically bind that exact read path to one eligible metadata descriptor or managed-form Form.xml. It may then prepare a LOCAL_QUALITY_REPORT_V1 using the internal allowlisted META_INFO, FORM_INFO and FORM_VALIDATE operations. source_search, task text and source_context hints never execute the adapter.

The adapter redistributes exactly three unchanged MIT-licensed scripts from Nikolay-Shirokov/cc-1c-skills at commit 1fa205b961f4ed3659f58f4b55d2d9b1d5e4810e. Their git-blob and SHA-256 identities are recorded in KNOWLEDGE/EXTERNAL_SOURCE_CATALOG.json and runtime.lock.json. Execution is fixed to Windows PowerShell 5.1 with shell=false, fixed internal arguments, bounded time/output, and a closure-only temporary sandbox. Authoritative Source is read-only and is re-hashed after execution; SOURCE_CHANGED_DURING_RUN discards the report/cache.

Prepared quality is at most 1200 UTF-8 bytes. At most two confirmed target reports are cached for the active session, and replay is accepted only while task/session/project manifest/PPA/source snapshot/target/confirming SHA/input closure/adapter/upstream/script/overlay bindings still match. Exact Source remains inspectable through source_read and quality findings do not change PROPOSAL_NOT_APPLIED or release/evidence ownership.

## Remote-call budget

Remote calls are budgeted. The product contract in runtime.lock.json records:

- exact known-path source read: normally 1 remote call;
- bounded source search with context: normally 1 remote call;
- ordinary non-trivial source question: target <=3 reader calls before Chat reasoning.

A single remote search may perform bounded local searches across admitted participant artifacts; that local fan-out does not create additional remote MCP calls. There is no polling loop for ordinary source operations.

## Human-readable progress and durable operations

Long operations use one shared operation/event model. Normal console progress resembles:

    [1/4] INSTALL Checking prerequisites ... RUNNING
    [2/4] INSTALL Installing/reusing pinned components ... RUNNING
    [3/4] INSTALL Verifying installed runtime ... RUNNING
    [4/4] INSTALL Complete authorization checkpoint ... WAITING_FOR_USER

Canonical states are:

RUNNING | PASS | FAIL | WAITING_FOR_USER | CANCELLED | RECOVERED

Durable machine-readable and human-readable operation evidence is maintained with bounded rotation. The operator UI includes:

- VIEW CURRENT OPERATION
- VIEW RECENT OPERATIONS
- VIEW LOGS
- EXPORT DIAGNOSTIC BUNDLE

STATUS is observational and cheap: project readiness uses FAST_STATE_CHECK_V1 over catalog/manifest identity, direct canonical roots/Configuration.xml, and bounded residue metadata; it does not recursively hash artifact trees. STATUS also shows product/install state, dependency versions/health, installed component integrity, active admission, helper/MCP connection evidence, current/last operation, last explicit VERIFY, recovery classification, and bounded Output proposal summaries.

Diagnostic bundles intentionally exclude secret values and passwords.

## Interrupted work and repair

The lifecycle follows RECOVER_FIRST_NOT_REPLAY_FIRST.

If the last material operation is still RUNNING, normal mutating actions stop with RECOVERY_REQUIRED; they do not blindly replay the request. PRECHECK may inspect state. An explicit INSTALL/REPAIR path classifies the interrupted operation and then performs idempotent bounded reconciliation.

Project REPAIR is intentionally narrow and recover-first. An ACCEPTED structurally present snapshot returns without a deep hash; interrupted staging is classified/cleaned first; legacy v1 may be adopted from durable proof; APPLY is used only for states that actually require publication. DEEP_INTEGRITY_VERIFY_V1 is invoked only when exact state cannot be proven from durable publication/recovery evidence. Warm START uses the accepted fast state, not an implicit deep verification.

## STATUS / DIAGNOSTICS examples

    .\OneCChatWorker.ps1 -Mode STATUS
    .\OneCChatWorker.ps1 -Mode VIEW_CURRENT_OPERATION
    .\OneCChatWorker.ps1 -Mode VIEW_RECENT_OPERATIONS
    .\OneCChatWorker.ps1 -Mode VIEW_LOGS
    .\OneCChatWorker.ps1 -Mode EXPORT_DIAGNOSTICS

For machine consumption add -Json to read-only/status-style commands.

## Safe uninstall / rollback

Without confirmation:

    .\OneCChatWorker.ps1 -Mode UNINSTALL

prints the exact plan and performs no mutation.

Runtime-only removal requires:

    .\OneCChatWorker.ps1 -Mode UNINSTALL -ConfirmUninstall

It STOPs the admission and removes only product-owned runtime/provider/helper/secret/product files and the installed launcher. It retains projects.json, all project Participants managed source copies, Output proposals/evidence, Detached archives, audit and operation logs, and the restricted local reader account.

It never deletes authoritative external business Source. Reader-account deletion and Source/Output purge are intentionally separate/not implemented destructive actions.

## Cleverence

The catalog schema is participant/platform-extensible, but this release is deliberately 1C-first. Any active non-ONEC participant fails closed with PLATFORM_NOT_IMPLEMENTED_1C_FIRST.

Cleverence must later reuse this same installer/catalog/lifecycle architecture after its own source-layout gate. No second installer architecture is introduced here.

## Reproducibility and verification

runtime.lock.json pins dependency versions, reference binary hashes, product component hashes, the stable hosted app identity, the exact five-tool surface, and the remote-call budget.

Run the Windows clean-root regression:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PRODUCT\OneCChatWorker\tests\run_local_regression.ps1

The cross-platform shareable CI also validates static product/security/observability contracts through TESTS/run_onecchatworker_product_regression.py.
