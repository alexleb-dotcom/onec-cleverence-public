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

---

## D0-R revision — response to independent FA #120 (2026-10-22)

**Status: REVISION FOR OPERATOR REVIEW, not an accepted WPF production contract.**
Independent FA verdict for earlier D0 HEAD
`e7fe1aaa06a6eedcee5497a3f3ae4cf813c1dd66`:
`UX7_D0_DESIGN_FA_REVISE`. Report:
https://github.com/alexleb-dotcom/private-onec-architecture-control/issues/120#issuecomment-6328461499.

This section supersedes previous D0 navigation and wizard *concept*:
- Prefer THREE first-level entries: **Мой проект / Все проекты / Настройки**.
  The default view is one explicitly selected and owner-validated project,
  not a duplicated global Home and Work dashboard. Zero or unverified projects
  show a chooser; globally active work in another project remains a visible
  owner-proven warning and cannot be rebound by UI selection.
- Project has FOUR scoped tabs **Обзор / Исходники / Расширения / История**.
  Owner-authorized current/new/continued task access belongs to the project
  overview, not a global generic new-goal Work page. Existing Worker START,
  CONTINUE, STOP, task, checkpoint, and SOURCE actions are preserved in
  documented contextual destinations and must not be mapped to fake states.
- Each project card and picker uses an actual *synthetic ID* in preview;
  RetailGroup/NeoHim/Nendo now route to their distinct selected identity
  and demonstrably different examples, not the shared RetailGroup screen.
  This is ONLY client-side simulated navigation; later WPF must round-trip
  selected identity in canonical UI_CONTEXT and discard stale responses.
- ONE disabled preview CTA chosen for sample state: READY/no active task
  `Начать новую задачу`; ACTIVE existing task
  `Открыть текущую работу`; UNKNOWN/HOLD
  `Обновить состояние`. No implementation may derive any positive status
  or admission eligibility from these synthetic examples. Actual connected
  readiness, status age/owner, project binding, relay freshness, task
  continuation and recovery are Worker-owned facts.
- THREE decision stages: identity, source input (optional extension reveal),
  review plus explicit confirmation. Local required-field UX assertions
  run before advancing, but never count as canonical Worker preflight.
  In D0-R **final Create stays disabled**; no Source reads. Later D3 must
  revalidate proposed fields via existing approved Worker interfaces, or
  HOLD if no approved preflight exists. Changing input invalidates preflight.
- No duplicated quick-action card or generic global Activity. Diagnostics,
  Source repair and receipts remain discoverable under project/Settings
  Maintenance and explicit details, with priority warning never buried.
- D0-R improves sample text contrast and adds keyboard tab arrow/home/end,
  modal Escape/Tab focus cycle and focus return. These browser behaviors
  DO NOT prove actual WPF screen-reader/packaged keyboard, DPI, large
  Cyrillic labels, nested dialog UAC, stale owner cases or process reality.

**FA improvement ADOPT:** display owner-verification freshness after *real*
context readback; prepare a reusable owner-scoped "Что изменится / Что
останется" review panel before every guarded write; distinguish work-intent
by Worker state, not three simultaneous equally prominent buttons.
**TRY:** recent verified project picker after operator usage testing.
**DEFER:** command palette; **REJECT:** automatic helper/source/update fix.

**Separate P0 defect** #121, Draft PR #79, MUST remain an independent owner:
interactive runas Helper admission currently fails from installed Orbit GUI
for operator (manual console works), actual root cause is only *hypothesized*
from source; do not use this concept to declare product Helper fixed. No
restart, stop, credential capture or automatic re-admission.

D0-R is a read-only standalone HTML navigation demonstration plus this design
contract, with no Worker, app binary, installer, production data or helper
modification. Operator design decision and a new independent bounded D1
implementation review remain necessary. Pending CI acceleration PR #77
passed its own exact-head FA #118 but has NOT received operator merge
permission; no one should merge it as a consequence of this UX report.
