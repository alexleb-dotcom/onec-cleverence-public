# HOOK_ORCHESTRATION

Use for extension advices (`&Перед`, `&После`, `&Вместо`), object/form event handlers, command handlers, subscription hooks, and integration entry points.

## Core rule

A hook is primarily an orchestration/adaptation boundary, not the default owner of substantial domain behavior.

Preferred shape:

```text
hook/event
→ trivial applicability/routing guards
→ named domain/service API
```

Do not turn this into a dogma that every hook must be one line. Small guards and adaptation that belong specifically to the event contract may remain local. The review question is ownership and cohesion, not line count.

## Mandatory checks

- state the single responsibility of the hook;
- keep event-specific applicability/routing guards local when they are truly event-specific;
- move reusable business validation, calculations, queries, persistence, mapping and multi-step mutation to an appropriately named owner/API;
- do not place reusable business logic into borrowed/typical modules when a project-owned module can be the owner;
- name the extracted routine by domain intent, not by technical event name alone;
- verify the hook does not duplicate a rule already owned by the callee;
- verify client/server context, `Отказ`/return/mutation semantics and event ordering remain correct;
- compare with nearest typical/project hook pattern when placement is uncertain.

## Responsibility test

For every changed routine ask:

1. What is its one responsibility?
2. Does its name state that responsibility?
3. Is there an independently nameable business step inside it?
4. Is the same invariant checked elsewhere without a different trust/time boundary?
5. Which preconditions are already guaranteed by caller/platform/metadata?
