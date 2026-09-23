# FORM_DATA_BINDING

Activate when a managed-form data binding is added or changed in `Form.xml` or BSL (`DataPath` / `ПутьКДанным`, dynamic form requisites, aggregate form attributes).

## Core contract

A path that is syntactically plausible is not necessarily present in the runtime form data context.

```text
metadata object exists
    ≠ form attribute contains that member
    ≠ DataPath is runtime-valid
```

For every changed binding:

1. resolve the path root to the actual form data context: an overlay/base form attribute or a proven platform pseudo-root;
2. for `A.B`, prove that `B` exists in the runtime value/shape of `A` at the binding point;
3. inspect the producer/composition of aggregate/provider-backed attributes instead of inferring members from global metadata;
4. if the form uses an own adapter attribute, prove both read/load and save/write paths and preserve the existing persistence semantics;
5. when static source cannot prove runtime shape, keep `RUNTIME_PENDING` and use a named form-open/edit/save acceptance case.

## ConstantsSet

`cfg:ConstantsSet` / `КонстантыНабор` is a particularly important case. The existence of `Constant.X` in the configuration or extension does **not** prove that `X` belongs to the concrete `ConstantsSet` held by a form attribute.

Do not approve `НаборКонстант.X` until membership in that actual set is evidenced. If the target/base mechanism does not include the constant, a separate form attribute with explicit, evidenced load/save behavior is a valid adaptation pattern; do not prescribe a specific API from memory when the target/typical source is available.

## Evidence

Prefer the smallest sufficient closure:

```text
changed Form.xml / BSL
+ companion form metadata
+ BaseForm / inherited form context when relevant
+ code or metadata that constructs/populates the aggregate value
+ exact persistent owner/read-write mechanism
+ runtime form-open/edit/save oracle when membership remains runtime-defined
```

Do not turn an unresolved nested member into `PASS` merely because the same name exists in configuration metadata.
