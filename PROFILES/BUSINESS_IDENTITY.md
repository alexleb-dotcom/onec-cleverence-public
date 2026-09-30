# PROFILE — BUSINESS_IDENTITY

## Detection

- deduplication, grouping, matching, search or merge keys;
- one-plan-many-fact or split/merge flows;
- packaging, unit, coefficient, barcode, presentation or another representational field is proposed as part of identity;
- 1C ↔ Cleverence mapping changes the fields used to recognize the same business entity/line;
- a warehouse/container/marking/logistics/regulatory identifier is treated as equivalent to another domain identifier.

## Mandatory invariant

Use the smallest stable set of fields that answers “is this the same business entity or line?”. Keep representation and quantity normalization separate from identity unless the business domain explicitly proves that the representation creates a different entity.

Do not silently add packaging, unit, coefficient, barcode, display text or converted quantity to a deduplication/grouping/search key. Such a field may vary while the business entity remains the same, or remain the same while different entities exist.

Do not collapse identities from different domains merely because they travel through the same workflow. In marking/warehouse scenarios distinguish, unless exact project evidence proves a mapping:

```text
trade-item type / GTIN
individual marked or serialized item
warehouse plan/fact line
internal warehouse box/container
logistics unit / SSCC
regulatory aggregation/package fact
```

An internal container is not automatically a logistics/regulatory package, and a product identifier is not automatically an individual physical-item identity. Equivalence is accepted only with an explicit end-to-end mapping and lifecycle contract.

## Mandatory checks

- name the identity owner and the exact business relation it represents;
- classify every key field as intrinsic identity, scope/tenant boundary, representation, quantity normalization or service/transport field;
- when multiple domains participate, classify each identifier by domain role and prove every claimed equivalence/mapping across producer, persistence/exchange and consumer;
- prove why each included field changes sameness rather than only display or conversion;
- prove why every excluded intrinsic field cannot merge distinct entities;
- verify producer, mapping, storage, grouping/search and consumer use the same invariant;
- cover changed packaging/unit/barcode with stable identity and distinct identity with equal presentation;
- preserve one-plan-many-fact and split/merge behavior without quantity loss or duplicate lines;
- when identity-sensitive behavior changes, cover relevant adversarial symmetry: filled/empty input, entity A/B, new/existing object or fact, and first/reverse operation order;
- for any derived key that controls row/index/register/object/fact creation, complete all type/domain/completeness/required-uniqueness checks before the first `Добавить()`/`Вставить()`/`Записать()` or other result mutation.

Required order:

```text
derive
→ validate type/domain/completeness/required uniqueness
→ mutate
```

## Completion rule

An identity key is accepted only with a stated business invariant, counterexamples and pre-mutation validation. “The field is available and makes the key more unique” is not evidence. “These identifiers refer to the same box/item” is also not evidence when they belong to different warehouse, logistics, marking or regulatory domains. Unresolved identity semantics or mutation before key validation are `EVIDENCE_REQUIRED`/`BLOCKING_DEFECT` according to side effects.
