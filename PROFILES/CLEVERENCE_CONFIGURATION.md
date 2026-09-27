# PROFILE — CLEVERENCE_CONFIGURATION

## Detection

Route by the semantic Cleverence configuration namespace, not by one physical export layout:

- `Metadata/**`
- `DocumentTypes/**`
- `ContainerTypesBook` / `ContainerSchema.mslx`
- `DocumentType`
- `CommonFieldInfoCollection` and related field-declaration metadata

Known physical representations include, but are not limited to:

```text
Configuration/Metadata/**
Configuration/DocumentTypes/**
WinClient/Configuration/**
Documents.zip!/Metadata/**
Documents.zip!/DocumentTypes/**
unpacked Metadata/** / DocumentTypes/**
```

`TOOLS/artifact_corpus.py` owns container/layout normalization. The physical representation remains evidence for delivery and mirror checks; it must not become the semantic identity of the configuration contract.

This profile is deliberately separate from `CLEVERENCE_MSLX`: configuration metadata defines data/parser/document contracts, while Operations/Actions define the execution graph. A metadata-only change must not inherit an unrelated Operation graph review merely because the file suffix is `.mslx`.

## Mandatory checks

### Exact source, artifact role and schema
- inventory the supplied artifact before filtering source files;
- identify whether the input is a configuration export, configuration source tree/subset, runtime database, mixed artifact or unresolved artifact;
- identify the authoritative configuration root from the accepted target baseline rather than assuming `Configuration/`;
- prove whether `WinClient/Configuration` is an active mirror before requiring synchronized edits;
- run `TOOLS/analyze_cleverence_configuration.py <candidate> [--baseline <baseline>]` on the smallest supplied closure containing the changed metadata and relevant competing declarations/templates;
- record exact field name/code points, native type, scope (document/header/line/object), default/nullability and producer/consumer path;
- never treat transliteration, similar spelling or Cyrillic/Latin confusables as field identity.

### Barcode/container templates
- extract the full competing template set, not only the edited `ContainerType`;
- distinguish structural overlap from actual parser precedence: overlap is evidence to review, not proof of a defect;
- when a new/changed broad template can also match the prefix of a more specific template, prove which template the actual Cleverence parser selects for both representative full input and prefix-only input;
- do not infer precedence from XML order, apparent specificity or regular-expression intuition unless actual vendor source/runtime establishes that contract;
- validate GS/control characters through actual parser/runtime evidence, not copied visible text.

### Field contract
For every changed Mobile SMARTS field trace:

```text
declaration
→ exact identifier/code points
→ native type
→ document/header/line scope
→ load/mapping/expression
→ writer/mutation
→ export/import
→ Business Process/Core mapping when applicable
→ 1C consumer
```

A declaration existing somewhere in the configuration does not prove that every writer or integration path populates it.

### Runtime
When parser/schema behavior is material, include:
- configuration load/startup;
- changed field availability and native type;
- representative normal input;
- negative/competing barcode input when templates overlap;
- repeat/re-entry if parser/session state participates;
- actual target deployment behavior for every physical tree/container that participates.

## Delivery boundary

A bundled/reference Cleverence configuration is evidence for stock analogs only. It does not define the target project's delivery layout.

`FULL_COMPARE` means preserving the exact authoritative configuration delivery shape of the accepted target baseline and changing only the allowlisted content. A runtime database must not be copied wholesale into a configuration delivery merely because it contains configuration files.

If artifact role/layout/authoritative root is `UNKNOWN` or materially mixed, analysis may continue but exact-delivery / merge-ready claims remain blocked until the source role is resolved and the plan is rebuilt.

## Completion rule

Structural extraction may prove declarations, exact names, types, artifact layout and changed template overlap. It cannot by itself prove parser precedence, runtime population or end-to-end field mapping. Those remain `EVIDENCE_REQUIRED`/`RUNTIME_PENDING` until actual stock/runtime evidence closes them.
