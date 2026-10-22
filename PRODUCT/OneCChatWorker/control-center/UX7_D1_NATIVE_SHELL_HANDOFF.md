# UX7-D1 OneC Orbit: native WPF shell and minimal navigation

**Status:** bounded WPF source implementation under private control #122.
This is **not** an installed product update or a production trusted release.
Operator explicitly approved the final 3+4 information architecture on
2026-10-22, and relaxed preservation of the unused *installed GUI*; project
Source/Main/Incoming, active Helper/Worker/admission and S4 remain out of scope.

## Immutable authority and design

Based on independently accepted read-only UX7-D0R design PR #78 HEAD
`c7296c45bcf7e8d6a000b0f766031ade8632811b`
(FA #120 `UX7_D0R_THREE_FINDINGS_HOTFIX_EXACT_HEAD_FA_PASS_WITH_CONDITIONS`).
Branch is based on protected `main` at
`a475caa71246816c38dd969cf84f8df62228af96`.
D0R prototype is **not merged** or silently imported into D1.

## D1 native implementation

- Exactly three prominent sidebar buttons: **Мой проект / Все проекты /
  Настройки**, localized RU/EN with the existing Segoe UI/light/dark system.
  Legacy Work/MCP Activity/Maintenance/Advanced sidebar buttons remain present
  **in XAML only with Visibility=Collapsed** while the existing C# named
  references and event handlers are preserved.
- Four project tabs in the content header, only when an authoritative
  selected_project.project_id is known and only on contextual pages:
  **Обзор** → existing safe Home and its single owner-based next-step link;
  **Исходники** → the general Source/verify/recovery panel;
  **Расширения** → the selected-extension panel;
  **История** → owner-provided MCP activity page.
  This is bounded *navigation* of existing panels, not an early D2 rewrite of
  project activity/source/extension data contracts.
- **Настройки** provides explicit secondary buttons to existing Maintenance
  and Advanced/diagnostics. Existing Work remains one click from the
  owner-based Home CTA; no accepted operation is deleted. Technical pages
  remain discoverable but do not occupy the main menu.
- Project selection, state, task and permission gating continue to derive
  from canonical Worker UI_CONTEXT; no local success heuristics are introduced.
  The header shows the parsed owner `generated_utc` when available, otherwise
  an explicit unknown/disabled message (not wall-clock 'just checked').
  Active task belonging to another project and active task without owner
  confirmed helper connection show warning copy from actual UI_CONTEXT only.
- Existing chosen-ID/stale-response checks and safe Work/Source/extension
  action boundaries remain unchanged. **No changes to WorkerClient,
  MainWindow mutation handlers, Worker/Core, restricted launch, S4,
  installer or user project files** in this branch.
- An isolated fake-owner WPF fixture checks three visible navigation
  destinations, scoped tab visibility and Source/Extensions split, History
  navigation, Settings shortcuts and no Worker mutation on navigation.
  The old distributed SHA-pinned EXE remains in the repository and its
  separate packaged keyboard probe tests **that old executable**, not the
  newly compiled D1 shell; do not conflate test evidence.

## Known D1 limitations / next owner milestones

- D1 keeps original dense Home, Work, maintenance content and the old
  single-page ProjectWizard while establishing a simplified navigation
  scaffold. UX7-D2 will recompose project Work as native inline status/action
  and enforce no stale project context in every tab; UX7-D3 implements the
  independently designed **three-stage** real wizard with owner preflight;
  UX7-D4 moves all remaining technical and potentially dangerous maintenance
  into contextual flows. Do not call the source patch a complete UX7 redesign.
- Physical WPF screenshots in RU/EN light/dark at 100/125/150% on 920×620 and
  1180×760, focus/tab/arrow and 3-tab navigation require fresh independent
  assessment; browser D0 FA does not substitute for D1 native testing.
- `PROJECT_READY` source context != Helper CONNECTED. Prior Helper #121
  source-level FA PASS / PRODUCTION HOLD remains a separate Draft PR and was
  **not** merged or used here; real credential prompt and published GUI EXE
  production operation still unproven.
- Do not install or merge this WPF source change without terminal exact-head
  hosted 5/5 CI, independent bounded D1 FA and **separate** operator
  authorization for protected main/release.

## D1 independent FA review — exact-head correction (2026-10-22)

FA #122 returned `UX7_D1_NATIVE_WPF_SHELL_EXACT_HEAD_FA_REVISE`
on previous SHA `e0bab5b4a9dc5c694208eac6135a86a51d352a2c`,
despite terminal five-gate CI success. Independent FA reproduced an OWNER
IDENTITY / FRESHNESS presentation defect: while asynchronous selection from
RetailGroup to NeoHim was pending, global header still displayed the previous
project's generated_utc "verified by Worker" time and active/helper warning
beside the newly selected project name. The action gates correctly disabled
mutations, but presented owner state as current for the wrong project.

Correction in MainWindow.xaml.cs:
- The `ProjectsList_SelectionChanged` handler atomically sets new selected
  identity and clears old `_contextReady`/`_context`, then calls
  `ClearOwnerProjection(WorkspaceVerificationPending)` BEFORE requesting
  fresh `UI_CONTEXT` and before any await.
- Explicit pending/unknown copy is RU/EN localized; previous verification
  timestamp, owner/other-project warning, Helper badge, active task claim,
  S4 usage and checkpoint projection are downgraded, never falsely bound
  to new project. Actions continue disabled during the transition.
- A failed/nonzero UI_CONTEXT readback now also calls
  `ClearOwnerProjection(WorkspaceVerificationUnknown)`; only a matching
  canonical successful Worker result can restore verified fields.
- Existing RefreshContextAsync request-target comparison and stale response
  rejection are preserved, as are all Worker mutation/admission boundaries.
  This change never refreshes owner data by reading files directly.

A new in-process native WPF adversarial fixture injects RetailGroup-era
timestamp, active warning, Helper/Task state, holds a Worker context result,
changes selected identity to NeoHim and asserts immediate clearing while
the readback remains pending. It then delivers a stale RetailGroup readback
and verifies that the requested NeoHim projection wins; switches back to
RetailGroup, returns a nonzero error, verifies explicit UNKNOWN and disabled
actions, then requires fresh confirmed context for recovery. No extra
RunAsync or real Worker/Helper action occurs. Native isolated Windows
runner PASS 205 assertions, 93 synthetic screenshots, plus legacy packaged
EXE keyboard probe PASS. Packaged probe is still the **OLD** distribution
EXE, not a rebuild containing this D1 correction.

This correction is a NEW SHA and needs committed-blob canonical integrity,
privacy, terminal five-gate hosted CI, independent D1 RECHECK verdict and
a distinct operator-authorized protected merge/packaged release. Do not
reuse the earlier FA REVISE or earlier successful old-head CI for acceptance.
