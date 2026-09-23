# PROFILE — CROSS_OBJECT_DUPLICATION_REVIEW

## Detection

Route this profile whenever a change-set contains more than one BSL/OS artifact. Run
`TOOLS/analyze_changeset_architecture.py` to obtain structural candidate pairs. A
candidate is a prompt for evidence-backed review, not a defect verdict.

## Mandatory checks

- inventory changed objects/modules/forms and the responsibilities added or changed;
- compare related handlers, call sequences, queries, business fields and invariant implementations across the whole change-set;
- classify each candidate as `SAME_RESPONSIBILITY`, `SAME_BUSINESS_RULE`, `SAME_ALGORITHM`, `INCIDENTAL_SIMILARITY` or `INTENTIONAL_ADAPTER_DUPLICATION`;
- for a shared business rule/invariant, name one owner and replace parallel implementations or prove why a common owner is unsafe;
- for intentional duplication, record the concrete trust, runtime, client/server, vendor/version or performance boundary and the equivalence/drift control;
- perform the semantic whole-change-set pass even when the analyzer reports zero candidates.
- when `analysis_coverage` is `SCOPE_REVIEW_REQUIRED`, narrow to the actual changed dependency closure or deliberately raise the explicit routine/pair budget; never read a budget stop as zero candidates.

## Completion rule

`0 HIGH`, `0 MEDIUM` or zero similarity candidates is only a deterministic result. It
is not semantic or architectural PASS. A proven duplicate owner is blocking until
consolidated or justified; uncertain similarity remains `EVIDENCE_REQUIRED`, never an
automatic refactoring request.
