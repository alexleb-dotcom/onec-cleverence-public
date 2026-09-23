# KNOWN RUNTIME FINDINGS

These are reusable findings proven by actual runtime failures. Examples use neutral placeholder field names rather than names copied from a customer/project implementation.

## 1. ТаблицаЗначений.Свернуть removes unused columns

Observed pattern:
`Поле объекта не обнаружено (<DerivedKey>)`

Cause:
the required column was absent from both grouping and sum columns, therefore `Свернуть()` removed it.

Rule:
every column used after collapse must belong to grouping or aggregate set.

## 2. Query-result alias is a data contract

Observed pattern:
`Поле объекта не обнаружено (<OriginalField>)`

Cause:
query returned `<OriginalField> КАК <AliasField>`, while the consumer still expected `<OriginalField>`.

Rule:
avoid unnecessary alias drift; update all consumers atomically when alias is necessary.

## 3. DynamicList MainTable does not guarantee field availability

Observed:
`Ошибка при установке значения атрибута контекста (ПутьКДанным): Недопустимое значение`

Cause:
DynamicList had a custom TextQuery. Metadata field existed in MainTable but not in SELECT.

Rule:
query result first → assign TextQuery → SetRequiredUse → create form column → PathToData → runtime open form.

## 4. QuerySchema auto joins

Previously observed:
`Противоречивая связь "#2"`.

Root cause:
`СхемаЗапроса` mutation has platform semantics beyond the visible source edit: adding a source can create implicit joins. A local syntactic edit was incorrectly treated as full topology control.

Universal rule:
for programmatic DynamicList/query text changes, prefer a complete readable query/template with unique `СтрЗаменить()` anchors when stable anchors exist (std437). `СхемаЗапроса` mutation is not the default workaround; if it is unavoidable, snapshot/inspect auto-generated joins, justify the exception, materialize the final query, and runtime-open the target form.

## 5. Form DataPath does not inherit aggregate members from global metadata

Observed pattern:
`Ошибка при установке значения атрибута контекста (ПутьКДанным): Недопустимое значение` while binding a field to `<AggregateAttribute>.<Member>`.

Cause:
the aggregate form attribute existed and the target metadata object also existed, but that did not prove membership of the target member in the concrete aggregate held by the form. The nested runtime path therefore did not exist.

Rule:
`metadata existence ≠ aggregate runtime membership ≠ valid DataPath`. For every changed `A.B` form binding, prove `B` in the actual runtime shape of `A`. For aggregate attributes such as a constants set, prove membership in the concrete aggregate. If an own form attribute is used as an adapter, prove both load/read and save/write paths and validate the real form through the relevant lifecycle.
