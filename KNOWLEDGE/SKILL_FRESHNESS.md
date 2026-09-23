# SKILL FRESHNESS — long-lived chat contract

The universal skill is versioned source. A long-lived chat must not assume that the copy of the skill it read earlier is still current.

This contract applies to the **skill repository itself**, not to the user's target project or deployed baseline.

## Session skill state

When the skill is first loaded, keep an internal working state equivalent to:

```text
repository = canonical repository resolved from the active Git remote/connector or explicit distribution configuration
tracking_mode = TRACK_CANONICAL | PINNED
tracked_ref = main | explicit user-pinned ref
loaded_sha = exact commit whose execution/routing contract was loaded
freshness_status = FRESH | UNVERIFIED | REFRESH_REQUIRED | BOOTSTRAP_REQUIRED | REBOOTSTRAP_REQUIRED
```

Default behavior is `TRACK_CANONICAL` on the repository's canonical branch (`main`). If the user explicitly pins a tag/commit/ref for reproducibility, respect that pin and do not silently move the chat to a newer `main`.

Repository identity is deployment-local. Resolve it from the repository currently supplying the skill: prefer an explicit user pin/configuration, otherwise the active Git remote or connected repository identity. Never hard-code the private maintenance repository into a shareable/public copy. A downloaded snapshot with no resolvable canonical repository may preserve its embedded `source_commit` as provenance, but freshness remains `UNVERIFIED` until a tracked repository/ref is established; the provenance SHA is not permission to query an unrelated private repository.

`loaded_sha` is skill execution state, not project evidence. Do not present it as a target-project baseline.

## When to check freshness

Perform a lightweight skill-head check when:

- starting a new substantive analysis/review/implementation task in a chat where this skill was already loaded;
- resuming substantive work after the skill was maintained/updated or after a meaningful pause where freshness is uncertain;
- before a final claim such as `PROVEN`, `ANALYSIS_COMPLETE`, production-ready delivery, or a skill-maintenance merge/release when the task spans multiple turns/tool calls and the canonical source is accessible.

Do **not** resolve/reload the repository for every tiny follow-up, wording edit or local clarification. Freshness is a cheap version check first, not a reason to consume the whole repository repeatedly.

## Decision procedure

Resolve the current commit for the tracked ref and compare it with `loaded_sha`.

```text
loaded_sha unknown
→ BOOTSTRAP_REQUIRED
→ load the minimal skill core and record its exact resolved SHA

current tracked SHA unavailable
→ UNVERIFIED
→ continue only as the explicitly loaded skill version permits
→ do not claim that the skill is current/latest

current_sha == loaded_sha
→ FRESH
→ continue; do not reread the repository

current_sha != loaded_sha and history/diff is comparable
→ REFRESH_REQUIRED
→ inspect loaded_sha...current_sha diff
→ reload only changed execution material that can affect the current task
→ invalidate/rerun affected routing/proof/tool evidence
→ only then advance loaded_sha = current_sha

current_sha != loaded_sha and old SHA cannot be compared/reached
→ REBOOTSTRAP_REQUIRED
→ reload the minimal core entrypoints/routing state from the tracked ref
→ reroute/revalidate active work as necessary
→ only then record the new loaded_sha
```

Merely observing a newer SHA is **not** a refresh. Never overwrite `loaded_sha` before the changed contract has been inspected and its task impact handled.

## Diff-first selective reload

Classify changed files before loading content.

### Core execution contract

At minimum:

```text
README_FIRST.md
SKILL.md
KNOWLEDGE/SKILL_FRESHNESS.md
```

If one changed, reload it. `README.md` bootstrap/execution sections are also reloaded when changed and relevant.

### Routing / gates / proof structure

Changes under or to these paths can invalidate routing/proof state:

```text
RULES/**
PROFILES/INDEX.json
REQUIREMENTS/INDEX.json
WORKFLOW/**
TOOLS/rule_registry.py
TOOLS/build_requirements_contract.py
TOOLS/requirements_gate.py
TOOLS/build_review_plan.py
TOOLS/build_validation_ledger.py
TOOLS/release_gate.py
```

When they changed during an active task, rerun routing and rebuild/reconcile downstream requirements/plan/ledger proof structures before reusing old dispositions. Do not keep an old routed rule set just because the target source did not change.

### Execution tooling

A changed analyzer/bootstrap/signature/tool under `TOOLS/**` invalidates only machine/tool evidence that depended on that tool unless it also belongs to the routing/gate group above. Rerun affected machine evidence before using it as current proof.

### Routed profiles / knowledge

For changed `PROFILES/**` or `KNOWLEDGE/**`, inspect the diff and reload only material that is active/relevant to the current task. A changed unrelated profile is not permission to bulk-load every profile.

### On-demand evidence stores

Changes in:

```text
REFERENCE/**
ARCHIVE/**
THIRD_PARTY/**
```

remain on-demand. They matter when the current task actually depends on that evidence/source. If a reused evidence claim depends on a changed reference, invalidate/re-check that claim; otherwise do not load the store merely because its SHA changed.

### Tests / CI / maintenance-only files

`TESTS/**`, `.github/**`, packaging metadata and maintenance-only files normally do not alter a target-project task contract by themselves. They are relevant during skill maintenance and must still be inspected when they explain or enforce a changed protection.

## Mid-task drift

A task can begin on a fresh skill and become stale while it is in progress. Before a final current-skill compliance/readiness claim, perform one lightweight tracked-ref SHA check when the task was long-lived enough for drift to be plausible.

If the SHA changed:

```text
final claim
→ pause claim only
→ refresh diff impact
→ reroute/revalidate affected obligations
→ then finalize
```

Do not restart unrelated target analysis from zero. Invalidate only proof/routing/evidence whose dependency changed.

## Failure behavior

- If the canonical repository is temporarily inaccessible, keep `loaded_sha` and mark freshness `UNVERIFIED`; do not invent a current SHA and do not say the skill is latest/current.
- If a user explicitly requested a pinned historical release, being behind `main` is not stale; the pin is the contract.
- If the old SHA is unreachable or history was rewritten, do not pretend a partial diff is complete. Use `REBOOTSTRAP_REQUIRED`.
- Do not ask the user to manually say “reread the repository” as the normal update mechanism once this contract has been loaded.
- Do not turn freshness into repository-administration reporting. The SHA check is internal execution hygiene; mention it to the user only when an update materially changes/blocks the current task or when the user asks.

## Anti-bypass invariants

The following shortcuts are forbidden:

```text
STALE_SKILL_CONTEXT_BYPASS
  continue a new substantive task without checking the tracked skill version

FRESHNESS_ACK_WITHOUT_REFRESH
  see a new SHA and simply replace loaded_sha without inspecting/applying the diff

STALE_ROUTING_AFTER_SKILL_UPDATE
  retain an old rule/routing/gate plan after those execution sources changed

MID_TASK_SKILL_DRIFT_IGNORED
  claim current-skill readiness after a long task without a final lightweight freshness check

FRESHNESS_FULL_RELOAD_OVERREACH
  repeatedly bulk-load the whole repository when the SHA is unchanged or the diff is narrow
```

The correct optimization is **SHA check → diff → task-impact reload**, not either “never refresh” or “reload everything every turn”.
