# Distribution and privacy policy

This repository has two different distribution roles. Do not treat them as interchangeable.

## INTERNAL_FULL

The internal development repository may contain:

- Git history and development provenance;
- optional private/reference corpora used for stronger evidence discovery;
- generated exact-source indexes;
- internal CI and maintenance material.

It remains private unless a separate history/licensing/privacy audit proves the entire repository safe to publish.

Sharing a private repository with a collaborator gives that collaborator repository access, including reachable Git history. Use this only when the recipient is allowed to see the internal development history and any retained private/reference material.

## SHAREABLE_CORE

`SHAREABLE_CORE` is the default artifact for giving the skill to another person or creating a public clean repository.

Build it with:

```text
python TOOLS/build_distribution_snapshot.py --output onec-cleverence-shareable.zip
```

The builder uses the active manifest as an allowlist input, then removes distribution-restricted surfaces and validates the exact selected files before creating the archive.

The shareable core excludes by default:

```text
ARCHIVE/**
REFERENCE/SOURCES/**
REFERENCE/INDEXES/**
MAINTENANCE/INTERNAL/**
manifest.txt
```

It may include reviewed public discovery metadata under:

```text
REFERENCE/CATALOGS/**
```

A public catalog is `DISCOVERY_ONLY`: it may contain mechanism names, intent/search terms, candidate module/object names and exact-file request hints. It must not be treated as proof of API signatures, source behavior, target-version availability or runtime semantics.

It may also include the bounded canonical example layer under:

```text
PATTERNS/**
```

Every distributed pattern is `ILLUSTRATIVE_PATTERN` with `evidence_role=NONE`, `copy_policy=ADAPT_ONLY`, `proves_api=false`, `proves_runtime=false` and `requires_exact_source=true`. Patterns exist to teach implementation shape to weaker/general LLMs after requirements/design are proven. They never replace target/user-authorized source for real names, signatures, fields, lifecycle order, vendor actions or runtime behavior.

`TESTS/fixtures/**` remains regression/analyzer input, including `*_good` files; it is never an implementation precedent.

The shareable artifact therefore separates three different roles:

```text
PATTERN
→ HOW a sound implementation shape may look
→ NOT evidence

DISCOVERY CATALOG
→ WHERE/WHAT to inspect
→ NOT proof

TARGET / AUTHORIZED EXACT SOURCE
→ HOW this concrete version actually behaves
→ evidence
```

It also blocks high-confidence privacy/secrets/path leaks in selected first-party text files.

## Data that must not enter a shareable artifact

Do not distribute:

- customer/client/project names or uniquely identifying project descriptions when they are not necessary to understand a universal rule;
- personal names, private e-mail addresses, phone numbers or other personal contact data copied from project evidence;
- local workstation/user paths;
- passwords, access tokens, private keys, connection strings or credentials;
- customer/project `PROJECT_CONTEXT`, working ledgers, review history or runtime logs;
- project snapshots, deployed baselines, compare exports, delivery packages or patches;
- environment fingerprints that reveal internal infrastructure;
- raw third-party/vendor/typical source or source-derived API/content indexes unless redistribution rights are explicitly verified for that material.

Reusable engineering knowledge should be transformed as follows:

```text
private/project evidence
→ prove technical finding
→ generalize the invariant
→ replace concrete identifiers with neutral placeholders
→ add rule/profile/regression coverage
→ optionally retain only a DISCOVERY_ONLY locator
→ optionally add a neutral ILLUSTRATIVE_PATTERN when implementation shape is genuinely reusable
→ distribute only generalized rules/locators/patterns that pass privacy/licensing review
```

## Reference architecture

The long-term public-ready reference architecture is:

```text
PUBLIC PATTERN LIBRARY
→ neutral good/bad implementation shapes
→ no concrete API/runtime proof

PUBLIC DISCOVERY CATALOG
→ mechanism/domain terms
→ likely module/object names
→ smallest exact files to request
→ NOT proof

USER/TARGET/AUTHORIZED SOURCE
→ supplied for the actual project/version
→ exact source evidence

LOCAL EXACT INDEX
→ generated ephemerally from supplied source
→ signatures/locations for analysis
→ not universal reusable source content
```

This preserves three different kinds of memory:

```text
universal skill remembers HOW a good shape looks
universal skill remembers WHERE/WHAT to inspect
project evidence proves EXACTLY HOW this version behaves
```

For BSP, the first public implementation is:

```text
REFERENCE/CATALOGS/bsp_discovery.json
TOOLS/reference_locator.py
TOOLS/build_local_bsl_reference_index.py
TOOLS/check_bsl_call_signatures.py
```

The internal BSP source/index remains available during migration and must not be removed until quality-equivalence regressions show that `SHAREABLE_CORE + exact supplied source` can recover the same required evidence.

## Reference packs

The internal skill can use private/reference packs to strengthen evidence discovery. They are not part of `SHAREABLE_CORE` by default.

A shareable installation uses this evidence hierarchy when an exact analog/API/source contract is needed:

```text
public pattern for shape (optional, never evidence)
→ public locator catalog
→ actual target source
→ user-provided/authorized reference source
→ official/platform/vendor documentation
→ explicitly licensed external source
→ EVIDENCE_REQUIRED when exact behavior is still unresolved
```

The pattern step improves implementation form; the locator step only reduces discovery cost. Neither outranks target source.

Missing private reference packs must never be replaced with guessed APIs or signatures.

## Project/vendor adaptation modules

A reusable skill may learn that a **class of project/vendor adaptation module** is important for a mechanism, but should not retain customer-specific source merely because it was useful in one project.

Preferred flow:

```text
mechanism class known
→ inspect target repository for the actual adapter/module
→ request exact module + caller/dependency closure when needed
→ analyze as PROJECT/TARGET evidence
→ promote only generalized invariant or safe locator metadata
```

A concrete module name may be retained in universal public metadata only when it is intentionally a reusable product/standard locator and has passed privacy/licensing review. Otherwise keep the category generic and acquire the name from the target project.

## Third-party material

Third-party content is distributable only when its redistribution license/notice is explicit and retained. The MIT attribution under `THIRD_PARTY/cc-1c-skills/` is intentionally kept with the shareable core.

Raw BSP/typical/Cleverence reference packs and their source-derived detailed indexes are excluded from the public/shareable core until their redistribution status is independently established.

## Git history warning

Deleting or anonymizing a file in the current tree does not remove it from previous commits.

For public publication, the required history mode is `CLEAN_SNAPSHOT_ONLY`:

```text
INTERNAL_FULL private repository
→ build deterministic SHAREABLE_CORE
→ validate exact manifest/file hashes and privacy
→ satisfy the private publication-readiness gate
→ extract into a new empty working directory
→ verify that no .git directory or private history is present
→ recheck the pinned public bootstrap identity immediately before publication
→ create a publication branch descending from bootstrap commit 4d8e1738188f0dc2b41a01a7d52dd1a224451f43
→ commit only the validated SHAREABLE_CORE snapshot on that branch
→ publish through a PR into the existing alexleb-dotcom/onec-cleverence-public repository
```

Do not use `git push --mirror`, copy the private `.git` directory, preserve private commits through subtree/filter tricks, or otherwise transfer internal history merely to create the public CI mirror. A history rewrite of the internal repository is a separate destructive operation and is not the publication path.

## Confirmed owner decisions

The publication decisions below are owner-confirmed and `DECIDED`. Tooling must not reopen them, infer alternatives, or present them as unresolved unless the owner explicitly changes the policy.

| Decision | Status | Confirmed value |
| --- | --- | --- |
| Public repository | `DECIDED` | `onec-cleverence-public` |
| Root rights notice | `DECIDED` | `ALL_RIGHTS_RESERVED_NOTICE` via `RIGHTS_NOTICE.md`; rights holder `alexleb-dotcom` |
| ProjectSnapshotCollector public surface | `DECIDED` | `EXCLUDE_COLLECTOR` |

These decisions authorize only the publication shape. They do not by themselves assert that the current candidate passed privacy, CI, runtime, project, or legal/redistribution acceptance.

## Publication runtime identity and CI

A shareable snapshot must not keep the private maintenance repository as its canonical freshness target. The public repository already exists as the verified one-commit README-only bootstrap `alexleb-dotcom/onec-cleverence-public`. Before any future snapshot publication, recheck that `main` still matches the pinned bootstrap identity, then publish the validated SHAREABLE_CORE only through a branch/PR descending from that bootstrap. A ZIP with no canonical remote reports freshness as `UNVERIFIED` until a tracked repository/ref is established.

The public `DISTRIBUTION_MANIFEST.json` intentionally does **not** publish the private source commit or the names of excluded internal files. Exact private-candidate ↔ public-snapshot binding belongs to a private publication/acceptance receipt, not to the public tree.

CI is split by trust boundary:

```text
.github/workflows/internal-distribution-equivalence.yml
→ INTERNAL_FULL only
→ may consume retained private reference/internal acceptance inputs
→ excluded from SHAREABLE_CORE

.github/workflows/shareable-validation.yml
→ distributed public workflow
→ builds/uses only the exact SHAREABLE_CORE tree
→ exposes separate Public Fast and Public Full checks
→ uses read-only permissions and immutable action SHAs
→ must pass without private reference/index/maintenance paths
→ proves only the public SHAREABLE_CORE tree, never private authoritative/runtime acceptance
```

Do not publish an internal comparative workflow and then rely on missing private files being supplied later. The distributed workflow itself is part of the public artifact contract.

## Capability matrix

| Capability | `INTERNAL_FULL` | `SHAREABLE_CORE` |
| --- | --- | --- |
| Canonical repository role | Private canonical development repository with internal history | Clean public/shareable snapshot only; never a copy of private Git history |
| ProjectSnapshotCollector source/payload | Present and subject to private integrity/source/runtime/package regressions | Excluded by confirmed `EXCLUDE_COLLECTOR` policy |
| Automatic ProjectSnapshot EPF delivery | Available only when the repository-pinned Collector is present and integrity-verifiable | Unavailable; report that the public distribution does not include Collector, keep the evidence gap unresolved, and request only the smallest bounded manual evidence |
| Private reference/source packs | May be present for stronger internal equivalence/acceptance checks | Excluded; public catalogs remain discovery-only and cannot replace exact evidence |
| Public static CI | Executes the same canonical public-safe inventory as the exact public prefix of private Full | Public Fast = bounded prefix; Public Full = complete public-safe inventory |
| Project/runtime proof | Requires actual target/runtime evidence; static CI alone is not project acceptance | Same evidence requirement; missing Collector or private packs never converts an unresolved project/runtime claim into PASS |
| Third-party terms | Internal material may have separate authorization constraints | Only explicitly reviewed distributable third-party material is shipped with its own retained license/notice |
| Publication history | Existing private history remains private and canonical | `CLEAN_SNAPSHOT_ONLY`: verified one-commit README-only public bootstrap already exists; future validated snapshot is appended through a branch/PR descending from that bootstrap, never by importing private history |

When `SHAREABLE_CORE` resolves `COLLECTOR_UNAVAILABLE`, the assistant must state the capability limitation to the user, must not fabricate `ProjectSnapshotCollector.epf` or evidence, and must not weaken any project/runtime evidence requirement. The fallback is acquisition-only: it changes how missing evidence is requested, not what is considered proven.

## Release gate

A release intended for people outside the trusted internal group is not share-ready until:

```text
TOOLS/validate_distribution_privacy.py
+ TOOLS/validate_distribution_snapshot.py --root <extracted-shareable-root>
+ TOOLS/run_public_ci.py --mode FAST
+ TOOLS/run_public_ci.py --mode FULL
+ TOOLS/validate_patterns.py
+ TESTS/run_distribution_privacy_regression.py
+ TESTS/run_public_ci_regression.py
+ TESTS/run_pattern_regression.py
+ TESTS/run_reference_discovery_regression.py
+ deterministic SHAREABLE_CORE archive inspection
+ private-side publication-readiness approval for owner decisions and CLEAN_SNAPSHOT_ONLY history
```

all pass.

Before removing an internal reference dependency, additionally require an explicit quality-equivalence test proving that the public locator + exact supplied source reconstructs the evidence needed by representative tasks.
