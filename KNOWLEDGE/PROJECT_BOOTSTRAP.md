# Project bootstrap and discovery contract

## Purpose

A new chat or newly connected repository is not yet a ready development context. Before implementation, build a durable **project context** once, then build task requirements on top of it.

The bootstrap must reduce repeated user corrections. It should discover what can be proven from the repository/artifacts first, request only unresolved material information, and preserve project-specific conventions separately from universal rules.

Durable context is versioned evidence, not eternal truth. Read `KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md` for mutable project decisions, temporary approximations, supersession and dependency-driven revalidation. Read `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md` before labeling any 1C source «типовой»: typicality is a provenance claim, not a synonym for familiar, supported, partner-supplied or inherited.

## Separation of concerns

```text
PROJECT BOOTSTRAP
→ durable project identity, source topology, protected surfaces, conventions, delivery/runtime capabilities

PROJECT DECISION LIFECYCLE
→ current vs temporary vs stale/superseded mutable project decisions

TASK REQUIREMENTS
→ need, target outcome, business behavior, acceptance and task-specific scope

TECHNICAL REVIEW PLAN
→ surface/risk, routed rules, analyzers and evidence obligations
```

Do not rebuild the whole project context for every task. Refresh only facts/decisions invalidated by a new baseline, repository revision, deployment version, explicit user/project-policy change or evidence dependency drift.

## Mandatory startup sequence

For a new project / empty chat / newly connected repository:

```text
1. INVENTORY AVAILABLE INPUT
2. DISCOVER PROJECT FACTS FROM SOURCE
3. CLASSIFY WHAT IS KNOWN / UNKNOWN
4. REQUEST ONLY MATERIAL MISSING INFORMATION
5. UPDATE PROJECT CONTEXT + DECISION LIFECYCLE
6. BUILD TASK REQUIREMENTS
7. REQUEST TASK-SPECIFIC MISSING ARTIFACTS
8. DESIGN / IMPLEMENT
9. VALIDATE / RUNTIME
10. EXTRACT NEW PROJECT OR UNIVERSAL KNOWLEDGE
```

The assistant must not jump directly from repository access to implementation merely because source files are available.

For a **later substantive task in an existing project**, first inspect only the project-context decision keys/evidence dependencies the task actually relies on. A newer explicit decision or stronger/current source that conflicts with an old decision must supersede/invalidate/revalidate it before the old statement is reused. Do not silently carry historical project facts forward and do not re-bootstrap unrelated project context.

For a **genuinely new task after prior delivery in the same project**, reuse only current valid durable project decisions, then build a **new task requirements contract**. Do not inherit previous-task assumptions, proposed solutions or task-local evidence as new-task requirements merely because they remain in chat history. Revalidate only relevant stale/conflicting decision keys; unrelated project facts must not become bootstrap blockers.

When the chat contains mixed or unrelated project history, bind the exact current target/project identity before reusing any prior context or source. Same-named objects or artifacts from another project/baseline are not reusable evidence without that binding.

## 1. Inventory before questions

First inspect what is already available:

- repository root/tree and current revision;
- actual supplied archives/directories and nested containers;
- project README / technical notes / manifests / CI files;
- 1C configuration/extension source;
- Cleverence configuration/export/runtime artifacts;
- project-specific standards/instructions;
- existing tests and runtime tooling;
- examples of current custom code and metadata.

Do not ask the user for information that can be derived safely from these sources.

## 2. Discover project contracts

Bootstrap should attempt to resolve at least the following durable contracts.

### Project identity

- project/system name;
- repository + branch/commit or exact artifact baseline;
- 1C configuration/platform versions when evidenced;
- exact official 1C release baseline used for typical-vs-customization comparison when that distinction matters;
- source provenance classification: `TYPICAL_1C`, `TYPICAL_WITH_CUSTOMIZATIONS`, `CUSTOMIZATION`, or `NOT_PROVEN_AS_TYPICAL`;
- Cleverence product/configuration/platform versions when evidenced;
- deployed vs reference vs historical source roles.

### Participant and artifact identity

A project may contain one or more **Participants**. Bind exact source/evidence to the tuple `Project → Participant → Artifact` whenever more than one participant or artifact can exist; same-named metadata/code in another participant or artifact is not interchangeable evidence.

For ordinary unpacked 1C, treat artifact directories as direct source roots:

- `Target/Main` — Main artifact root;
- `Target/Extensions/<extension-id>` — one Extension artifact root;
- other artifact families keep their evidenced project-specific roots.

Do not add redundant `Target/Main/Main` or `Target/Extensions/<extension-id>/<extension-id>` wrappers. Project-specific physical prefixes remain Project Context, not universal Skill semantics. Preserve participant/artifact provenance through evidence, Implementation Intent/change scope and delivery binding.

### Mutable project decisions

Material project facts/policies that may change over time must have a stable `decision_key` and lifecycle status:

```text
ACTIVE | TEMPORARY | REVALIDATION_REQUIRED | SUPERSEDED | INVALIDATED
```

Record evidence dependencies and supersession links. A temporary technical proxy (document type, BP/operation ID/name, fallback constant, hard-coded version, provisional mapping) must remain explicitly `TEMPORARY` with a replacement criterion and revalidation trigger. Technical route identity is not automatically the business applicability rule.

### Modification policy

- allowed objects/files/systems;
- protected/vendor/third-party surfaces;
- whether existing customer/third-party code may be changed;
- minimal-diff expectation;
- whether refactoring outside task scope is forbidden;
- whether originals must remain untouched;
- extension/typical-1C-configuration/customization modification policy;
- universal `FORM_CHANGE_MODE = PROGRAMMATIC_ONLY`: form structure/properties may be changed only through reproducible programmatic/static artifact mutation; interactive Designer/Configurator editing is not a selectable project preference;
- exact form mutation route/evidence when a task changes a form; if no authorized programmatic/static route can be proven, keep the task BLOCKED/EVIDENCE_REQUIRED rather than falling back to interactive editing.
- existing Form.xml/form metadata may still be read, inventoried, diffed and structurally/runtime validated; this evidence path does not authorize interactive mutation.

### Attribution and comment contract

Resolve these independently; do not collapse them into one `comment convention` field:

```text
METADATA_ATTRIBUTION
AUTHOR_MARKER
TECHNICAL_COMMENT
PUBLIC_INTERFACE_COMMENT
EXISTING_COMMENT_POLICY
```

For each, record exact syntax and source evidence when applicable.

Before the first **final changed-code output** in a new project, `AUTHOR_MARKER`, `TECHNICAL_COMMENT` and `EXISTING_COMMENT_POLICY` are material project contracts. If current target source/PROJECT_CONTEXT does not prove them, explicitly ask the user; do not silently choose a default style. `PUBLIC_INTERFACE_COMMENT` becomes material when the task creates or changes a public/exported procedure/function. `METADATA_ATTRIBUTION` is separate and becomes material when metadata objects/attributes require a `Comment`/`Комментарий` convention.

One concise question may gather several answers, but store the contracts independently. A clear answer such as `специальных требований к техническим комментариям нет` is valid evidence; silence is not. Unaffected analysis may continue while these code-output contracts remain open.

Examples of separate questions:

- what goes into metadata `Comment` / `Комментарий` for a newly created object;
- how a changed block in standard/customer/vendor source is marked;
- whether dates/task ids/company/user markers are required;
- whether existing comments/markers may be rewritten;
- whether new procedures/functions require public interface comments;
- when technical `why/invariant/constraint` comments are expected.

Never infer an author/company/date/task-marker format from a different project or from one isolated historical example.

### Delivery contract

- expected 1C delivery form;
- expected Cleverence delivery form;
- exact compare/full/patch semantics;
- target artifact layout;
- forbidden environment/version mutations;
- manifest/hash requirements;
- which runtime files must never leak into a configuration delivery.

### Runtime/evidence capabilities

- 1C runtime availability;
- Configurator availability;
- Cleverence Designer/emulator/device availability;
- logs/browser/runtime automation availability;
- which runtime scenarios the user can execute locally.

Persist ProjectSnapshot **capabilities and durable contour facts** here (for example whether Designer/source export is available and which configuration/platform identity is current when evidenced). Keep task-specific request IDs, CollectionPlans, package hashes, returned module contents and delta-request history in task evidence/ledger/orchestration state rather than turning them into durable project policy.

## 3. Known / inferred / open states

Every bootstrap field has one of:

```text
KNOWN
DERIVED_WITH_EVIDENCE
OPEN
NOT_APPLICABLE
```

These bootstrap-field states are different from the per-decision lifecycle statuses in `PROJECT_CONTEXT_LIFECYCLE.md`.

Do not use `ASSUMED` for project policy that can change what files are modified, how code is attributed, what may be delivered, or what is considered an acceptable change.

A missing value is not automatically blocking. It is blocking only when it can materially change the next action. For changed-code output, unresolved `AUTHOR_MARKER`, `TECHNICAL_COMMENT` and `EXISTING_COMMENT_POLICY` are blocking because they directly change the delivered source. `PUBLIC_INTERFACE_COMMENT` is conditional on a public-interface change.

## 4. Question minimization

Questions are generated only after source discovery.

A good bootstrap request must state:

- exact missing fact or artifact;
- why it matters now;
- what decision it controls;
- whether work can continue without it;
- the smallest acceptable answer/artifact.

Avoid generic forms such as:

```text
"Расскажите про проект"
"Какие у вас стандарты?"
"Пришлите всю конфигурацию"
```

Prefer:

```text
"В репозитории я нашёл маркеры `// <...>` в изменённых типовых модулях, но не могу доказать, что это обязательный формат для новых изменений. Нужен либо проектный стандарт, либо один подтверждённый актуальный пример. До этого могу продолжить анализ, но не формировать финальный код с attribution markers."
```

For unresolved code comments prefer one compact grouped question rather than a questionnaire, for example:

```text
"Перед тем как выдавать финальный изменённый код, нужно зафиксировать проектную политику комментариев: какой формат маркера автора/компании/даты использовать, нужны ли отдельные технические комментарии `почему/ограничение`, и можно ли менять существующие комментарии/исторические маркеры? Если специальных требований нет — достаточно так и сказать."
```

The grouped wording is only a UX optimization; `AUTHOR_MARKER`, `TECHNICAL_COMMENT` and `EXISTING_COMMENT_POLICY` remain separate project-context fields.

## 5. Missing artifacts are iterative, not only startup-time

Project bootstrap cannot know every dependency needed by a future task.

During task analysis use the normal evidence acquisition loop:

```text
analyze available closure
→ identify exact unresolved claim
→ request smallest missing artifact
→ continue unaffected analysis
→ incorporate provided artifact
→ repeat until design/release gate is sufficiently resolved
```

The workflow is therefore deliberately iterative:

```text
REQUEST → ANALYZE → REQUEST MISSING → ANALYZE → IMPLEMENT → VALIDATE
```

not:

```text
REQUEST EVERYTHING → IMPLEMENT
```

## 6. Existing code and unrelated changes

At bootstrap record the ownership/protection model for existing custom code.

Default evidence-first behavior when no broader permission is proven:

- do not rewrite unrelated existing project/customer/third-party logic;
- do not normalize formatting/comments across untouched code;
- for changed/new BSL, apply the universal source-layout floor: official 1C std444 line-length/wrapping rules, no more than one consecutive blank line, and no avoidable vertical decomposition of a simple readable expression/call/condition; project style may tighten but not weaken this floor;
- preserve the existing source encoding and newline convention outside the necessary changed hunk unless an evidenced delivery contract requires otherwise;
- do not refactor merely because a better implementation is visible;
- if an existing defect blocks the requested change, identify it separately and explain the minimum required intervention;
- preserve attribution/history markers unless the project contract explicitly authorizes changing them.

This is not a universal prohibition on refactoring. It is a fail-safe until the project modification policy is known.

## 7. Repository is evidence, not complete project truth

Connecting a repository does not prove that it contains:

- the deployed baseline;
- all 1C metadata;
- active event subscriptions;
- exact BSP/version dependencies;
- current Cleverence Business Process;
- production runtime settings;
- customer acceptance rules;
- project comment/attribution policy.

Bootstrap must classify repository completeness explicitly. Missing project truth becomes a targeted request, not an implicit assumption.

## 8. Handoff into task work

Before non-trivial implementation, the task should have:

```text
PROJECT_CONTEXT
+ CURRENT PROJECT DECISIONS (no unresolved stale conflict for used keys)
+ TASK REQUIREMENTS CONTRACT
+ ACTUAL CANDIDATE/SOURCE CLOSURE
+ EXPLICIT OPEN EVIDENCE REQUESTS
```

For changed-code output, `PROJECT_CONTEXT` must also contain resolved `AUTHOR_MARKER`, `TECHNICAL_COMMENT` and `EXISTING_COMMENT_POLICY`; add `PUBLIC_INTERFACE_COMMENT` when a public/exported interface changes and `METADATA_ATTRIBUTION` when metadata comments are in scope.

`PROJECT_CONTEXT` answers "how this project is developed and delivered".

The decision lifecycle answers "which durable mutable project statements are current enough to rely on".

The requirements contract answers "what this task must accomplish".

The review plan answers "which technical contracts must be proved".

## 9. Learning from user corrections

If the user has to correct the same class of project behavior more than once, do not merely remember the concrete value. Determine whether the bootstrap failed to discover a **category of project contract** or failed to retire stale context.

Examples:

- repeated correction of metadata `Comment` → strengthen `METADATA_ATTRIBUTION` acquisition;
- repeated correction that new chats forgot to ask how changed code must be commented/marked → strengthen `AUTHOR_MARKER` + `TECHNICAL_COMMENT` + `EXISTING_COMMENT_POLICY` acquisition and regression coverage;
- repeated "не меняй существующий код" → strengthen modification/protected-surface acquisition;
- repeated missing-file requests late in coding → strengthen dependency-closure discovery;
- wrong Cleverence package shape → strengthen artifact classification/delivery-shape discovery;
- a former BP/document-type proxy is later rejected → supersede the old project decision instead of keeping both statements active;
- a temporary workaround survives several tasks → keep it `TEMPORARY` until its replacement criterion is satisfied, not silently `ACTIVE`.

Project-specific values remain in project context; only the discovery/lifecycle category and reusable validation workflow may be promoted universally.
