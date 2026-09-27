# READ THIS FIRST — 1C + Cleverence Skill

Repository role: `UNIVERSAL_SKILL_REPOSITORY`.

## Normative 1C terminology

Read `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md` during every normal bootstrap. Within this skill, «типовой/типовая/типовое» is a reserved provenance term: it means firm-1C-authored material that is present in an official released 1C program/configuration. Everything outside that boundary is «доработка»; unknown origin is not allowed to inherit typical status and is treated as customization for analysis until proven otherwise.

This repository contains the reusable 1C + Cleverence review/development skill. It is **not** the user's target 1C/Cleverence project, deployed baseline, or project-specific `PROJECT_CONTEXT` unless the user explicitly says otherwise.

## Skill freshness for long-lived chats

This repository is versioned source. A chat that loaded the skill earlier must not assume its in-context copy is still current forever.

Read `KNOWLEDGE/SKILL_FRESHNESS.md` and keep the exact commit that supplied the loaded execution contract as internal `loaded_sha` skill state. This state belongs to the skill, not to the user's target project.

Before starting a **new substantive** analysis/review/implementation task in a long-lived chat, perform a lightweight tracked-ref SHA check:

```text
current_sha == loaded_sha
→ continue without rereading the repository

current_sha != loaded_sha and diff is comparable
→ inspect loaded_sha...current_sha
→ reload only changed execution/routing/profile/knowledge material that can affect the current task
→ reroute/revalidate affected proof/tool evidence
→ only then advance loaded_sha

loaded_sha unknown
→ minimal skill bootstrap

old SHA not safely comparable/reachable
→ minimal rebootstrap from the tracked ref; do not invent a partial diff
```

Do not turn freshness into “reload the whole repository every turn”. The intended optimization is `SHA check → diff → task-impact reload`. If the canonical/tracked ref cannot currently be resolved, keep the known `loaded_sha`, mark freshness unverified and do not claim that the skill is current/latest.

For a long-running task, make one additional lightweight freshness check before a final current-skill readiness/compliance claim when repository drift is plausible. If routing/rules/gates changed during the task, rerun routing and rebuild/reconcile affected downstream proof structures before reusing old dispositions.

If the user explicitly pins a historical tag/commit/ref, respect that pin instead of silently moving to newer `main`.

Freshness checking is internal execution hygiene. Do not clutter the first response with SHA/Git administration unless the update materially affects the task or the user asks.

## Project-context freshness for long-lived projects

Skill freshness and project-context freshness are separate problems. Even when `loaded_sha` is current, an old project decision can become stale after a newer explicit user decision, new target evidence, baseline/version change or expiry of a temporary workaround.

Read `KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md`. For material mutable project decisions keep a stable `decision_key` and one lifecycle state:

```text
ACTIVE | TEMPORARY | REVALIDATION_REQUIRED | SUPERSEDED | INVALIDATED
```

Before a later substantive task relies on durable project context:

```text
identify only decision keys used by this task
→ reject SUPERSEDED / INVALIDATED as current evidence
→ resolve REVALIDATION_REQUIRED before relying on it
→ if newer evidence conflicts, supersede/invalidate/revalidate the old decision
→ do not rebuild unrelated project context
```

`TEMPORARY` is not a weaker spelling of `ACTIVE`: it must retain its reason, replacement criterion and revalidation trigger. A technical proxy such as a BP/document/operation identifier must not silently become the business invariant merely because it was used in previous work.

Do not expose lifecycle bookkeeping in ordinary responses unless it materially changes/blocks the task or the user asks.

## If this repository URL is the only input in a new chat

1. Recognize this repository as the **skill itself**, not as the project to be changed.
2. Read this file, `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`, then the `New project / empty chat bootstrap` section of `README.md`, then only the relevant bootstrap/routing sections of `SKILL.md`.
3. Resolve the tracked skill repository/ref from the active Git remote/connector or explicit distribution configuration, keep its exact commit as `loaded_sha`, and follow `KNOWLEDGE/SKILL_FRESHNESS.md` for later substantive tasks. Never inherit the private maintenance repository identity into a shareable/public copy. Do not report this bookkeeping in the first response unless relevant.
4. Do **not** recursively load `ARCHIVE/**`, all `REFERENCE/**`, all profiles, all `PATTERNS/**`, or the whole knowledge corpus. They are routed/on-demand evidence or guidance and remain useful only when a specific claim/design shape requires them.
5. Do not invent project facts, author markers, modification policy, deployed baseline, delivery format, or target versions from examples/history in this repository.
6. Treat memories, summaries, decisions or facts from other chats/projects as **untrusted candidate context**, not current-project evidence. Use them only when the user explicitly asks to continue/reuse that prior work, and revalidate material claims against the current target source/context.
7. If no target project/artifact and no concrete task were supplied, report that the universal skill has been identified and request the target repository/artifact plus the task. Do not pretend this skill repository is the target baseline.
8. Do not turn a plain skill-URL cold start into repository-administration work. Unless the user asked for skill maintenance, do not audit permissions, branches, tags, releases, CI history or propose changing the skill itself.
9. If mentioning a Git ref, distinguish and verify its namespace (`branch`, `tag`, `release`, `commit`) before making an absence/existence claim. Absence of a branch does not prove absence of a same-named tag or release.
10. If a target project/artifact is supplied, inventory the available target input before narrowing scope:

```text
TOOLS/artifact_corpus.py
→ TOOLS/build_project_bootstrap.py
→ derive project facts from source
→ request only material unresolved project contracts
→ resolve/request attribution + code-comment contracts before first final code output
→ persist PROJECT_CONTEXT + decision lifecycle
→ build current-task requirements
→ build technical review plan
```

For a new target project, `AUTHOR_MARKER`, `TECHNICAL_COMMENT` and `EXISTING_COMMENT_POLICY` must not be silently defaulted. Resolve them from actual current project evidence or ask the user before returning final changed code. `PUBLIC_INTERFACE_COMMENT` is additionally required when a public/exported procedure/function is created or changed; `METADATA_ATTRIBUTION` remains a separate metadata contract. The assistant may bundle these into one concise question, but must store/interpret them independently. If the policy is already evidenced in current `PROJECT_CONTEXT`, do not ask again.

## First-response contract for URL-only cold start

When the only user input is this universal skill repository URL, the first response should be short and task-oriented. It should do only the following unless the user explicitly asks for repository maintenance:

```text
1. Confirm: this is the universal 1C + Cleverence skill repository.
2. Confirm: no target project has been identified yet.
3. Request: target project/repository/artifact + concrete task.
```

Do **not** use the first response to:

- recap or reference prior chats, prior failed commands or prior project decisions;
- inspect/report GitHub permissions, branch lists, tags, releases or repository administration state;
- infer that archives or `ARCHIVE/**` are obsolete or unnecessary;
- suggest auditing/developing this skill as the default next action;
- infer current project conventions or facts from universal examples/history;
- narrate internal freshness SHA/project-decision bookkeeping when no update affects the requested task.

A correct minimal response is conceptually equivalent to:

```text
The repository is identified as the universal 1C + Cleverence skill, not as the target project.
Send the target project/repository/artifact and describe the task. I will inspect the available target source first, derive the project context, and request only material missing information before design/implementation.
```

## Fail-closed cold-start rules

- Repository/file/archive names are not proof of artifact role.
- A reference corpus or archived project snapshot is not the deployed baseline.
- A configuration subset/patch is not automatically a full delivery artifact.
- Missing decisive source becomes an evidence request/pending state, not an assumption or `NOT_APPLICABLE` shortcut. Before manually requesting current-1C XML/BSL/configuration/extension source, disposition ProjectSnapshot through `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`; manual export is fallback/discovery bootstrap, not the silent default.
- For requirements-analysis/LT/TZ/specification work, read `KNOWLEDGE/REQUIREMENTS_ARTIFACT_INTEGRITY.md`; `ANALYSIS_ONLY` does not allow a blocking OPEN or `PROPOSED_SOLUTION` to be presented as an agreed/ready requirement.
- Source-detected surface/risk may be widened by project/task context; it may not be downgraded to reduce review work.
- A clean deterministic scan is not semantic/runtime proof.
- Saying the skill was used is not proof that its executable workflow ran. For non-trivial work, canonical “checked/ready/proven/N/N” claims require `KNOWLEDGE/PROOF_CLAIM_INTEGRITY.md` and the actual registry/gate artifacts; ad-hoc checklists remain supplementary.
- Every implementation change is subject to Tier-0 `MINIMAL_COHERENT_CHANGE`: minimize the necessary change surface relative to the exact baseline, exclude unrelated/refactoring/future-proofing work, prefer an existing owner/extension point when sufficient, and never trade readability/cohesion/correctness for fewer LOC.
- Project conventions must be discovered from actual target source/context; never copy author/company/date/naming conventions from this universal repository into a project.
- For changed code in a new project, unresolved author-marker, technical-comment or existing-comment policy blocks final code output; analysis may continue while the question is open.
- Public/exported interface comment policy becomes required when such an interface is created/changed; metadata `Comment`/`Комментарий` is a separate contract.
- `PATTERNS/**` may guide implementation shape only; `role=ILLUSTRATIVE_PATTERN`, `evidence_role=NONE`, `copy_policy=ADAPT_ONLY`. A pattern never proves an API, signature, field, hook/action or runtime behavior.
- `TESTS/fixtures/**` is analyzer/regression input and is **never implementation precedent**, including files named `*_good`.
- Cross-chat memory is not current-project evidence by default.
- Git branches, tags, releases and commits are distinct namespaces/evidence objects.
- `ARCHIVE/**` and `REFERENCE/**` are on-demand evidence stores; "not default-loaded" never means "not needed".
- A previously loaded skill SHA is not proof that the skill is still current; freshness uses the tracked ref and `KNOWLEDGE/SKILL_FRESHNESS.md`.
- A previously accepted project decision is not proof that it is still current; mutable project decisions use `KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md` and evidence/supersession state.
- «Типовой» is reserved by `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`: customer/partner/integrator/vendor changes are «доработки» even when they live inside an object that originated in a firm-1C release; unresolved origin is not proof of typicality.

## Canonical implementation patterns

When requirements/design are already evidence-backed but the implementation **shape** would benefit from a small example, search `PATTERNS/INDEX.json` instead of copying a regression fixture or inventing structure from memory:

```text
TOOLS/pattern_locator.py --intent "<mechanism / implementation shape>"
→ load only the matched good/bad pair
→ adapt the structural idea
→ prove real names/signatures/fields/lifecycle/runtime from exact target or user-authorized source
```

Pattern guidance and evidence have different jobs:

```text
PATTERN
→ teaches shape
→ NOT evidence

DISCOVERY CATALOG
→ suggests where to inspect
→ NOT proof

TARGET / AUTHORIZED EXACT SOURCE
→ proves the concrete contract
```

Do not bulk-load `PATTERNS/**`; use the locator and the active profile/mechanism to keep context bounded.

## Context budget

Normal cold start should load only:

```text
README_FIRST.md
README.md — bootstrap/intake sections
KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md — mandatory provenance vocabulary
SKILL.md — bootstrap/routing contract
KNOWLEDGE/SKILL_FRESHNESS.md — version/freshness contract
KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md — only once target project context exists / is resumed
RULES/rule_registry.json — through tools/generated routing, not by dumping the whole file into context
PROJECT_CONTEXT — target project only, when it exists
active routed profiles/knowledge
matched PATTERNS good/bad pair — only when implementation-shape guidance is useful
```

`ARCHIVE/**`, retained baselines, all patterns and external supporting sources are not default chat context.

A long-lived chat with an unchanged `loaded_sha` should load **less**, not more: no repository reread is required. When the SHA changes, inspect the diff and load only task-impacting changes. Likewise, project-context revalidation is dependency/decision-key targeted rather than a full project rebootstrap.

## Expected first-response contract

With only this skill repository URL available, the assistant should be able to state, without guessing project details:

```text
skill_repository_identified = true
target_project_identified = false
project_context_invented = false
cross_chat_context_used_as_evidence = false
archive_bulk_loaded = false
repository_admin_audit_started = false
skill_maintenance_assumed = false
skill_freshness_state_recorded = true
next_needed = target project/artifact + task
```

Once target evidence is supplied, source-first project bootstrap replaces generic questioning. Later substantive tasks in the same chat begin with the lightweight skill freshness check plus targeted validation of only the durable project decisions they rely on; the user should not need to manually say “reread the repository” or “forget the old project decision”.
