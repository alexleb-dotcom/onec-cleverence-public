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

### 5. Implement minimal coherent change

**Minimize necessary change surface, not raw line count.** Among implementations that fully satisfy the proven requirements, correctness, standards, maintainability, runtime safety and delivery contract, prefer the one that changes the fewest necessary objects/files/routines/material hunks and introduces the least new executable code or new abstractions relative to the exact baseline.

Every changed artifact, routine and material hunk must map to an agreed requirement, confirmed defect or proven technical/delivery necessity. Keep opportunistic refactoring, unrelated cleanup, cosmetic renames/moves and speculative future-proofing out of the task change. Reuse or extend an existing owner/extension point when it can satisfy the same contract; a broader redesign or parallel mechanism requires concrete evidence that the smaller coherent alternative is insufficient.

This is **not code golf**. Do not reduce LOC by collapsing responsibilities, hiding invariants, weakening names, duplicating dense expressions or bypassing standard/supported mechanisms. Required caller updates, delivery closure, readability, responsibility cohesion, correctness, performance and runtime safety take precedence over a smaller numeric diff.

Preserve source style, encoding and project conventions evidenced by the actual code. Do not invent author/date tags, prefixes, regions or comment formats.

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

For implementation work, summarize what changed, changed objects/files, key design decisions, delivery and material verification. Keep the exact selected result mode and ChangePackage delivery closure intact; the user summary must not replace a required manual-transfer specification, patch, artifact or compare set.

If a blocking requirement/evidence dependency remains, use the blocked/partial result profile and name the smallest concrete missing input. Do not dump the complete validation ledger, rule inventory or routing table into the final answer by default. Omit empty sections and omit “Что нужно от пользователя” when no user action remains.

## Critical requirements rules

### Traceability and acceptance

A technical action (`добавить`, `автоматизировать`, `реализовать`) is not automatically the need. Preserve the chain `need/problem → observable target outcome → behavior/rules → acceptance`. Acceptance must prove correctness, not only that an action completed.

### Process/data lifecycle

For stateful behavior prove initiator/roles, trigger/preconditions, relevant states/transitions, repeat/re-entry, material concurrency and alternative/error paths. For significant data prove source, semantic meaning, source of truth, identity vs representation, transformation/storage/transmission/use and behavior on repeat/source change.

### Integration contract

If a method/API/message is fixed, trace `trigger → input source/semantics → mapping/call → output semantics → validation/transform → persisted/consumed use → retry/idempotency/partial failure → final state in every system → acceptance`. If only target behavior is agreed, do not force an API prematurely.

### Question minimization

Do not ask broad “clarify roles/process/data” questions when the gap can be named precisely. Read available source/context first. Ask only unresolved questions whose answers can materially change behavior, ownership, scope or acceptance.

## Critical 1C rules

### BSP

Suitable public BSP behavior is preferred and normally mandatory for platform-adjacent/infrastructure tasks. Record evidence of reuse, non-applicability or justified exception. Search by intent/domain, use the public BSP locator only to find candidate modules, and prove the actual exported contract from exact target/user-authorized source before calling it. If that source is missing, request the smallest sufficient module/metadata/call-site closure and keep the claim `EVIDENCE_REQUIRED`; do not fall back to remembered or prebuilt signatures. Exact source/local reproducible evidence beats every derived reference index.

### Cross-module calls

Every changed qualified call that may be a module/API boundary must be classified. For real boundaries, resolve the actual exported declaration and verify required/optional arguments, semantic order, context, return/mutation behavior and deployment caller closure.

### Queries and DynamicList

Prefer complete valid query variants and native/typical extension patterns. Do not invent a general query parser with positional `СтрНайти/Сред/Лев` surgery. Stored/default/intermediate query text expected to be normal 1C query language must remain constructor/runtime-valid.

For DynamicList, inspect the actual effective query/СКД, use BSP setters when applicable, preserve result contracts across variants and keep expensive operational state out of repeated online calculation unless profiling/evidence justifies it.

For every empty/default/sentinel query parameter, prove its meaning, caller authorization and cardinality effect. A sentinel that disables a point filter requires an explicit bulk-mode contract or separate branch/API. For reference-dot dereference, review implicit joins, cardinality/index cost and whether an already joined source owns the value.

### Managed-form data and client/server cost

Do not infer performance cost from dot count alone. In an existing form context, direct `Форма.Объект.X` / `Объект.X` access reads the form data attribute; it is not by itself a DB query or a new client/server transition. A longer path such as `Форма.Объект.Договор.Организация` is different: prove the runtime type of `Договор`; if it is a reference, account for DB-read/N+1 risk, especially inside loops. Treat unresolved nested paths as `REVIEW`, not an invented defect.

For `ДанныеФормыКоллекция`, distinguish client from server execution. Material client traversal/search can trigger implicit server reads; perform it on the server when applicable. Judge the complete user action by explicit and implicit server transitions and traffic. Prefer a justified context server call when platform delta transfer for form collections is cheaper than copying whole form data through parameters.

### Structural XML: metadata, forms, CFE, roles/RLS and XDTO

Treat exported 1C XML as source code with structural contracts, not as prose for the model to infer. When relevant, route `ONEC_XML_STRUCTURE` plus the specialized `FORM_XML_STRUCTURE`, `METADATA_XML_STRUCTURE`, `CFE_EXTENSION_STRUCTURE`, `ROLE_RIGHTS_STRUCTURE` or `XDTO_STRUCTURE` profile and run `TOOLS/analyze_onec_xml.py` on final bytes with enough companion context.

For managed forms, respect separate identity scopes for form elements, attributes, commands and per-attribute columns; an extension `BaseForm` is a separate serialized baseline subtree. A changed `DataPath`/`ПутьКДанным` is also a runtime data-shape contract: resolve its root from the actual form context and prove every changed nested member against the producer/composition of that value. Do not infer `A.B` merely because a metadata object named `B` exists elsewhere. For `cfg:ConstantsSet` / `КонстантыНабор`, the target constant must be proven to belong to that concrete set; otherwise use an evidenced adaptation and prove both load and persistence paths. For CFE, prove adopted/own ownership and base UUID/Form/interceptor bindings from actual extension + base source. For roles, bind `Rights.xml` to role metadata, inspect RLS structurally and interpret absent rights using the actual format/default semantics; in 2.19+ absence of a `<right>` node is not by itself proof of denial because default-valued rights may be omitted. For XDTO, prove the namespace/import/type graph and package registration before serializer/parser code.

`KNOWLEDGE/EXTERNAL_1C_STRUCTURAL_REFERENCE.md` catalogs a curated external MIT-licensed structural corpus (`cc-1c-skills`). It is supporting evidence, not an official standard. Never promote a corpus heuristic to a blocking rule until it survives validation against real 1C/typical/project artifacts.

### Domain validation and hooks

Before adding an `Если` for values/ranges/states, prove what the type/metadata/platform already guarantees and what boundaries can bypass that guarantee. Multi-field/piecewise business rules require an acceptance/rejection case matrix before code.

`&Перед`, `&После`, `&Вместо`, event/command/subscription/integration handlers are primarily orchestration/adaptation boundaries. Small event-specific guards may stay local; reusable validation/calculation/query/persistence belongs to a named owner API unless a proven project/typical pattern says otherwise.

### Implementation reachability

Correct code that is not connected to the intended runtime scenario is dead functionality. For every new or materially changed routine, classify it as an entrypoint/external callback/helper and prove the path `entrypoint → caller(s) → routine` from exact source. `Экспорт` means callable, not called. New private routines with no resolved caller and new-only orphan subgraphs are blocking. Dynamic/platform/vendor dispatch requires an explicit callback/event contract and runtime evidence rather than an assumed PASS.

Run `TOOLS/analyze_onec_reachability.py` with candidate + baseline when BSL routines are added/rewired. If the intended feature depends on a specific route, prove the expected entrypoint/target path. Delivery must include every caller/hook needed to connect the new code.

### Artifact scope discovery

Do not infer artifact scope from a filename, archive name or top-level folder. Before narrowing relevance, inventory the actual supplied corpus: file count/types, roots, 1C/Cleverence/XML/BSL mix, metadata objects and unexpected companion artifacts. A file named like one subsystem/package may still contain full documents, forms, modules or integration context. Scope filtering happens **after** factual inventory.

### Lifecycle and standard-pipeline ownership

Before accepting a parallel document/calculation/row-building/write chain, trace the actual standard pipeline and map each source business dimension through its intermediate and target representation. A parallel source of truth is blocked until required semantic loss and inability to extend the standard owner are proven.

For each meaningful custom field assignment, run field-aware temporal review: trace later writers of the **same field on reachable paths** through selection, filling, recalculation, handlers and before-write/write hooks. Same-module lifecycle words are not evidence by themselves. Resolve dynamic/external callbacks as evidence gaps. Validate the final persisted/consumed value after the complete scenario; a locally correct assignment is not proof.

### Business identity

For deduplication/grouping/search/merge/split flows, state the smallest stable identity before coding. Packaging, units, coefficients, barcodes, display values and quantity normalization are representation unless domain evidence proves they change business sameness.

When a derived key controls creation of a row, index entry, register record, object or fact distribution, use `derive → validate type/domain/completeness/required uniqueness → mutate`. Do not leave partial state by validating after `Добавить()`/`Вставить()`/`Записать()`.

## Cleverence is first-class, not an appendix to 1C

Route Cleverence by mechanism, not by the `.mslx` suffix alone:

```text
Configuration/Operations/**
→ CLEVERENCE_MSLX
→ execution graph / state / writers

Configuration/Metadata/** + Configuration/DocumentTypes/**
→ CLEVERENCE_CONFIGURATION
→ parser / field / document-schema contracts

1C ↔ Cleverence mapping/BP/Core
→ CLEVERENCE_INTEGRATION
→ end-to-end producer/consumer contract
```

For MSLX/operations review execution as a graph, not just XML:

- physical Action order;
- serialized `indent` and scope boundaries;
- explicit directions and scoped `up:` targets;
- implicit fall-through/former-END behavior;
- ordered `ButtonDirections`;
- error/abort/Escape/back/cancel paths;
- scan-session state (`SelectedProduct`, `ScannedBarcode`, `BarcodeData`) and repeat entry;
- semantic stage before quantity control: new picking vs mutation/reallocation of existing fact;
- all applicable writer paths for changed fact fields, not one convenient writer;
- live `CurrentItem` rebind by technical identity before mutation, with verify/rollback when state moves between rows;
- active Business Process;
- standard writer/router/Core integration hooks.

Treat `DeclaredItems` as plan and `CurrentItems` as fact unless actual configuration proves otherwise. Preserve `BindedLine`, one-plan-many-fact identity, quantity conservation, marks/SN/SSCC/series/weight/service fields, retry and re-entry.

For configuration metadata, use `TOOLS/analyze_cleverence_configuration.py`. Exact declaration names/code points and native types are contracts. Similar/transliterated/confusable identifiers are not equivalent. Barcode-template overlap is structural evidence, not automatically a defect: if a changed broad/specific pair can compete, prove actual parser selection on representative full and prefix-only input. Do not infer precedence from XML order or apparent specificity.

For 1C ↔ Cleverence tasks, changing only one file/system does not make the task one-sided. Producer, exact Mobile field declaration, mapping, storage/grouping/search, every applicable writer and consumer form one cross-system contract.

## Delivery discipline

- Every non-trivial implementation result must include a final `Особенности реализации` section with two mandatory one-time header fields above the table: `Проект: <...>` and `Задача: <...>`. They must not be repeated as table columns.
- The table itself has the **exact immutable columns and order**: `Контейнер | Объект конфигурации | Процедура / функция | Статус | Описание изменения`. These five labels, their order and composition are a delivery contract: never rename, remove, merge, split, reorder or replace them; do not add extra columns to the base table.
- Create one row per material implementation change/decision at the most precise practical object/member level. The same configuration object may legitimately appear in multiple rows for different procedures/functions/members. `Объект конфигурации` remains one base field (do not split it into type/name columns); `Процедура / функция` may name an exact routine, member/event, or multiple exact members when one status/description applies.
- `Статус` records the factual row status using grammatically appropriate wording such as `Создана`, `Добавлена`, `Изменена`, `Удалена`, `Удалены`, `Оставлена без изменения`, `Удалена привязка`. `Описание изменения` states factually what changed or was deliberately retained and how the resulting behavior/mechanism works.
- Take header fields `Проект`/`Задача` only from bound project context/requirements and table field `Контейнер` only from the exact source layout (for example `Расширение <имя>` or `Основная конфигурация <имя>`). Never collapse same-named objects from the main configuration and extensions or from different extensions.
- Additional rationale, evidence, risks, performance notes, verification results or links may be added **outside** the mandatory project/task header and five-column table, but supplementary information must never alter either part of the base format. Cleverence and other non-1C artifacts may be documented additionally without mutating the mandatory 1C format.
- When `COLLECTION_ALGORITHM` is routed, add the canonical exact-candidate `Performance Review` projection outside that base format. Show current/proposed passes, nested searches, loop I/O, asymptotic time, memory/copies, topology, reviewed scale, semantics preservation and runtime status. `STRUCTURAL_ONLY` must state `Измеренное ускорение не доказано.`; a measured claim requires verifier-confirmed `RUNTIME_ADAPTER` evidence. Missing/stale/generic/active-N/A review remains blocked and the projection must never change implementation readiness or final release outcome.
- Never modify the user's baseline in place.
- Validate exact final bytes/archive, not an earlier worktree.
- Transfer only changed files plus contract-coupled dependencies actually required by the deployed baseline.
- Preserve UTF-8/Cyrillic filenames; ZIP mojibake is blocking.
- New skill/output filenames must not use version suffixes like `v2`, `_fix`, `_new`, `final2`; revision belongs in metadata/manifests.
- If runtime cannot be executed here, say so and use `READY_FOR_RUNTIME_TEST`/`RUNTIME_PENDING`.

## Learning protocol

A substantive task always ends with a knowledge-extraction disposition: `PROMOTED`, `PROJECT_ONLY`, `NO_REUSABLE_KNOWLEDGE` or `EVIDENCE_PENDING`. Read `KNOWLEDGE/LEARNING_PROTOCOL.md`.

A confirmed reusable failure is not fully learned until all four questions are answered:

1. **Rule:** what universal contract was violated?
2. **Activation:** how will the router know to apply it next time?
3. **Enforcement:** how is it checked/demonstrated?
4. **Release:** how does missing evidence prevent unsupported delivery?

A novel model hypothesis is not a confirmed reusable failure. It becomes promotion material only after falsifiable source/runtime/authoritative evidence and a search proving that no existing registry owner already covers it.

Add the generalized lesson to `RULES/rule_registry.json`, relevant profile/knowledge and deterministic fixture when possible. Then regenerate views and run the complete self-validation/regression suite.

Do not learn project/customer names, prefixes, authors or one-off business decisions into universal rules. Historical material remains available under `ARCHIVE` on demand; reducing bootstrap context never means deleting accumulated knowledge.

## Progressive loading

Normal task startup should read only:

```text
SKILL.md
compact requirements/review/validation summary or validation work queue
routed profile(s)
exact needed reference/index/source
```

`RULES/rule_registry.json` stays out of normal LLM context. Builders and gates read it directly. Full plan/contract/ledger JSON remains durable machine evidence on disk; use `--full-json` only when an explicit diagnostic requires the entire artifact.

For 1C XML work, load `KNOWLEDGE/EXTERNAL_1C_STRUCTURAL_REFERENCE.md` only when a structural profile is routed; do not load the external families wholesale.

Do not eagerly load `ARCHIVE`, all BSP modules, all Cleverence operations or the full standards corpus.
