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
