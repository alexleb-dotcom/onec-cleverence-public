# PROFILE — QUERY

## Detection

- `Новый Запрос`
- `Запрос.Текст`
- `СхемаЗапроса`

## Triggered standards

- `std436`
- `std438`
- `std437`
- `std496`
- `std654`
- `std728`
- `std729`
- `std777`
- `std658`
- `std652`
- `query_methodical`

## Mandatory checks

- transitive DB round trips
- query inside loop
- every sentinel/default query parameter: meaning, caller authorization, disabled predicates and cardinality change
- TOP/FIRST determinism
- UNION/DISTINCT/GROUP semantics
- ORDER BY necessity
- JOIN cardinality
- target row grain and fan-out: for every join with a possible many-side, prove expected pre/post-join cardinality at the business grain and preserve additive measures; reduce each many-side to the required grain or use a complete correlation tuple before composition
- aggregation after joins: `DISTINCT`/`GROUP BY`/aggregate functions must not be used merely to hide fan-out from an under-specified join; prove semantic equivalence and measure preservation
- effective-time alignment: when current, periodic, historical, slice/virtual-table or cached sources are combined, define one intended business moment/version and prove each source is evaluated consistently with it; any deliberate mismatch must be explicit in the business contract
- materialization is not transaction-snapshot proof: temporary tables, cached values and staged/intermediate package/query results do not by themselves prove transaction-wide consistency against concurrent changes; prove transaction/isolation/locking/version semantics separately
- measure semantics: for quantities/amounts/weights/prices and other numeric facts, prove unit/currency, scale, sign convention and coefficient direction before compare/join/sum/substitution; convert exactly once to a common basis
- rounding semantics: prove precision, rounding mode and stage; per-row/early/double rounding must not silently change required aggregates or persisted business facts
- absence/defaulting semantics: missing row/NULL/missing fact is not automatically equivalent to `0`, `Ложь`, empty reference or empty string; every fallback substitution must be justified by the downstream business contract
- required-fact retention: prove source-to-result coverage at the business grain across joins, filters, HAVING, virtual-table restrictions and pre-aggregation; every dropped required fact must have an explicit business exclusion rule
- LEFT JOIN null-rejection by WHERE
- reference-dot dereference: implicit join, cardinality/index path and reuse of an already joined source
- subquery joins
- virtual-table joins
- virtual-table filter parameters
- OR in critical predicates
- functions around parameters/sargability
- index evidence for WHERE/ON/virtual-table parameters/HAVING
- temporary-table size/index need
- RLS/cardinality sensitivity
- sentinel cardinality matrix: normal, empty/Undefined, nonexistent and other-valid-context values; prefer an explicit bulk-mode API/query branch when broadening is intentional
- programmatic text modification: preserve a complete query/template; use `СтрЗаменить()` for dynamic field/table/query fragments instead of embedding variable fragments by concatenation (std437)
- every replacement marker must be unique enough to avoid replacing an unintended occurrence; after replacement the resulting query must remain constructor-readable where practical

- dynamic package/query fragment assembly: prefer a complete template + explicit marker + `СтрЗаменить()`; do not splice optional UNION/WHERE/package fragments with `+` when a replacement anchor can express the variant (std437)
- generated query variants: materialize every supported variant and validate the FINAL query text, not only the BSL source; a dynamic query is not PASS until each variant is accepted by the 1C query parser/runtime
- exact query-text bytes: literal `\\\\t`, `\\\\r` and `\\\\n` pairs are not indentation/line breaks in BSL; block them in query-language token/whitespace positions while preserving legitimate quoted query data/comments and real whitespace
- fragment boundaries: separators (`;`, package divider, `ОБЪЕДИНИТЬ`) belong to a deliberate template boundary; no branch may accidentally contribute/remove a separator
- source aliases in JOIN/UNION must be role-specific and unambiguous; when the same physical table participates in different roles, use different semantic aliases (std758)

- performance claims: distinguish structural optimization hypotheses from proven lower cost; fewer queries/packages/materializations/server calls require plan/index/cardinality/volume/profiler/benchmark evidence before claiming faster execution

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.

## External ITS discovery additions

After internal QUERY review, independently search ITS for the exact query constructs used. In particular, generated query text must be compared with std437 good/bad examples, not only parsed as BSL. Follow related query standards at least one level.

For programmatically assembled queries verify both:
```text
each conceptual fragment/template is independently understandable/validatable
AND
each final generated branch is runtime-parsed in 1C
```

Use meaningful role-specific aliases per std758 to reduce ambiguous-field risk.
