# V8STD supporting standards source policy

Purpose: use `v8std` as an on-demand discovery/index layer for 1C standards and diagnostics without replacing the official 1C standard as the normative source.

## Sources

```text
Website:    https://v8std.ru/
Repository: https://github.com/zeegin/v8std
Public MCP: https://ai.v8std.ru/mcp
```

The repository/site exposes a machine-friendly standards/diagnostics corpus and links standards to diagnostics. Use it to discover relevant rules, related material and diagnostic mappings that may be absent from the embedded catalog.

## Trust level

`v8std` is `SUPPORTING_REFERENCE`, not the normative authority.

Evidence priority for standards-sensitive conclusions:

```text
current official 1C/ITS standard or official documentation
→ actual target/typical/BSP implementation when implementation semantics are in question
→ v8std supporting discovery/index/diagnostic mapping
→ embedded skill snapshot/catalog
```

A `v8std` page may widen review and identify a likely standard/diagnostic. A blocking standards claim should be confirmed against the current official source when it is available. If the official source is unavailable, record that limitation explicitly rather than silently promoting the supporting source to official authority.

## Claim fidelity

For every standards-sensitive conclusion keep three layers separate:

```text
SOURCE CLAIM
= current standard ID / clause / official text actually relied on

INTERPRETATION
= what that source means for the reviewed construction

ENGINEERING RATIONALE
= why a specific design/change is recommended
```

Do not merge neighboring clauses, a supporting-source paraphrase or the reviewer's preferred design into a false statement that “the standard requires” something it does not state. When exact wording matters, reopen the current official source instead of relying on a remembered paraphrase. A recommendation may be good engineering without being a literal normative requirement; label it accordingly.

## When to use

Use live `v8std` discovery when at least one is true:

- `BIDIRECTIONAL_STANDARDS` is active for non-trivial 1C work and the embedded catalog/profile may be incomplete;
- `GAP_DISCOVERY` finds a mechanism whose applicable standard is unknown;
- a diagnostic code from BSL Language Server, EDT or АПК needs explanation/mapping;
- a current standard/related-standard chain must be discovered quickly;
- a runtime defect indicates a standards class not predicted by the skill;
- the mechanism is version/freshness-sensitive and current coverage must be challenged.

Do not query the external source merely to confirm a preferred solution. Search for counterexamples, prohibitions, performance constraints, related diagnostics and `См. также` relations.

## Repository/MCP usage

When ordinary web access is available, search/open `v8std.ru` or the GitHub repository on demand.

When an environment exposes the v8std MCP, it may be used as a retrieval transport. The transport does not change the trust model above.

Do not send confidential project code to a public snippet-explanation endpoint. Prefer mechanism names, diagnostic codes, a sanitized minimal fragment, or a local/private retrieval path when sensitive source is involved.

## Assimilation rule

A newly discovered reusable rule from `v8std` is not inserted directly into `RULES/rule_registry.json`.

Required promotion path:

```text
v8std discovery
→ identify official/source evidence
→ prove applicability to a real failure or authoritative contract
→ generalize beyond the current project
→ add activation + enforcement regression
→ calibrate machine heuristics on good/bad/known-working corpora when applicable
→ only then change blocking behavior in the registry
```

This prevents an external diagnostic or heuristic from becoming an uncalibrated hard gate.
