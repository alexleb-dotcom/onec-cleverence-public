# UX7-D0 — OneC Orbit Workspace: design preview and WPF handoff

**Status:** DESIGN-ONLY / OFF-PRODUCTION / NOT IMPLEMENTED. Control #119,
related accepted #100/#103 UX3/UX4 and #116 visual simplification, #114 desktop-first.
Built from protected main `4a0fb72a52e8188465c58e48a5f0024708dbff4d`
without changes to WPF, executable, Worker/Core, CI or production installation.

## Preview

Open `control-center/design-preview/orbit-workspace.html` locally in an ordinary
browser. It is a self-contained read-only UX mockup (inline CSS/JS, installed
Segoe UI fallback, relative existing Orbit brand image, **no external assets**).
Clickable Overview, Projects, project workspace tabs, Work, History, Settings,
and 4-step Add Project. Project names RetailGroup/NeoHim/Nendo and EVERY
status/event in the mockup are **illustrative synthetic samples**, NOT facts
about current real project state. No network, process call, file input, device
query, durable persistence, update/installer action or Worker invocation exists.
Create is deliberately DISABLED after the last wizard step.

## Actual present problems, evidenced by current XAML

- `MainWindow.xaml` contains seven simultaneously equally weighted top-level
  nav entries: Home, Projects, Work, MCP Activity, Maintenance, Settings, Advanced.
- Maintenance screen presents Refresh Source, Deep verify, Recover safely,
  Update Worker, Source quick-sync and manual Incoming actions near each other.
- Home duplicates task/helper/source/recommendation details and a secondary
  Advanced entry. This competes with the single safe next action.
- `ProjectWizardWindow.xaml` currently has all fields on one view: name, base,
  purpose, Main XML path, extension name/path and create+refresh. It is *named*
  Wizard but does not have a step-by-step review or validation screen.
- Existing native Segoe UI Variable fallback and light/dark theme already
  exist; reducing text density/IA is more important than adding a custom font.

## Screen decisions, distinct from technical owner

| User-visible destination | Main role | Primary action | Advanced/technical |
|---|---|---|---|
| Overview / Обзор | Chosen project + short honest status + next step | canonical owner recommendation ONLY | source detail and hashes collapse into details |
| Projects / Проекты | Choose a project from canonical catalog | Open project | file Source operations are contextual |
| Project / Проект | One selected canonical project context | One owner-approved task action | project tabs State, Work, Files, Extensions, History |
| Work / Работа | Show existing task, helper, admission, continuation facts | Start/Continue/Recover as owner permits | raw id/checkpoint/receipts go to details |
| History / История | Timeline/activity and diagnostic evidence | inspect an event | MCP/technical identities not default Home |
| Settings / Настройки | Language/theme/autostart | standard preferences | Maintenance and Advanced nested, not mixed with tasks |

Home main CTA is conditional and **must not** be hardcoded to Start or
Continue: no project => Add/select; active+helper offline => owner-proven
Recover connection or HOLD (never Stop/Start); active+helper online =>
view existing work; expired with owner checkpoint => Continue; source
recovery blocked => owner-prescribed recovery; damaged product => repair
only via an accepted bounded owner action; no trusted release => NO update.

## 4-step wizard contract

1. **Project identity**: name, system/base, optional purpose; input validation,
   back and Cancel. Draft persists only in wizard memory, never as live catalog.
2. **Files**: Main XML folder, optional extension(s), explicit permission
   context. Do not read/copy/hash Source from WPF; show only canonical owner
   validation. No automatic selected extension or Main APPLY.
3. **Review preflight**: call EXISTING Worker owner to validate the exact
   proposed request. Show actual READY/BLOCKED/REQUIRES_CREDENTIAL status;
   never invent green PASS from an input path or mock. If unavailable, HOLD.
4. **Confirm**: exact project/Source scope, what changes and remains unchanged,
   explicit single canonical `Create` action, guard against double submission,
   cancellation or UAC dismissal; verify authoritative post-state before success.

Preview stage 3 is deliberately labelled NOT verified and cannot create.
No new backend ownership is authorized by this specification.

## Functional and accessibility acceptance for separate WPF PRs

- ONE primary CTA per view and canonical state, no destructive surprise.
- Display RU/EN resource parity; no untranslatable technical GUID/SHA or MCP
  epoch on the default surface. Warning/error grammar:
  *what happened / what is preserved / safe next step / details*.
- Test NO_PROJECT, CATALOG_DRIFT vs selected ACCEPTED, active+helper online,
  active+helper offline, expired/exhausted, offline startup, disconnected
  helper vs independently valid product integrity, recovery, interrupted
  Source update, UAC cancel, invalid extension, source stale, unavailable
  trusted update. Never simulate these facts in a production view model.
- Preserve current Worker action IDs, `UI_CONTEXT` canonical owner,
  asynchronous stale-response guard, existing button automation properties,
  persisted theme/language/startup, active task/recovery, S4/Source restrictions.
  NEVER touch RetailGroup/NeoHim/Nendo Source/Main/Incoming during testing.
- Physical Windows WPF screenshots at 1180×760 and 920×620, 100/125/150%
  display scaling, RU/EN and light/dark. Check keyboard Tab/Enter/Space,
  focus restoration after closing wizard and project navigation, accessible
  disabled-action explanations, clear Cyrillic glyph rendering, proper
  contrast and no clipped controls.
- New WPF must remain isolated in one sequential MainWindow owner branch;
  do not merge UX7 with pending CI #118/PR77 or S2-L1B trusted signing,
  or roll out production without explicit separate authorization.

## Release slices (not contained in D0)

D1 first: Home + sidebar + status header (existing UX4 #116), exact
keyboard/RT UI test; D2 project workspace/tabs/History/Work only after D1 FA;
D3 proper wizard and Worker preflight after D2 FA; D4 Maintenance progressive
disclosure and product updater entry only after trusted S2-L1B authority.
Every later implementation has its own exact-head CI, screenshots and
independent FA. The D0 preview is intended for operator design feedback and
should **not** be treated as a deployable Control Center.
