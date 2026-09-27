# PROFILE — BSP_REUSE

## Detection

Mandatory for every non-trivial 1C change that implements infrastructure, platform-adjacent behavior, managed-form behavior, files, users, printing, long operations, background work, properties, dynamic lists, messages/errors, external resources, update logic, exchange infrastructure, or a helper that could plausibly exist in БСП.

## Triggered standards / contracts

- `std467` — prefer standard mechanisms and avoid unnecessary custom mechanisms where applicable.
- `KNOWLEDGE/BSP_USAGE_POLICY.md`
- `KNOWLEDGE/REFERENCE_SOURCE_ARCHITECTURE.md`
- exact exported API contract from target/user-authorized source.

## Mandatory checks

- search the supplied target/configuration corpus first;
- search `REFERENCE/CATALOGS/bsp_discovery.json` by intent/domain when the target search does not already identify the mechanism;
- treat the catalog as `DISCOVERY_ONLY`: candidate module names do not prove API existence, signature, execution context, side effects or target-version compatibility;
- request/read the smallest sufficient exact source, normally `CommonModules/<Module>/Ext/Module.bsl`; add common-module metadata when client/server properties matter and a real call site when usage semantics remain ambiguous;
- build `TOOLS/build_local_bsl_reference_index.py` from that exact source when an index is useful; keep it as ephemeral project/task evidence rather than universal reference content;
- do not use `REFERENCE/INDEXES/bsp_public_api.csv` or another prebuilt derived index as an API oracle; exact source and a reproducible local index win on contradiction;
- do not guess signatures from memory;
- prefer supported public interface over `Служебный`/internal code;
- check client/server context, serialization, transitive I/O, side effects and loop/hot-path cost;
- if BSP is not used, record `BSP_NOT_APPLICABLE` or a justified exception with evidence;
- custom duplication of a suitable supported BSP API is `BSP_REUSE_MISSED`.

## Completion rule

A non-trivial 1C change cannot be review-complete without an explicit BSP-discovery result.

A locator hit alone cannot close the rule. If a material API/behavior claim depends on source that is not supplied, request the exact module/dependency closure and keep it `BSP_EVIDENCE_REQUIRED` / `EVIDENCE_REQUIRED` rather than converting the locator or a historical index into proof.

`BSP_NOT_APPLICABLE` may be short when the changed mechanism is outside plausible BSP domains, but it must still record the searched intent/domain and available target evidence.
