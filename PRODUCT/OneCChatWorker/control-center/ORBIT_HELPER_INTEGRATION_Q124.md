# Q124 — OneC Orbit Helper transport integration and bounded owner readback

**Scope:** source-only integration candidate from protected main merge `296df26fe860254e59abbe60d6a36bd5c2e84516`.
**Source donor:** Q121 PR #79, FA-reviewed transport HEAD `e9a1a16e7a27c0e54ada732452241c4ed2bb0b9f`. **UX owner:** unified PR #83 (merged) exact source HEAD `dd3806e8d68fd05a37c0fc0671de06198718d61d`.

## Why we must not merge old Q121 HEAD directly

Q121 was written before the accepted D1/D2/D2B/D2C owner and admission protections, so the Q121 branch diverged from current `main`. Blind cherry-pick/replacement of `MainWindow.xaml.cs` or old WPF fixture would regress exact selected-project identity checks, pending-admission project pinning, and queued post-action readback. This candidate starts **from current main**; only Q121's reviewed `WorkerClient` START/CONTINUE console transport is ported. The current native UI implementation of START/CONTINUE admission serialization remains intact.

## Transport contract

- Only **non-elevated START and CONTINUE** use a visible Windows PowerShell console with native `runas.exe` password handling. No GUI-managed credentials, `-Json`, output redirection, or persistent passwords.
- `UI_CONTEXT` and other ordinary Worker invocations retain hidden, redirected UTF-8 JSON. Elevated STOP remains Windows UAC, without a new credential broker or implicit START/STOP.
- Process exit code **never means Helper CONNECTED**. The GUI checks a later canonical, selected-project-bound owner `UI_CONTEXT`, with the existing single-flight drain and admission lease. Nonzero/foreign/missing owner response is UNKNOWN/HOLD; no second prompt or project switch can execute while admission is pending.
- GUI owner queries have an independent **25-second watchdog**. Timeout maps to nonzero `UI_CONTEXT_TIMEOUT` without owner JSON; the corresponding read-only child process is cancelled and, when still alive, terminated by scoped process-tree cleanup. Cancellation of the caller is propagated. **No kill, watchdog, or timeout is added to interactive START/CONTINUE or the real Helper.**
- Timeout recovery is through another deliberate read-only owner refresh; never reuse stale `START` or `CONTINUE` entitlement.

## Evidence to require before acceptance

1. Current **exact HEAD** five-gate GitHub Actions PASS; native Windows WPF fixture proves visible START/CONTINUE metadata, hidden UI_CONTEXT, preserved elevated STOP, watchdog cooperative and noncooperative owner timeouts, cancellation, existing 314 owner UI fixture assertions and six timer/admission overlap cases.
2. Independent FA source/hosted review of the **whole main→candidate diff** on immutable SHA, including elevated-vs-interactive transport and process cleanup safety.
3. **Separate production HOLD:** no claim of real restricted-account prompt, wrong password, cancellation, authenticated Helper CONNECTED, packed new EXE, installer, update/rollback or trusted runtime.lock until separately tested.
4. A future test with a **user-authorized disposable restricted Windows identity**, isolated Worker/Orbit roots and synthetic projects only; operator controls any password entry. Never use the real installed product, live Helper, customer Source/Main/Incoming or S4 for this acceptance fixture.
5. New EXE must receive separately pinned file hash and manifests, RU/EN & DPI keyboard usability, signed/trusted release authority as applicable, install/rollback/owner timeout recovery acceptance. Production release requires explicit operator authorization.

**Environment and limits:** DESKTOP-N0TQA0J was online at planning time, but only **9%** of Desktop Commander quota remained. No remote test commands, production mutations, credential usage or software installation were performed for this implementation; hosted CI and GitHub API are the acceptance path for this PR.
