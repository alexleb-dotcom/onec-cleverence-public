# PROFILE — REFERENCE_SELECTION_CONTRACT

## Detection

Activate when a 1C change controls which reference/object values may be selected in a form field, including `ПараметрыВыбора`, `СвязиПараметровВыбора`, selection handlers or equivalent project/typical mechanisms.

## Core invariant

Do not collapse different user-facing contracts:

```text
data access
≠ general visibility
≠ interactive view
≠ reference selection
≠ business admissibility in the current field/scenario
```

A requirement “the object must not be selectable here” is not automatically a requirement to hide the object globally, deny read/view rights, remove it from ordinary lists or make historical references unreadable.

## Mandatory checks

- state the exact business admissibility rule and the form field/scenario where it applies;
- prove whether the requirement is about access/security, visibility, selection, or post-selection business validation instead of choosing one mechanism by convenience;
- before custom filters/handlers, inspect the target/typical supported selection mechanism (`ПараметрыВыбора`, `СвязиПараметровВыбора` or another evidenced equivalent) and its update/runtime constraints;
- prove all applicable selection routes: selection form, input-by-string/autocomplete, pick/selection command, alternative selection form and any custom handler;
- define behavior for an already persisted value that later becomes inadmissible: display/open/history semantics are separate from selecting a new value;
- identify programmatic assignment/import/fill/copy routes that bypass interactive selection; if the business invariant must hold there too, assign a separate validation owner instead of pretending UI selection restriction is a security boundary;
- do not satisfy “cannot select” by global RLS/query hiding unless the requirement explicitly calls for that broader access/visibility restriction and effective behavior is proven;
- runtime acceptance must include at least one allowed and one forbidden value through every materially distinct active selection route.

## Evidence

Prefer the smallest sufficient closure:

```text
changed form/metadata/module
+ actual field selection properties/handlers
+ nearest target/typical selection example
+ relevant rights only when access itself changes
+ runtime allowed/forbidden selection cases
```

Unknown selection-route behavior remains `EVIDENCE_REQUIRED`/`RUNTIME_PENDING`; a value disappearing from one list is not proof that the complete selection contract is enforced.
