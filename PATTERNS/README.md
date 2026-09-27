# Canonical implementation patterns

`PATTERNS/**` is a small public library of **illustrative implementation shapes** for 1C and Cleverence.

It exists to help an LLM turn an already-proven requirement/design into well-shaped code without treating private/typical/vendor source as distributable training examples.

## Evidence role

Every pattern has this contract:

```text
role = ILLUSTRATIVE_PATTERN
evidence_role = NONE
copy_policy = ADAPT_ONLY
proves_api = false
proves_runtime = false
requires_exact_source = true
```

A pattern may teach structure such as `derive → validate → mutate`, thin hook orchestration, complete query variants or explicit re-entry state handling. It **never** proves that a module, method, field, action, signature, execution context or runtime behavior exists in the target version.

Before adapting a pattern, exact target/user-authorized source still controls names, signatures, field ownership, lifecycle order and vendor/runtime semantics.

## `good` and `bad`

Each indexed pattern contains a small `good` and `bad` example. They are deliberately neutral and incomplete outside the concept being illustrated.

- `good` means “preferred structural shape for the stated concept”, not “production-ready copy/paste code”.
- `bad` means “counterexample that demonstrates the failure boundary”.
- project conventions, comments, author markers, exact API contracts and runtime hooks must still come from current project evidence.

## TESTS fixtures are not examples

`TESTS/fixtures/**` is analyzer/regression input. It contains intentionally malformed, bad, review-only and narrowly minimized cases.

```text
TESTS/fixtures/**
→ regression/analyzer input
→ NEVER implementation precedent
```

Do not search a `*_good` fixture and treat it as canonical project code. Use `PATTERNS/INDEX.json` / `TOOLS/pattern_locator.py` for implementation-shape guidance.

## Loading discipline

Do not load all patterns by default. Search by intent:

```text
python TOOLS/pattern_locator.py --intent "hook orchestration"
python TOOLS/pattern_locator.py --intent "sentinel query bulk mode"
python TOOLS/pattern_locator.py --intent "DeclaredItems CurrentItems identity"
```

Then load only the matching `good`/`bad` pair plus the exact target source needed to prove the real implementation contract.
