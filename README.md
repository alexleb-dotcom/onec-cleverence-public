# 1C + Cleverence Developer Skill

Requirements-first, evidence-first skill for 1C:Enterprise and Cleverence Mobile SMARTS.

For a new LLM/chat opened from only this repository URL, start with `README_FIRST.md`. This repository is the universal skill, not the target project or deployed baseline. Read `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md` before classifying 1C source as «типовой» or «доработка».

## Sharing and distribution

The internal development repository and the shareable skill artifact are intentionally different surfaces:

```text
INTERNAL_FULL
→ private development repository, Git history and optional authorized reference packs

SHAREABLE_CORE
→ sanitized snapshot without Git history, project archives or raw/derived private vendor/reference corpora
```

To give the skill to another person or seed a clean public repository, prefer:

```text
python TOOLS/build_distribution_snapshot.py --output onec-cleverence-shareable.zip
```

Read `DISTRIBUTION.md`. Do not infer that a clean current tree makes the existing Git history public-safe. Missing private reference packs in `SHAREABLE_CORE` do not relax evidence requirements: inspect actual target/authorized source or keep the claim `EVIDENCE_REQUIRED` rather than guessing API/signature/runtime behavior.

The distributed `.github/workflows/shareable-validation.yml` is self-contained: in the private maintenance repository it rebuilds and validates the exact snapshot, while in a clean public repository it validates that repository directly. Private cross-profile equivalence remains in an internal-only workflow and is not shipped.

## New project / empty chat bootstrap

A newly connected repository or uploaded corpus is evidence, not yet a complete project context. Do not jump directly to implementation.

For a new project first run source-first discovery:

```text
python TOOLS/artifact_corpus.py <repository-or-artifact-paths>
python TOOLS/build_project_bootstrap.py <repository-or-artifact-paths> --output project-bootstrap.json
```

Then inspect the actual source, classify 1C provenance using `KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md`, resolve the project contracts that can be proven from it, and ask only the remaining material questions/artifacts. Read `KNOWLEDGE/PROJECT_BOOTSTRAP.md` and persist durable facts in `PROJECT_CONTEXT` using `TEMPLATES/PROJECT_CONTEXT_TEMPLATE.md`.

The intended startup loop is:

```text
INVENTORY AVAILABLE INPUT
→ DISCOVER PROJECT FACTS
→ REQUEST ONLY MATERIAL PROJECT GAPS
→ PERSIST PROJECT_CONTEXT
→ BUILD TASK REQUIREMENTS
→ ANALYZE TASK SOURCE
→ REQUEST SMALLEST MISSING DEPENDENCY CLOSURE
→ IMPLEMENT
→ VALIDATE / RUNTIME
→ UPDATE PROJECT OR UNIVERSAL KNOWLEDGE
```

Project bootstrap and task requirements are separate. `PROJECT_CONTEXT` answers how this project may be developed, attributed and delivered; the requirements contract answers what the current task must accomplish.

Open project-policy fields do not stop unaffected analysis. They block only the actions they control. For example, unresolved `AUTHOR_MARKER` may allow source analysis but blocks final changed code; unresolved deployed baseline/delivery shape blocks exact compare/full delivery.

Core execution flow for non-trivial change work after project bootstrap:

```text
python TOOLS/build_requirements_contract.py <requirement/context> --task-text "..." --output requirements-contract.json
# fill only from actual evidence; if a concrete missing file can resolve a material gap, request the smallest sufficient artifact instead of guessing
python TOOLS/requirements_gate.py requirements-contract.json
python TOOLS/build_review_plan.py <candidate> --requirements-contract requirements-contract.json --output review-plan.json
python TOOLS/build_validation_ledger.py --plan review-plan.json --output validation-ledger.json
# fill evidence/dispositions, including independent gap_discovery lenses/hypotheses
python TOOLS/release_gate.py --plan review-plan.json --ledger validation-ledger.json
```

R0-local work may use a compact contract. R1/R2/R3 progressively require source-of-truth/invariants, lifecycle/state/error semantics and the full cross-system functional contract.

For skill maintenance:

```text
python TOOLS/generate_registry_views.py --check
python TESTS/run_cold_start_regression.py
python TESTS/run_distribution_privacy_regression.py
python TESTS/run_llm_bypass_regression.py
python TESTS/run_artifact_bootstrap_regression.py
python TESTS/run_external_source_regression.py
python TESTS/run_review_regression.py
python TOOLS/validate_skill.py
```

For an external/shareable release, additionally build and inspect the exact `SHAREABLE_CORE` artifact:

```text
python TOOLS/validate_distribution_privacy.py
python TOOLS/build_distribution_snapshot.py --output onec-cleverence-shareable.zip
# from the extracted snapshot/repository:
python TOOLS/validate_distribution_profile.py --profile SHAREABLE_CORE
```

`RULES/rule_registry.json` is the only executable registry for requirements and technical rules. `ARCHIVE/**` is not part of normal bootstrap or shareable distribution; project-specific historical evidence belongs outside the shareable repository tree.

## Stable result delivery

For non-trivial work, final user-facing output is governed by `WORKFLOW/RESULT_DELIVERY_CONTRACT.json`; read `KNOWLEDGE/RESULT_DELIVERY.md` for the compact human-facing rules. The result shape is stable across analysis, implementation and blocked/partial work, while readiness wording remains bound to the existing requirements/release/evidence gates.

The contract intentionally omits empty sections and does not turn short technical answers into formal reports.

## Artifact intake

`TOOLS/artifact_corpus.py` separates **physical inventory** from **analyzable content**. Physical inventory sees nested containers, runtime files and other non-source artifacts before any source-code suffix filtering. Analyzers consume only the normalized analyzable corpus.

Known delivery wrappers may normalize to a semantic path without erasing physical provenance, for example:

```text
Configuration/Operations/X.mslx
Documents.zip!/Operations/X.mslx
Operations/X.mslx

→ semantic mechanism path: Operations/X.mslx
```

Semantic path is for mechanism routing. Physical/container path remains authoritative for baseline identity and delivery reconstruction. `UNKNOWN` or `MIXED_ARTIFACT` classification must never be silently treated as an exact configuration delivery baseline. Distinct physical inputs with the same basename must remain distinct corpus entries; semantic normalization may never collapse evidence obligations.

## Proof integrity

The generated requirements/validation ledgers are fail-closed proof structures, not editable PASS summaries. Required rows may not be deleted, duplicated or relabeled `NOT_APPLICABLE` to obtain readiness; core need/outcome/behavior/acceptance fields are non-optional. The exact task text and source identities remain attached to the requirements proof, and a narrower requirements surface/risk cannot authorize a wider technical plan. Technical `PROVEN` requires independently completed `CODE_TO_STANDARDS` and registry-expanded `STANDARDS_TO_CODE`, concrete `{kind, ref}` evidence, named PASS machine/runtime evidence links, and no blocking finding. A source-bearing 1C/Cleverence plan cannot suppress its forward pass. Reused evidence is dependency-bound through `{kind, id, fingerprint}` records. For R1+ work, a PASS adversarial gate also requires at least one concrete structured failure attempt. When recorded source origins remain accessible, the requirements/release gates rehash current requirements/candidate/baseline/project-context bytes to detect edits made after planning.

## LLM adversarial / anti-bypass validation

The assistant itself is part of the threat model. A helpful LLM can accidentally shortcut required work by narrowing scope/risk, promoting assumptions to facts, laundering missing evidence through `NOT_APPLICABLE`, collapsing duplicate artifacts, substituting a convenient baseline or treating machine-zero/static PASS as semantic/runtime proof.

Read `KNOWLEDGE/LLM_ADVERSARIAL_VALIDATION.md`. Maintain the explicit threat inventory in `TESTS/LLM_BYPASS_MATRIX.json` and execute `TESTS/run_llm_bypass_regression.py`. The required development loop is:

```text
protection
→ hypothesize an LLM shortcut/bypass
→ construct the smallest attack
→ require a mechanical blocker where practical
→ add/extend the owning rule
→ add regression
→ attack the new defense through a second representation
```

Instruction-only defenses are weaker than impossible-by-construction data models, deterministic gates and executable regressions. New safeguards must be red-teamed for second-order bypasses rather than considered complete when the happy path passes.

## Structural 1C XML evidence

When exported 1C XML is in scope, route the structural profiles and run:

```text
python TOOLS/analyze_onec_xml.py <file-or-directory-or-zip>
```

This layer covers Form.xml scopes/BaseForm and DataPath structural summaries (including ConstantsSet bindings without guessing member availability), metadata payloads and adopted-object bindings, CFE extension structure, role Rights.xml/RLS with version-aware omission semantics, and XDTO namespace/import/type contracts. `FORM_DATA_BINDING` then proves changed nested paths against the actual runtime data shape; metadata existence alone never proves container membership. External `cc-1c-skills` material is retained only as attributed supporting reference; it does not override official 1C contracts or project/runtime evidence.

## Field lifecycle evidence

For meaningful custom assignments use:

```text
python TOOLS/analyze_onec_field_flow.py <bsl-file-or-zip>
```

It routes same-field reachable overwrite/lifecycle review. It intentionally does not treat unrelated `Заполнить/Пересчитать` routines elsewhere in the same module as overwrite evidence.

## Whole-change-set architecture

For a candidate with multiple changed BSL objects run:

```text
python TOOLS/analyze_changeset_architecture.py <changed-files-or-directory> [--baseline <baseline>]
```

The tool reports structural REVIEW candidates, not defects. Its explicit routine/pair budgets never silently sample: an oversized corpus receives `SCOPE_REVIEW_REQUIRED`, which means narrow to the real changed dependency closure or deliberately raise the budget. Zero candidates never replaces the semantic responsibility/owner map.

`KNOWLEDGE/GAP_DISCOVERY_PROTOCOL.md` adds independent source-anchored discovery lenses. Every retained hypothesis needs a counterexample and falsifier; the release gate blocks unanchored, unresolved or falsely “covered” hypotheses.

## Cleverence mechanism coverage

Cleverence is routed into separate active mechanisms rather than treating every `.mslx` as an Operation graph:

```text
python TOOLS/analyze_cleverence_mslx.py <operations-candidate> --baseline <baseline>
python TOOLS/analyze_cleverence_configuration.py <metadata-or-documenttypes-candidate> --baseline <baseline>
```

`CLEVERENCE_MSLX` covers Action graph structure plus scan/re-entry state, quantity-stage ownership, writer-path coverage and live `CurrentItem` mutation. `CLEVERENCE_CONFIGURATION` covers configuration `Metadata/**` and `DocumentTypes/**` semantic paths, exact field names/types and container/barcode templates. Physical layout may be `Configuration/...`, a legacy nested export such as `Documents.zip!/…`, or another evidenced stock layout. Structural barcode overlap is not classified as a defect by itself; a changed overlap requires actual stock/parser/runtime precedence evidence. Cross-system tasks additionally route `CLEVERENCE_INTEGRATION` and trace the exact Mobile field through writer/BP/Core to the 1C consumer.

## Missing artifact evidence

A missing source is an explicit evidence state, not permission to infer. Read `KNOWLEDGE/EVIDENCE_ACQUISITION.md`. Use `evidence_requests` in the requirements contract and `artifact_requests` in the validation ledger when a concrete file/metadata/module/log can resolve a material claim. A blocking request that has not been made, is still waiting, or is unavailable keeps the corresponding gate blocked.

The evidence loop is iterative by design:

```text
analyze available closure
→ identify exact unresolved claim
→ request smallest missing artifact
→ continue unaffected work
→ incorporate provided evidence
→ repeat
```

Do not request an entire configuration when a narrower dependency closure can prove the claim, and do not silently drop a mechanism because its decisive source is absent.
