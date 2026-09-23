# Learning and knowledge-extraction protocol

Real tasks improve the universal skill only after the process gap is closed, not merely the current code.

A discovery hypothesis is not knowledge. Before promotion it must be source/runtime/authoritatively confirmed, survive a falsifier/counterexample check, generalize beyond the project and be shown not to duplicate an existing registry owner. Model novelty alone is never evidence.

## Chat experience is discovery evidence, not automatic promotion evidence

A real chat can reveal a valuable failure mode: the model may miss a mechanism, infer a false platform rule, choose the wrong owner or bypass a protection. That observation is enough to create a candidate lesson/threat, but it does not automatically prove the technical/platform statement inferred from the conversation.

Use this promotion split:

```text
observed LLM behavior
→ direct evidence for an LLM/review-process failure candidate

technical/platform/vendor/standards claim inferred from the chat
→ hypothesis only
→ validate against actual target/runtime evidence and/or current authoritative source
→ generalize
→ regression/adversarial coverage
→ promote
```

For platform/1C/Cleverence/standards facts, re-check the current authoritative source before promotion when practical. Supporting references may discover or challenge a claim but do not become normative merely because they agree with the chat. A reproduced runtime failure can itself be strong technical evidence, but its generalized rule must still be bounded to what the reproduction proves.

## Mandatory post-task extraction

After every substantive task classify the result:

1. project/baseline/customer-only fact → `PROJECT_CONTEXT` or on-demand archive;
2. source/official/runtime-proven reusable technical fact → active knowledge/reference corpus;
3. reusable false negative/error class → rule check plus anti-pattern/semantic class;
4. deterministically detectable class → validator plus positive/negative fixture;
5. changed development/review algorithm → registry/profile/workflow;
6. equivalent existing rule → extend its owner instead of creating a duplicate;
7. insufficient evidence → do not promote as universal truth.

Record one outcome:

```text
PROMOTED
PROJECT_ONLY
NO_REUSABLE_KNOWLEDGE
EVIDENCE_PENDING
```

For every promoted item record evidence, generalized statement, owner file, activation/enforcement coverage and deduplication decision.

## Confirmed reusable failure

1. explain why the previous review missed it;
2. generalize the invariant without project/customer identifiers;
3. independently validate any technical/platform/vendor/standards claim that was discovered through chat/model behavior;
4. add/update the rule in `RULES/rule_registry.json`;
5. define activation, concrete checks and evidence modes;
6. add activation regression coverage;
7. add a machine positive/negative fixture when deterministic, otherwise a semantic regression check;
8. connect unresolved evidence to release behavior;
9. regenerate registry views;
10. run `TESTS/run_review_regression.py` and `TOOLS/validate_skill.py`;
11. prove the historical failure is routed/blocked and its control case still passes.

Bootstrap reduction never destroys accumulated experience: historical corpora remain in `ARCHIVE` without default loading.

## Requirements learning

A recurring requirement ambiguity is learned the same way as a code defect: identify why discovery missed it, generalize it, add/extend a requirements rule/check, prove activation and gate enforcement, and keep project-specific business decisions outside universal knowledge. A scoring/reporting convention from an external requirements-review skill is not automatically a development rule.
