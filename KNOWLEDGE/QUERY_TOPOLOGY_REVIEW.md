# QUERY TOPOLOGY REVIEW

## Failure mode discovered 2026-08-26

The previous design review analyzed local query correctness, JOINs and in-memory O(N*M), but did not enumerate all DB calls reachable through helpers from a public business operation. This allowed sequential queries and an N-query loop pattern to survive review.

## Corrective control

For every changed public server operation:

1. build call graph;
2. enumerate DB/API boundaries;
3. flag queries in loops;
4. if >1 query execution is reachable, evaluate one query / IN / UNION / batch / temporary tables / BSP bulk API;
5. consult standard 436 before approving multiple query executions;
6. state why any remaining separate DB calls cannot be consolidated;
7. only then review in-memory complexity.

## Generalized examples

- A multi-step business operation may hide sequential queries across helpers even when each local routine looks efficient.
- A query inside a transitive helper called from a loop is still N+1 I/O from the business entrypoint.
- When navigation-link/string identifiers or external transformations must be produced between stages, separate bulk stages can be justified, but the boundary and expected volume must be documented.
- A remaining BSP bulk call is not an N+1 defect merely because it performs database work internally; inspect its contract and call frequency.
