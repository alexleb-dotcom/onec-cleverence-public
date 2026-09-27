# Development handoff workflow: ProjectSnapshot -> ChangePackage

## Purpose

The skill must work in customer environments where development happens on remote servers and customer databases, while a stable local clone or reliably assembled `.cf`/`.cfe` may not exist. The default integration pattern therefore separates **evidence acquisition** from **delivery packaging**:

`Task / requirements -> ProjectSnapshotRequest -> CollectionPlan -> ProjectSnapshot -> analysis/design/development -> ChangePackage`

A later `PostTransferSnapshot` is reserved for verification, but is optional by default until project policy explicitly requires it.

## 1. ProjectSnapshotRequest

The skill first derives a machine-readable collection request from the accepted requirement, active review rules and unresolved evidence dependencies. The request is **not** a static list of every possible configuration artifact.

It must:
- name the exact baseline/configuration identity currently expected;
- name entry objects/scenarios and material evidence categories;
- request the smallest sufficient dependency closure that can prove the active claims;
- distinguish callers, callees, metadata companions, form/command wiring, rights, scheduled jobs, subscriptions and integration contracts when they are relevant;
- declare the minimum evidence fidelity required by each material item (`FULL` or `PARTIAL`);
- state privacy/data minimization constraints;
- allow iterative delta requests when a newly discovered dependency expands the required closure.

A whole-configuration dump is permitted when it is the smallest practical supported acquisition path or the user explicitly chooses it, but it must not be described as necessary merely because targeted collection has not been designed.

## 2. Collection planning

Before collecting evidence, run `TOOLS/plan_project_snapshot_collection.py` with the backends that are actually available at the customer contour.

The planner consumes:
- `PROJECT_SNAPSHOT_REQUEST.json`;
- `KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_CAPABILITIES.json`;
- the explicit available-backend set.

It emits a `PROJECT_SNAPSHOT_COLLECTION_PLAN` that selects the strongest permitted backend for each requested evidence item and classifies it as `READY`, `PARTIAL` or `UNSUPPORTED`.

The plan also preserves `baseline_expectation` from the originating request so the returned package can be checked against the expected configuration identity instead of being bound only by a request id.

Planning is fail-closed with respect to evidence semantics:
- an available backend that is disallowed by request policy is ignored;
- `RUNTIME_METADATA` cannot be upgraded into module source merely because the target object exists at runtime;
- partial evidence remains partial when the request requires full fidelity;
- `HYBRID` is derived only when more than one direct backend is needed;
- unresolved items stay explicit and can drive a delta/manual/source-export request.

A valid plan can be `PARTIAL` or `BLOCKED`. That means planning succeeded but the current contour cannot yet close every required proof dependency. `--strict` turns this into a hard automation failure when a fully ready plan is required.

## 3. Collector/backend honesty

A collector may use different backends depending on what is available at the customer site. The contract recognizes at least:
- `SOURCE_EXPORT` — exported source/configuration files are available;
- `CONFIGURATOR_ASSISTED` — a helper uses supported configurator/designer export facilities and then selects the requested evidence;
- `RUNTIME_METADATA` — only runtime-visible metadata/evidence can be collected;
- `MANUAL_ATTACHMENTS` — the user supplies artifacts that the automatic backend cannot access;
- `HYBRID` — several of the above are combined by the collection plan.

The backend must not claim evidence it cannot observe. In particular, runtime-visible metadata is not automatically proof of module source text, form source, role source or exact configuration bytes.

The maintained capability boundary is documented in `KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR.md` and represented mechanically in `KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_CAPABILITIES.json`.

## 4. ProjectSnapshot

`ProjectSnapshot` is an evidence package, not a configuration delivery artifact. In the current v1 package, acceptance is bound by the originating `request_id` across CollectionPlan/manifest/runtime evidence, the known configuration identity when supplied, exact item/category/logical-target/backend correspondence, collector/read-only identity and SOURCE_EXPORT manifest/content presence. A separate `snapshot_id` is not required by the current validator and must not be invented as if it were present.

Package hashes, returned source-file hashes and stronger baseline fingerprints may be recorded by the surrounding task evidence when available; they supplement rather than replace the current validator contract.

If required evidence is missing, the snapshot may still be useful for partial analysis, but the affected claim remains `EVIDENCE_REQUIRED`; the snapshot must not be laundered into a claim of complete context.

For packages produced by `ProjectSnapshotCollector.epf`, validate package/request/plan/configuration binding first with `TOOLS/validate_project_snapshot_package.py`. A produced ZIP is candidate evidence until that check succeeds.

## 5. Iterative evidence acquisition

The expected workflow is incremental:
1. derive the first snapshot request from the task and known target objects;
2. plan collection against the actually available backends;
3. when the maintained desktop Collector can satisfy the selected rows, verify/materialize the repository-pinned `ProjectSnapshotCollector.epf` and give the user that EPF together with the exact CollectionPlan using `KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md`;
4. the user presses **Собрать пакет** and returns one `ProjectSnapshot.zip`;
5. validate package binding, accept only matching successful runtime rows at their observed fidelity, and inspect returned source bytes for source-dependent items;
6. analyze the accepted evidence;
7. if a material dependency is discovered outside the captured closure or the plan leaves a decisive item unresolved, issue a delta request for only the missing closure/evidence class;
8. bind the accepted snapshot set to the development result.

This allows the skill to work without a permanent static customer contour while avoiding repeated full configuration exports when a smaller evidence set is sufficient. The user should not need to interpret collector JSON or manually map evidence rows.

## 6. ChangePackage

`ChangePackage` is the delivery envelope around the selected result mode. It may contain a manual-transfer instruction, direct source changes, patch/diff, importable artifact, full compare set, analysis report or a justified combination.

The package manifest must bind the result to the exact ProjectSnapshot/baseline used for development and trace each material change item to:
- target object/artifact;
- create/modify/delete action;
- exact code or payload artifact when applicable;
- instruction section / placement anchor when manual transfer is used;
- dependencies and ordering;
- verification hooks that can later be checked after transfer.

The package does **not** prove that customer target bytes were changed merely because the package itself is complete.

## 7. Post-transfer verification seed

The schema reserves `post_transfer_verification` with policy:
- `OPTIONAL` — default for the current workflow;
- `REQUIRED_BY_PROJECT` — a project may explicitly make verification mandatory later.

For `OPTIONAL`, absence of a post-transfer snapshot does not block delivery-artifact readiness. It also does not upgrade applied-target/deployment/runtime proof. The verification hooks and expected changed-object closure are retained so the same collector contract can later produce a `PostTransferSnapshot` without redesigning ChangePackage.

## 8. Current portable 1C collector

`ProjectSnapshotCollector.epf` consumes the generated collection plan and creates one chat-returnable evidence package.

The current desktop path:
- executes `RUNTIME_METADATA` rows through the embedded read-only runtime collector;
- leaves rows assigned to another backend explicitly skipped in runtime evidence;
- performs bounded `SOURCE_EXPORT` for rows assigned to that backend by launching Designer with `/DumpConfigToFiles -listFile` against only the requested metadata owners;
- writes `collection-plan.json`, `runtime-evidence.json`, `manifest.json`, source-export diagnostics and the bounded `source/` tree into one ZIP;
- never uses configuration load/update commands as part of collection.

Exact module/form/role source is still owned by source bytes, not by runtime metadata. A successful source-export manifest means the bytes are available for inspection; the chat must inspect and bind them before closing the source-dependent claim.

The collector implementation remains replaceable. `ProjectSnapshotRequest`, `CollectionPlan`, package binding and evidence semantics are the durable interface.
