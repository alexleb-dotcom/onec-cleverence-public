# Proof-claim integrity

The skill is an execution system. Referring to its vocabulary is not evidence that its workflow was executed.

## Canonical validation claims

For non-trivial implementation/review work, statements such as “the skill was applied”, “fully checked”, “N/N checks passed”, “ready”, “proven”, or equivalent readiness/compliance claims are allowed only when they are bound to the canonical workflow artifacts that actually exist for the current candidate: requirements contract/gate when required, review plan, validation ledger, deterministic/runtime reports as applicable, and the final release-gate outcome.

If these artifacts were not built or are incomplete, say exactly that. You may say that skill guidance was used conceptually or that a partial/manual review was performed, but do not promote that into canonical validation.

A model-authored checklist, prose recap, or ad-hoc `N/N` count is supplementary review material only. It cannot replace registry routing, child-check disposition, reverse review, adversarial cases, runtime/profiling evidence, or the release gate.

## MANUAL_SKILL_EXECUTION

If a deterministic tool/hook/verifier cannot be executed, state `MANUAL_SKILL_EXECUTION` explicitly and perform only the smallest manual evidence path needed for the current claim. This does not reduce proof requirements.

- Manual exact-source inspection may prove only the source property actually observed.
- A tool/search/provider hit remains candidate/supporting evidence until the existing proof owner accepts exact evidence.
- Do not emit a machine/release/runtime PASS for an operation that did not run.
- Required machine/runtime/profile evidence remains pending until the actual canonical executor/evidence is available.
- Manual execution is a task/turn disposition, not a new persisted workflow state or alternate release gate.

## Evidence-property binding

Every material evidence item must be bound to the exact property it supports. Evidence does not inherit stronger meaning merely because it is authoritative or similar.

Examples:

- a firm-1C release analog may prove that a construction/API usage exists in that release; it does not by itself prove the business semantics, performance, lifecycle, or correctness of a new customization;
- a project convention may prove naming/style placement; it does not prove algorithm correctness;
- a parser/analyzer PASS proves only the machine-detectable property it checked; it does not prove runtime behavior;
- one successful runtime scenario does not prove untested cardinality, concurrency, retry, or alternative-state behavior.

Record the property under test, the evidence anchor, and any remaining boundary. Unsupported stronger conclusions stay `EVIDENCE_REQUIRED`, `RUNTIME_PENDING`, or `NEEDS_PROFILING` as appropriate.

## Performance claims

Structural heuristics are not measured performance proof. Fewer queries, one package instead of several, fewer `Выгрузить()`, fewer server calls, a temporary table, or a smaller-looking loop may be useful hypotheses, but none alone establishes lower cost.

A claim of improved performance needs evidence appropriate to the claim: query plan/index/cardinality evidence, representative volume model, profiler/benchmark/runtime measurement, or another explicit cost model. Without it, classify the change as a structural optimization hypothesis and keep performance proof pending.

## Dataflow materialization is not a transaction snapshot

A temporary table/intermediate result can make later calculations consume one materialized dataflow state. It does not by itself prove transactional consistency against concurrent changes. Words such as “snapshot”, “consistent view”, “same checked state”, or equivalent require transaction/isolation/locking/version evidence for the interval being claimed.

## Failure invalidates prior proof

A parser/runtime failure, newly discovered user counterexample, or review defect invalidates every prior PASS/readiness claim that depended on the failed property. Fix the local defect, then rerun routing and re-evaluate the affected dependency closure before restoring readiness. “The next exception is fixed” is not a substitute for full post-fix validation.

## Reporting contract

Final reporting must distinguish:

- **canonical gate result** — actual output of the requirements/release gate for the exact candidate;
- **machine checks** — only what named analyzers prove;
- **manual/semantic review** — explicitly scoped;
- **runtime/profiling pending** — not silently collapsed into PASS;
- **supplementary checklist** — never presented as the canonical skill result.

## Exact rule/check claim binding

A `PASS` evidence row is not fungible across obligations. For every routed rule and every child check the verifier computes a stable claim id:

- `RULE:<rule-id>`;
- `CHECK:<rule-id>:<check-id>`.

The ledger may display that id for usability, but the verifier recomputes it from the registry and routed structure. Deleting or rewriting the ledger value does not change the obligation.

For rule/check `PASS`:

1. evidence must carry the exact claim id;
2. the evidence kind must be admitted by the owning rule `evidence_modes`;
3. at least one evidence item must be primary proof for that claim;
4. `SOURCE_REQUIRED`/`SEMANTIC` may be primary only when bound to the exact claim;
5. `RUNTIME` may be primary only when the verified runtime observation property equals the exact claim id;
6. a broad deterministic analyzer capability such as `STATIC:ONEC_BSL` is supporting evidence only and must be marked `supporting_only=true`; zero findings do not prove the rule/check semantic claim;
7. a MACHINE receipt may become primary only when a registered analyzer verifies the exact claim property itself.

This prevents three shortcuts: reusing one evidence item for unrelated checks, laundering a generic static pass into semantic proof, and attaching an unrelated passing runtime case to a claim.

## Coverage states are not synonyms

Keep these states separate in skill maintenance and release claims:

- **REGISTERED** — a rule/check exists in the registry;
- **GATE_ENFORCED** — executable verifier logic actually rejects an unresolved/misbound instance of that registered obligation;
- **BEHAVIORALLY_SAMPLED** — a concrete positive/negative fixture or scenario exercises the domain failure mode;
- **RUNTIME_PROVEN** — accepted runtime evidence observes the required property in the target environment.

A registry entry or `check:<id>` reference is not, by itself, behavioral sampling. A gate-enforcement regression proves that the obligation cannot silently disappear; it does not prove the domain semantics of every possible implementation.

## Threat-matrix maturity binding

`TESTS/LLM_BYPASS_MATRIX.json` is a threat inventory, not automatic behavioral proof. Its `mechanical_regressions` may establish at most `GATE_ENFORCED`. A threat case reaches `BEHAVIORALLY_SAMPLED` only when it names a concrete positive/negative scenario that is executed by normal CI. `RUNTIME_PROVEN` additionally requires accepted target-runtime evidence. CI must reject unresolved `check:<id>` proof bindings and must report the observed maturity state instead of inferring it from the presence of prose.

Behavioral maturity must be established by execution of the portable semantic regression itself, not by the presence of an internal-only workflow file, so the same proof boundary remains valid in both `INTERNAL_FULL` and `SHAREABLE_CORE` distributions.
