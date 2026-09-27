# 1C terminology contract — «типовое» vs «доработки»

This document is a **normative vocabulary contract** for every chat and every project that uses this skill. It is loaded during normal bootstrap and overrides colloquial or partner-specific usage of the same words.

## Reserved meaning of «типовой»

Within this skill, the words **«типовой» / «типовая» / «типовое»** are reserved for artifacts of firm **1C** that are part of an official released 1C program/configuration.

An artifact may be called `ТИПОВОЙ_1C` only when both conditions are true:

```text
authored_by = FIRM_1C
AND
present_in_official_1c_release = TRUE
```

When the claim concerns a concrete target release, the artifact/fragment must also be proven to belong to that exact release or to match it for the property being discussed.

Everything that does not satisfy this definition is a **«доработка»** for 1C project terminology.

## Canonical terms

### Типовая конфигурация

`ТИПОВАЯ КОНФИГУРАЦИЯ` means the official configuration as released by firm 1C, without customer, partner, integrator or project-specific changes.

If a working configuration originated from a 1C release but contains any project changes, call it:

```text
конфигурация на базе типовой
конфигурация на базе типовой с доработками
доработанная типовая конфигурация
```

Do not describe the whole changed target as simply «типовая конфигурация» when the distinction matters.

### Типовой код

`ТИПОВОЙ КОД` means code authored by firm 1C and present in an official 1C release.

A code block added by a customer, franchisee, partner, integrator or another vendor is a `ДОРАБОТКА`, even when it is located inside a module that originally came from a typical 1C configuration.

A copied or adapted fragment from a typical 1C release placed into a project-owned/custom artifact is still a `ДОРАБОТКА` in the target artifact. It may be described as «заимствовано/адаптировано из типового кода», but not as target typical code.

### Типовой объект / модуль с доработками

When an object/module exists in the official 1C release but has project changes, use the mixed-origin wording:

```text
типовой объект с доработками
типовой модуль с доработками
доработка типового объекта/модуля
```

The changed fragment is a `ДОРАБОТКА`. Unchanged fragments may be called typical only when comparison/evidence against the relevant official release proves that they are unchanged for the discussed property.

### Доработка

`ДОРАБОТКА` is every 1C artifact, fragment, object, extension, metadata change or behavior that is not part of the official firm-1C release under the definition above.

This includes, without exception based only on reputation or partner status:

- customer code;
- code written by a 1C franchisee;
- code written by an integrator or implementation partner;
- sector/vendor adaptations not released by firm 1C as part of the referenced 1C program/configuration;
- project extensions and added metadata objects;
- changed fragments inside originally typical modules/objects;
- copied/adapted typical fragments moved into project-owned/custom artifacts.

## Terms that must not be conflated with «типовой»

`ПЛАТФОРМЕННЫЙ` describes the 1C platform/API/runtime mechanism. A platform API is not «типовой код» merely because firm 1C owns the platform.

`БСП` describes the Standard Subsystems Library. BSP source is `ТИПОВОЙ_1C` for the target only when the relevant BSP code is actually included in the official 1C release being discussed. A BSP source from another distribution/version is a 1C reference, not proof that the target contains the same typical code.

`ШТАТНЫЙ` / `ВЕНДОРСКИЙ` may describe stock Cleverence or another third-party product mechanism. These words do not mean `ТИПОВОЙ_1C`.

`СТАНДАРТНЫЙ`, `РЕКОМЕНДУЕМЫЙ`, `ПОДДЕРЖИВАЕМЫЙ`, `ВСТРОЕННЫЙ` and `ТИПОВОЙ` are not synonyms. A supported or recommended mechanism may still be a customization; a typical 1C mechanism may still require version-specific proof before reuse.

## Unknown origin is not permission to say «типовой»

If origin/release membership is not proven, do not label the artifact as typical.

Use:

```text
не подтверждено как типовое
происхождение не доказано
для целей анализа до подтверждения трактуется как доработка
```

This is an evidence state, not a claim that firm 1C definitely did not author the code. The important rule is fail-closed vocabulary: **«типовой» requires proof; absence of proof cannot create typical status.**

## Version boundary

Typicality is release-aware.

Code that is typical in release `R2` is not automatically typical in target release `R1`. When comparing versions, say:

```text
типовой код релиза R2 — reference/analog
```

until the target release proves the same artifact/fragment exists there.

## Required wording examples

Incorrect under this contract:

```text
«типовой код партнера»
«типовая доработка интегратора»
«типовой модуль Cleverence»
«в типовой конфигурации клиента» — when the target has project changes and the distinction is material
```

Correct:

```text
«доработка партнера»
«доработка интегратора в типовом модуле»
«штатный/вендорский механизм Cleverence»
«конфигурация на базе типовой с доработками»
«типовой код релиза 1C <version>»
```

## Evidence and analysis rule

When the task distinguishes typical code from custom changes, classify source provenance before making recommendations:

```text
exact official 1C release / exact target baseline / reliable diff
→ prove typical fragment/object

project-only addition or deviation from the official release
→ customization

origin unresolved
→ not proven as typical; treat as customization for analysis until resolved
```

Do not infer typicality from object names, common module names, BSP-like naming, comments, coding style, partner status, customer statements such as «у нас почти типовая», or the fact that a mechanism resembles another 1C release.

## Relation to reference discovery

A `typical_onec_discovery` locator may help find a likely 1C release analog. It does not grant `ТИПОВОЙ_1C` status to the target artifact. Exact target/release source still proves the classification.

This terminology contract governs user-facing prose, review findings, project context, source classification, analog selection and knowledge extraction. Project-specific language may add narrower terms, but it may not redefine `ТИПОВОЙ_1C` to include project/partner/vendor modifications.
