# PROFILE — COLLECTION_ALGORITHM

## Detection

- `nested loops`
- `Найти/НайтиСтроки inside loop`
- `Соответствие used as index`
- hierarchy/tree/parent-child traversal implemented over collections

## Triggered standards

- `std436`
- `std729`

## Mandatory checks

- derive and justify asymptotic complexity; reject avoidable multiplicative scans rather than forcing every correct algorithm to O(N)
- nested scan replaceable with index
- same data rescanned across phases
- memory growth bounded
- 10x/100x scale challenge
- for hierarchy/tree algorithms, state whether the result is a complete tree, a forest or a subtree rooted at the supplied/scanned node
- for hierarchy/tree algorithms, prove cycle handling/visited semantics when input can be inconsistent or graph-like
- if the structure claims one-parent tree semantics, detect/classify multiple parents and duplicate edges
- define missing-parent behavior relative to the intended root/subtree boundary; a parent outside an intentionally selected subtree is not automatically a defect
- prove behavior when traversal starts from an internal node rather than the global root

## Mandatory Performance Review

When this profile is activated, implementation-readiness additionally requires the structured, exact-candidate `performance_review` contract owned by `COLLECTION_ALGORITHM`. Compare current and proposed algorithms for passes, nested searches, loop I/O, asymptotic time, memory/copies, data ownership, client/server/DB topology and a justified scale boundary up to 100,000 rows. Preserve result, ordering, rounding, side effects and error/retry semantics or bind any intentional change to a requirement. Static/semantic reasoning may justify structure and complexity but must not claim measured acceleration; measured speedup requires verifier-confirmed `RUNTIME_ADAPTER` evidence bound to the exact candidate.

`NOT_APPLICABLE` is valid only when the canonical planner, recomputed from the exact candidate, reports this owner inactive with no activation triggers. Free-form prose cannot waive the review.

## Completion rule

Every applicable check above must be classified with evidence or explicit non-applicability. Unknown material behavior is not PASS. Do not convert a deliberate subtree boundary into an “orphan node” defect merely because the external parent is outside the requested result.

## Cross-object loop gate

For every helper/vendor call inside a loop, inspect the actual callee and transitive callees for query/server/external I/O. Local in-memory appearance is not evidence. Hidden transitive I/O is reviewed under std436/std729 and requires either bulk alternative analysis or an explicit volume/compatibility compromise.
