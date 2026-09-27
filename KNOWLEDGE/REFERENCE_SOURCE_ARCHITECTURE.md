# Reference source architecture

Purpose: preserve source-first quality while allowing the universal skill to be distributed without embedded third-party, customer or vendor project source code.

## Four evidence roles

Do not collapse these roles:

```text
DISCOVERY_ONLY
→ knows likely source families, module/artifact names, intent terms and what to request
→ never proves API/signature/behavior/version

EXACT_TARGET_SOURCE
→ actual target/deployed/user-authorized source for the relevant version
→ primary evidence for declarations, metadata and implementation semantics

LOCAL_EXACT_SOURCE_INDEX
→ ephemeral index derived from EXACT_TARGET_SOURCE
→ may contain exact signatures/interface comments/hashes for the current task
→ must not be committed as reusable public reference data

SUPPORTING_REFERENCE
→ official docs/standards or supporting external repositories
→ authority depends on the owning source policy; never silently overrides target implementation evidence
```

A public discovery catalog is a **locator**, not a miniature copied API reference.

## Acquisition flow

For a non-trivial BSP / typical-1C / project-customization / vendor / Cleverence question (categories are distinct under `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`):

```text
task intent
→ search supplied target corpus first
→ use DISCOVERY_ONLY catalog to widen source discovery when needed
→ identify the smallest material artifact/dependency closure
→ acquire exact target/user-authorized source
→ fingerprint source
→ build LOCAL_EXACT_SOURCE_INDEX when useful
→ inspect exact declaration + nearby implementation/call site/module metadata as required
→ make only evidence-bounded claims
```

If the exact source needed for a material claim is unavailable, the claim remains `EVIDENCE_REQUIRED`; a locator hit is not enough for PASS.

## BSP rule

BSP remains a preferred implementation source for suitable 1C infrastructure/platform-adjacent mechanisms. Public distribution must not weaken BSP discovery.

The reusable core may retain:

- BSP mechanism/domain vocabulary;
- candidate common-module names;
- expected source path shapes;
- instructions describing which exact files to request;
- tooling that reconstructs exact exported declarations from supplied source.

The reusable core should not require embedded:

- complete BSP module source;
- copied public API signatures;
- copied interface comments/descriptions;
- source hashes tied to one BSP snapshot;
- a prebuilt index whose parser/provenance cannot be independently reproduced.

After a candidate BSP module is located, exact target/BSP source is required before using a method signature or claiming behavior. When client/server properties matter, request/read the relevant common-module metadata as well as `Module.bsl`. When side effects or intended usage remain unclear, inspect nearby implementation and real call sites.

## Prebuilt index rule

A derived reference index is not automatically trustworthy merely because it was once generated from trusted source.

Before treating any prebuilt index as authoritative, prove at least:

```text
source identity
+ reproducible generator/parser semantics
+ exact semantic parity against source for the property being claimed
```

Matching file hashes, module counts or row counts does **not** prove semantic correctness of the index.

If exact source contradicts a prebuilt index:

```text
exact source wins
→ index becomes STALE / LEGACY / NON_AUTHORITATIVE
→ fix the generator or rebuild locally
→ add a regression for the bypass that allowed the stale index to look valid
```

This rule exists because a historical BSP API index matched the retained BSP module hashes and per-module row counts while systematically replacing actual exported routines with internal non-export routines. Count parity alone would have produced a false confidence signal.

## Local exact BSL index

`TOOLS/build_local_bsl_reference_index.py` is intended for current-task evidence. It records source fingerprints and exact exported declarations obtained from the supplied files/ZIP. It may also retain the contiguous interface comment immediately above an exported declaration so useful BSP documentation is not lost when embedded snapshots are removed.

The generated JSON is ephemeral task evidence. Do not commit it into the universal shareable skill.

The export parser must bind `Экспорт` to the declaration itself. Finding the word later in a body/comment/string is not sufficient.

## Typical 1C and non-typical project/vendor analogs

Use the same evidence architecture for firm-1C release configurations and for project/vendor adaptations, but do not merge their terminology. Under `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`, project/vendor adaptations are «доработки» unless they themselves are part of the referenced official firm-1C release.

For reusable public knowledge, prefer:

```text
mechanism role
+ discovery vocabulary
+ likely object/module/artifact family
+ why it matters
+ minimal source closure to request
```

over copied implementation source.

A concrete customer/vendor module name may be retained only when it is genuinely product-level/public discovery vocabulary. Project-specific names such as a customer adaptation module should remain project context. The universal skill may know that such an adaptation layer can exist and must be searched before inventing a parallel mechanism, but it must not assume a module from another project exists in the current target.

## Cleverence

For Mobile SMARTS the same separation applies:

```text
stock mechanism/operation family locator
≠ exact MSLX execution graph
```

The public core may know which stock operation/document type/writer/router families are relevant and which export fragments to request. Exact transitions, implicit fall-through, writer identity, field names and runtime semantics must be proven from the actual target/stock export used by the project.

## Distribution rule

Shareable/public distributions may include `REFERENCE/CATALOGS/**` and the generic locator/local-index tooling. Raw third-party/project sources and detailed derived API indexes belong to internal/dev storage or user-supplied task evidence unless their redistribution is explicitly allowed and intentionally chosen.

Privacy is not the only reason for this boundary. Exact-source acquisition also prevents version drift and makes the evidence chain stronger.
