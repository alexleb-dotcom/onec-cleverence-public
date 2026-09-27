# Executable rule registry

`rule_registry.json` is the single source of truth for **requirements routing**, technical routing and release coverage.

A reusable rule is complete only when it declares:

- activation strategy;
- tier and surface/risk applicability;
- concrete checks;
- required evidence modes;
- regression activation coverage;
- regression enforcement coverage.

The same registry also owns `requirements_contract_fields`: the risk-scaled functional-contract fields that are independently fail-closed even if a requirements rule is marked PASS.

Generated views:

- `PROFILES/INDEX.json`
- `KNOWLEDGE/MECHANISM_REVIEW_PROFILES.json`
- `TESTS/SEMANTIC_REGRESSION_CLASSES.md`
- `REQUIREMENTS/INDEX.json`
- `TESTS/REQUIREMENTS_SEMANTIC_CLASSES.md`

Regenerate them with `TOOLS/generate_registry_views.py`. `TOOLS/validate_skill.py` fails if generated views drift from the registry.

Technical Tier 0 means **always requires a disposition**, not “always applicable”. Requirements Tier 0 (`REQUIREMENTS_TRACEABILITY`, `ACCEPTANCE_ORACLE`) is always present in the pre-code contract. `NOT_APPLICABLE` is valid only with a reason **and only where the registry/plan permits it**. A gate routed as `REQUIRED` cannot be discharged as `NOT_APPLICABLE`; the core functional spine (`need`, `target_outcome`, `target_behavior`, `acceptance_cases`) is likewise non-optional.

After every substantive task the `KNOWLEDGE_EXTRACTION` gate records `PROMOTED`, `PROJECT_ONLY`, `NO_REUSABLE_KNOWLEDGE` or `EVIDENCE_PENDING`. A promoted lesson is incomplete until its registry owner, activation and enforcement coverage are explicit.

## Missing-source handling

`EVIDENCE_ACQUISITION` is Tier 0. A resolvable evidence gap must become an explicit, minimal artifact request. Silence, guessed contracts and silent scope reduction are not valid dispositions. Structured ledgers may record requests in `artifact_requests`; requirements contracts use `evidence_requests`.

`GAP_DISCOVERY` is also Tier 0. The ledger carries registry-defined independent lenses and source-anchored hypotheses. Hypotheses are not findings: they require a counterexample, falsifier and fail-closed disposition. The release gate rejects unresolved/unanchored hypotheses and rejects machine-zero as a substitute for semantic discovery.

`CROSS_OBJECT_DUPLICATION_REVIEW` is derived from a multi-BSL change-set rather than lexical keywords. Its analyzer returns REVIEW candidates only; the semantic owner map is required even when no pair is reported.
