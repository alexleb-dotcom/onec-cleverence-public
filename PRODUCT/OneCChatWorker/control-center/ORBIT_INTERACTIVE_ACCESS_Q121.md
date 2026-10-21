# Q121 — WPF Helper interactive START/CONTINUE transport candidate

**Status:** Off-production draft / unverified on live credential prompt / FA HOLD.
Control: private issue #121. Base public protected main:
`4a0fb72a52e8188465c58e48a5f0024708dbff4d`.

## Reported reproduction

Operator states: after using Orbit to stop the helper, "Открыть доступ ChatGPT"
did not launch a usable helper, but the equivalent manual console workflow did.
The reported GUI displayed a selected project, *"Помощник запущен;
подключение ещё не подтверждено"*, Start/Continue/Stop admission actions
and an optional access purpose. Treat this as a functional startup regression.
Screenshot and production project/session details remain in the private operator
conversation; **never commit screenshots or logs with live paths/session IDs**.

## Code-based hypothesis and patch boundary

Before patch, `WorkerClient.CreateStartInfo` launched **every** non-elevated
PowerShell command (including START and CONTINUE) with
`UseShellExecute=false`, `CreateNoWindow=true`, `WindowStyle.Hidden`, and
redirected output. But `OneCChatWorker.ps1` Run-Start/Run-Continue invokes
`Start-WorkerAdmission` in `core/OneCChatWorker.Core.psm1`, which issues
native `runas.exe /profile /user:<machine>\\OneCSourceReader` and expects
password input inside a console. This hidden-console mismatch is a **plausible
and high-confidence cause**, not yet a demonstrated exact production root
cause; other causes (credential denial, process lease, active admission,
relay authentication) remain possible.

Smallest bounded reference candidate in WorkerClient.cs only:
- Non-elevated START and CONTINUE use `UseShellExecute=true`, a normal
  interactive console, no redirected stdout/stderr and **no -Json**.
- WPF never asks for or captures the restricted password or shows it in logs.
  The original runas.exe prompt is Windows-owned in the child Worker console.
- All other non-elevated UI_CONTEXT/normal Worker commands preserve hidden
  process with UTF-8 JSON redirection, and elevated operations preserve their
  existing UAC policy.
- After the interactive process exits, WPF re-reads canonical `UI_CONTEXT`;
  exit 0 is NOT evidence of authenticated helper connectivity. When the
  process fails, expose only bounded process exit code, not password content.
- `MainWindow.Start_Click` selection/action guards are unchanged, especially
  ACTIVE_TASK+HELPER_OFFLINE must **not** silently mint another START,
  replay CONTINUE, STOP or clear active admission.

## Evidence and unresolved acceptance

WPF fixture assertions exercise START/CONTINUE process creation metadata,
correct typed action and arguments, visible interactive console/no capture,
and unchanged UI_CONTEXT/Verify/Apply hidden JSON route and STOP UAC boundary,
without executing a real password prompt. A manual user-owned real-credential
test is STILL required in a specifically authorized disposable Windows
session before acceptance. Do not run it on a working admission, live project
or restricted account without operator approval.

FA #121 identified a fail-open user-interaction race in the original
`MainWindow.Continue_Click`: it did not serialize its async Worker mutation
while an interactive credential prompt was pending, so double click/Enter
could create multiple native runas prompts. The new candidate explicitly
requires `_contextReady`, canonical `ContinueButton.IsEnabled`, and claims
`_mutationsEnabled=false` BEFORE awaiting Worker. All admission action
buttons are disabled; after exactly one owner readback, the gate is released
in `finally`. This mirrors guarded START; there is no automatic STOP/START,
and an already active offline session cannot be reminted.

A disposable fake IWorkerClient now holds CONTINUE on a
`TaskCompletionSource<WorkerCallResult>`, deliberately invokes the handler
twice before resolving and checks exactly one Worker CONTINUE call, no
competing action, one owner readback, and lock restoration for success and a
nonzero exit code. No real user credentials or helper processes are used.

New local native Windows WPF fixture completed SUCCESS with 0 build errors and
0 warnings; **all synthetic in-process cases and actual packaged EXE keyboard
focus probes PASSED on the latest isolated run** (including the prior
`PACKAGED_ASSERT:keyboard input restricted to owned EXE` assertion).
This does NOT retroactively invalidate the previous failed packaged run,
or prove it was mere desktop interference. It only provides fresh local
positive evidence. The exact live runas password prompt, wrong password,
non-interactive user account restrictions and confirmed Helper CONNECTED still
require separate disposable operator-authorized test and independent FA.
The PR remains Draft/HOLD even with green CI.

### FA-specific negative cases

- START/CONTINUE first launch, visible runas prompt, wrong password,
  cancellation, nonzero exit, delayed/no CONNECTED evidence.
- Closed GUI console vs untrusted/expired state; no false connected label.
- Existing active session/helper offline, blocked credential recovery;
  owner-proven recovery only, no auto STOP/START or cleared admission.
- UI_CONTEXT still hidden/UTF-8 JSON, UAC operations unchanged, no elevation
  of restricted Source access rights, no password capture in app/telemetry.
- Real packaged WPF keyboard/focus fixture repeat on an isolated Windows
  desktop, RU/EN, 100/125/150% DPI, no live helper/source mutations.
- Only after exact-head 4/4 CI, independent FA and explicit operator merge/
  production rollout approval may this patch be considered for use.

This is NOT an installed OneC Orbit update or a new credential broker.
