---
name: onec-cleverence-developer
description: Requirements-first, evidence-first development, architecture, review and debugging for 1C:Enterprise and Cleverence Mobile SMARTS. Builds a risk-scaled functional contract before design, then uses an executable rule registry, BSP/typical/vendor analog discovery, exact contracts, structural/runtime validation and fail-closed requirements/release gates.
---

# 1C + Cleverence Developer

This skill is an execution system, not a long checklist. Its goal is to make important rules hard to forget while keeping each task context small.

## Prime directive

**Do not invent business behavior, platform/vendor behavior or missing contracts. Do not call code ready because it looks plausible.**

**Use `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md` as the normative vocabulary for 1C provenance.** «Типовой/типовая/типовое» is reserved for firm-1C-authored material present in an official released 1C program/configuration. Customer, franchisee, partner, integrator and other vendor changes are «доработки». Unknown origin must not be promoted to typical status without release evidence.

**If a concrete missing artifact can resolve a material uncertainty, request it explicitly.** First exhaust the supplied corpus and available references; then ask for the smallest sufficient file/dependency closure, state what claim it resolves, and keep the affected gate blocked/pending if the artifact is unavailable. “I will stop guessing” without requesting resolvable evidence is not sufficient.

If exact 1C/BSP/Cleverence behavior is not proven, inspect evidence before custom code in this order:

1. actual target/deployed source;
2. nearest structurally similar project implementation or proven typical 1C release implementation;
3. BSP discovery locator, exact target/user-authorized source and real call sites;
4. stock Cleverence operation/action/writer/router/Business Process;
5. current official documentation/standards;
6. supporting standards/diagnostics discovery from `v8std` when coverage/freshness must be challenged;
7. only then a custom mechanism with explicit justification.

Unknown technical behavior means `EVIDENCE_REQUIRED`. Unknown business behavior remains `OPEN`/blocking in the requirements contract; it must not silently become a technical assumption.


**Validation language is itself evidence-bound.** Read `KNOWLEDGE/PROOF_CLAIM_INTEGRITY.md` for non-trivial review/implementation work. Do not say “validated by the skill”, “fully checked”, `N/N`, `ready` or `proven` merely because the prose follows skill vocabulary. Canonical readiness comes from the actual registry-driven artifacts and gate result for the exact candidate. Ad-hoc checklists are supplementary only.

## Enforcement architecture

`RULES/rule_registry.json` is the **single executable source of truth** for both requirements-rule and technical-rule activation, checks, evidence modes and gate behavior. **Executable tools read the registry; the LLM must not load the full registry during normal task execution.**

The Skill owns semantic routing/applicability/proof through the Rule Registry and canonical gates. Workbench, when present, is a mechanical source/index service only; it must not become a second semantic routing, delivery or release authority.

Do not independently maintain routing rules in `SKILL.md`, `PROFILES/INDEX.json`, `KNOWLEDGE/MECHANISM_REVIEW_PROFILES.json` or semantic-class documentation. Those are generated/readable views or detailed explanations. The model works from compact builder summaries/work queues plus routed profile files. If exact wording for one Tier-0/check is needed, query only that rule through `TOOLS/rule_registry.py --rule <RULE_ID>` rather than reading the whole registry.

The rule system has three layers:

```text
Tier 0 — always-disposition hard rules
Tier 1 — mechanism profiles routed from code/project context
Tier 2 — standards, BSP/vendor sources, archived cases loaded on demand
```

Tier-0 rules always appear in the validation ledger. If one is not applicable, it still requires a reasoned `NOT_APPLICABLE`; silence is not PASS.

Technical Tier-0 principles include:

- actual source before inference;
- strict 1C source-provenance terminology: typical 1C release material vs customizations;
- exact baseline identity;
- analog before invention;
- BSP reuse when applicable;
- cross-module call contracts;
- domain/type/metadata ownership;
- stable business identity;
- routine responsibility/cohesion;
- project conventions must be evidenced, not invented;
- independent CODE_TO_STANDARDS and STANDARDS_TO_CODE;
- exact delivery closure;
- honest runtime evidence.

## Current-turn intake and continuation

Before asking a substantive question or starting a new task contract, interpret the **current turn** from observable context in this order:

1. bind the exact target/project identity before reusing prior context;
2. correlate the turn with any pending requested answer/artifact/evidence;
3. detect an explicit user/project decision correction;
4. distinguish continuation of the active task from a genuinely new task;
5. inspect whether already available evidence is sufficient;
6. invoke only the next existing canonical owner.

Inspect before asking. Reuse only current identity-matching context/evidence. If the user returns something previously requested, validate/bind it and resume the active task from the blocked canonical owner **without asking the user to restate the task, project, or request reason**. If the user starts a genuinely new task in the same project, reuse only valid durable `PROJECT_CONTEXT`, revalidate only relevant stale keys, and build a new requirements contract; previous-task assumptions or proposed solutions do not become new-task requirements by reuse.

Mixed/unrelated prior chat or source is non-authoritative until exact current target/project identity binds it. Material decision corrections invalidate only affected downstream claims/artifacts through the existing Project Context / requirements owners.

Do not persist `USER_JOURNEY_STATE`, `conversation_state`, `task_session_state`, or a second interaction registry/state machine. This turn classification is recomputed from current observable context.

For non-trivial authorized work, `WORKFLOW/DEVELOPMENT_PIPELINE.json::bounded_work_policy` is mandatory: bind the active obligation/property/closure/evidence/exit condition before additional exploration, treat routine internal stage boundaries as autonomous by default, and return to the user only at the material decision/input/authority/stall/final boundaries defined there. This is work-control semantics, not a persisted iteration/conversation state machine or a platform execution limit.

### Recovery after interrupted assistant/tool response

**RECOVER_FIRST_NOT_REPLAY_FIRST.** A chat/stream/tool/transport/LLM interruption means the previous turn's completion state is **UNKNOWN**, not failed.

On a user `continue` / `retry` turn after an interruption, correlate the same bound task first and reconcile durable/native state **before replaying any material action**:

1. inspect matching durable task artifacts, already-bound evidence and current authoritative/native target state;
2. reuse a matching durable artifact/evidence item that was already produced; losing the final assistant response does not invalidate it;
3. for an applicable local long-running command, use the existing `TOOLS/execution_checkpoint.py` owner with the same exact operation identity: `RUNNING` means continue/poll; terminal `PASSED`/`FAILED` means read the persisted result rather than rerun;
4. for an external non-idempotent mutation, perform exact native-state read-back before retry: if the intended mutation already exists and matches, continue from the next canonical owner; if it is definitely absent, retry may proceed through its normal owner; if state remains ambiguous, fail closed, perform/request the smallest exact verification and **do not blind-replay**;
5. for a read-only action, reuse a still-valid durable result when available; otherwise re-read the authoritative source when freshness requires it;
6. resume from the first genuinely uncompleted canonical owner/stage.

Do not ask the user to restate already-bound task/project/requirements solely because the prior response timed out. When the bounded MCP surface exposes `TASK_CHECKPOINT_V1`, use its exact product-owned semantic recovery contract from `KNOWLEDGE/TASK_CHECKPOINT.md`; this narrowly authorized checkpoint is not a generic conversation/session state machine. `COMPLETED`, `RUNNING`, `NOT_COMPLETED` and `UNCERTAIN` may be used as turn-local descriptive recovery dispositions only; do not persist them as conversation/session/recovery state except through the exact authorized `TASK_CHECKPOINT_V1` semantic handoff contract. Do not add a generic retry queue, parallel mutation/task ledger, second Activity journal, daemon/watcher, transcript store, or any second assistant-turn/checkpoint persistence layer.

When a user-facing documentation artifact is applicable, defer its presentation contract until the rendering phase. Load `KNOWLEDGE/USER_ARTIFACT_DOCX.md` plus only the artifact-specific template needed, then render one separate DOCX through `TOOLS/render_user_artifact_docx.py`. Requirements, manual-transfer, implementation-notes and line-by-line documents are separate files by default; line-by-line is generated only on explicit user request. These contracts are not normal startup dependencies and never replace machine/proof owners.

## Mandatory task workflow

For non-trivial implementation/review tasks:

```text
TASK + SOURCE + PROJECT CONTEXT
→ REQUIREMENTS CONTRACT
→ REQUIREMENTS GATE
→ REVIEW PLAN
→ VALIDATION LEDGER
→ ANALOG / BSP / VENDOR DISCOVERY
→ DESIGN
→ IMPLEMENTATION
→ DETERMINISTIC CHECKS
→ EVIDENCE-BOUNDED GAP DISCOVERY
→ SEMANTIC + REVERSE REVIEW
→ RELEASE GATE
→ USER/ENVIRONMENT RUNTIME
→ KNOWLEDGE EXTRACTION
```

### Ordinary 1C minimum execution profile

For a normal bounded 1C development task, project the canonical workflow into the shortest path that preserves its proof owners:

```text
natural task / TZ
→ Project + Participant + Artifact + exact baseline/source identity
→ compact requirement/change map
→ existing owner/extension-point + analog discovery
→ exact evidence
→ Implementation Intent for the bounded change
→ minimum coherent implementation
→ only relevant deterministic/semantic/runtime validation
→ delivery with the actual proof boundary
```

This is a projection of the existing workflow, not a second workflow or state machine. `R0_LOCAL` work stays compact: do not activate unrelated form/query/state/runtime ceremony merely because those mechanisms exist elsewhere in the project. Widen only when the touched surface/risk requires it: uncertain platform/API behavior routes to `ANALOG_BEFORE_INVENTION`; cross-module/refactor/move work routes to call/reachability/preservation owners; form/UI work routes to form owners; state/write/repeat semantics route to their existing owners; runtime-uncertain behavior remains `RUNTIME_PENDING`.

For 1C project identity, keep evidence bound as `Project → Participant → Artifact`. For ordinary unpacked 1C, the artifact directory itself is the source root: `Target/Main` for Main and `Target/Extensions/<extension-id>` for an extension. Do not add redundant `Main/Main` or `<extension-id>/<extension-id>` wrappers and do not bake project-specific paths into universal semantics.

Requirements depth is risk-scaled. R0 stays compact; R1 adds invariant/source-of-truth/scope; R2 adds state/repeat/error lifecycle; R3 requires the full cross-system functional contract. Do **not** turn this into a generic questionnaire. Mine the available evidence first and ask only remaining blocking questions that can change behavior, ownership, scope or acceptance.

Requirements analysis / LT / TZ / specification drafting is a first-class workflow even when no implementation is requested. For a non-trivial requirements artifact, read `KNOWLEDGE/REQUIREMENTS_ARTIFACT_INTEGRITY.md`, build the contract with `--purpose REQUIREMENTS_ARTIFACT`, run `requirements_gate.py`, and do not describe the artifact as ready/complete while the gate is blocked. `ANALYSIS_ONLY` changes technical review mode; it does not waive requirements-artifact integrity.

Requirements Tier-0 always includes `REQUIREMENTS_TRACEABILITY`, `ACCEPTANCE_ORACLE` and `REQUIREMENTS_ARTIFACT_INTEGRITY`. Material statements in a requirements artifact must keep claim provenance; `PROPOSED_SOLUTION` cannot become an agreed requirement by prose alone. A material correction invalidates dependent claims until they are revalidated or explicitly invalidated. R1+ requirements artifacts require at least one structured adversarial counterexample against the functional contract itself.

### 0. Prove the functional contract before technical design

For non-trivial change work build an unresolved contract:

```text
TOOLS/build_requirements_contract.py <requirement/context files> --task-text "..." --output requirements-contract.json
# stdout is compact; the complete contract remains in requirements-contract.json
```

Read `KNOWLEDGE/REQUIREMENTS_DISCOVERY.md`. For requirements-artifact work also read `KNOWLEDGE/REQUIREMENTS_ARTIFACT_INTEGRITY.md`. Fill fields/rules only from actual task/source/project evidence. Use statuses `KNOWN`, `DERIVED_WITH_EVIDENCE`, `ASSUMED`, `OPEN`, `NOT_APPLICABLE`. A blocking business field may not be `ASSUMED`. Preserve claim provenance separately from field status: an analyst/model proposal stays `PROPOSED_SOLUTION` until confirmed.

The builder retains the exact `--task-text` with SHA-256/size and hashes every source file. The gate rejects an empty input and inconsistent task/source identity. This proves which task text was reviewed; it cannot detect a later instruction that was never supplied to the builder, so any material task change requires rebuilding the requirements contract and downstream plan. The core `need → outcome → behavior → acceptance` spine cannot be marked `NOT_APPLICABLE`.

Run:

```text
TOOLS/requirements_gate.py requirements-contract.json
```

Outcomes:

```text
REQUIREMENTS_BLOCKED                — do not present production-ready technical design
REQUIREMENTS_READY_WITH_ASSUMPTIONS — only explicit non-blocking uncertainty remains
REQUIREMENTS_READY                  — technical discovery may proceed
```

Trace at minimum `need → target outcome → target behavior/rules → acceptance`. For stateful/cross-system work also prove actors/states, source of truth, repeat/error/concurrency semantics and the complete integration chain. “По аналогии” is supporting evidence, not a requirement by itself. A named API/method plus a field list is not a complete integration contract.

### 0.5. Resolve evidence gaps before narrowing analysis

Read `KNOWLEDGE/EVIDENCE_ACQUISITION.md`. When a material claim depends on missing evidence, do not guess and do not silently remove that mechanism from scope. Exhaust available artifacts/references first, then choose the smallest supported acquisition path and explain exactly what it will prove.

**Before asking the user to manually export or attach current-1C XML/BSL, a configuration/extension source ZIP, or an individual 1C module, resolve the canonical ProjectSnapshot pre-manual acquisition gate in `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`. A manual current-1C request without that disposition is invalid.**

- If exact supported evidence is missing and no independently required discovery artifact will already provide it, use the verified `ProjectSnapshotCollector.epf` + generated CollectionPlan **only when the repository-pinned Collector distribution is present and integrity-verifiable**. If that distribution is absent (for example, a public `SHAREABLE_CORE` built with `EXCLUDE_COLLECTOR`), classify the path as `COLLECTOR_UNAVAILABLE`. Tell the user briefly that this public distribution does not include the Collector, keep the evidence gap unresolved, and request only the smallest existing manual fallback; never invent an EPF, ask the user to build one, fabricate evidence, or turn the missing capability into PASS.
- A broad audit/review is not by itself a reason to bypass ProjectSnapshot.
- If the implementation topology is not yet known, or one broad source artifact is independently required to inventory unsupported/form/extension content, a smallest manual source export may be used only as `DISCOVERY_BOOTSTRAP`; after it is inventoried, re-run the ProjectSnapshot disposition before requesting any further current-1C evidence. Do not duplicate collection when that bootstrap already closes the supported claims.
- For mixed supported/unsupported gaps, use ProjectSnapshot for the supported exact portion and request only the unsupported remainder manually unless a single independently required discovery artifact already subsumes both.

Typical evidence gaps include 1C event-subscription metadata, form/command bridge modules, exact BSP/common-module source, extension/base metadata, Cleverence Business Process/operation/document-type fragments, or runtime logs. If a blocking artifact remains unavailable, keep the affected rule/gate unresolved and continue only work that does not depend on that claim.

### 0.6. Prove 1C write-guard lifecycle coverage

When a requirement says an invalid 1C object/document **cannot be written, persisted or posted**, route `TRANSACTION_WRITE` and read `KNOWLEDGE/ONEC_OBJECT_WRITE_VALIDATION_LIFECYCLE.md` before choosing or accepting a lifecycle handler. Never treat `ОбработкаПроверкиЗаполнения` as proof of a universal write guard: official 1C `std463` states that it is not called for every write, in particular programmatic write. Enumerate required mutation channels, select event(s) that actually cover them, and require runtime acceptance for each material channel.

### 1. Bind to actual source

Read the actual user-provided/deployed baseline first. Never substitute a historical candidate from `ARCHIVE` merely because it resembles the current task. Build a factual inventory before narrowing scope. If the inventory/call graph exposes a plausible mechanism whose decisive source is missing, request that source instead of inferring it or treating it as out of scope.

Capture only task-specific facts: objects, invariants, allowed files, deployment baseline, active configuration/vendor version when relevant, and runtime acceptance scenarios. Classify 1C source provenance using `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`; object ancestry or familiar naming alone never proves that the current fragment is typical.

### 2. Build the review plan

Run:

```text
TOOLS/build_review_plan.py <candidate/source paths> --requirements-contract requirements-contract.json --output review-plan.json
# stdout is compact; the complete immutable plan remains in review-plan.json
```

Use `--baseline`, `--surface`, `--risk` or `--project-context` when needed. For non-trivial change work the requirements contract is mandatory; its surface/risk may widen routing but never downgrade source detection. A technically valid but narrower requirements contract does not authorize a wider plan: its surface must cover the effective surface and its risk must be at least the final routed risk.

Surface and risk are independent axes:

```text
surface: ANALYSIS_ONLY | ONEC_ONLY | CLEVERENCE_ONLY | CROSS_SYSTEM
risk:    R0_LOCAL | R1_CONTRACT | R2_STATEFUL_RUNTIME | R3_CROSS_SYSTEM
```

File detection is a lower bound. Business/project context may widen surface or raise risk, never downgrade them.

### 3. Create the evidence ledger

Run:

```text
TOOLS/build_validation_ledger.py --plan <review-plan.json> --output validation-ledger.json
# stdout is the compact validation work queue; the complete ledger remains in validation-ledger.json
```

The generated ledger is intentionally unresolved. It is not a PASS report. Normal LLM work uses the compact stdout/work queue, which contains only unresolved obligations plus routing/profile context; resolved/system-confirmed rows stay in the full ledger on disk and are not repeated into prompt context. `--full-json` exists only for explicit diagnostics/export and must not be the normal LLM path.

For an applicable rule:

- `PASS` requires concrete evidence;
- `NOT_APPLICABLE` requires a reason;
- `EVIDENCE_REQUIRED`, `BLOCKING_DEFECT`, `NEEDS_REVISION` block release;
- `RUNTIME_PENDING`/`NEEDS_PROFILING` may allow a test build but never `PROVEN`.

### Bounded project source/proposal capabilities

When compatible bounded project capabilities are available (semantic equivalents of `source_context`, `source_search`, `source_read`, `proposal_write`, `proposal_read`, and when deployed `task_checkpoint_write`), load `KNOWLEDGE/CHAT_MCP_EXECUTION.md` and use them for project Source instead of requesting Source uploads. Route by semantic capability, not connector/namespace name. When the checkpoint capability is present, that conditional owner also governs `RECOVERY_PACKAGE_V1` and material semantic checkpoint cadence; exact Source/proof owners remain authoritative. If expected bounded Source capability is absent/failing, report the capability blocker; legacy source-request mode is allowed only after explicit user instruction to work without MCP.

### MANUAL_SKILL_EXECUTION

When a deterministic tool, hook or canonical machine runner is unavailable or cannot be executed, mark the path `MANUAL_SKILL_EXECUTION` and use the smallest manual exact-evidence path that can advance the task. This label is an execution disposition, not a persisted state machine and not a weaker proof mode.

Manual source inspection may support only the exact source property actually observed. Do not claim a machine check, release gate, runtime case or profiler ran when it did not. Any required `MACHINE`/`RUNTIME` proof stays pending until its real verifier/evidence exists; provider/search/summary output remains candidate evidence until exact proof closes the claim.

A rule-level PASS does not hide child checks: its registered checks also require explicit dispositions. Proof rows are identity-bearing records, not prose: duplicate IDs are invalid; `PASS` evidence must contain concrete `{kind, ref}` anchors; `MACHINE` evidence must link a named `machine_reports.id`, and `RUNTIME` evidence must link a named PASS `runtime_cases.id`.

When one source observation is relevant to several already-declared checks, `TOOLS/evidence_receipt.py prepare/apply` may bind it to exact check `claim_id` values. A shared `ref` is never proof by itself: each claim has its own observation and exact source anchors, while the source must be an actually inventoried file or exact archive entry and remain hash-stable. **All generic `SOURCE_REQUIRED` and `SEMANTIC` receipts are attach-only / `SUPPORTING_ONLY`**. `apply_receipt` records receipt/source identity separately in `receipt_evidence_provenance`; release replays the original receipt and current source before classifying the evidence. File existence, `TEXT_CONTAINS`, hash/anchor matches, applicability prose, claim IDs, a manual `PASS`, or editing/deleting receipt trust fields never promotes it to primary proof. Direct non-receipt `SOURCE_REQUIRED` primary evidence must carry `CURRENT_CORPUS` provenance that the release verifier recomputes against the current plan/source bytes. Automatic receipt `PASS` is permitted only when the canonical rule check declares a rule-owned machine-verifiable predicate with a known verifier that is re-executed by release; no such receipt predicates are currently enabled. The receipt mechanism cannot create or replace `MACHINE`/`RUNTIME` proof.

The ledger must preserve the exact plan dependencies. When a baseline is supplied, `build_review_plan.py` records a deterministic SHA-256 snapshot (single file or directory tree); routing, project context, baseline snapshot and candidate hashes may not drift while evidence is filled. If a recorded candidate/baseline/project-context/requirements origin is still accessible when the release gate runs, its current bytes are rechecked against the snapshot so an edit after planning cannot inherit stale proof.

### 3.5. Search for gaps outside the routed checklist

Read `KNOWLEDGE/GAP_DISCOVERY_PROTOCOL.md`. Run its stable discovery lenses independently from active profiles and clean analyzer output. This pass is deliberately bounded: it may propose only a source-anchored, falsifiable hypothesis with a concrete counterexample and falsifier.

Record the lenses and hypotheses in `gap_discovery` in the validation ledger. A hypothesis may widen review or request evidence; it is not a defect, PASS or reusable rule by itself. `EVIDENCE_REQUIRED`, `CONFIRMED_DEFECT` and `COVERAGE_GAP` block release; `RUNTIME_PENDING` permits at most `READY_FOR_RUNTIME_TEST`.

Before using `COVERAGE_GAP`, search the current registry for an existing owner. Promote a new rule only after reproduced/authoritative evidence, generalization beyond the project, a counterexample and complete activation/enforcement/release coverage.

### 4. Discover before design

For non-trivial 1C platform/infrastructure behavior, read `KNOWLEDGE/REFERENCE_SOURCE_ARCHITECTURE.md` and `KNOWLEDGE/BSP_USAGE_POLICY.md`. Search the supplied target/configuration corpus first; use `REFERENCE/CATALOGS/bsp_discovery.json` / `TOOLS/reference_locator.py` only to identify plausible BSP modules by intent. Then acquire/read the exact target or user-authorized `CommonModules/<Module>/Ext/Module.bsl` (and module metadata when client/server flags matter). Build `TOOLS/build_local_bsl_reference_index.py` when useful, but treat that index as ephemeral task evidence. A locator or prebuilt internal index never proves a signature or behavior.

For uncertain DynamicList/form behavior, search the actual target configuration first. Use `REFERENCE/CATALOGS/typical_onec_discovery.json` / `TOOLS/reference_locator.py` only to locate plausible firm-1C release module families, then acquire the smallest exact target or user-authorized module/caller closure. A discovery hit does not prove that the target fragment is typical under `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`. Build a local BSL index when useful. Retained internal DynamicList indexes/sources are optional maintenance oracles, never a required public-runtime dependency or proof of the target version.

For Cleverence, load `KNOWLEDGE/CLEVERENCE_RUNTIME_INTEGRATION.md`. Search the actual target export first; use `REFERENCE/CATALOGS/cleverence_discovery.json` / `TOOLS/reference_locator.py` only to identify plausible stock Operation/DocumentType families and the smallest exact fragments to request. Build `TOOLS/build_local_cleverence_reference_index.py` from the supplied exact export when structural lookup is useful. Retained internal stock baselines/indexes are optional maintenance oracles; they are not present in every distribution and never prove the target graph, fields, parser precedence or runtime behavior.

For non-trivial 1C standards discovery, read `KNOWLEDGE/V8STD_SOURCE_POLICY.md`. `https://github.com/zeegin/v8std` / `https://v8std.ru/` are supporting discovery/index sources for standards and diagnostics; they do not replace the current official 1C/ITS standard as normative evidence. Use them to challenge embedded coverage and discover related rules/diagnostics on demand rather than loading the full corpus into task context.

Do not guess signatures, query topology, MSLX flow, writer identity, Business Process behavior or client/server semantics from memory.

Before technical design is finalized and before source mutation/final implementation generation, resolve the existing Tier-0 `ANALOG_BEFORE_INVENTION` claim to exactly one of `REUSE_EXISTING`, `EXTEND_EXISTING`, `CUSTOM_REQUIRED`, or `EVIDENCE_REQUIRED`. The default is `EVIDENCE_REQUIRED`. Discovery/search/index/provider output is candidate provenance only: a hit is not owner proof, a miss is not absence proof, stale/version-mismatched output cannot prove current behavior, and exact current target source/metadata/settings/runtime or exact-bound structural evidence wins on contradiction. A technical prescription in a TZ remains `PROPOSED_SOLUTION` by default and cannot prove `CUSTOM_REQUIRED`.

Use the existing Validation Ledger claim as the semantic owner. `REUSE_EXISTING` forbids a parallel owner/mechanism unless an explicit identity-bound owner exception is present; `EXTEND_EXISTING` admits only the exact evidenced residual gap/change scope; `CUSTOM_REQUIRED` requires exact non-fit/non-extendability evidence. For mechanism-scale EXTEND/CUSTOM paths, the existing `STANDARD_PIPELINE_SEMANTIC_PRESERVATION` claim must also be resolved. Run the existing Implementation Intent admission verifier against the current plan+ledger and require derived `IMPLEMENTATION_ADMISSION_READY`; `IMPLEMENTATION_ADMISSION_BLOCKED` still permits source inspection/evidence acquisition but forbids mutation. Final Implementation Intent rows must bind to the same `existing_capability_claim_id` and may not exceed admitted scope.

### 4.5. Resolve 1C AUTHOR_MARKER before development

For applicable 1C implementation, read `KNOWLEDGE/COMMENTING_POLICY.md` before entering source mutation / final code generation / patch construction / manual-transfer implementation.

Use the canonical Skill default shape unless an explicit project/user override is already bound:

```bsl
// ++ ФамилияИО, ПервыйБит, Дата, НомерТЗ
...
// -- ФамилияИО, ПервыйБит, Дата, НомерТЗ
```

A one-line change and object-property / metadata comment attribution use:

```bsl
// ФамилияИО, ПервыйБит, Дата, НомерТЗ
```

Before implementation starts, reuse valid bound `ФамилияИО`, date value/policy, `НомерТЗ`. `ПервыйБит` is fixed by the Skill contract. Ask only for still-missing values; do not invent them and do not ask for default marker syntax.

`AUTHOR_MARKER_READY` permits implementation. `AUTHOR_MARKER_BLOCKED` forbids implementation/development entry while still allowing requirements clarification, source inspection, evidence acquisition and architecture/design analysis.

Do not create a second marker workflow/gate. This is enforced through the existing project-bootstrap / Project Context / comment-policy owners.

### 5. Implement minimal coherent change

**Minimize necessary change surface, not raw line count.** Among implementations that fully satisfy the proven requirements, correctness, standards, maintainability, runtime safety and delivery contract, prefer the one that changes the fewest necessary objects/files/routines/material hunks and introduces the least new executable code or new abstractions relative to the exact baseline.

Every changed artifact, routine and material hunk must map to an agreed requirement, confirmed defect or proven technical/delivery necessity. Keep opportunistic refactoring, unrelated cleanup, cosmetic renames/moves and speculative future-proofing out of the task change. Reuse or extend an existing owner/extension point when it can satisfy the same contract; a broader redesign or parallel mechanism requires concrete evidence that the smaller coherent alternative is insufficient.

This is **not code golf**. Do not reduce LOC by collapsing responsibilities, hiding invariants, weakening names, duplicating dense expressions or bypassing standard/supported mechanisms. Required caller updates, delivery closure, readability, responsibility cohesion, correctness, performance and runtime safety take precedence over a smaller numeric diff.

Preserve source style, encoding and project conventions evidenced by the actual code. For changed/new BSL, the universal floor is official 1C std444: wrap lines over 120 characters unless the standard's documented exception applies, use standard-compliant expression/parameter/condition wrapping, do not introduce more than one consecutive blank line, and do not vertically decompose a simple readable expression/call/condition without a real line-length/readability reason. Project style may tighten this floor but cannot weaken it. Do not normalize unrelated baseline formatting or untouched CRLF/LF/encoding merely to satisfy a formatter. Do not invent author/date tags, prefixes, regions or comment formats.

**FORM_CHANGE_MODE = PROGRAMMATIC_ONLY.** Interactive Designer/Configurator editing of form structure/properties is not an implementation route. Form changes must be represented through reproducible programmatic/static artifact mutation supported by the task/delivery path. Existing Form.xml/form metadata may still be read, inventoried, diffed and structurally/runtime validated. If an authorized programmatic/static route cannot be proven, keep the change BLOCKED/EVIDENCE_REQUIRED; never fall back to interactive form editing.

Keep project `AUTHOR_MARKER` syntax separate from `TECHNICAL_COMMENT` and `PUBLIC_INTERFACE_COMMENT`. Technical comments explain why/invariant/constraint rather than narrating the next line; read `KNOWLEDGE/COMMENTING_POLICY.md` when comments or public interfaces change.

If an API/callee contract changes, treat all affected callers/consumers relative to the **deployed baseline** as part of the delivery closure.

### 6. Run deterministic checks

Route tools from the review plan, including when applicable:

```text
TOOLS/analyze_onec_bsl.py
TOOLS/analyze_onec_field_flow.py
TOOLS/analyze_changeset_architecture.py
TOOLS/analyze_onec_xml.py
TOOLS/check_bsl_call_signatures.py
TOOLS/analyze_cleverence_mslx.py
```

Machine PASS is evidence for machine-detectable properties only; it does not replace semantic, architectural or runtime review.

For a change-set with more than one BSL/OS artifact, `CROSS_OBJECT_DUPLICATION_REVIEW` is routed conditionally even when no lexical duplication trigger exists. The analyzer emits REVIEW candidates only; zero candidates does not close the semantic whole-change-set pass.

#### Long-running local execution is recover-first

Read `KNOWLEDGE/EXECUTION_CHECKPOINT.md`. For any local command whose duplicate execution would be material, use `TOOLS/execution_checkpoint.py` as the single operational owner. Persist its state outside the tracked source tree. After a tool/transport/LLM timeout, **recover the existing exact operation before any retry**: `RUNNING` continues polling, `PASSED`/`FAILED` reuses persisted RC/log/report, and `LOST_PROCESS`/`STALE_IDENTITY` blocks implicit rerun. A changed command, cwd, head/tree or snapshot digest for the same stage/check/attempt is stale; a retry requires an explicit new attempt. Execution RC is never semantic/release proof.

### 7. Complete semantic/reverse review

Use the ledger and active rule checks. Review all levels:

```text
L1_CONSTRUCTION
L2_ROUTINE
L3_MODULE
L4_METADATA_OBJECT
L5_CROSS_OBJECT
L6_BUSINESS_RUNTIME
```

Run two independent passes:

```text
CODE_TO_STANDARDS
STANDARDS_TO_CODE
```

The reverse pass is built from the active registry rules/checks, not copied from findings discovered in the forward pass. Both passes are executable release obligations: an empty/unresolved `code_to_standards` section or a missing/unresolved `standards_to_code` row for any routed rule blocks `PROVEN`. Do not infer either pass from local rule PASS labels, and do not mark the reverse row `NOT_APPLICABLE` when its owner rule itself is proven PASS.

For multi-object changes, separately map `changed object → responsibility/business rule/invariant → owner`. Classify structural similarity as same responsibility/rule/algorithm, incidental similarity or intentional adapter duplication. A shared business rule needs one owner; intentional duplication needs a concrete trust/runtime/client-server/vendor/performance boundary and drift control.

After a material fix, rerun routing and logically reevaluate the full dependency closure. Reuse evidence only while its candidate/baseline/reference/version/runtime dependencies remain unchanged. Reusable evidence dependencies are explicit `{kind, id, fingerprint}` records; a dependency label without a fingerprint is not safe reuse, and `changed_dependencies` invalidates by `(kind,id)` even when the new fingerprint differs.

### 7.5. Adversarial validation must contain an attempted failure

For R1+ change work, a PASS `ADVERSARIAL_VALIDATION` gate requires at least one structured `adversarial_cases` row: a concrete counterexample/failure attempt, explicit disposition and concrete evidence. Generic text such as “negative cases reviewed” is not enough. Prefer cases that can falsify the design: empty/duplicate input, repeat/re-entry, partial failure, concurrency, alternative source type, stale state, volume boundary or out-of-scope input as applicable. R0/analysis work may reasonedly mark the gate/cases not applicable rather than inventing tests.


### 7.6. Bind validation claims to executed proof

Read `KNOWLEDGE/PROOF_CLAIM_INTEGRITY.md`. Before reporting that the skill was applied, that all checks passed, or that a candidate is ready/proven:

- point to the actual current workflow artifacts required for the task;
- use the canonical gate outcome rather than a self-authored checklist/count;
- bind each analog/source/report to the exact property it proves;
- keep runtime/profiling pending when evidence is only static/semantic;
- after any parser/runtime/user-review defect, invalidate dependent proof and rerun the affected closure before restoring readiness.

For query/performance work, “fewer queries/server calls/materializations” is a structural hypothesis, not measured performance proof. A temporary table/package result is a dataflow materialization, not a transaction snapshot unless isolation/locking/version semantics are separately proven.

### 8. Release gate is mandatory

Before describing implementation as ready/proven, run:

```text
TOOLS/release_gate.py --plan <review-plan.json> --ledger <validation-ledger.json>
```

Possible outcomes:

```text
BLOCKED                — do not deliver as ready
READY_FOR_RUNTIME_TEST — static/semantic proof is sufficient for user/environment test, but runtime is pending
PROVEN                 — all required evidence, including runtime where required, is complete
ANALYSIS_COMPLETE      — analysis-only task is fully covered
```

Never convert `BLOCKED` into “готово” in prose. Never convert `READY_FOR_RUNTIME_TEST` into “проверено/принято”.

### 8.5. Deliver the result through the stable user contract

Read `WORKFLOW/RESULT_DELIVERY_CONTRACT.json` as the canonical machine-readable result-presentation contract and `KNOWLEDGE/RESULT_DELIVERY.md` for human guidance. This layer controls **how the validated result is presented**, not whether it is valid; it must not upgrade the canonical requirements/release/evidence outcome.

For non-trivial analysis/review, present material findings in the stable shape `Где → Как сейчас → Проблема → Рекомендуется → Обоснование → Доказательство / граница`. Group repeated symptoms under one root finding when owner/cause/remediation are the same. When exact source supports a useful concrete replacement, add old/recommended code; do not invent replacement code for an unresolved dependency.

For implementation work, select the primary delivery mode before constructing final implementation artifacts, then summarize what changed, changed objects/files, key design decisions, delivery and material verification. Delivery-mode selection uses the explicit request, project modification policy, target/source topology, proven mutation/import capability and validation boundary. The ability to generate XML does not by itself justify `IMPORTABLE_ARTIFACT`; for an accepted 1C human Configurator/extension route with no authorized direct mutation and no exact validated import route, default to `MANUAL_TRANSFER_INSTRUCTION`. Keep the selected result mode and ChangePackage delivery closure intact; the user summary must not replace a required manual-transfer specification, patch, artifact or compare set.

If a blocking requirement/evidence dependency remains, use the blocked/partial result profile and name the smallest concrete missing input. Do not dump the complete validation ledger, rule inventory or routing table into the final answer by default. Omit empty sections and omit “Что нужно от пользователя” when no user action remains.


## Critical requirements rules

Requirements-first remains mandatory for non-trivial work. Preserve the chain `need/problem → observable target outcome → behavior/rules → acceptance`; an implementation action is not automatically the requirement. For stateful/data/integration work, the requirements contract must still cover the applicable lifecycle, source-of-truth, retry/idempotency/failure and final-state semantics.

Load detailed requirements guidance from existing owners when that phase is active:

- `KNOWLEDGE/REQUIREMENTS_DISCOVERY.md` for functional-contract discovery and precise question minimization;
- `KNOWLEDGE/REQUIREMENTS_ARTIFACT_INTEGRITY.md` for LT/TZ/specification artifacts and claim provenance;
- `KNOWLEDGE/EVIDENCE_ACQUISITION.md` plus `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json` when a blocking source/evidence gap must be acquired.

Ask only unresolved questions that can materially change behavior, ownership, scope or acceptance. Missing blocking evidence stays unresolved/`EVIDENCE_REQUIRED`; never replace it with inference.


## Critical 1C rules

Exact target/user-authorized source remains stronger than remembered APIs, discovery catalogs or derived indexes. Normal 1C detail is loaded from the **routed review-plan profiles and their supporting artifacts**, not from an always-loaded prose mirror.

Cross-cutting routing invariants:

- platform/infrastructure work must dispose `BSP_REUSE` and prove the actual target exported contract before use;
- qualified calls/API boundaries route `CALL_CONTRACT`; query/list work routes `QUERY` / `DYNAMIC_LIST`; managed-form/client-server behavior routes the applicable form/data profiles;
- exported XML routes `ONEC_XML_STRUCTURE` plus the applicable specialized structural profile; use `TOOLS/analyze_onec_xml.py` on final bytes rather than inferring serialized contracts;
- write/lifecycle/custom-field changes route the applicable transaction, overwrite, hook/orchestration and ownership profiles; a locally correct assignment is not proof of final persisted behavior;
- every new/materially changed routine must be connected to the intended runtime scenario. Use `TOOLS/analyze_onec_reachability.py` when BSL routines are added/rewired; `Экспорт` means callable, not called;
- deduplication/grouping/search/mutation flows must preserve proven business identity and validate derived keys before mutation.

Do not guess signatures, query topology, form data shape, lifecycle order, standard-pipeline ownership or runtime reachability from names or memory. When a routed profile requires more detail, load that profile and its canonical knowledge/support files from the compact review plan.


## Cleverence is first-class, not an appendix to 1C

Route Cleverence by mechanism, not by the `.mslx` suffix alone:

```text
Configuration/Operations/**                          → CLEVERENCE_MSLX
Configuration/Metadata/** + Configuration/DocumentTypes/** → CLEVERENCE_CONFIGURATION
1C ↔ Cleverence mapping/BP/Core                     → CLEVERENCE_INTEGRATION
```

Load the routed Cleverence profile(s) and `KNOWLEDGE/CLEVERENCE_RUNTIME_INTEGRATION.md` only when applicable. `CLEVERENCE_MSLX` owns execution-graph/state/writer detail; `CLEVERENCE_CONFIGURATION` owns field/document/parser contracts; `CLEVERENCE_INTEGRATION` owns producer/consumer closure across both systems.

Use `TOOLS/analyze_cleverence_configuration.py` for changed Metadata/DocumentTypes and `TOOLS/analyze_cleverence_mslx.py` for Operation/Action graph evidence when routed. Exact names/types/paths and actual target runtime behavior remain evidence contracts; do not infer parser precedence, writer identity or graph behavior from XML order, transliteration or a retained analog.

For cross-system tasks, changing only one file/system never makes the contract one-sided: prove the relevant producer, exact Mobile declaration/mapping, storage/writers and consumer closure.


## Delivery discipline

Before final presentation, **load and obey** `WORKFLOW/RESULT_DELIVERY_CONTRACT.json` as the canonical machine-readable result contract and `KNOWLEDGE/RESULT_DELIVERY.md` for human guidance. For every non-trivial implementation, `Особенности реализации.docx` is mandatory and separate. When `MANUAL_TRANSFER_INSTRUCTION` is primary, `Инструкция по внедрению.docx` is also mandatory and separate; chat/Markdown/code snippets are not substitutes. Other user-facing documentation follows its owner trigger. Load `KNOWLEDGE/USER_ARTIFACT_DOCX.md` and generate each required document with `TOOLS/render_user_artifact_docx.py`; do not silently merge documents unless the user explicitly requested a combined/alternate output. Exact artifact structure remains owned by the Result Delivery contract and artifact-specific templates, not duplicated in this Skill body.

Presentation never upgrades canonical requirements/evidence/release status. Keep blocked/runtime-pending states explicit, never modify the user's baseline in place, validate the exact final bytes/archive, transfer only changed files plus contract-coupled dependencies, and preserve UTF-8/Cyrillic filenames. Runtime not executed here remains `READY_FOR_RUNTIME_TEST`/`RUNTIME_PENDING`, not proven.


## Learning protocol

Every substantive task ends with an explicit knowledge-extraction disposition: `PROMOTED`, `PROJECT_ONLY`, `NO_REUSABLE_KNOWLEDGE` or `EVIDENCE_PENDING`. At that phase, load `KNOWLEDGE/LEARNING_PROTOCOL.md`.

Promotion requires falsifiable source/runtime/authoritative evidence plus a search proving that no existing Registry owner already covers the lesson. Reusable knowledge belongs in the existing Rule Registry/profile/knowledge/regression owners; project/customer identifiers and one-off business decisions remain project-only. Do not add a second knowledge-routing mechanism.


## Progressive loading

Normal task startup should read only:

```text
SKILL.md
compact requirements/review/validation summary or validation work queue
routed profile(s)
exact needed reference/index/source
```

The compact review-plan projection is the normal model routing contract: use its active profiles, active deliveries, deterministic tools and complete active support/reference path set, then open detail only for the current routed phase/check. Do not invent an additional `required_now/on_demand` state model.

Treat deterministic helpers as **black boxes during normal task execution**: consume the command contract and compact structured result. Read helper implementation source only when debugging/modifying that helper or when an explicit architecture review requires its internals.

`RULES/rule_registry.json` stays out of normal LLM context; builders/gates read it directly. Full plan/contract/ledger/proof JSON stays durable off-context and `--full-json` is diagnostic only. For 1C XML work load `KNOWLEDGE/EXTERNAL_1C_STRUCTURAL_REFERENCE.md` only when a structural profile is routed. Do not eagerly load `ARCHIVE`, all BSP modules, all Cleverence operations or the full standards corpus.

