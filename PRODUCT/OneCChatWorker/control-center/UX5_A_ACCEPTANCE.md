# Control Center UX5-A acceptance

This slice binds explicit project selection to the existing typed Worker actions.
`UI_CONTEXT -ProjectId <selection>` reads the selected project's canonical fast
state; it does not acquire or verify Source content. Multiple projects without
an active session require an explicit choice. Unknown/inactive selections fail
closed. Selection is retained across pages within this application instance;
on reopening, choose again unless the Worker supplies the active session project.

Worker owns the action projection. WPF disables actions while selection is
loading and discards responses for an earlier selection. Failed context refresh
invalidates old permissions. START requires a matching, confirmed selected id;
the existing Worker still revalidates its action. Blank purpose means general
reference access, not an implicit business development task. A new ChatGPT chat
does not require STOP/START. Existing offline admission recovery remains blocked
by its accepted owner; this slice creates no recovery mechanism.
An interrupted global operation without a project-bound recovery action stays
blocked; the UI does not guess its recovery target.

Normal status/reason copy uses RU/EN resources. Technical identities, owner enums
and raw diagnostics stay in Advanced. Usage and recorded expiry are separate
from helper connectivity and package integrity. Exact caps are not invented when
the owner prohibits their display. Source remains read-only and proposals are
not applied. Existing source-update actions are retained; the next source UX
slice is not implemented here.

## Isolated checks

- `tests/run_ui_context_regression.ps1`: real PS5.1 UI_CONTEXT and fast-state
  owners with isolated catalog/manifest/snapshot fixtures. First project drift,
  second accepted project, invalid selection, explicit choice, navigation,
  unchanged files and exclusive Main payload handle throughout context reads.
  No lifecycle or source acquisition command is executed.
- `tests/run_control_center_wpf_fixture.ps1`: real WPF windows and resources
  with an injected fixture owner. Captures typed START arguments without
  launching a Worker. Tests stale response, page selection, failed refresh,
  offline/connected admission, expiry, max20 input errors, empty state and
  disabled reasons. Renders RU/EN Home/Projects/Work/Maintenance/wizard at
  100/125/150 percent in both themes plus error/loading/empty/offline fixtures.
- Windows CI publishes `control-center-ux5-fixtures` from the exact PR commit.
  These are offscreen WPF renders and keyboard/style contract checks, not an
  interactive multi-monitor or production smoke certificate.
- Packaging regression installs only the distributed UI artifact and shortcut
  under its isolated scratch roots and verifies the runtime-lock hash.

## Independent RP/FA acceptance

Review the exact commit, CI screenshot artifact and shipped executable digest.
In an isolated product fixture choose the second ready project, navigate between
pages and verify the captured action targets that project. Check keyboard focus,
theme/language switching and monitor DPI transitions interactively if required.
Review active offline copy: no clearing, reminting or automatic recovery.

The candidate is an unsigned internal pilot executable. No production Worker,
Cloudflare, Source, Output, admission, S4 or installed runtime was modified.
Installation and any live acceptance require the independent RP procedure.
