# ProjectSnapshot chat workflow

## Purpose

This document is the human-facing guide for chats that use the skill against a customer 1C environment. The **canonical executable orchestration contract** for exact states, transitions, repository paths and responsibility keys is `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`. This guide explains that contract; it must not become a second independently maintained state machine.

ProjectSnapshot is an **evidence-acquisition adapter**, not a separate analysis mode. Requirements, review-plan, validation-ledger and release-gate semantics remain unchanged.

The ordinary developer experience is:

```text
chat identifies a concrete evidence gap
→ chat verifies repository payload and materializes ProjectSnapshotCollector.epf
→ chat prepares PROJECT_SNAPSHOT_COLLECTION_PLAN.json
→ developer opens the supplied EPF, loads the supplied plan and presses "Собрать пакет"
→ developer uploads ProjectSnapshot.zip
→ chat validates, inspects and binds the evidence
→ chat resumes the original task automatically
```

Read `KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_DISTRIBUTION.md` for the collector distribution contract.

The developer must not be asked to build the Collector, clone the skill repository merely to obtain it, understand repository payload encoding, interpret collector JSON, map evidence rows manually, decide whether a returned row is trustworthy, or restate the original task after uploading the ZIP.

## Responsibility split

### Chat / skill owns

- deciding whether a snapshot is actually needed;
- deriving the smallest sufficient `PROJECT_SNAPSHOT_REQUEST` from the active claim/gate;
- choosing only backends genuinely available in the customer contour;
- retrieving the repository-pinned ProjectSnapshotCollector payload declared by the artifact manifest;
- validating payload Git blob identities, reconstructed EPF SHA-256/size/Git-blob identity and exact EPF source-input bindings;
- materializing/providing the verified `ProjectSnapshotCollector.epf` as a user-visible file;
- running `TOOLS/plan_project_snapshot_collection.py` or enforcing the same planner contract;
- producing the exact `PROJECT_SNAPSHOT_COLLECTION_PLAN.json`;
- explaining only the minimum run steps;
- recognizing a returned ProjectSnapshot ZIP as continuation of the active evidence request;
- validating package/request/baseline/item binding;
- reading `manifest.json`, `runtime-evidence.json`, `designer.log` and returned source files itself;
- binding concrete returned bytes/observations to exact requested items;
- preserving failed/unsupported/insufficient items as unresolved;
- issuing only a delta request for newly discovered evidence;
- continuing the original analysis/design/review without asking the developer to repeat context.

### Developer owns

- opening the `ProjectSnapshotCollector.epf` supplied by chat in the intended infobase;
- loading the CollectionPlan supplied by chat;
- supplying Designer authentication locally when required;
- pressing **Собрать пакет** and choosing the ZIP output location;
- uploading `ProjectSnapshot.zip` back to chat;
- reporting a local UI/runtime failure only when the processing itself cannot produce a diagnostic package.

The developer is **not** responsible for building `ProjectSnapshotCollector.epf`, running `build_epf.ps1`, reconstructing repository payload parts, deciding which objects to export, editing the CollectionPlan, interpreting collector statuses, or extracting modules from the ZIP.

## Activation and pre-manual acquisition rule

Do **not** run the Collector merely because it exists, but do **not** bypass it silently either. Before any manual request for current-1C XML/BSL, a configuration/extension source export, or an individual 1C module, resolve the canonical `pre_manual_current_onec_gate` from `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`.

First inspect all evidence already available in the current task: supplied source/configuration archives, repository files, exact modules/XML, logs/runtime artifacts, current `PROJECT_CONTEXT`, already accepted ProjectSnapshot packages for the same baseline, and exact authorized reference evidence when it is the correct evidence class.

Then disposition the missing current-1C evidence:

```text
existing evidence closes claim
→ EVIDENCE_ALREADY_SUFFICIENT

exact supported item is known and no required discovery artifact already subsumes it
→ PROJECT_SNAPSHOT_REQUIRED

supported exact items + unsupported companion evidence
→ SPLIT_ACQUISITION
   ProjectSnapshot for supported items
   manual only for unsupported remainder

implementation topology/changed-object surface must first be discovered,
or one broad source artifact is independently required for unsupported/form/extension audit scope
→ DISCOVERY_BOOTSTRAP
   request the smallest discovery artifact once
   inventory it
   re-run this gate before any next current-1C evidence request

collector does not support the material target/evidence class
→ MANUAL_FALLBACK_UNSUPPORTED

collector cannot run in the actual contour / user declines it
→ COLLECTOR_UNAVAILABLE / USER_DECLINED_COLLECTOR
```

A **broad audit is not an exemption**. Asking for "the whole extension/configuration ZIP" merely because the implementation is broad is forbidden when the same missing exact evidence can be acquired directly by ProjectSnapshot.

At the same time, do not create duplicate work. If a broad extension/source archive is independently necessary to enumerate changed objects/forms or other currently unsupported source shapes and it will also contain supported module source, request it as `DISCOVERY_BOOTSTRAP` first. Once returned, use what it actually proves; only then issue ProjectSnapshot for remaining exact gaps.

If supplied evidence already closes the claim, **do not run the Collector again**.

## Repository collector availability

Before choosing `PROJECT_SNAPSHOT_REQUIRED`, first confirm that the active skill distribution actually contains the repository-pinned Collector manifest/payload and that the integrity path is available. Collector-specific delivery obligations below are conditional on that availability.

If the active distribution intentionally omits the Collector (for example, public `SHAREABLE_CORE` with `collector_surface=EXCLUDE_COLLECTOR`), resolve the existing pre-manual disposition `COLLECTOR_UNAVAILABLE`. Do not invent an EPF, do not ask the ordinary developer to build one, and do not claim ProjectSnapshot is available. Request only the smallest manual evidence needed for the unresolved claim. The private/internal distribution may continue to use the verified repository-pinned Collector normally.

## Repository collector delivery

Canonical repository distribution inputs are:

```text
COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json
COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/
TOOLS/materialize_project_snapshot_collector.py
```

The repository stores the accepted EPF bytes as text-safe Base64 parts. This is an internal transport representation only; the developer receives a normal `ProjectSnapshotCollector.epf`.

Before delivering the Collector, chat must verify the equivalent of `TOOLS/materialize_project_snapshot_collector.py`:

1. artifact manifest status is `READY`;
2. every declared payload part exists and its Git blob identity matches;
3. the concatenated payload has the declared encoded size and is strict Base64;
4. reconstructed EPF byte size, SHA-256 and Git blob identity match the manifest;
5. every pinned EPF build input still has its exact accepted Git blob identity;
6. build/open acceptance and SOURCE_EXPORT runtime acceptance remain recorded.

Only after all checks pass may chat materialize and expose the bytes as `ProjectSnapshotCollector.epf`.

A missing/stale/mismatched payload or reconstructed EPF is a **skill distribution defect**, not a normal developer build step. Do not silently tell an ordinary developer to rebuild it. `build_epf.ps1` is a maintenance path for explicit Collector-development work or an explicitly accepted maintenance fallback.

When collection is required, normally provide both files together:

```text
ProjectSnapshotCollector.epf
PROJECT_SNAPSHOT_COLLECTION_PLAN.json
```

Within the same task, a verified EPF may be reused for delta plans while its artifact identity remains unchanged.

## Chat state machine

The exact state set and transition graph live only in `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`. Human-facing reasoning must preserve these boundary milestones: collector+plan ready, package received, package bound/rejected, source content inspected when required, evidence bound, then original task resumed or a smallest delta request issued.

`PLAN_READY` means the exact plan is fixed **and the verified materialized EPF is available to the developer**. Receiving a package is not proof, and package binding is not source-content proof.

## Deriving the request and plan

The chat derives `PROJECT_SNAPSHOT_REQUEST` from the active evidence gap using `TEMPLATES/PROJECT_SNAPSHOT_REQUEST.json`.

Each required item carries a stable `id`, exact `category`, exact `logical_target`, `required_for_claim`, and minimum required fidelity. Preserve known `baseline_expectation`; do not invent unknown versions.

For the accepted desktop workflow, normal available backends are `RUNTIME_METADATA` and, when Designer can be launched read-only against the same infobase, `SOURCE_EXPORT`.

Run or enforce:

```text
TOOLS/plan_project_snapshot_collection.py <request.json> \
  --available-backends SOURCE_EXPORT RUNTIME_METADATA
```

The plan must preserve request ID, baseline expectation, exact item identities, selected backend, minimum fidelity and unsupported/partial rows.

When artifact creation is available, emit the file itself as:

```text
PROJECT_SNAPSHOT_COLLECTION_PLAN.json
```

Do not make the developer copy JSON from prose unless file creation is unavailable.

## Developer-facing instruction

The normal instruction is deliberately short:

1. Open the supplied `ProjectSnapshotCollector.epf` in the target infobase.
2. Load the supplied `PROJECT_SNAPSHOT_COLLECTION_PLAN.json`.
3. If Designer authentication is required, enter it locally in the collector form.
4. Press **Собрать пакет** and save `ProjectSnapshot.zip`.
5. Upload that ZIP back into this chat.

Do not ask the developer to inspect/edit package internals, clone the repository, reconstruct payload parts, or build the EPF.

Designer credentials are local execution inputs, not evidence-package data. Never place a password into CollectionPlan/ProjectSnapshotRequest and **never ask the developer to paste a password into chat**.

## Recognizing a returned archive

When an uploaded ZIP contains `manifest.json`, `collection-plan.json`, `runtime-evidence.json`, and `manifest.package_kind = PROJECT_SNAPSHOT_EVIDENCE`, treat it as a ProjectSnapshot candidate automatically.

The developer does not need to say "analyse this ProjectSnapshot". If an active collection request exists, the ZIP is the expected continuation. In another/new chat the package may be validated and inventoried, but it must not be attached to an unidentified historical task merely by similarity.

## Mandatory package handling

A returned ZIP is candidate evidence until validated.

Run or enforce exactly:

```text
TOOLS/validate_project_snapshot_package.py \
  ProjectSnapshot.zip \
  --expected-request-id <active-request-id>
```

Preserve archive safety: reject duplicate entries where required, absolute/parent traversal paths, and never execute returned content.

The validator binds package schema/kind, request ID across plan/manifest/runtime evidence, known configuration identity, collector/read-only identity, exact runtime item/category/target rows, runtime summary, `SKIPPED_OTHER_BACKEND` semantics, SOURCE_EXPORT requested-item correspondence, and successful source status to actual `source/` content.

A stale, wrong-database, wrong-request or inconsistent package is rejected; do not salvage it by name similarity.

For non-trivial work tracked through the canonical validation ledger/release gate, capture the successful package-binding validator execution as a verifier-owned machine receipt using `TOOLS/machine_receipts.py` with property `EVIDENCE:PROJECT_SNAPSHOT_PACKAGE_BINDING`. That receipt proves only package/request/plan/configuration binding at the validator's scope. It never replaces semantic inspection of returned `SOURCE_EXPORT` bytes or runtime/business proof.

## Item-level evidence semantics

### Runtime rows

Only a matching `RUNTIME_METADATA` row supports its exact item. `COLLECTED`/`PARTIAL` are usable only at their real fidelity. `ERROR`, `UNSUPPORTED*`, missing rows and wrong-backend rows remain unresolved. `collector.runtime_proven` is implementation-level status, not a package-wide allow/deny switch.

### SOURCE_EXPORT rows

A successful source-export manifest only says source bytes are available. For every source item:

1. locate manifest `source_file` / exact packaged path;
2. confirm it exists and is non-empty;
3. read the returned bytes/text;
4. confirm path/content corresponds to the requested logical target;
5. only then bind it to the claim.

The package validator intentionally leaves `SOURCE_REQUIRES_CONTENT_INSPECTION` until this happens. Matching `expected_module_paths` and `found_module_paths` is useful acquisition evidence, but concrete packaged bytes are the source proof object.

## Automatic continuation

After binding, default behavior is **continue the original task immediately**.

Chat accepts usable runtime rows, inspects/binds source bytes, updates active evidence/artifact requests, preserves unresolved items, and resumes the exact requirements/review/design/implementation point that required the evidence.

Do **not** reply to a successful ZIP with only "package accepted" and stop.

Do **not** ask the user to repeat the original requirement, object name or investigation if already present in chat/project context.

## Delta collection

If accepted evidence reveals another dependency, default to `DELTA_REQUIRED`: retain the applicable baseline/task, request only new missing items, explain which new claim they resolve, and do not re-request unchanged source.

Reuse the same verified materialized EPF while its distribution identity is unchanged. If the Collector distribution changed, provide the new verified EPF automatically with the next plan.

## Failure handling

### Wrong database/configuration
Reject the package when known baseline identity conflicts with runtime identity; regenerate/reuse the correct plan rather than interpreting the wrong snapshot.

### Source export failure
Keep otherwise bound runtime evidence. Inspect `manifest.source_export` and `designer.log` yourself and report the concrete failure. Do not ask the developer to diagnose the log.

### Package is partial
Use valid evidence now and keep only unresolved items pending.

### Repository collector distribution is broken
If artifact status is not `READY`, a payload part is missing or changed, reconstructed binary integrity fails, or pinned source inputs drifted, do not distribute the EPF and do not turn this into a normal user build instruction. Mark a skill-maintenance/distribution defect. Build-from-source is only an explicit maintenance fallback.

### Developer cannot run the processing
Continue with available evidence and preserve affected claims as pending; do not fabricate runtime/source facts and do not block unrelated analysis.

### Web client / unsupported path
The accepted one-click SOURCE_EXPORT path is the tested managed desktop/thin-client flow. Web-client source export is not claimed.

## Privacy and mutation boundary

The normal ProjectSnapshot flow is read-only with respect to application/configuration state. Exclude runtime business data by default, bound SOURCE_EXPORT to requested owners, never use configuration load/update commands for acquisition, and never persist developer credentials into the evidence contract.

## Proof boundary summary

```text
repository payload present
!= reconstructed EPF integrity accepted
!= ProjectSnapshotRequest
!= CollectionPlan
!= package produced
!= package bound
!= source bytes inspected
!= item-level runtime observation
!= deployed business behavior proven
```

The Collector reduces evidence-acquisition friction. It does not weaken the skill's evidence model.

## Snapshot-loop definition of done

The loop is complete only when a verified current EPF and exact plan were provided when needed; returned package is bound or rejected; every requested item has a real disposition; required SOURCE_EXPORT bytes are inspected; unresolved items stay explicit; useful evidence is incorporated; and the original task is resumed or the smallest delta request is issued.
