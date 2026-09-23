# IMPLEMENTATION_REACHABILITY

## Purpose

A routine can be syntactically correct, architecturally well placed and still have **zero runtime effect** when no live scenario calls it. This profile proves integration into the intended execution path.

## Mandatory review

For each new or materially changed routine:

1. classify it as a platform/event entrypoint, explicit external API/callback, or helper;
2. name the business/runtime scenario it is supposed to affect;
3. prove the path `entrypoint → caller(s) → changed routine` from exact source;
4. for newly added helpers, reject `defined but never called` and new-only orphan clusters;
5. do not treat `Экспорт` as proof of invocation — it only makes the routine callable;
6. if the platform/vendor invokes the routine dynamically, cite the exact handler/callback contract and keep runtime evidence pending when static proof is impossible;
7. when a feature requires changing an existing hook/caller, include that caller in the delivery closure.

## Machine evidence

Run `TOOLS/analyze_onec_reachability.py` with the exact candidate and, when available, the exact baseline. For a feature-specific review, declare the expected `--entrypoint` / `--target` when they are known.

Key findings:

- `NEW_ROUTINE_WITHOUT_CALLER` — blocking;
- `NEW_ROUTINE_CLUSTER_NOT_CONNECTED` — blocking;
- `NEW_EXPORTED_ROUTINE_WITHOUT_RESOLVED_CALLER` — review/evidence required;
- `TARGET_NOT_REACHABLE_FROM_ENTRYPOINT` — blocking.

## False-pass prevention

The following are **not** reachability evidence by themselves:

- routine exists in the correct common module;
- routine is `Экспорт`;
- code compiles;
- unit/local helper logic is correct;
- caller with the desired name exists in another draft but is absent from delivered bytes.
