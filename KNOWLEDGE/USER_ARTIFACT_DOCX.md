# User-facing DOCX artifact delivery

This contract governs only the human-facing Word projection of existing canonical task state.

## Presentation owner

Use `TOOLS/render_user_artifact_docx.py` with pinned runtime dependency:

`python-docx==1.2.0`

The renderer is presentation infrastructure only. It does not own:
- requirements semantics/readiness;
- Project Context truth;
- evidence/proof state;
- ChangePackage semantics;
- validation/release status.

Do not commit generated `.docx` files or binary DOCX templates into SHAREABLE_CORE. Runtime DOCX files are task outputs.

## Separate-file default

Each applicable user-facing artifact is generated as its own DOCX file:

- requirements: `Функциональная спецификация.docx`;
- manual transfer: `Инструкция по внедрению.docx`;
- implementation notes: `Особенности реализации.docx`;
- line-by-line justification: `Построчное обоснование изменений.docx`.

Do not combine these documents unless the user explicitly requests a combined/alternate format. Machine/proof artifacts remain in native formats.

One renderer invocation produces exactly one artifact class.

## Triggers

### requirements
Generate when a human-readable requirements / functional specification / TZ artifact is requested or required by the project.

Source contract:
`TEMPLATES/REQUIREMENTS_ARTIFACT_TEMPLATE.md`

### manual_transfer
Generate when `MANUAL_TRANSFER_INSTRUCTION` is the selected delivery mode.

Source contract:
`TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md`

### implementation_notes
Generate for every non-trivial implementation.

Source contract:
`TEMPLATES/IMPLEMENTATION_NOTES_DOCX_TEMPLATE.md`

### line_by_line
Generate only on explicit user request.

Source contract:
`TEMPLATES/LINE_BY_LINE_JUSTIFICATION_DOCX_TEMPLATE.md`

The renderer itself requires `explicit_user_request=true` for this artifact.

## Language and fidelity

For a Russian user/project:
- headings, labels, explanations and warnings are Russian;
- exact object names, procedures/functions, code, API identifiers, paths, hashes and required machine tokens remain literal;
- exact source/code fragments must not be normalized by the renderer.

The renderer must not invent:
- source identities;
- before/after values;
- standards/rules;
- implementation choices;
- proof/readiness.

## Filename rules

Default filenames above are canonical user-facing names.

A user-requested alternate basename is allowed when:
- it remains a single `.docx` filename;
- it contains no path traversal or invalid filename characters;
- it does not use pseudo-version suffixes such as `v2`, `final`, `fix`, `new`.

Revision identity belongs in project/task metadata/history rather than filename suffixes.

## Proof boundary

DOCX generation proves only that a user-facing projection could be rendered from the supplied payload.

It does not prove:
- requirements readiness beyond the requirements gate;
- application to target;
- deployment/import;
- runtime behavior;
- release readiness.

Final delivery language must remain bound to the existing canonical owners.

## Validation

Public regression must prove:
- four artifact classes produce separate files;
- exact Russian labels/order;
- requirements conditional sections can be omitted when empty;
- internal authoring rules are not rendered;
- manual transfer is object-first, not STEP-first;
- implementation notes header/table are exact;
- line-by-line output requires explicit request;
- code/AUTHOR_MARKER text remains literal;
- no accidental combined document is produced.
