# Q113 — existing extension one-command sync (CLI first)

## Intent and limits

Use `SYNC_EXTENSION` **only for an existing extension already present in
the accepted project manifest**. This is an operator-initiated, foreground
command. It never installs/deploys a Worker, stops/starts MCP, alters Main,
uses `APPLY`, imports a new extension, publishes an output proposal, or
updates a project while a live admission exists.

The CLI resolves the authoritative external Source from the **registered
catalog** — no destination or replacement source can be supplied to the
one-command workflow. Files under the selected existing extension only
are compared and hashed. Both Main payloads are metadata-only.

Example (on the machine with the installed Worker):

```powershell
& "C:\OneCChatWorker\OneCChatWorker.ps1" -Mode SYNC_EXTENSION -ProjectId RetailGroup -ParticipantId do -ExtensionId bitdo -Json
```

For `un/bit`, use `-ParticipantId un -ExtensionId bit`.

The launcher asks for UAC when necessary. It does **not** ask for the
`OneCSourceReader` password; that password is only relevant to the
separate local `START` operation.

## Workflow

1. Fail closed unless the installed project is `ACCEPTED`, the specified
   extension is already accepted, the current catalog extension Source and
   canonical path match the accepted manifest, no other Intake exists,
   no recovery marker exists, and **no active admission** exists.
2. Inspect and SHA-256-hash the external Source and accepted selected
   extension only, rejecting junctions/reparse points and overlapping Source.
   Compare relative filenames, file lengths, full SHA-256 and directories.
   If identical, return `NO_CHANGE` without creating any generation.
3. Otherwise call **existing** `Prepare-SourceUpdate` for the **single**
   exact key, fill only the returned Incoming slot, verify the original
   Source and every staged file after copying, and recheck the admission
   guard. Use the generated `generation_id` and the same exact
   `expected_artifact_key` in **existing** `Accept-SourceUpdate`.
   Only that native owner performs seal, final validation and publication.
4. If a failure occurs **after PREPARE**, do not automatically cancel,
   overwrite, recover, stop/restart the helper or run a second PREPARE.
   Preserve the exact generation for `UI_CONTEXT`, diagnostics and
   operator-authorized native recovery. An admission arriving during the
   operation prevents ACCEPT; `SEALED_VALIDATED` is reported as
   `WAITING_FOR_USER`, not success.
5. A **new** artifact gives
   `QUICK_SYNC_NEW_EXTENSION_USE_SELECTED_ADD`: register it once
   through native `ADD_EXTENSION`, then explicit selected
   `PREPARE_SOURCE_UPDATE` and `ACCEPT_SOURCE_UPDATE`. Never fall
   back to full `APPLY`.

The command deliberately does not attempt to switch a model-facing MCP
snapshot in the middle of a task. To publish changes during a live task,
the operator must explicitly stop the admission first, then run the sync
and start a new task locally.

## Regression and release gate

`tests/run_extension_quicksync_regression.ps1` runs only in an isolated
checkout fixture on Windows PowerShell 5.1. Existing selected Source
owner and zero-copy promotion are real; only OS ACL/UAC test account
integration is substituted. Both Main trees are held with exclusive
Windows handles throughout SHA/copy/publish, so a Main read or hash
throws. The suite tests unchanged skip, changed publish, Main invariance,
existing-other-extension invariance, folder copy, idempotence, live
admission refusal, new identity refusal and existing Incoming refusal.

The separate real ACL test remains mandatory. Require same-head
Public Fast, UI, Windows and Full CI and independent FA review
before RP merge. This PR is **off-production**; do not upgrade the
installed Worker without a separate operator authorization.
