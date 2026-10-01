# Evidence acquisition and missing-artifact protocol

## Principle

`Недостаточно доказательств` is not a reason to guess and is not a reason to silently abandon a branch of analysis. If a concrete missing artifact can resolve a material claim, ask for it explicitly.

## Required sequence

```text
material claim / suspected mechanism
→ inspect supplied corpus and factual artifact inventory
→ inspect available baseline / BSP / typical / Cleverence references
→ identify the exact missing dependency closure
→ choose the smallest supported acquisition adapter
→ request/collect the smallest sufficient artifact set
→ bind the request to the claim/gate it resolves
→ PROVIDED: validate + continue proof
→ UNAVAILABLE/DECLINED: preserve explicit limitation and blocking/pending status
```

Never replace a missing source with an implementation guess. Never say only “I cannot prove this” when the missing proof is reasonably requestable from the user. Continue unaffected parts of the task, but keep the affected gate unresolved.

## Bounded evidence work

Before additional search/read/test for an already accepted task, bind the current material/evidence obligation, the exact decision/property being established, the smallest justified closure, the expected discriminating evidence and the sufficiency/blocker condition. Use a small finite evidence plan rather than an open-ended discovery goal.

Repeat a search/read/test only when the question/property changed, the source/baseline changed, a new dependency/call edge was proven, prior output was truncated/paginated/incomplete, or current evidence contradicts the prior closure. Cosmetic rephrasing is not a new reason. Truncation, pagination and an incomplete index justify completing the bounded read/search; they never prove absence.

Finding another unrelated file/symbol, repeating a green result on unchanged bytes, rewriting the explanation, or observing a search miss does not by itself count as material progress. Extend the evidence budget only for a source-anchored dependency necessary to the accepted outcome and give the extension a finite exit condition. Novelty outside that outcome is a follow-up candidate, not automatic scope growth.

After repeated non-progress, reassess source/strategy and allow one bounded discriminating retrace for the same claim. If it still does not advance, keep the affected claim unresolved, close independent work and request the smallest exact evidence/input/experiment that can decide it.

## Returned requested input resumes the active task

When the user returns an answer, source file, archive, log, runtime result or other artifact that was previously requested for the active task:

1. correlate it to the exact request / claim / target / baseline it was meant to resolve;
2. validate provenance, integrity and content at the fidelity required by that claim;
3. bind only the evidence it actually closes and keep any remainder explicit;
4. resume from the canonical owner that was blocked by the missing input.

Do **not** ask the user to restate the original task, project identity, reason for the request or already accepted answers. If correlation is ambiguous, ask only for the smallest missing binding fact. ProjectSnapshot keeps its existing local orchestration states; this generic resume invariant does not introduce a second task/session state machine.

### Interrupted response does not invalidate bound evidence

If the assistant/tool response is interrupted after evidence or a task artifact may already have been accepted/bound, treat completion as unknown and inspect current durable evidence/artifact state before requesting or producing it again. Reuse every matching item that is still valid for the exact task/target/baseline and resume from the first canonical owner whose work is genuinely incomplete.

Do not re-request evidence merely because the response that acknowledged it was lost. If current binding is ambiguous, verify only the smallest exact identity/provenance fact needed to decide whether the existing item is reusable.


## Request quality

A useful request states all of:

- **what to provide** — exact object/module/XML/folder/log/operation when known;
- **why** — the behavior or contract that cannot currently be proven;
- **what it resolves** — e.g. call reachability, event subscription, form source, BSP signature, MSLX writer, mapping, runtime error;
- **minimum scope** — prefer the dependency closure over the whole configuration/project;
- **fallback** — if the artifact is unavailable, what remains blocked/pending and what can still be completed.

Do not ask for files that are already present in the supplied archive, file inventory, active project context or reference corpus.

## ProjectSnapshot is the default supported 1C acquisition adapter

When missing evidence belongs to the current 1C target and can be acquired by the maintained ProjectSnapshot Collector, use `KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md` **before** turning the request into a manual file-hunting checklist or asking for a broad configuration export. This requires a repository-pinned Collector distribution that is actually present and integrity-verifiable; if the active distribution intentionally excludes it, resolve `COLLECTOR_UNAVAILABLE` and use only the smallest manual fallback needed for the unresolved evidence.

The decision sequence is:

```text
missing current-1C evidence
→ can existing supplied/authorized source already prove it? yes → use that source
→ can ProjectSnapshot acquire the needed evidence class/target? yes → use ProjectSnapshot
→ otherwise request the smallest exact manual artifact/fallback evidence
```

ProjectSnapshot is not invoked merely because it exists. It is used when it is the smallest deterministic supported route to the missing evidence. However, **every manual request for current-1C source/evidence must first receive an explicit ProjectSnapshot disposition**. The decision itself is mandatory even when the correct outcome is a manual fallback.

### Pre-manual current-1C acquisition gate

Before saying "пришли выгрузку расширения/конфигурации", "пришли XML/BSL" or asking the developer to locate an individual current-1C module, resolve one of the canonical dispositions from `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`:

- `PROJECT_SNAPSHOT_REQUIRED` — exact missing items are supported and should be collected by the supplied EPF + plan;
- `SPLIT_ACQUISITION` — supported exact items go through ProjectSnapshot, manual request is limited to the unsupported remainder;
- `DISCOVERY_BOOTSTRAP` — exact implementation targets cannot yet be named, or one independently required broad source artifact is necessary to inventory extension/form/changed-object scope; request that smallest discovery artifact first, then re-run this gate after inventory;
- `MANUAL_FALLBACK_UNSUPPORTED` — the required target/evidence class is outside the current Collector implementation;
- `COLLECTOR_UNAVAILABLE` / `USER_DECLINED_COLLECTOR` — ProjectSnapshot cannot be used in the actual contour;
- `EVIDENCE_ALREADY_SUFFICIENT` — do not request anything.

A broad audit does not automatically mean `DISCOVERY_BOOTSTRAP`. If exact supported target rows are already known and the broad artifact is not independently required, use ProjectSnapshot. Conversely, do not make the developer run the Collector **and** export a broad archive when that independently required archive will already contain the same source proof; inventory it first and collect only remaining gaps.

For an audit from a TZ/LT with no implementation source, a full extension-source ZIP can legitimately be a discovery bootstrap when the audit must enumerate changed objects/forms and the current one-click Collector cannot export that complete surface. The chat must say why this is a bootstrap rather than silently acting as if ProjectSnapshot does not exist, and after the ZIP is inventoried it must use ProjectSnapshot automatically for any remaining supported exact current-1C gaps instead of asking the developer to hunt individual modules.

The normal user-facing loop when ProjectSnapshot is selected is:

```text
chat derives ProjectSnapshotRequest from exact unresolved claims
→ chat runs collection planner for the actually available customer-contour backends
→ if repository-pinned collector distribution is present and integrity-verifiable, chat verifies/materializes ProjectSnapshotCollector.epf
→ chat provides ProjectSnapshotCollector.epf + PROJECT_SNAPSHOT_COLLECTION_PLAN.json together
→ otherwise resolve COLLECTOR_UNAVAILABLE and request only the smallest manual evidence fallback; never synthesize or require the user to build the missing EPF
→ developer opens the supplied EPF, loads the supplied plan and presses "Собрать пакет"
→ developer uploads ProjectSnapshot.zip
→ chat validates package binding and archive integrity
→ chat inspects returned source/runtime evidence itself
→ chat binds only the exact usable items
→ chat resumes the original task automatically
```

The developer must not be asked to:

- build, locate or version-match `ProjectSnapshotCollector.epf` for ordinary collection;
- decide which metadata objects/modules belong in the plan;
- edit generated CollectionPlan JSON;
- inspect `manifest.json`, `runtime-evidence.json` or `designer.log` for the chat;
- extract individual source modules manually from a valid ProjectSnapshot ZIP;
- repeat the original requirement after the ZIP is uploaded.

When a ProjectSnapshot ZIP returns, receiving the archive is a continuation of the active evidence request, not a new generic file-analysis task. Validate it with `TOOLS/validate_project_snapshot_package.py` or enforce the same checks before evidence is used. Then inspect returned `SOURCE_EXPORT` bytes before closing any source-dependent claim.

Wrong `request_id`, wrong known configuration identity, unsafe/duplicate package entries, row/target mismatch, `ERROR`/`UNSUPPORTED`, a runtime row claiming an item assigned to another backend, or missing requested source bytes must remain unresolved or reject the package as defined by the validator/workflow.

A valid partial package is not all-or-nothing: use correctly bound usable items now, preserve failed items as unresolved, and issue only a **delta** CollectionPlan if a newly discovered material dependency remains missing.

`collector.runtime_proven` is implementation-level status. It never turns a package into blanket proof, and `false` does not invalidate a concrete matching runtime observation by itself. Use each observation only for its exact plan item and observed fidelity. `SOURCE_EXPORT` rows are not closed until the returned source bytes are actually inspected and matched to the requested item.

When a durable `PROJECT_CONTEXT` exists, record material ProjectSnapshot acquisition/baseline/backend facts there so later chats do not repeatedly ask whether the same contour can run the collector. Do not promote task-specific returned module contents into durable project policy.

## 1C examples

### Suspected event subscription

If a new common-module routine appears unused by the static call graph but may be called through a subscription, do not conclude either “dead code” or “it is probably subscribed”. Request, as applicable:

- the relevant `EventSubscriptions` metadata/XML or the configuration fragment containing the subscription;
- the handler common module containing the target procedure;
- the source object's event/metadata only when needed to disambiguate the event;
- extension/base subscription metadata when interception may exist in either layer.

When the currently maintained Collector can acquire the relevant bounded evidence class, prefer a ProjectSnapshot request for the supported portion; request only unsupported companion evidence manually.

The request should state: “I need these files/evidence items to prove `event → subscription → handler` reachability for `<routine>`.”

### Form/event bridge

If execution may enter through `СобытияФорм`, a command module, a form handler, or an extension advice, request the missing form module / command module / bridge module instead of assuming the call path. If the current SOURCE_EXPORT profile does not support the required form-module logical target, do not relabel another source item as equivalent; request the unsupported artifact through the smallest valid fallback.

### Form DataPath / aggregate form attribute

If a changed form control binds to `A.B` and the supplied source proves only that `A` exists, do not infer `B` from global configuration metadata. Request/inspect the smallest closure that proves the runtime shape:

- changed `Form.xml` or BSL that assigns `ПутьКДанным`;
- companion form metadata and `BaseForm`/inherited form context when relevant;
- the code/metadata that constructs or populates `A`;
- for `cfg:ConstantsSet` / `КонстантыНабор`, evidence that the target constant belongs to that concrete set;
- if a separate adapter attribute is introduced, the exact read/load and save/write owner paths.

If static source still cannot prove member availability, preserve `RUNTIME_PENDING` and bind it to a named form-open/edit/save scenario. The existence of `Constant.X` in metadata is not evidence that `НаборКонстант.X` is a valid runtime path.

### BSP / typical API

If a method name is known but the signature/semantics are not, request or inspect the exact common module source. Do not guess parameters from memory. When that exact common-module source is in the current Collector's supported SOURCE_EXPORT target shape, prefer the bounded ProjectSnapshot module request over a whole-configuration export.

## Cleverence examples

If MSLX flow appears to jump into an external operation, writer, Business Process or dynamic action that is absent from the current corpus, request the exact operation/BP/document-type/configuration fragment needed to prove the transition and data contract. Do not silently treat the missing branch as out of scope.

For a changed Mobile field, request/inspect the smallest closure that proves **all applicable writers**, not just the first writer found: relevant stock Operation(s), DocumentType/field declaration, active BP mapping/grouping/search fragment and the 1C consumer when exchange is affected.

For barcode/container-template changes, request the changed `ContainerSchema.mslx` together with the accepted baseline or at least the competing template set. If structural overlap cannot establish actual precedence, keep `RUNTIME_PENDING` and bind it to named parser/emulator inputs (representative full code plus broad-prefix/competing input).

For a fresh-scan/re-entry issue, request the calling menu/Operation plus the exact stock operation used as an entrypoint so `SelectedProduct`/`ScannedBarcode`/`BarcodeData` ownership and cleanup can be traced instead of assumed.

ProjectSnapshot currently applies to the 1C side of evidence acquisition; do not pretend it can collect Cleverence MSLX/vendor runtime evidence unless an explicit supported backend is added and proven later.

## Structured request states

Validation ledgers may use `artifact_requests` records:

```text
REQUEST_REQUIRED     — a material source gap is known but has not yet been asked for; release BLOCKED
REQUESTED            — user was asked / ProjectSnapshot plan issued; blocking requests remain BLOCKED while waiting
PROVIDED             — artifact/package item received, validated and bound to evidence refs
UNAVAILABLE          — source cannot be obtained; blocking claim remains unresolved
DECLINED              — user declined; blocking claim remains unresolved
RESOLVED_NOT_NEEDED  — further evidence proved the artifact is not required; reason mandatory
```

For ProjectSnapshot, `PACKAGE_RECEIVED` alone is **not** `PROVIDED`. Mark the request `PROVIDED` only after package binding and the item-level evidence needed by the claim has actually been accepted; SOURCE_EXPORT also requires content inspection.

The fact that an artifact was requested is not proof of the claim. It only proves correct handling of the evidence gap.

## Runtime execution adapters

Runtime evidence is a proof class, not a mandated test technology. When a published 1C web client is available, browser automation (for example Playwright) may be used to execute representative acceptance scenarios and capture the final visible/persisted result. Treat this as an evidence-acquisition adapter only: static reachability, structural validation and browser execution remain separate evidence layers, and browser success does not prove unexercised roles, background/server paths or device-specific Cleverence behavior.
