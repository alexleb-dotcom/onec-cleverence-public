# PROFILE — EXTERNAL_COMPONENT_LIFECYCLE

Read `KNOWLEDGE/EXTERNAL_COMPONENT_LIFECYCLE.md` when this profile is active.

## Detection

- external-component install/connect/load methods;
- `ТипВнешнейКомпоненты` / `AddIn.*` object construction;
- BSP external-component connection APIs;
- external events and asynchronous external-component callbacks.

## Triggered standards

- `std669` — external-code trust, controlled storage and BSP connection policy;
- `std700` — interactive installation consent;
- `std794` — prefer platform capabilities where they cover the need.

## Mandatory review model

Treat the integration as a chain of independent proof layers:

`trusted artifact/storage → install/connect → instance → minimal health call → optional native/UI host → async callback lifecycle → provider/network/business call`.

A PASS at one layer never proves a later layer.

Review all checks generated from `RULES/rule_registry.json`, with special attention to:

- production connection mechanism vs diagnostic file selection/path;
- client/platform/OS/bitness/runtime/UI compatibility;
- one lifecycle owner for each component/native/window/subscription resource;
- parent/owner window, resize, close/destroy and reopen;
- callback after form close/disposal;
- repeated attach/open/close/reopen and duplicate subscription prevention;
- failure classification by layer;
- production trust/consent/BSP requirements;
- runtime shutdown without a hung 1C client.

## Completion rule

Static code review cannot prove native/UI/async behavior. Runtime-visible lifecycle checks remain `RUNTIME_PENDING` until exercised in the actual supported client/environment.
