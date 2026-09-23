# Data, state, classification and version contracts

This chapter owns reusable failure classes that repeatedly appear across 1C, Cleverence and mixed integrations. It defines proof obligations, not product-specific implementation APIs.

## Barcode input and classification

Treat barcode handling as a staged pipeline:

`raw device bytes/code points → normalization → parsing/classification → domain identity → business route`.

A displayed string is not proof of the raw scanner payload. Non-printable separators such as GS must be verified as actual code points/bytes. Normalization has one named owner. If multiple patterns can match, specificity and precedence are explicit; a broad prefix matcher must not silently steal a more specific code. Full, shortened and transport representations are not equivalent merely because one can be derived from another. Emulator/manual paste and physical scanner paths require separate runtime evidence whenever control characters or encoding can differ.

## Reference/master-data authority and freshness

Replicated reference data has four independent properties: authoritative owner, semantic validity, freshness and propagation. A row can exist and have the right type yet be business-wrong; a semantically correct source row can also be stale downstream.

Before changing code to explain a data mismatch, prove snapshots along the propagation path and use a controlled refresh/re-export/reload as a diagnostic when appropriate. If behavior changes only after refresh, preserve that evidence instead of hiding the data-state cause with a code patch.

## Version-gated capability

A capability observed in another release is discovery evidence, not target proof. Record the exact target product/configuration/vendor version and prove feature gates, settings, predicates, migrations/defaults and runtime effectiveness there. UI visibility, a status label or a read-only setting is not enough to prove that the capability is enabled for the current business class.

## Stateful UI mode

Temporary UI behavior is a state machine. Name the state owner and enumerate enter, consume/success, cancel, invalid input, no-data, error, selection change, repeated activation, close and reopen transitions. A mode that is cleared only on the happy path is incomplete. Transient state bound to one row/object must not leak after selection changes.

## Identity around external irreversible side effects

When an external system observes identity/projection A and the internal object becomes identity/projection B afterward, keep both temporal identities explicit:

`validate A → send/commit A externally → confirmed success boundary → transform internally to B → downstream B consumers`.

Failure or ambiguous completion must not accidentally advance to B before retry semantics are resolved. Record idempotency/correlation and independently trace reverse/refund/cancel flows. External and later internal identities may intentionally differ only when the audit/correlation contract proves that they belong to the same business event.

## Business-classification partition

A new correct predicate can still break an adjacent existing scenario. Treat related business classifiers as a partition: prove coverage, mutual exclusion, precedence and unchanged neighboring/out-of-scope behavior. Positive acceptance for only the new class is insufficient.

## Activation precision

Routing vocabulary must distinguish a mechanism from incidental serialization or domain labels. Bare `GTIN`/`SSCC` declarations identify barcode data but do not by themselves prove scanner-input normalization or runtime classification. Likewise an XML declaration such as `version="1.0"` is serialization metadata, not evidence of a version-gated product capability. Activation rules should require mechanism-specific context rather than escalate risk from these incidental tokens alone.

## Evidence boundary

These contracts do not prove a concrete parser API, BSP helper, Cleverence action, platform flag or version-specific implementation. Exact target/typical/BSP/vendor source remains required for signatures and runtime behavior; real runtime evidence remains required for device, state and cross-system outcomes.
