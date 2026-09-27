# ProjectSnapshot collector architecture

## Purpose

The collector is a replaceable acquisition layer between `PROJECT_SNAPSHOT_REQUEST.json` and evidence used by the skill. Its job is not to claim complete knowledge of a customer configuration. Its job is to acquire the strongest supported evidence available at the customer site, report unsupported evidence honestly, bind the returned package to the active request/baseline, and leave unresolved proof dependencies explicit.

The durable flow is:

```text
ProjectSnapshotRequest
→ collection planner
→ ProjectSnapshotCollector/backends
→ ProjectSnapshot.zip
→ package validation
→ source-content inspection where required
→ bound item-level evidence
→ original task resumes
```

Executable pieces:

- `TOOLS/plan_project_snapshot_collection.py` — creates the exact item-by-item CollectionPlan;
- `COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/**` — source of portable `ProjectSnapshotCollector.epf`;
- `TOOLS/validate_project_snapshot_package.py` — validates a returned ZIP before chat/analysis uses it.

For exact states/transitions and responsibility keys, use canonical `WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json`; `KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md` is its human-facing guide.

## Evidence backends

### SOURCE_EXPORT

Use an already exported configuration/extension source tree or a supported Designer export. This is the preferred backend for exact module/source evidence when it is available.

The current one-click EPF performs a **bounded metadata-owner source export** for CollectionPlan rows assigned to `SOURCE_EXPORT`. It maps requested logical targets to metadata owners and launches Designer with the standard read-only dump mechanism:

```text
/DumpConfigToFiles <temporary-source-dir> -listFile <source-objects.txt> -Format Hierarchical
```

The list contains only requested metadata owners. Designer may still export sibling metadata/modules owned by those objects; therefore successful export means source bytes are available for inspection, not that every requested source claim is already proven.

Current `SOURCE_EXPORT_V1` logical target shapes supported by the one-click collector are bounded module-source targets such as:

- `COMMON_MODULE.<name>`;
- `DOCUMENT.<name>.ObjectModule`;
- `DOCUMENT.<name>.ManagerModule`;
- `CATALOG.<name>.ObjectModule`;
- `CATALOG.<name>.ManagerModule`.

Unsupported source-target shapes must remain unsupported rather than being approximated by another module.

The collector must never use configuration load/update commands as acquisition mechanisms.

References:
- https://1c-dn.com/1c_enterprise/dumping_and_restoring_configuration_files/
- https://1c-dn.com/library/v8update_2079252606_new_functionality_and_changes/
- https://1c-dn.com/library/v8update_2569827938_new_functionality_and_changes/

### CONFIGURATOR_ASSISTED

Use supported Designer/Configurator facilities to create source evidence on demand, then select only the requested dependency closure. This generic backend remains useful when a different helper/orchestrator is used instead of the current EPF path.

The contract does not require unrestricted full export. If tooling can reliably export a smaller requested closure, that is preferred.

### RUNTIME_METADATA

Use the external processing in 1C:Enterprise mode to capture evidence exposed by supported runtime APIs and metadata objects.

The current runtime collector v1 implements:

- `METADATA_PROPERTIES` — bounded structural metadata projection;
- `SCHEDULED_JOBS` — configuration-level scheduled-job metadata.

Both are intentionally bounded and may be `PARTIAL`. Runtime observations can prove exact named runtime facts at their observed fidelity, but they are not automatically equivalent to design-time source.

Examples of evidence boundaries:

- runtime metadata is not module source text;
- effective access for the current runtime context is not a complete role/RLS source definition;
- observable form/command surface is not proof of every design-time handler binding;
- scheduled-job metadata is distinct from handler source, execution history and server scheduler state.

The runtime collector emits `SKIPPED_OTHER_BACKEND` for plan rows owned by another backend rather than pretending they were runtime-observed.

References:
- https://1c-dn.com/1c_enterprise/access_rights/
- https://v8.1c.ru/platforma/reglamentnoe-zadanie/
- https://v8.1c.ru/platforma/podpiska-na-sobytie/
- https://1c-dn.com/1c_enterprise/configuration_objects/

### MANUAL_ATTACHMENTS

Use exact artifacts supplied by the user only for evidence that cannot be acquired automatically in the current contour. Manual evidence is a normal fallback, not a reason to weaken provenance requirements.

### HYBRID

`HYBRID` is an orchestration result rather than an independent evidence source. The planner emits it when the accepted request requires more than one direct backend. The current one-click package can combine runtime evidence and bounded source export in one ZIP.

## Capability matrix semantics

`KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_CAPABILITIES.json` is the machine-readable generic capability contract. `KNOWLEDGE/PROJECT_SNAPSHOT_RUNTIME_V1_CAPABILITIES.json` narrows what runtime collector v1 actually implements.

Each evidence category/backend pair has one state:

- `FULL` — backend can produce the evidence class at full fidelity, subject to the concrete artifact being present and inspected;
- `PARTIAL` — backend provides useful evidence but cannot close the full claim by itself;
- `UNSUPPORTED` — backend must not claim the evidence class.

These are capability/fidelity bounds, not blanket proof claims.

## Planner behavior

`TOOLS/plan_project_snapshot_collection.py`:

1. validates request schema and evidence categories;
2. intersects request-allowed backends with backends actually available in the customer contour;
3. chooses the strongest acceptable backend per item, preferring required fidelity before convenience;
4. emits `READY`, `PARTIAL` or `UNSUPPORTED` per requested item;
5. carries `baseline_expectation` from the originating request;
6. emits exact remaining gaps/limitations;
7. reports collection mode (`SOURCE_EXPORT`, `CONFIGURATOR_ASSISTED`, `RUNTIME_METADATA`, `MANUAL_ATTACHMENTS`, `HYBRID` or `NONE`);
8. never upgrades partial runtime visibility into unavailable source evidence.

A valid plan may still be `PARTIAL` or `BLOCKED`; planning itself succeeded. `--strict` converts unresolved required evidence into a non-zero process exit for hard-gated automation.

## Current portable external processing

`ProjectSnapshotCollector.epf` is built from `COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/**` and consumes the exact generated CollectionPlan.

Normal desktop workflow:

1. load CollectionPlan;
2. press **Собрать пакет**;
3. collect runtime rows read-only;
4. perform requested bounded `SOURCE_EXPORT` when applicable;
5. write one `ProjectSnapshot.zip` for return to chat.

The package contains, as applicable:

```text
collection-plan.json
runtime-evidence.json
manifest.json
source-objects.txt
designer.log
source/
  ...
```

A source-export failure does not discard valid runtime evidence and does not invent source evidence. The package retains diagnostics so the chat can explain the concrete failure.

Designer credentials, when required, are local execution inputs. They are not part of ProjectSnapshotRequest/CollectionPlan evidence and must not intentionally be persisted in the evidence package.

The current one-click source-export path targets managed desktop/thin-client use. Web-client source-export acceptance is not claimed.

## Package binding before evidence use

**Package produced != evidence accepted.**

Before the skill uses a returned ZIP, run:

```text
TOOLS/validate_project_snapshot_package.py ProjectSnapshot.zip --expected-request-id <active-request-id>
```

The validator checks, among other things:

- package schemas/kind;
- `request_id` consistency across plan/manifest/runtime evidence;
- known configuration name/version against `baseline_expectation`;
- collector identity and `read_only=true`;
- exact runtime item ID/category/logical-target binding;
- runtime summary consistency;
- other-backend rows remain `SKIPPED_OTHER_BACKEND`;
- SOURCE_EXPORT manifest rows match exact plan rows;
- successful source-export status is accompanied by actual `source/` content;
- unsafe/duplicate package paths are rejected.

A stale, mismatched or cross-database package is rejected rather than reused by similarity.

## Runtime proof boundary

There are two different questions that must not be collapsed:

1. **Is this collector implementation runtime-accepted for a capability/path?**
2. **Did this concrete run return a bound observation for this concrete plan item?**

`collector.runtime_proven` answers the first question for the runtime-metadata implementation. It is not a global allow/deny switch for every returned observation.

A correctly bound `PARTIAL`/`COLLECTED` runtime row may support the exact matching item at its observed fidelity even when `collector.runtime_proven=false`. Conversely, a future `runtime_proven=true` must never promote another item, source bytes, deployment state or unexecuted business behavior.

`ERROR`, `UNSUPPORTED*`, missing rows and mismatched rows remain unresolved.

## Source proof boundary

A successful `SOURCE_EXPORT` manifest proves that bounded source acquisition completed and source bytes are available. It does **not** by itself prove the requested module content.

The chat must:

1. locate the packaged source file associated with the exact requested item;
2. confirm it exists/non-empty;
3. inspect the concrete returned bytes/text;
4. bind them to the requested logical target;
5. only then close the source-dependent claim.

`ConfigDumpInfo.xml` is diagnostic, not a source-proof prerequisite. Concrete requested module files are the evidence objects.

## Acceptance status

### EPF build/open and runtime-metadata smoke

The EPF source was built and opened successfully on 1C platform `8.3.27.1688`. Runtime smoke covered configuration identity, supported metadata target kinds, missing-target error isolation, `SKIPPED_OTHER_BACKEND`, scheduled-job metadata and saving/reopening runtime JSON without truncation.

The separate runtime-metadata implementation marker remains intentionally bounded by `KNOWLEDGE/PROJECT_SNAPSHOT_RUNTIME_V1_CAPABILITIES.json`; SOURCE_EXPORT acceptance does not silently rewrite that flag.

### SOURCE_EXPORT_V1 accepted desktop path

A real end-to-end package was accepted on:

```text
1C platform:     8.3.27.1688
configuration:   УправлениеТорговлей 11.5.27.81
request_id:      acceptance-ut-11-5-27-81-source-export-20260916-03
package SHA-256: d59bdd67d51823dfa661f40cc7059dd2af790330dd0e61da0bbed062b3f885c6
```

Observed acceptance facts:

- `source_export.status = COLLECTED_MODULE_FILES`;
- Designer exit code `0`;
- `unresolved_items = []`;
- exact expected/found module paths matched;
- returned source files were non-empty and inspected against the requested logical targets;
- `DOCUMENT.ЧекККМ.ObjectModule` returned `Documents/ЧекККМ/Ext/ObjectModule.bsl`;
- `COMMON_MODULE.CRMЛокализация` returned `CommonModules/CRMЛокализация/Ext/Module.bsl`;
- absence of `ConfigDumpInfo.xml` did not prevent concrete module-file proof.

This proves the tested `SOURCE_EXPORT_V1` desktop path and supported target shapes. It does **not** claim web-client acceptance, every metadata/source kind, every authentication model, or universal runtime/deployment behavior.

## Chat integration status

ProjectSnapshot is integrated as the standard supported adapter for missing current-1C evidence through:

```text
SKILL.md evidence-gap stage
→ KNOWLEDGE/EVIDENCE_ACQUISITION.md
→ KNOWLEDGE/PROJECT_SNAPSHOT_CHAT_WORKFLOW.md
→ PROJECT_SNAPSHOT_REQUEST / collection planner
→ ProjectSnapshotCollector.epf
→ validate_project_snapshot_package.py
→ item-level evidence binding
→ original task continuation
```

The user-facing loop should remain compact. The complexity belongs to the skill/chat, not to the developer operating the collector.

## Durable interface

Collector implementation details may evolve. The durable contract is:

```text
ProjectSnapshotRequest
→ CollectionPlan
→ returned package
→ package binding
→ item-level evidence/content inspection
→ original task continuation
```

Changing the collector must not weaken request identity, baseline identity, backend provenance, item-level fidelity, archive safety, source-content inspection or unresolved-evidence semantics.
