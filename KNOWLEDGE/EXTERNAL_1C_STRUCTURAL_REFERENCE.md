# External 1C structural reference corpus

## Source

Public repository: `Nikolay-Shirokov/cc-1c-skills`

- https://github.com/Nikolay-Shirokov/cc-1c-skills
- License: MIT, Copyright (c) 2025-2026 Nick Shirokov.
- Local license notice: `THIRD_PARTY/cc-1c-skills/LICENSE.txt`.

This repository is **supporting engineering evidence**, not an official 1C standard and not a substitute for actual target source, Configurator/runtime validation or current 1C documentation.

## Why it is useful to this skill

Our skill is strongest at semantic/business/architecture/BSP/Cleverence/release-evidence review. `cc-1c-skills` contributes a complementary strength: compact structural understanding and validation of real 1C source-dump XML instead of asking an LLM to infer XML shape from memory.

The highest-value families for our workflow are:

| Artifact | External reference family | How we use the idea |
|---|---|---|
| Managed form | `form-info`, `form-validate` | summarize Form.xml; validate structural identity pools and extension/base-form context before BSL assumptions |
| Configuration extension | `cfe-diff`, `cfe-validate` | distinguish adopted/own objects, base UUID bindings, BaseForm/event interception and transfer/diff closure |
| Metadata XML | `meta-info`, `meta-validate` | classify actual metadata payload and validate structure before architecture/code conclusions |
| XDTO | `xdto-info`, `xdto-validate` | prove namespace/type/import/cardinality structure and package registration before writing serializer/parser code |
| Role/RLS | `role-info`, `role-validate`, role specifications | parse `Rights.xml`, bind role metadata, preserve version-aware default/omission semantics and separate structural RLS facts from effective authorization |

Second-wave/on-demand references (do not load by default): `skd-*`, `cf-*`, `subsystem-*`, `interface-*`, EPF/ERF and MXL families.

## Mandatory interpretation rule

Do **not** copy an external validator's finding as truth merely because the tool reports it. Before promotion to our universal hard rule:

1. identify the exact structural invariant;
2. test it against actual 1C/typical/project corpus;
3. classify whether it is platform requirement, strong convention, warning, or corpus heuristic;
4. make machine checks fail closed only for invariants with sufficient evidence;
5. keep uncertain or corpus-derived checks as `REVIEW`/`EVIDENCE_REQUIRED`;
6. preserve an attribution and regression fixture.

This rule exists because apparently simple XML properties such as IDs may have separate identity pools/scopes. A naive global rule can produce thousands of false positives on valid extension Form.xml files.

## Local tool

`TOOLS/analyze_onec_xml.py` is the compact structural evidence layer used by this skill. It is maintained here and intentionally narrower than the upstream suite. It currently covers the facts we have validated strongly enough to include in our release pipeline:

- Form.xml element/attribute/command/column identity scopes and extension BaseForm/event context;
- metadata payload/name/UUID/ChildObjects basics;
- CFE adopted-object binding (`ObjectBelonging`, `ExtendedConfigurationObject`) with known special cases;
- XDTO package target namespace, declaration order, local/imported references, duplicate types/properties, metadata/configuration binding and suspicious `xs:anyType` degradation review;
- role `Rights.xml` global flags, object/right/RLS/template structure, companion-role binding and version-aware omitted-right interpretation.

When a task needs structural behavior outside this local coverage, consult actual target XML first, then this external corpus and/or official evidence; do not extrapolate a generic XML grammar.

## Form DataPath boundary

The upstream form corpus/spec is useful structural evidence that `cfg:ConstantsSet` is a managed-form attribute type and that controls serialize `DataPath` strings. It does **not** prove the runtime member composition of a particular ConstantsSet. Treat that composition as target-form/runtime evidence. A nested binding such as `НаборКонстант.X` requires proof that `X` belongs to the actual set; global Constant metadata existence is insufficient.
