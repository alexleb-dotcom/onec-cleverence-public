# Requirements execution layer

`RULES/rule_registry.json` remains the single source of truth. This directory contains generated/readable requirements views, not an independent registry.

Normal non-trivial change flow:

```text
python TOOLS/build_requirements_contract.py <requirement/context files> --task-text "..." --output requirements-contract.json
# fill only from evidence; leave unknown business decisions OPEN
python TOOLS/requirements_gate.py requirements-contract.json
python TOOLS/build_review_plan.py <candidate/source> --requirements-contract requirements-contract.json --output review-plan.json
```

The assistant must first mine actual source/project context and ask only unresolved blocking questions. Do not use the contract as a generic questionnaire.
