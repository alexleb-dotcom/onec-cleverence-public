# DYNAMIC POST-VALIDATION ALGORITHM

Goal: discover performance/correctness checks from actual changed code, not from a fixed memory-based checklist.

Route by surface first. The passes below apply to changed 1C BSL/query code. For Cleverence route by mechanism: Operation/Action graphs use `TOOLS/analyze_cleverence_mslx.py` + `PROFILES/CLEVERENCE_MSLX.md`; `Configuration/Metadata/**` and `Configuration/DocumentTypes/**` use `TOOLS/analyze_cleverence_configuration.py` + `PROFILES/CLEVERENCE_CONFIGURATION.md`. Use the accepted baseline when available. For cross-system work run every affected Cleverence branch plus the integration contract profile.

## Pass A — inventory

1. Enumerate changed files.
2. Parse procedures/functions and call sites.
3. Build public-operation call graph.
4. Mark loops and nesting.
5. Mark explicit I/O.
6. Mark possible implicit I/O.
7. Parse query text:
   - sources/aliases;
   - dereference depth;
   - joins;
   - virtual tables;
   - DISTINCT/GROUP/ORDER;
   - UNION vs UNION ALL;
   - temp tables;
   - packages.
8. Mark data-shape mutations:
   - Свернуть;
   - Скопировать;
   - ВременныеТаблицы;
   - merge keys;
   - aliases/contracts.

## Pass B — classify

Infer left-side type from:
- procedure parameter contract;
- assignments;
- metadata;
- known platform/BSP return types.

Classify each dot access as:
- reference dereference;
- loaded object;
- table row;
- structure;
- query alias field;
- query multi-hop dereference;
- unresolved.
- Structure-like `.Свойство(..., outVar)` reads: presence and out-value type are separate facts; track the local out value to any later bare Boolean condition and require Boolean normalization/type proof on the reachable path.

## Pass C — trigger official standards

Use `Standards Trigger Map` from master skill.
Search official documentation when a triggered mechanism is not already grounded.

## Pass D — solution matrix

For every risk compare:
- current solution;
- one query;
- `В (&Array)`;
- `UNION ALL`;
- package;
- temp table;
- BSP bulk API;
- explicit JOIN / `ВЫРАЗИТЬ`;
- in-memory index;
- minimal-diff fallback.

## Pass E — adversarial check

Try to invalidate the chosen solution:
- hidden I/O?
- N+1 through helper?
- reference dot in loop?
- redundant JOIN?
- cardinality growth?
- unnecessary DISTINCT/GROUP/ORDER?
- duplicate elimination pushed to DB without need?
- query result/data-contract drift?
- runtime-only dependency?

## Pass F — post-change rescan

Repeat Pass A on the final code.
Delivery is blocked if a HIGH finding remains without explicit justification. `STRUCTURE_PROPERTY_OUT_PARAM_UNSAFE_BOOLEAN` is a property-scoped HIGH finding only when the receiver is locally proven Structure-like (`Новый Структура` or an active exact `ТипЗнч(...)=Тип("Структура")` guard); a generic `.Свойство` method name with unresolved receiver type is REVIEW-only and does not import Structure absent-key semantics. The exact finding may be resolved through the existing claim-bound SOURCE_REQUIRED/SEMANTIC evidence path when current source/API evidence proves the specific out value is Boolean. This proves only the bounded same-routine property, not general BSL type safety.
Previously gathered evidence may be cited again only when its declared dependency hashes/versions remain unchanged.


## Mandatory relation to bidirectional validation

This algorithm is a discovery aid, not the coverage authority. After it runs, `KNOWLEDGE/VALIDATION_ENGINE.md` still requires both `CODE_TO_STANDARDS` and an independent `STANDARDS_TO_CODE` pass across L1-L6. A clean analyzer cannot close an evidence row by itself.
