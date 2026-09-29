# PROJECT_CONTEXT template

Use this as durable project state. Populate from repository/artifact evidence first; ask only unresolved material gaps. For project-policy fields use `KNOWN`, `DERIVED_WITH_EVIDENCE`, `OPEN`, or `NOT_APPLICABLE`. Do not use assumptions for permissions, protected surfaces, attribution syntax, or delivery shape.

Mutable durable decisions are not eternally true. Read `KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md`: newer explicit project decisions/evidence must supersede, invalidate or force revalidation of conflicting older context rather than coexist with it as current truth.

## Bootstrap state
- bootstrap status: OPEN | READY_WITH_GAPS | READY
- project-context revision / source commit:
- last refreshed because:
- unresolved material project questions:
- repository/source completeness limitations:

## Project decision lifecycle

For each material mutable project decision keep one record per `id` and one current decision per `decision_key`.

- id:
- decision_key:
- claim:
- status: ACTIVE | TEMPORARY | REVALIDATION_REQUIRED | SUPERSEDED | INVALIDATED
- scope:
- established_by / evidence:
- evidence dependencies: kind / id / fingerprint
- decision dependencies:
- supersedes:
- superseded_by:
- temporary reason:
- replacement criterion:
- revalidation triggers:
- status reason:
- last revalidated:

Rules:
- `TEMPORARY` must keep its reason, replacement criterion and revalidation triggers; never promote a proxy to a permanent invariant merely because it survived multiple chats.
- `SUPERSEDED`/`INVALIDATED` records remain historical provenance, not current project truth.
- changed evidence fingerprints make only dependent decisions `REVALIDATION_REQUIRED` until rechecked.
- conflicting `ACTIVE`/`TEMPORARY` decisions for the same `decision_key` are invalid.
- technical route identity (BP/document type/operation/action) is not automatically a business applicability predicate; record the authoritative business owner/source separately.

## Identity
- Project:
- Actual deployed/user baseline artifact:
- Baseline SHA256 / configuration commit:
- Candidate SHA256 / change set:
- repository / branch / commit and role:
- Cleverence appName/appVersion:
- minPlatformVersion:
- configId:
- 1C configuration/version:
- official 1C release baseline used for provenance comparison:
- 1C source provenance: TYPICAL_1C | TYPICAL_WITH_CUSTOMIZATIONS | CUSTOMIZATION | NOT_PROVEN_AS_TYPICAL
- provenance evidence / diff against official release:
- 1C platform:
- source roles: deployed | candidate | reference | historical | unknown

## Artifact/source topology
- artifact family / role / layout / confidence:
- authoritative source root(s):
- nested container structure:
- configuration vs runtime separation:
- missing source layers/dependency closures:
- evidence:

## Review routing
- surface: ANALYSIS_ONLY | ONEC_ONLY | CLEVERENCE_ONLY | CROSS_SYSTEM
- risk: R0_LOCAL | R1_CONTRACT | R2_STATEFUL_RUNTIME | R3_CROSS_SYSTEM
- routing evidence:

## Modification policy
- status/evidence:
- allowed objects/files/systems:
- forbidden/protected surfaces:
- existing project/customer/third-party code may be changed:
- unrelated refactoring allowed:
- existing comments/attribution markers may be rewritten:
- preserve original user files: yes | no
- minimal coherent diff: yes | no
- typical 1C configuration / customization / vendor code modification policy:
- extension/preferred adaptation policy:
- form change mode: PROGRAMMATIC_ONLY (universal floor; interactive Designer/Configurator form structure/property mutation is forbidden)
- form mutation evidence: exact programmatic/static artifact route, affected Form.xml/metadata artifacts and validation evidence
- form mutation fallback: BLOCKED/EVIDENCE_REQUIRED when no authorized programmatic/static route is proven; never fall back to interactive editing
- environment/AppDescription/version changes allowed:

## Attribution and comment contracts

Resolve each independently and bind it to source evidence.

### METADATA_ATTRIBUTION
- status:
- applies to:
- exact `Comment` / `Комментарий` value or construction rule:
- required company/person/task/date components:
- evidence:

### AUTHOR_MARKER
- status: KNOWN | OPEN | NOT_APPLICABLE
- development gate: AUTHOR_MARKER_READY | AUTHOR_MARKER_BLOCKED
- applies to new blocks / one-line changes / modified typical 1C code / customizations / object-property attribution:
- syntax source: SKILL_DEFAULT_1C | EXPLICIT_PROJECT_OVERRIDE | EXPLICIT_USER_OVERRIDE
- explicit override syntax (only when explicitly supplied):
- ФамилияИО:
- organization marker: ПервыйБит (fixed by Skill default when no explicit override applies)
- Дата value / rendering policy:
- НомерТЗ:
- unresolved required values:
- evidence:

### TECHNICAL_COMMENT
- status:
- expected when:
- forbidden/redundant style:
- project-specific wording/format constraints:
- evidence:

### PUBLIC_INTERFACE_COMMENT
- status:
- procedures/functions requiring it:
- parameter/result/side-effect/context format:
- evidence:

### EXISTING_COMMENT_POLICY
- status:
- preserve/update/remove rules:
- may historical markers be normalized:
- evidence:

## Other evidenced project conventions
- object/module prefix:
- regions/formatting convention:
- naming/transliteration convention:
- Operation/Action naming convention if project-specific:
- source evidence for each convention:

## Scope and delivery
- primary development result mode: DIRECT_SOURCE_CHANGESET | MANUAL_TRANSFER_INSTRUCTION | PATCH_DIFF | IMPORTABLE_ARTIFACT | FULL_COMPARE_SET | ANALYSIS_REPORT | OTHER
- supporting result modes:
- user-requested / accepted result mode:
- selection reason / constraints:
- result artifact path/name/format:
- 1C delivery form:
- Cleverence delivery: FULL_COMPARE | MANUAL_PATCH | BOTH | OTHER
- delivery artifact family/role/layout:
- DIRECT_SOURCE_CHANGESET exact meaning for this baseline:
- PATCH_DIFF exact meaning for this baseline:
- IMPORTABLE_ARTIFACT exact meaning and import mechanism:
- FULL_COMPARE_SET exact meaning for this baseline:
- files that must remain byte-identical:
- files that must never enter delivery:
- manifest/hash/encoding requirements:
- deployment/import procedure:
- evidence:

### ProjectSnapshot acquisition capability
- collector delivery available from skill/chat: yes | no | unknown
- accepted collector artifact identity / version when relevant:
- usable client mode: managed desktop/thin client | web | other | unknown
- available acquisition backends: SOURCE_EXPORT | RUNTIME_METADATA | MANUAL_ATTACHMENTS | other
- Designer/Configurator availability:
- local authentication constraint (never store credentials/secrets):
- last evidenced configuration name/version when this is a durable project fact:
- capability limitations / unsupported evidence classes:
- revalidation triggers (platform/configuration/auth/deployment changes):
- evidence:

Task-specific `request_id`, CollectionPlan rows, package path/hash, returned source files, delta requests and ChangePackage linkage belong to the current task evidence/ledger/orchestration state. Do **not** accumulate them in durable `PROJECT_CONTEXT` as project policy.

The fields below define durable **project delivery policy/constraints**, not the rendered task instruction itself. When `MANUAL_TRANSFER_INSTRUCTION` is selected, render the task-specific human instruction through `TEMPLATES/MANUAL_TRANSFER_INSTRUCTION_TEMPLATE.md`. Stable step ids, payload refs and task-specific transfer steps belong to the task/ChangePackage artifact, not durable PROJECT_CONTEXT.

### MANUAL_TRANSFER_INSTRUCTION contract
- applies: yes | no
- ordered create / modify / delete inventory:
- metadata objects and exact material properties to create/change:
- modules / procedures / functions and exact code contents:
- insertion / replacement / region / handler anchors:
- forms / commands / roles / subsystems / scheduled jobs / event subscriptions / integration wiring, as applicable:
- dependencies and required execution/import order:
- data migration / initialization / one-time steps, if applicable:
- post-transfer static verification:
- runtime scenarios the implementer/user must execute after transfer:
- material implementation choices left for the human to invent: none | BLOCKING list

### Delivery proof boundary
- delivered artifact completeness validated: yes | no | pending
- applied target bytes/state observed: yes | no
- deployment/import success observed: yes | no
- runtime proof observed: yes | no | partial
- strongest justified claim about this delivery:

## Business invariants
- invariant list:
- established_by / relied_on_by / defensively_rechecked_by / reason_for_recheck:
- accepted cases:
- rejected cases:
- boundary/default/zero/partial cases:
- type/metadata/platform-guaranteed domains:
- external/legacy/exchange/migration boundaries that can bypass them:

## Data identity
- smallest stable business identity:
- intrinsic identity fields:
- representation/normalization fields excluded from identity:
- quantity/unit conversion contract:
- plan identity:
- fact/CurrentItem identity:
- special analytics / indivisible item types:
- derived-key validation before first mutation:

## Standard pipeline and field lifecycle
- standard business pipeline:
- source dimension → intermediate representation → target mapping:
- preserved dimensions:
- lost dimensions and evidence:
- parallel pipeline necessity/constraint:
- custom field assignment:
- writers after custom point in execution order:
- authoritative final value owner:

## Query sentinel contracts
- parameter / normal meaning / sentinel meaning / caller authorization:
- normal / empty / nonexistent / other-context expected cardinality:

## Cross-system contract
- authoritative business applicability / derived-predicate owner:
- 1C producer:
- mapping/business process:
- Cleverence writer/router:
- technical route vs business-predicate separation:
- if predicate is recomputed in multiple systems: input parity / semantic-equivalence / revalidation evidence:
- grouping/search key:
- 1C consumer:
- retry/re-entry/partial failure semantics:

## Runtime/evidence capabilities
- available Configurator:
- available Designer/emulator/device:
- available 1C runtime:
- browser/runtime automation available:
- logs/diagnostic access:
- runtime scenarios the assistant can execute directly:
- runtime scenarios the user/environment must execute:
- performance/cardinality cases:

## Evidence requests
- request id / status / exact artifact-or-answer / claim controlled / blocking / reason:

## Evidence dependencies
- evidence id / claim / source / hash-or-version / invalidated by:

## Knowledge extraction
- outcome: PROMOTED | PROJECT_ONLY | NO_REUSABLE_KNOWLEDGE | EVIDENCE_PENDING
- project-context updates:
- promoted universal statements / owners / regression coverage:
- deduplication decision:

## Requirements contract
- requirements contract artifact/hash:
- requirements gate outcome: REQUIREMENTS_BLOCKED | REQUIREMENTS_READY_WITH_ASSUMPTIONS | REQUIREMENTS_READY
- unresolved blocking questions:
- explicit non-blocking assumptions / impact / validation plan:
- need → target outcome → target behavior → acceptance traceability:
