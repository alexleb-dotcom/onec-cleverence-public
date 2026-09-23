# 1C query and DynamicList modification guide

## Default rule

First write and understand the final query in ordinary 1C query language. Programmatic modification must preserve a visible text contract; syntax knowledge alone is not proof of platform behavior.

Preferred order for changing an existing query:

1. find the exact target query and a typical/BSP implementation of the same or nearest mechanism;
2. keep the stored/default/intermediate query text valid 1C query language so it can be opened in the query constructor whenever the mechanism permits it;
3. prefer a complete known query variant or an official extension hook over parsing an arbitrary query string;
4. use `СтрЗаменить` only on a **proven exact fragment/anchor** whose before/after forms are valid and understandable query text;
5. if the source structure/anchor is not proven, stop with `EVIDENCE_REQUIRED` instead of inferring SELECT/FROM/JOIN positions;
6. materialize every final query variant and validate it in the 1C query constructor/runtime.

Do not build optional UNION/WHERE/package boundaries by arbitrary `+` concatenation. Do not introduce custom `#ИмяМаркера` tokens into query-language text that is expected to remain constructor-readable. Do not implement a generic query grammar parser with `СтрНайти`/`Сред`/position surgery unless an exact supported typical/vendor analog proves that approach and the exception is explicitly justified.

Literal backslash pairs `\\t`, `\\r` and `\\n` are not BSL escapes. In final query text they are blocking corruption when they occupy query-language token/whitespace positions. The detector is intentionally narrower than a global backslash scan: quoted query literals/comments and real tabs/newlines are not defects.

**Nuance:** this is a project hard gate, not a claim that the `#` character is universally forbidden by 1C standards. The defect is storing/processing a query template that is not valid at the point where the query constructor or platform expects valid query language.

## QuerySchema

`СхемаЗапроса` is not the default mutation mechanism for an existing dynamic-list query. Adding a source can create or rearrange implicit joins, and serializing the schema can hide the exact text contract that must be reviewed.

Use QuerySchema mutation only as an explicitly justified exception when a stable textual anchor cannot be defined. Such an exception requires inspection of the final serialized query and a runtime form/query test.

## DynamicList contract

If `ДинамическийСписок.ТекстЗапроса` is non-empty, a metadata field of the main table is not automatically present in the query result. `УстановитьОбязательноеИспользование` does not add a missing SELECT field.

When BSP is available, do not directly assign `ДинамическийСписок.ТекстЗапроса`. Use:

```1c
СвойстваСписка = ОбщегоНазначения.СтруктураСвойствДинамическогоСписка();
СвойстваСписка.ТекстЗапроса = НовыйТекстЗапроса;
ОбщегоНазначения.УстановитьСвойстваДинамическогоСписка(ЭлементСписка, СвойстваСписка);
```

The first argument is the managed-form `ТаблицаФормы` element connected to the dynamic list, not the `ДинамическийСписок` value itself. Apply query properties before operations that rely on list settings, then call `УстановитьОбязательноеИспользование` and create/bind the form field.

## Root-source rule

Before adding a join, ask who owns the required field.

- If the field belongs to the already proven root source, select it directly from that source alias.
- Do not self-join the same table only to expose its own field.
- Add a LEFT JOIN only when the required field belongs to another source and preserving baseline rows requires left semantics.
- A WHERE condition on the right side of a LEFT JOIN must be reviewed for accidental null rejection.

For textual mutation of a runtime query, the preferred proof is **an exact target/typical query variant**, not a homemade parser. Prove at minimum:

```text
exact baseline query or official/typical extension hook inspected
constructor-readable before-state
constructor-readable after-state
replacement fragment is exact and unique
all SELECT/UNION result contracts preserved
no unrelated fragment changed
BSP setter contract verified when used
```

If achieving the change would require discovering arbitrary query topology by string positions, stop and obtain the real baseline/typical implementation instead. “Fail closed” does not make an invented parser an accepted architecture.

## Runtime gate

Static review cannot prove the generated query is accepted by the 1C platform. For every changed DynamicList query, open the real form and test rows with and without the joined business object, plus filtering/sorting by the added field when applicable.

## General query performance review

Always review:

- queries inside loops and transitive helper I/O;
- virtual-table parameters;
- index evidence for material predicates;
- reference dereference chains;
- join cardinality and redundant joins;
- temporary-table necessity;
- unnecessary presentations and selected fields;
- FIRST/TOP consumer semantics;
- alias consistency across SELECT / GROUP BY / ORDER BY / consumers.

## ТаблицаЗначений.Свернуть

After `Свернуть()` only grouping and aggregate columns remain. Every column consumed later must be preserved in one of those sets.
