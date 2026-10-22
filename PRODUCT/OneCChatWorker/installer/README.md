# OneC Orbit Slice A

Build on disposable Windows x64 with .NET 10 SDK and Inno Setup 6:

```powershell
git checkout <reviewed-exact-commit>
powershell.exe -NoProfile -ExecutionPolicy Bypass -File PRODUCT/OneCChatWorker/installer/Build-Installer.ps1 -OutputRoot C:\Build\orbit-new
```

The output directory must be new. `OneCOrbit-Setup.exe` includes freshly published
native WPF, Worker launcher/Core/runtime and the Node/ripgrep executable versions
and SHA256 identities in `runtime.lock.json`. No arbitrary download URL or
executable path is accepted by the installed product. The build receipt records
the exact checkout HEAD, installer SHA256 and actual GUI SHA256. This is an
unsigned internal pilot, not a signed production release.

Setup requires UAC for the protected runtime, Reader account and Source ACLs.
The interface runs in the user's desktop session. The Reader receives a random
password generated in memory; the password is neither embedded nor persisted.
Helper enrollment and actual Reader logon remain separately authorized operator
work. No Helper connection or production readiness is inferred from installation.

Default roots are `C:\OneCOrbit` and `C:\ProgramData\OneCOrbit`. Any preexisting
destination, legacy installation, trial GUI directory, shortcut or Reader
account causes a hold. Setup never adopts or migrates that data. The test-only
caller uses explicit empty roots on the disposable GitHub runner. Do not run the
installer smoke on an operator machine.

The first-run wizard opens only after a healthy installed `UI_CONTEXT_V1`
explicitly confirms zero projects and authorizes adding a project. It collects
project/system names, ONEC platform and a MAIN archive plus 0..15 extension ZIPs,
shows review/confirmation, then delegates one transaction to Worker. The GUI
does not inspect, extract, copy or hash Source payloads. Extensions receive
stable technical IDs `ext-1` ... `ext-15` in selection order.

Supported format: ZIP of a 1C XML export with `Configuration.xml` directly at ZIP
root. `.cf`, `.cfe`, wrapped directories, encrypted ZIPs, executable payloads,
links, duplicate Windows aliases, traversal and ADS are unsupported. Limits:
512 MiB archive, 50,000 entries, 128 MiB per entry, 2 GiB expanded per archive.
Worker uses existing validated initial acquisition/Apply/snapshot primitives;
the source-update generation API requires an already accepted MAIN and is not
used to invent an empty accepted snapshot.

Failed imports retain their `.bootstrap-*` transaction outside the project
catalog. Retry can complete an interrupted prepared directory promotion only
when the request identity, staged catalog and published manifest still match.
Unknown or changed state is held for recovery. No generic recursive transaction
purge is provided. Cancelling the wizard performs no Worker mutation.

Setup journals intended owned-file hashes before publication. On failure it
rolls back matching writes and the Reader created by that transaction; changed
or unknown files are retained. The journal permits explicit idempotent recovery:

```powershell
# Only against an operator-authorized incomplete installation, elevated:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <app>\SetupRuntime.ps1 -Mode Rollback -AppRoot <app>
```

The normal uninstaller validates the entire runtime receipt before deletion.
Active admission, unadjudicated Helper state, missing evidence, reparse paths
or modified owned files produce a hold. Projects/catalog, Source, Output,
post-install unknown files and the Reader identity are retained by default.
Inno owns package files, uninstall registration and its own logs; runtime
ownership and hashes are in `install-receipt.json`.

Windows CI builds the installer, installs under disposable roots, verifies a
real first-run WPF wizard, cancels it, imports MAIN + EXTENSION through real
Worker, reopens the installed interface, uninstalls, verifies retained Source
and no owned runtime-file leak, and tests rollback/journal replay. Artifacts:
`orbit-slice-a-windows` and existing `control-center-ux5-fixtures` (RU/EN
keyboard and DPI render fixtures). Human UAC consent, native archive-dialog
selection, physical monitor DPI transitions and independent FA still require
separate acceptance. A green hosted runner is not production migration approval.
