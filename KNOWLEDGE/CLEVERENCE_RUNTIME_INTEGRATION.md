# CLEVERENCE RUNTIME + INTEGRATION CONTRACT

## Purpose

Cleverence Mobile SMARTS is a first-class half of the developer skill, not an appendix to 1C.

For any task that touches TSD behavior or the 1C ↔ Cleverence contract, load this file together with the relevant MSLX/integration profiles. Do not rely on the legacy full skill for mandatory checks.

## 1. Source of truth

There is no universal physical Mobile SMARTS export root that is valid for every version/artifact family.

Start with `TOOLS/artifact_corpus.py` and prove the actual artifact role/layout before narrowing the source layer. Known valid representations include, for example:

```text
Configuration/Operations/**
Configuration/Metadata/**
Configuration/DocumentTypes/**

or a legacy configuration export:

outer export
├─ AppDescription.xml
├─ 1CConfigs.xml
├─ settings.xml
├─ ...
└─ Documents.zip
   ├─ Operations/**
   ├─ Metadata/**
   └─ DocumentTypes/**

or an already unpacked configuration subset:
Operations/**
Metadata/**
DocumentTypes/**
```

These representations may describe the same semantic configuration mechanisms but have different delivery shapes. Physical path is provenance/delivery evidence; it is not the semantic identity of an Operation, DocumentType or Metadata contract.

Runtime database content such as `Cells.sqlite`, `DeviceStorage`, runtime documents, messages, logs, connections/server folders and similar state is not automatically part of the standard configuration export. Never copy the whole runtime database into a configuration delivery merely because it also contains configuration files.

`Backup/**`, logs, runtime document XML and old configuration archives are not automatically authoritative.

`WinClient/Configuration/**` can be a mirror. Never assume mirror identity; prove it by hashes. If the target deployment workflow actually requires both copies and they are proven mirrors, keep changed files synchronized.

Treat semantic `Operations/**` and `Metadata|DocumentTypes/**` as different review mechanisms. Operations are execution graphs; metadata/document types define parser/data/document contracts and route to `CLEVERENCE_CONFIGURATION`.

Start reference discovery from the exact target export. If it does not already expose the required stock mechanism, use `REFERENCE/CATALOGS/cleverence_discovery.json` and `TOOLS/reference_locator.py` only to identify plausible Operation/DocumentType families and the smallest exact source fragments to request. Build `TOOLS/build_local_cleverence_reference_index.py` from the supplied target or user-authorized export when a structural index is useful.

An `INTERNAL_FULL` maintenance installation may additionally retain a stock/reference corpus and derived indexes for migration regression, calibration and forensics. They are optional maintenance oracles, not public-runtime dependencies, and do **not** define the physical layout, graph, fields, parser behavior or runtime semantics of another target project/version.

The exact accepted target/project baseline remains authoritative for current delivery.

If artifact role/layout/authoritative root is unresolved or mixed, analysis may continue, but exact-delivery / merge-ready / `FULL_COMPARE` claims remain blocked until the authoritative configuration artifact is established and the review plan is rebuilt.

## 2. MSLX is an execution graph

Do not validate `.mslx` as XML text only.

Start deterministic review with `TOOLS/analyze_cleverence_mslx.py`. Pass the accepted baseline when available so Action additions/removals, explicit direction changes and physical predecessor/successor changes become explicit review items. The analyzer compares equivalent semantic operation paths across supported physical layouts, but proves only structural facts; vendor runtime meaning still requires stock-source and emulator/device evidence.

For every changed/affected Action inspect:

```text
owner operation
action type and id/name
parent/depth
physical order
nextDirection
yesDirection / noDirection
abort/error directions
ButtonDirections
operationName
conditions / expressions
variables read/written
Document fields
SelectedProduct fields
CurrentItems mutations
UI behavior
```

### Implicit fall-through

An empty direction may mean the physical successor, container successor or end of operation depending on structure/runtime semantics.

Changing physical order can therefore change behavior even if all explicit directions are byte-identical.

For a moved/inserted Action prove:
- previous implicit successor;
- new successor;
- false/negative path;
- error/abort/Escape path;
- former-END behavior.

## 3. Plan/fact identity

Treat these as different roles unless the actual configuration proves otherwise:

```text
DeclaredItems / declared line = plan
CurrentItems / CurrentItem = fact
BindedLine = binding to plan
```

A single declared line may legitimately produce several current lines because of:
- boxes/packages;
- marks;
- serial numbers;
- lots/series;
- weight;
- other business identity fields.

Never merge current lines merely because the product is the same.

Before writing/merging fact determine the exact identity fields used by the standard writer/router.

## 4. Split/merge invariants

For every split or packaging change prove:

```text
sum(fact quantity) = source/accepted quantity according to business rule
no unintended duplicate fact
no loss of mark/SN/SSCC/series/weight identity
rollback/cancel restores the correct state
re-entry does not multiply fact
repeat scan follows the intended identity
```

If a standard Mobile SMARTS writer/merge action already owns identity and persistence semantics, prefer it over a custom full writer.

## 4.5. Scan state, quantity stage and live fact mutation

Do not assume automatic cleanup of:

```text
SelectedProduct
ScannedBarcode
BarcodeData
```

A stock operation such as `SearchProduct` may be a continuation stage rather than a fresh scan entry. For an independent menu/re-entry flow prove cleanup/fresh scan semantics on success, error, back/cancel and retry.

Before changing quantity behavior, map the stage pipeline. If a path reallocates existing fact rather than selecting new quantity, classify that mode before the first stock quantity-control that can reject it as over-pick.

Before mutating fact obtained through a view/selection, prefer technical rebind to the live `Document.CurrentItems` row by `Uid`, validate current identity/quantity, then mutate with reread/verify and rollback for multi-step source→target changes. A linear Uid lookup is a performance question only after correctness is secured.

## 4.6. Writer-path coverage

One found writer is not sufficient proof for a field that must appear in every applicable `CurrentItem`. Inventory the actual active writer variants (ordinary, `AcceptInDocumentAction`, mark/SN/SSCC/weighted/buffer variants and other stock routes) and trace the field through each applicable path.

## 5. Marks / serials / SSCC

Marked, serialized and package identifiers are correctness-critical identity, not presentation.

Never optimize by dropping/recombining:
- mark/KM;
- serial number;
- SSCC/package barcode;
- binding fields used by standard writer;
- service keys required for undo/re-entry.

For barcode templates, separator/control-character semantics must be validated against the actual Cleverence parser/runtime, not inferred from visible text alone.

Also review the **competing template set**. A broad `(01){GTIN...}`-style pattern and a more specific pattern may both be structurally plausible for the same input. Structural overlap is not automatically a defect, and XML order/specificity is not automatically precedence. For a changed overlap, prove which template the actual parser selects for representative full and prefix-only input.

### Cross-domain identity boundary

Do not collapse identifiers merely because they are present in one scan/packing process. Unless the actual project mapping proves an equivalence, keep these roles distinct:

```text
trade-item type / GTIN
individual marked or serialized physical item
Declared/Current warehouse line identity
project-internal box/container number
logistics unit / SSCC
regulatory aggregation/package fact
```

An internal Cleverence box/container is not automatically an SSCC or regulatory package. A GTIN is not automatically the identity of one physical item. A `CurrentItem` is not automatically a regulatory aggregation fact. If the project intentionally maps one role into another, trace the complete producer → mapping → persistence/exchange → consumer lifecycle, including who creates the regulatory/logistics identity and when the equivalence becomes valid.

## 6. 1C → Mobile SMARTS contract

For every field sent to TSD record:

```text
1C source
Mobile field
native type
nullable/default
header or line scope
load mapping
used in identity?
used in presentation?
used by writer/router?
```

Preserve native technical types end-to-end unless a real serialization boundary requires conversion.

Field identity is exact, not semantic: declaration, script/mapping, writer, export/import and 1C consumer must use the intended exact identifier/code points. `NomerKoroba`, `НомерКороба` and visually confusable Cyrillic/Latin variants are not assumed to be the same field.

A numeric local package id must not become a String merely because UI displays text.

## 7. Mobile SMARTS → 1C contract

Trace the full consumer chain:

```text
CurrentItem
→ BindedLine
→ exported fields
→ effective Business Process search/grouping
→ Core normalization
→ integration hook
→ 1C row/object
→ document write
```

Mandatory questions:
- can one declared line yield multiple current lines?
- does loader keep or group them?
- what fields participate in grouping/search?
- when is the 1C document written?
- what happens on repeat load/retry?
- can partial failure produce mixed state?

## 8. Effective Business Process

Business Process configuration is a separate layer from MSLX.

Before modifying exchange determine the effective active profile:

```text
typical BP
custom BP
whether custom overrides typical
active/disabled profile
load mappings
unload mappings
search rules
grouping
custom handlers/codes
```

Presence of code/configuration in export does not prove that it is referenced by the active BP.

## 9. Cleverence Core / Integration hooks

Before implementing a full custom integration path, search the existing Core/Integration layer for a supported hook.

Record:

```text
input contract
output contract
phase
before/after standard mapping
can cancel?
can set error?
can mark written?
can change identity/search?
```

Preferred order:

```text
standard behavior
→ extension/integration hook
→ minimal project-specific override
```

Do not copy large Core blocks when a hook exists.

## 10. Runtime/performance

On TSD, treat repeated scans over `Document.CurrentItems` as potentially linear until runtime/source evidence proves otherwise.

Review:
- repeated `select ... CurrentItems`;
- rebind/search by Uid;
- nested collection scans;
- writer/merge calls in loops.

Correctness of identity/rollback has priority over shaving one collection pass for mark/SN/SSCC flows.

## 11. Packaging/delivery hard gate

`FULL_COMPARE` is layout-neutral. It means:

```text
accepted authoritative target baseline
→ preserve its exact configuration delivery shape
→ apply only allowlisted replacements
→ preserve all unrelated authoritative bytes
→ prove final diff/shape against the baseline
```

It never means “always use `Configuration/**`”, “copy every file found in the runtime database”, or “reconstruct a plausible export from indexes”.

For Cleverence delivery verify:

```text
artifact role/layout/authoritative root
exact accepted baseline
allowlisted diff only
unrelated authoritative bytes preserved
no runtime→configuration leakage
XML/MSLX parse
unique Action/Operation constraints
all operation targets resolved
local directions resolved
implicit successor preserved outside scope
button paths
error/abort/Escape paths
split/merge and quantity invariants
mark/SN/SSCC preservation
condition-false baseline equivalence
BOM/CRLF/encoding
ZIP CRC + filename integrity
Configuration/WinClient mirror sync only when required by actual target layout
runtime emulator/device scenarios
```

A syntactically valid MSLX file is never sufficient proof of behavior.
