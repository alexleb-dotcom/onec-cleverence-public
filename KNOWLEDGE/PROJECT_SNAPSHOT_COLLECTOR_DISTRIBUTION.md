# ProjectSnapshot Collector distribution

## Purpose

When the active skill distribution includes the repository-pinned Collector artifact and payload, ordinary developers must receive a ready `ProjectSnapshotCollector.epf` from chat. Building the collector is maintenance work, not part of normal evidence acquisition. If the active distribution intentionally excludes the Collector, the workflow must resolve `COLLECTOR_UNAVAILABLE` and use the bounded manual fallback; it must not fabricate an EPF or transfer build responsibility to the developer.

Canonical repository distribution inputs are the artifact manifest plus transport-safe Base64 payload parts under:

```text
COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json
COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/
```

The payload encoding is an internal repository/chat transport detail. It must never be exposed to the developer as a replacement for the normal `.epf` file.

## Chat contract

When ProjectSnapshot collection is activated, chat must:

1. read `ProjectSnapshotCollector.artifact.json`;
2. require `status = READY`;
3. retrieve every declared payload part and verify its Git blob id;
4. reconstruct the exact EPF bytes from strict Base64;
5. verify byte size, SHA-256 and binary Git blob id of the reconstructed EPF;
6. verify that every declared EPF build input still has the accepted build-input Git blob id;
7. materialize a user-visible `ProjectSnapshotCollector.epf`;
8. provide that EPF together with the exact generated `PROJECT_SNAPSHOT_COLLECTION_PLAN.json`;
9. give only the short run instruction: open EPF -> load plan -> Собрать пакет -> upload ZIP.

The user should not need to clone the repository, execute `build_epf.ps1`, locate the correct collector version, understand the payload encoding, or keep the EPF between tasks.

## Integrity and staleness

The distributed EPF is derived from, but is not a substitute for, `COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/**`.

A material change to a declared build input invalidates the currently pinned binary. CI/maintenance validation must fail closed until a new EPF is built on the real 1C platform and accepted at the required proof boundary. Static CI may verify payload identity, reconstructed binary hashes and exact build-input Git blob identity; it may not claim a new EPF build/open/runtime proof by itself.

`TOOLS/materialize_project_snapshot_collector.py` is the repository-side integrity checker/materializer. The materializer verifies payload bindings before decoding and verifies the reconstructed binary before writing it.

## Evidence ownership after collection

Distribution integrity and returned-package evidence are separate proof layers. After the developer uploads `ProjectSnapshot.zip`, package/request/plan/configuration binding is owned by `TOOLS/validate_project_snapshot_package.py` and may be recorded as verifier-owned machine evidence through `TOOLS/machine_receipts.py` using property `EVIDENCE:PROJECT_SNAPSHOT_PACKAGE_BINDING`.

That machine property proves only the validator's binding scope. It does not prove `SOURCE_EXPORT` source content, business behavior, performance, concurrency, deployment state or any unrelated claim. Returned source bytes still require content inspection and exact item binding before they can close a source-dependent claim.

## Failure behavior

If the manifest is not `READY`, a payload part is missing or changed, reconstructed SHA/size/blob identity does not match, or a declared build-input Git blob drifted, chat must treat this as a **skill distribution defect**. Do not silently shift the maintenance burden to the ordinary developer by telling them to rebuild the collector.

A source-build fallback is appropriate only when:

- the conversation is explicitly maintaining/developing the Collector; or
- no distributable artifact exists and the user explicitly accepts that maintenance fallback.

## Version reuse

Within the same chat/project, once the exact collector artifact identity has been provided and remains current, delta CollectionPlans may reuse it. A new EPF need only be provided when the developer no longer has it, requests it again, or the distribution identity changed.
