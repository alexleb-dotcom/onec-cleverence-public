# PROFILE — DYNAMIC_LIST

## Detection

- `ДинамическийСписок`
- `СхемаЗапроса used to mutate list`

## Triggered standards

- `std768`
- `std732`
- `std437`
- `std489`
- `std729`

## Mandatory checks

- exact target/typical DynamicList implementation inspected before inventing a query mutation when behavior is not known exactly
- effective query acquisition follows proven typical pattern: current `ТекстЗапроса` for `ПроизвольныйЗапрос`, otherwise `ПолучитьИсполняемуюСхемуКомпоновкиДанных()` / `НаборДанныхДинамическогоСписка`
- when target-specific root/alias proof is needed, prefer platform query structures read-only; do not infer arbitrary query topology from string positions
- default/intermediate query is valid and can be opened by query constructor where the mechanism permits it
- the complete most-frequent/default query remains in the DynamicList query editor; programmatic override has a proven runtime variant or extension/update-safety constraint rather than replacing one static query with another on every open
- main table correctness
- hot-path query cost: avoid calculating complex operational state on every list refresh; when appropriate, use a transactionally maintained indexed state register and prove its freshness/rebuild contract
- query/main-table set before settings or parameters
- BSP УстановитьСвойстваДинамическогоСписка when available
- if query text itself is modified programmatically, prefer complete known query variants / exact typical anchors; `СтрЗаменить()` is allowed only on a proven fragment, not as a license to invent custom query grammar
- custom `#...` placeholders in constructor-expected query text are blocking under the project constructor-readability gate
- parsing arbitrary SELECT/FROM/JOIN/package structure through `СтрНайти`/`Сред`/position math is blocking unless an exact supported typical/vendor analog and explicit exception exist
- `СхемаЗапроса`-based mutation of dynamic-list text is not the default project pattern; it requires an explicit `EXCEPTION_JUSTIFIED` decision when stable `СтрЗаменить()` anchors cannot be defined
- required fields exist before PathToData
- all UNION operators preserve result contract
- group/search fields indexable for large lists
- every changed cross-module helper call matches the exact exported signature
- runtime open form and query-constructor/runtime validation of final text

## Completion rule

Every check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS.

## Independent ITS discovery

Always inspect std768 and std732 plus neighboring DynamicList standards discovered from `См. также`. Current known neighbor: std489 (grouping/search/tree restrictions).

When query text is programmatically changed, QUERY/std437 review is also mandatory; DynamicList/std768 only governs the DynamicList-specific contract and property application.
