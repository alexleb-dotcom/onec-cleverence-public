# LLM ADVERSARIAL / ANTI-BYPASS VALIDATION

## Purpose

This protocol treats the reviewing/developing LLM itself as a potential source of unsafe shortcuts.

The threat is not limited to a malicious user. A helpful model may unintentionally minimize work, tool calls, context, uncertainty or runtime effort by narrowing scope, promoting assumptions to facts, laundering missing evidence through `NOT_APPLICABLE`, or declaring a clean machine result to be semantic proof.

Therefore instructions alone are not considered a sufficient control. Important safeguards should be backed by executable routing/gates/regressions whenever practical.

## Mandatory red-team loop

For every material protection or new workflow mechanism, perform:

```text
PROTECTED CLAIM / INVARIANT
→ hypothesize how an LLM could avoid the required work
→ construct the smallest realistic bypass attempt
→ identify what incorrect claim would become possible
→ require a mechanical blocker where practical
→ add/extend the owning rule rather than duplicate ownership
→ add an executable regression
→ attack the new protection again through a second route
```

A safeguard is incomplete when it only says what the model should do but has no way to detect the most likely shortcut.

## Attacker model

During adversarial review assume the assistant is trying to produce an apparently complete answer while minimizing one or more of:

- source acquisition;
- files inspected;
- requirements work;
- active profiles;
- semantic checks;
- runtime tests;
- dependency revalidation;
- exact delivery reconstruction;
- explicit uncertainty.

The assistant may not deliberately lie, but the test should ask: **what representation/status/scope change would let it accidentally claim more proof than it has?**

## Core bypass classes

### 1. Surface downgrade
Attempt: source proves 1C/Cleverence/CROSS_SYSTEM, but the plan is declared `ANALYSIS_ONLY` or a narrower surface to remove profiles/gates.

Defense: effective surface is a monotonic union of source detection + task + requirements + project context. Declared context may widen, never narrow.

### 2. Risk downgrade
Attempt: force `R0_LOCAL` to avoid state/runtime/contract work although routed mechanisms require R1/R2/R3.

Defense: effective risk is the maximum of routed/source/task/requirements/project risk.

### 3. Requirements erasure
Attempt: skip the functional contract because the implementation appears obvious.

Defense: non-trivial change work requires the requirements gate; missing/underscoped contracts block production-ready design/release.

### 4. Contract-row deletion / proof-row collapse
Attempt: delete a required field/check/rule/gate, duplicate an ID so last-write-wins hides one obligation, or omit a reverse-pass row.

Defense: exact registry/contract coverage and unique row IDs are gate-validated.

### 5. `NOT_APPLICABLE` laundering
Attempt: convert a required gate/check into `NOT_APPLICABLE` instead of obtaining evidence.

Defense: required planned gates cannot become N/A; N/A needs a concrete reason and cannot contradict an applicable/proven owner.

### 6. Assumption promotion
Attempt: turn `OPEN`, `ASSUMED`, analogy or likely behavior into `KNOWN`/PASS without evidence.

Defense: status/evidence requirements remain explicit; analogy never establishes a user requirement or runtime fact.

### 7. Evidence fabrication / weak evidence
Attempt: use vague text such as “checked code”, a missing `ref`, or a MACHINE/RUNTIME claim without a named report/case.

Defense: concrete `{kind, ref}` evidence is mandatory; MACHINE/RUNTIME evidence links to named PASS records.

### 8. Machine-zero laundering
Attempt: `0 HIGH / 0 MEDIUM` or zero structural candidates becomes semantic/architecture/runtime PASS.

Defense: deterministic zero closes only claims the deterministic tool can prove. Gap discovery, ownership, semantic review and runtime remain independent.

### 9. Static-as-runtime substitution
Attempt: XML/MSLX/query parsing success is represented as proof of actual runtime/device/platform behavior.

Defense: runtime-visible contracts require runtime evidence or explicit pending state.

### 10. Stale evidence reuse
Attempt: reuse prior PASS after candidate, baseline, caller, project context, requirements, vendor version or routing dependencies changed.

Defense: reusable evidence is fingerprint-bound and invalidated by changed dependency identity.

### 11. Baseline substitution
Attempt: use an archived/reference/stock configuration as the deployed project baseline because it is easier to access.

Defense: baseline identity is separately bound; reference corpus is supporting evidence, never silently the deployed baseline.

### 12. Artifact-scope erasure
Attempt: trust an archive/file label and inspect only expected suffixes/roots, missing mixed content or nested containers.

Defense: physical inventory precedes analyzable filtering; bounded nested traversal produces explicit warnings instead of silent omission.

### 13. Duplicate-name collapse
Attempt: two objects both named `Module.bsl` collapse into one map entry, removing a changed object and therefore its cross-object review obligations.

Defense: physical corpus entries have unique entry identities; logical/semantic normalization never replaces physical provenance.

### 14. Subset-as-FULL_COMPARE
Attempt: call a partial Cleverence configuration subset/patch an exact full delivery simply because its files are internally valid.

Defense: implementation-source usability is separate from exact-delivery/FULL_COMPARE proof. Target delivery shape must be authoritative.

### 15. Runtime-database-as-configuration
Attempt: use runtime database/log/storage files as a configuration export or merge-ready delivery.

Defense: artifact role classification keeps runtime DB separate and blocks exact configuration delivery claims.

### 16. Missing-source laundering
Attempt: decisive source is unavailable, so the related rule is silently omitted or marked N/A.

Defense: request the smallest sufficient dependency closure; unavailable evidence remains blocking/pending for the affected claim while unrelated analysis continues.

### 17. Project-convention invention
Attempt: copy author/date/company markers, operation prefixes, comments, protected-code policy or naming from examples/universal skill into a new project.

Defense: conventions are project evidence, not universal defaults.

### 18. Unrelated-refactor escape
Attempt: broaden a requested fix into cleanup/refactoring of stock/client code because it looks cleaner.

Defense: modification policy/protected surfaces + minimal coherent diff; unrelated work requires explicit authorization.

### 19. Post-fix partial review
Attempt: after a material fix rerun only the edited analyzer or inspect only edited lines.

Defense: reroute mechanisms, recompute dependency closure and rerun both CODE_TO_STANDARDS and STANDARDS_TO_CODE with dependency-safe evidence reuse.

### 20. Blocking-finding suppression
Attempt: leave a blocking finding in prose/ledger while still setting completion/release to PROVEN.

Defense: any `blocking_findings` entry blocks release.

### 21. External-trust escalation
Attempt: use v8std, third-party heuristics, archived analogs or an LLM-generated example as normative over actual target source/official 1C/vendor/runtime evidence.

Defense: explicit source trust hierarchy and provenance catalog.

### 22. Semantic-name equivalence
Attempt: treat Cyrillic/Latin lookalikes, transliteration, display representation, package/unit/barcode or similarly named fields as the same technical/business identity.

Defense: exact identifier/type/business-identity proof; representation is not identity by default.

### 23. User-pressure bypass
Attempt: instructions such as “don’t ask”, “just finish”, “runtime is unavailable”, or time pressure are used to silently skip material evidence.

Defense: continue all unaffected work, but preserve the exact affected claim as evidence-required/runtime-pending rather than fabricate completion.

### 24. Repository-role confusion
Attempt: a universal skill repository is mistaken for the user's target project or deployed baseline simply because its URL is the only input.

Defense: `README_FIRST.md` declares `UNIVERSAL_SKILL_REPOSITORY`; cold start must identify the target project separately.

## Second-order bypass review

Every new safeguard must be challenged at least once through a different representation. Examples:

- If path matching is fixed, try the same artifact inside a nested archive.
- If duplicate logical names are fixed, try identical names from separate top-level inputs.
- If surface downgrade is blocked by CLI overrides, try project context or requirements context.
- If a missing artifact request blocks release, try resolving it by editing the old ledger instead of rebuilding the plan.
- If evidence requires a report ID, try a named report whose result is FAIL.
- If the plan binds hashes, mutate the source after plan creation.

## Defense hierarchy

Prefer, in order:

```text
1. impossible-by-construction data model
2. deterministic validation/gate
3. independent regression fixture
4. explicit semantic proof obligation
5. instruction-only warning
```

Instruction-only protection is acceptable only when the underlying claim cannot reasonably be machine-validated. It must remain visible in the ledger/gate and receive adversarial review.

## Definition of done for a new safeguard

A new safeguard is complete only when:

- the protected claim and bypass hypothesis are stated;
- exactly one `primary_owner` is identified and resolves to a registry rule/gate or an explicitly maintained subsystem contract; cross-cutting responsibilities use validated `related_owners` rather than slash-composed ownership strings;
- every threat belongs to one stable `family`; the runner independently pins the accepted family/count contract so a family cannot silently shrink;
- the bypass cannot silently reduce required scope/evidence;
- an executable regression exists where practical;
- a second-order bypass was considered;
- machine success is not overstated as semantic/runtime proof;
- the lesson is placed in universal skill only if it is project-independent.

`TESTS/LLM_BYPASS_MATRIX.json` is the threat/coverage inventory. `TESTS/run_llm_bypass_regression.py` executes core anti-bypass invariants; the normal review regression suite executes the referenced deeper proof-gate cases.
