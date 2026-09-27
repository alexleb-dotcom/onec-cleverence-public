# PROFILE — CLEVERENCE_MSLX

## Detection

Route execution graphs by semantic operation content/path, not by one export layout:

- `Operations/**`
- `Operation_*`
- actual `Operation` / Action graph content
- Action/Direction edits
- CurrentItems / DeclaredItems / BindedLine
- Mobile SMARTS writer/router actions

Known physical representations include:

```text
Configuration/Operations/**
WinClient/Configuration/Operations/**
Documents.zip!/Operations/**
unpacked Operations/**
```

`TOOLS/artifact_corpus.py` owns layout/container normalization. Physical location remains provenance/delivery evidence and mirror evidence; semantic operation identity is used for mechanism routing and cross-layout baseline comparison.

`.mslx` is not synonymous with this profile. Semantic `Metadata/**` and `DocumentTypes/**` are routed to `CLEVERENCE_CONFIGURATION` unless an actual Operation/Action execution graph is also present. Service XML from an outer configuration export is inventory evidence but is not an execution graph merely because it is XML.

## Triggered contracts

- `KNOWLEDGE/CLEVERENCE_RUNTIME_INTEGRATION.md`
- actual accepted Mobile SMARTS baseline
- actual active Business Process profile when exchange is affected

## Mandatory checks

### Evidence escalation
- if Action/Direction/writer/router behavior is not known exactly, inspect the nearest stock operation in the accepted/reference Cleverence configuration before creating a custom graph;
- compare the whole action contract: parent/order, inputs/outputs, directions, implicit fall-through, writer identity and error/cancel behavior;
- absence of a proven analog when semantics are uncertain is `EVIDENCE_REQUIRED`.

### Graph
- Action ids/names and owner operation;
- physical order, XML scope and serialized `indent`;
- `nextDirection`, `yesDirection`, `noDirection`, error/abort directions;
- ordered `ButtonDirections` slots, including empty positional slots;
- scoped `up:` directions resolve to the named action in the required ancestor scope;
- implicit fall-through before/after edit;
- former-END behavior;
- every operation target/direction resolves.

### Scan state and re-entry
Do not assume these are reset automatically:

```text
SelectedProduct
ScannedBarcode
BarcodeData
```

When a menu/action starts an independent scan, prove the fresh-entry contract before reusing a stock operation. `SearchProduct` or another stock operation may be a continuation stage rather than a scan entrypoint. Trace cleanup on success, error, back/cancel and retry, then test repeated entry.

### Quantity-stage ownership
Map the actual stage order, for example:

```text
scan → search/selection → quantity control → quantity input → second control → writer
```

If the scenario mutates/reallocates already existing fact, identify that mode **before the first standard quantity-control** that can treat it as new picking. Do not disable stock validation merely to suppress an over-pick symptom; first prove whether the path entered the wrong semantic stage.

### Data and identity
- Current vs Declared role;
- BindedLine identity;
- split/merge identity fields;
- quantity conservation;
- mark/SN/SSCC/series/weight preservation;
- rollback/cancel/re-entry;
- standard writer/router reuse.

### Writer-path coverage
Finding one writer is not proof that a changed fact field reaches every `CurrentItem`. Build an applicability inventory for all relevant creation/mutation paths, including where present:

```text
AcceptInDocumentAction
ordinary writer
mark-first / mark-after-product
single SN / range SN
group / SSCC
weighted
buffer / collective writers
other stock writer/router variants selected by the active scenario
```

For each applicable path trace the changed field from `SelectedProduct`/source state to the live `CurrentItem` and later export. Paths that are not applicable need an evidence-backed reason.

### Live CurrentItem mutation
A row selected in UI/view state is not automatically the live mutable row in `Document.CurrentItems`.

Preferred correctness pattern when a fact row is mutated:

```text
selected/view row
→ obtain technical Uid
→ rebind live CurrentItem in Document.CurrentItems
→ validate current identity/quantity/analytics
→ snapshot old values when multi-step mutation can partially fail
→ mutate source
→ reread/verify
→ mutate/create target
→ reread/verify
→ rollback on partial failure
```

A Uid lookup may be linear; correctness has priority. Profile only if real document size/operator latency makes it material.

### Cross-system contract
- 1C producer field/type/default;
- Mobile field and header/line scope;
- exact identifier/code points across mappings and scripts;
- active load/unload mapping;
- grouping/search identity;
- Mobile → 1C consumer path;
- repeat load/retry/idempotency.

### Delivery/runtime
- identify artifact role and authoritative configuration root before treating any source tree as the delivery baseline;
- exact baseline + allowlisted diff;
- run `TOOLS/analyze_cleverence_mslx.py <candidate> --baseline <baseline>` when baseline bytes are available;
- machine-check XML/MSLX parse, duplicate Action ids, `indent`, scoped `up:`, ordered `ButtonDirections`, former-END boundaries, unresolved directions, operation-target review, mirror drift and Action-flow deltas;
- physical Configuration/WinClient mirror proof/sync when Operations are actually mirrored in the target layout;
- BOM/CRLF/encoding;
- emulator/device runtime path including negative/back/cancel, repeat-entry, quantity-stage and applicable writer variants.

A stock/reference archive may provide a behavioral analog, but it does not define the target project's physical export/delivery shape.

## Completion rule

Every applicable check above needs evidence or explicit non-applicability. Unknown material runtime behavior is `EVIDENCE_REQUIRED`/`RUNTIME_PENDING`, never PASS.
A clean machine graph scan is not semantic PASS: insertion/movement findings must be reconciled with condition-false, former-END, back/cancel/error, fresh-scan/re-entry, quantity-stage and writer-path behavior.
