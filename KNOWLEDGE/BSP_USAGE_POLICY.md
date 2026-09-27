# BSP USAGE POLICY — reuse before custom infrastructure

## Purpose

For non-trivial 1C development, reuse of the public API of the Библиотека стандартных подсистем (БСП) is mandatory when the target configuration contains a suitable supported mechanism.

The goal is not "call BSP everywhere". The goal is:

```text
business requirement
→ discover likely BSP mechanism/module
→ acquire exact target/BSP source
→ verify public API and contract
→ reuse it when semantically suitable
→ custom implementation only when no suitable supported mechanism exists
```

A custom helper that duplicates a suitable BSP public API without a documented reason is a review finding.

## 1. Discovery gate

Before implementing generic infrastructure or platform-adjacent behavior, search the strongest authorized evidence available for the current task:

```text
actual target configuration/BSP source
→ authorized private/internal BSP reference pack when available
→ official documentation / current supported source
→ explicitly licensed supporting reference
→ EVIDENCE_REQUIRED when the exact contract remains unresolved
```

Discovery and proof are intentionally separate.

The shareable skill contains `REFERENCE/CATALOGS/bsp_discovery.json`. It stores only reusable **locator hints** such as intent terms and candidate common-module names. It does not contain exported API signatures/source bodies and cannot prove that an API exists in the user's BSP version.

Use:

```text
python TOOLS/reference_locator.py --query "<business/technical intent>"
```

A locator match means:

```text
candidate module identified
→ check whether target configuration contains it
→ request/read exact CommonModules/<Module>/Ext/Module.bsl
→ verify exact API/metadata/call site
```

It does **not** mean:

```text
candidate module identified
→ remembered method/signature is safe to call
```

The internal development repository may additionally contain compact indexes and exact source snapshots for faster evidence discovery. They are optional private reference packs, not a dependency that must be redistributed with `SHAREABLE_CORE`.

When an internal reference pack is present, examples include:

- `REFERENCE/INDEXES/bsp_public_api.csv` — historical derived API cache retained only for migration forensics; it is not an API oracle;
- `REFERENCE/INDEXES/bsp_module_catalog.csv` — private/generated module inventory and source-fingerprint evidence for the retained snapshot;
- `REFERENCE/SOURCES/BSP_COMMON_MODULES.zip` — exact source snapshot for selected modules.

These internal artifacts may accelerate discovery or regression diagnostics, but exact source is authoritative even for the same snapshot. A 2026-09-01 parity audit proved why: the historical API CSV had the correct module hashes and row counts yet substituted 180 non-export routines for 180 actual exports. Therefore source identity/count parity alone never proves derived-index semantics.

Search by **intent and domain terms**, not only by an already guessed procedure name.

Examples of domains that require a BSP search before custom code:

```text
managed-form / DynamicList setup
user messages and exceptions
client/server helper placement
long operations / background execution
files and temporary directories
attached files
users
connected commands
printing
additional reports/processings
report variants
properties / additional attributes
scheduled jobs
registration log
configuration update handlers
safe mode
access control
server notifications
internet file acquisition
external components
object filling/versioning
data exchange infrastructure
full-text search
```

The public locator is intentionally bounded rather than speculative. It currently preserves the known candidate-module vocabulary from the retained reference snapshot, but it is not a claim that every BSP version has exactly that set or that all BSP domains are represented. If a domain is not mapped, search the target configuration/BSP source and promote only a reusable locator after independent validation.

## 2. Source acquisition and local exact index

When the locator identifies likely modules, request the **smallest sufficient exact source** from the target project. Prefer individual common modules over asking for the entire BSP/configuration when they are enough.

Typical request shape:

```text
Please provide these exact files from the target configuration export:
- CommonModules/<CandidateModule>/Ext/Module.bsl
- module metadata/XML as well if client/server flags cannot be proven from available source
- one real target call site when usage semantics remain ambiguous
```

After the source is supplied, an exact local exported-BSL index can be generated without committing it to the universal skill:

```text
python TOOLS/build_local_bsl_reference_index.py \
  --source-file CommonModules/<Module>/Ext/Module.bsl \
  --output local-bsp-index.json
```

or from an authorized ZIP:

```text
python TOOLS/build_local_bsl_reference_index.py \
  --source-zip <authorized-source.zip> \
  --output local-bsp-index.json
```

The generated index is **project evidence**. Keep it with the task/project evidence if needed; do not promote exact signatures/source-derived summaries into the universal shareable catalog.

## 3. Source-of-truth and signature rule

Never guess a BSP signature from memory or from the public locator.

For a candidate API:
1. locate the likely module by target search/public locator/private authorized index;
2. open the exact declaration in the target/authorized source;
3. read its documentation comment, client/server flags from module metadata, side effects, return contract and nearby usage constraints;
4. inspect a target-configuration call site when behavior is still ambiguous;
5. only then use it.

An embedded/private BSP corpus is exact only for the source from which it was extracted. For another configuration/build it is a strong analog, not proof; verify exact source when a version difference could change correctness.

## 3A. Uncertainty escalation — analog before invention

Also read `KNOWLEDGE/TYPICAL_CODE_DISCOVERY.md` and `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md` for target / typical-1C / customization / vendor analog discovery. These provenance categories are not synonyms.

If the implementation or platform contract is not known exactly, **do not write the custom helper first**. Search for evidence before design:

```text
target configuration exact implementation
→ same/nearest authorized firm-1C release pattern
→ BSP public API + exact source + real call site
→ vendor/Cleverence stock pattern when relevant
→ official documentation / standards / examples
→ custom implementation only after the above are exhausted
```

The analog must match the mechanism, not just share a procedure name. Inspect how it is called, where it runs, which object it receives, what it returns/changes, and how the proven firm-1C release code preserves query/form/transaction semantics.

If no convincing analog exists, record `EVIDENCE_REQUIRED` or `BSP_EXCEPTION_JUSTIFIED`; do not convert uncertainty into guessed code.

## 3B. Call-signature gate

Every changed qualified cross-module call must be verified against the actual declaration available in the target/BSP/vendor source. At minimum verify:

```text
module and exported method really exist
required/optional parameter count
parameter order and semantic meaning
client/server availability
return value / mutation contract
```

A call with the wrong argument count or order is `CALL_SIGNATURE_MISMATCH` and blocks delivery. A remembered signature is not evidence.

Run `TOOLS/check_bsl_call_signatures.py` directly against the exact source supplied for the task, for example:

```text
python TOOLS/check_bsl_call_signatures.py \
  --definitions-file CommonModules/<Module>/Ext/Module.bsl \
  --focus <changed-module.bsl>
```

The static checker only validates contracts for definitions actually supplied. Unknown modules remain unresolved; they are never guessed.

## 4. Preference rule

When a suitable public BSP API exists, prefer it over:
- copying internal BSP code;
- calling `Служебный` modules directly;
- custom implementations of the same infrastructure concern;
- lower-level platform composition when BSP intentionally provides the configuration contract.

Exceptions require a concrete reason, for example:
- the target configuration does not include the subsystem/API;
- the API cannot satisfy the business invariant;
- the API introduces unacceptable side effects;
- official/current platform guidance explicitly replaces the BSP helper;
- target runtime/version contract differs.

Record an exception as evidence, not as a silent choice.

## 5. Public vs internal API

Default to modules/regions that expose `#Область ПрограммныйИнтерфейс` and exported procedures/functions.

Do not treat `Служебный`, internal implementation regions, generated handlers, or project adapters as a stable public contract merely because the procedure is technically callable.

Application/vendor/project adaptation modules may be essential evidence for a concrete project, but they are **target-specific evidence**, not universal skill content. The universal skill should know the mechanism class and request the actual module when it exists in the target project rather than storing that module's source.

`ИнтеграцияПодсистемБСП*` in an application configuration may contain project/application adaptation logic. It is not a universal replacement for the core BSP API.

## 6. Client/server and performance

BSP reuse does not remove architecture review.

For every chosen API still check:
- execution context;
- implicit server call;
- parameter serialization/traffic;
- DB/API I/O performed transitively;
- transaction interaction;
- idempotency/retry;
- side effects;
- use inside loops.

A "standard helper" can still be too expensive in a hot loop. Reuse correctness and performance evidence are separate gates.

## 7. Review statuses

Every non-trivial 1C change receives one BSP-discovery status:

```text
BSP_REUSED
BSP_NOT_APPLICABLE + searched domains/modules and reason
BSP_EXCEPTION_JUSTIFIED + exact reason
BSP_EVIDENCE_REQUIRED
BSP_REUSE_MISSED
```

`BSP_REUSE_MISSED` is blocking when the custom implementation duplicates a suitable supported BSP mechanism and there is no material reason not to use it.

## 8. Reference architecture and distribution

Also read `KNOWLEDGE/REFERENCE_SOURCE_ARCHITECTURE.md` for the common DISCOVERY_ONLY → EXACT_TARGET_SOURCE → LOCAL_EXACT_SOURCE_INDEX evidence model used beyond BSP.

The intended long-term architecture is:

```text
SHAREABLE_CORE
  REFERENCE/CATALOGS/**        locator-only, safe to distribute after review
  TOOLS/reference_locator.py
  TOOLS/build_local_bsl_reference_index.py
  TOOLS/check_bsl_call_signatures.py

OPTIONAL AUTHORIZED REFERENCE PACK
  raw target/BSP/typical/vendor source
  generated exact indexes
  project-local evidence only
```

The public locator preserves **discovery memory**; the user/target source restores **exact proof**.

This separation should improve version correctness rather than reduce it:

```text
old embedded snapshot
→ fast discovery, but may be a different BSP version

public locator + exact target source
→ fast-enough discovery + proof from the actual version in scope
```

Private/raw reference unavailable never means API may be guessed. It means request the smallest exact target source or keep `EVIDENCE_REQUIRED`.
