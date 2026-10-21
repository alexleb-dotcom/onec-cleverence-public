# OneC Orbit #115 — detached-update image-lease prerequisite (S2-L0)

**Scope:** independent, *read-only* preflight diagnostic and a disposable Windows regression. **NOT a functional self-updater**, update coordinator, release downloader, external release approval, installer gate, or authorization to change an installed application. The current WPF UPDATE button is not certified as a trusted self-updater.

## Why a separate process is required

The shipped WPF application hides on WM_CLOSE and survives minimized into the system tray. An additional instance may keep the same Win32 EXE section image mapped even after the window closes or the first instance exits. Native UPDATE replacing files while the original image is in use risks partial application replacement. Closing one visible window, waiting only for a parent PID, and checking exit code zero are insufficient.

`tests/Inspect-OrbitUpdaterImageLease.ps1` is a bounded, mandatory-explicit-fixture-root **observation-only** tool, not used by installed product. It queries Win32_Process for the actual image path (not visible windows), counts every matching running WPF image, and returns a machine-readable blocking status with `updater_ready=false`, `installed_image_write_permitted=false`, `update_invoked=false`, `process_terminated=false`, `worker_or_s4_touched=false` in *every* state. Inconclusive process enumeration/access/path/reparse/fixture isolation checks also block. Absence of processes is `DETACHED_HANDOFF_NOT_IMPLEMENTED`, **never READY**. This avoids inventing a falsely green updater.

`tests/run_orbit_update_image_lease_regression.py` creates a uniquely named `%TEMP%` fixture, verifies the copied EXE SHA against runtime.lock, runs two genuine WPF EXE copies with all Worker/UI settings redirected to a fixture-only UI_CONTEXT mock launcher, hides one via WM_CLOSE, verifies both still block, cleans up only the two owned fixture processes, and verifies the no-process case is still blocked. It does **not** hash/copy/read project Source/Main/Incoming, invoke any native Worker INSTALL/UPDATE, request UAC, or stop helper/MCP/S4. If fixture setup fails, CI fails rather than pretending update is safe.

## Next independently gated implementation (S2-L1 and beyond)

1. Trusted candidate: require **operator-selected immutable full GitHub SHA** reachable from fixed protected `alexleb-dotcom/onec-cleverence-public/main` via authenticated HTTPS GitHub API, local package *complete* tree validated against immutable Git blob IDs + modes and canonical runtime.lock + distribution manifest. Do not trust attacker-regenerated manifest/lock, mutable branch name or arbitrary ZIP contents.
2. Detached, separately owned updater executable **outside installed image** with explicit per-product exclusive handoff and launch admission gate in *all cooperating WPF instances*; gracefully request explicit shutdown across ALL relevant users without indiscriminate process killing. Block updates on unknown/non-cooperating/racing WPF processes. An inventory snapshot alone has a launch race; this L0 diagnostic **does not close that race**.
3. Reverify package bytes immediately before native elevation; do not run installed bare launcher. Request UAC only for adjacent verified package launcher with verified Core/lock, and handle UAC cancel with no mutation.
4. Prove durable journaled image-replacement atomicity/rollback on interrupted operation, installed identity readback matched to this attempt, full SHA integrity and Source/admission preservation. Do not show green UPDATE from process exit or installer exit code alone.
5. Run multiuser/tray-hidden/second-instance/race/denied-UAC/corrupt package/crash injection scenarios on disposable Windows paths, GUI RU/EN, light/dark, DPI 100/125/150, keyboard; require hosted Fast/UI/Windows/Full and independent FA on immutable PR head.

## Scope decision

L0 can be merged independently after FA and operator approval as a reusable hard-negative test fixture. It provides **no update capability** and grants **no permission** to install/migrate/replace anything on DESKTOP-N0TQA0J. PR and CI must not call native INSTALL/UPDATE/MIGRATE.
