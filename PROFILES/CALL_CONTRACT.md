# PROFILE — CALL_CONTRACT

## Detection

- a changed qualified cross-module call `Модуль.Метод(...)`;
- changed exported procedure/function signature;
- BSP/vendor/typical helper called from changed code;
- caller/callee edited in different modules.

Any changed qualified call activates this profile as `CONDITIONAL_REVIEW` until it is classified. Proven object/manager/native methods may close the row with evidence; a cross-module/BSP/vendor boundary makes the declaration checks required.

## Mandatory checks

- resolve the actual declaration from the exact target/candidate/BSP/vendor source;
- method is exported and available in the caller execution context;
- required and total parameter count matches;
- parameter order and semantic meaning matches;
- optional/default parameters are understood rather than inferred;
- return value or mutation/out-parameter behavior matches caller use;
- client/server availability and serialization constraints are compatible;
- all call sites are rechecked when an exported signature changes.

Run `TOOLS/check_bsl_call_signatures.py` for declarations available in the package. Static `CALL_SIGNATURE_MISMATCH` is blocking. Unresolved external calls remain `EVIDENCE_REQUIRED` and need exact source/metadata inspection.

## Completion rule

A changed call boundary has declaration evidence. “It looks like the method takes these parameters” is not evidence.
