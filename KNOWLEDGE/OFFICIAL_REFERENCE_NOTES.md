# OFFICIAL_REFERENCE_NOTES

Use official sources when validating platform semantics/performance.

1C:
- Dynamic list: platform page `Динамический список`.
- Example `Как добавить произвольные колонки в динамический список?`.
- Query mechanism: `Механизм запросов`.
- Standards: `Разыменование ссылочных полей составного типа в языке запросов`.
- Query optimization: `Общие рекомендации`, including avoiding queries in loops.

Cleverence:
- Object `Document` documentation: DeclaredItems and CurrentItems semantics.
- Direct write action documentation.
- Buffer write action documentation.
- Mobile SMARTS development examples with ItemsView over Declared rows and current fact quantities.

Version rule:
official docs are evidence, but actual project runtime and compatibility mode must also be recorded when behavior is version-dependent.

Supporting standards discovery:
- `v8std`: `https://v8std.ru/` and `https://github.com/zeegin/v8std`. Use as a practical standards/diagnostics index and related-material discovery layer; confirm blocking normative conclusions against current official 1C/ITS text when available.
- Public retrieval/MCP endpoint may be used when the execution environment supports it: `https://ai.v8std.ru/mcp`. Transport availability does not change source authority.
- Read `KNOWLEDGE/V8STD_SOURCE_POLICY.md` before promoting any externally discovered diagnostic/heuristic into a blocking registry rule.
