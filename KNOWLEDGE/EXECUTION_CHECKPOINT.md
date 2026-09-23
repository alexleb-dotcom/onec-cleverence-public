# Execution checkpoint and timeout recovery

`TOOLS/execution_checkpoint.py` is the canonical owner of **local operational execution state** for long-running commands. It answers only whether an exact command for an exact source identity was launched, is still running, and which persisted RC/log/report/output evidence belongs to that attempt. It is not semantic proof, a release gate, Performance Review, or authorization to publish.

## Required caller protocol

For a long-running local command, persist the operation outside the tracked source tree and invoke the command through the checkpoint CLI. The most important integration boundary is the **outer runner**: wrap `TOOLS/run_public_ci.py`, `MAINTENANCE/INTERNAL/CI/run_ci_fast_gate.py`, or `MAINTENANCE/INTERNAL/CI/run_ci_full_audit.py` rather than rewriting their internal check loops.

Before any apparent retry, invoke the same exact operation again or use `recover`. The canonical owner binds `stage_id + check_id + attempt_index` to one operation identity. A changed command, cwd, source head/tree, or snapshot digest for that slot is `STALE_IDENTITY`, not a new implicit attempt. Use a new explicit `attempt_index` only after a deliberate retry decision.

`RUNNING` means continue polling the persisted operation. `PASSED`/`FAILED` means read the existing RC/log/report and do not rerun. `LOST_PROCESS` and `STALE_IDENTITY` are fail-closed and require an explicit recovery decision. A tool/transport/LLM timeout never proves that the target process failed to start.

## CLI shape

The source identity is a JSON file outside the tracked source when it contains run-specific state. For a public snapshot use `SNAPSHOT` identity with `archive_sha256` and `snapshot_digest`; for private source use `PR_SOURCE` with repository/base/head/tree/verified local tree. Environment names may be fingerprinted with `--env-name`; plaintext values are never persisted.

Example shape:

```text
python TOOLS/execution_checkpoint.py run \
  --state-root <outside-source-state-dir> \
  --stage-id PUBLIC_CI --check-id FULL \
  --cwd <snapshot-root> \
  --source-identity <snapshot-identity.json> \
  --env-name CI \
  --expected-output <report-path> \
  --wait-seconds 1 \
  -- python TOOLS/run_public_ci.py --mode FULL
```

If the caller disappears after launch, repeat the exact command or call `recover` with the same arguments. Do not substitute remote read-back for a lost local process.

## Public-safe boundary

Only the generic module, tests, and this contract belong in `SHAREABLE_CORE`. Operation directories, PIDs, logs, reports, source-identity files, and environment fingerprints are runtime evidence and must stay outside the tracked source tree. Private source commit identity is not written into the public distribution manifest.

## Proof boundary

`RC 0` means execution succeeded for this exact operation. It does **not** prove the semantic property checked by that command. Existing machine receipts, validation ledger, semantic proof, runtime proof, and release gate remain responsible for interpreting whether the produced evidence satisfies their contracts.
