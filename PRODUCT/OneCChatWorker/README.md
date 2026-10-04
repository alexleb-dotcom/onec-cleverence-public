# OneCChatWorker turnkey product

This package is the 1C-first turnkey implementation of the accepted OneC Architecture runtime.

## Entry point

Run **`OneCChatWorker.ps1`**. With no arguments it opens the operator menu. The same file also exposes deterministic CLI modes for automation and support.

Main menu:

- START PROJECT
- STOP
- STATUS
- PROJECTS
- VERIFY / bounded REPAIR
- SETTINGS / DIAGNOSTICS
- INSTALL / UPDATE
- UNINSTALL GUIDANCE
- EXIT

The PROJECTS submenu supports list/add/deactivate project, add/deactivate participant, set/replace Main, add/deactivate extension, APPLY and VERIFY.

## First run

1. Download or clone this repository.
2. Run:
   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PRODUCT\OneCChatWorker\OneCChatWorker.ps1 -Mode PRECHECK
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PRODUCT\OneCChatWorker\OneCChatWorker.ps1 -Mode INSTALL
   ```
3. INSTALL self-elevates and:
   - installs pinned Node.js and ripgrep with WinGet when required;
   - creates the non-admin `OneCSourceReader` identity if absent;
   - installs the bounded provider/helper runtime under `C:\ProgramData\OneCChatWorker`;
   - initializes `C:\OneCChatWorker\projects.json`;
   - keeps the runtime OFF after installation.
4. One unavoidable remote-auth checkpoint remains:
   - connect the stable private MCP app in ChatGPT to
     `https://onec-g1q1-relay.alex-lebad1.workers.dev/mcp` and complete OAuth;
   - enroll this machine with the helper secret using:
     ```powershell
     .\OneCChatWorker.ps1 -Mode SETTINGS
     ```
   The secret is entered locally, is never committed to the catalog/repository, and receives a read-only ACL for `OneCSourceReader`.
5. Add a project/participant/Main/Extensions, APPLY, VERIFY, then START a task-bound admission.

## Canonical 1C layout

Direct artifact roots only:

```text
C:\OneCChatWorker\<project>\
  ProjectManifest\project.json
  Participants\<participant>\Target\Main\Configuration.xml
  Participants\<participant>\Target\Extensions\<extension>\Configuration.xml
  Output\<task>\...
  Detached\...
```

There is no redundant `Main\Main` or `<extension>\<extension>` wrapper.

## Catalog and APPLY

`C:\OneCChatWorker\projects.json` is desired operator state. JSON is used deliberately so the product has no YAML parser dependency.

APPLY:

- validates unpacked 1C roots;
- stages and hashes copies before promotion;
- creates a normalized `ProjectManifest\project.json`;
- binds the manifest to `projects.json` SHA-256;
- preserves Output;
- never edits external business Source;
- archives replaced artifacts under `Detached`;
- moves deactivated participant/extension artifacts to `Detached\Deactivated` instead of deleting them.

Catalog/manifest mismatch is reported as `DRIFT_APPLY_REQUIRED`.

## Runtime security boundary

The model-facing surface is exactly:

- `source_context`
- `source_search`
- `source_read`
- `proposal_write`
- `proposal_read`

No source write, shell, process, browser, arbitrary filesystem, delete, project switch, root switch or task switch is exposed.

START creates one manager-owned `active-admission.json` binding exactly one project and one task before the helper starts. The model cannot change either value.

`Participants` are read-only to `OneCSourceReader`. `Output` is writable only for proposal delivery. Proposal provenance is machine-readable and uses status `PROPOSAL_NOT_APPLIED`.

## Safe replacement and repair

Existing canonical artifacts are never silently recursively deleted. A requested replacement moves the old artifact to `Detached` first.

REPAIR is deliberately narrow: it may re-APPLY when the project is missing an applied manifest or has catalog/manifest drift. Unknown/hash-corruption states are not auto-repaired.

## Cleverence

The catalog schema already carries `platform`, but this release is intentionally 1C-first. Any active non-ONEC participant fails closed with `PLATFORM_NOT_IMPLEMENTED_1C_FIRST`. Cleverence must reuse this manager/installer architecture after its own canonical-layout gate; no second installer is intended.

## Uninstall

`-Mode UNINSTALL` returns the safe uninstall plan. The default policy removes runtime/launcher components only after STOP and **retains**:

- `projects.json`;
- project Participants copies;
- Output proposals/evidence;
- Detached archives.

It never silently deletes external business Source or project evidence.

## Reproducibility

Pinned package versions and reference hashes are recorded in `runtime.lock.json`.

Run local regression on Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\PRODUCT\OneCChatWorker\tests\run_local_regression.ps1
```
