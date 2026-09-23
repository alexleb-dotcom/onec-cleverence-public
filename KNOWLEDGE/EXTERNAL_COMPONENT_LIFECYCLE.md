# External component and native resource lifecycle

## Purpose

Use this contract for 1C external components (Native API/COM where applicable), embedded/native UI runtimes, device/add-in integrations and asynchronous callbacks/events. It generalizes recurrent failure classes without inventing a component-specific API.

## 1. Separate diagnostics from production architecture

A manual file picker can be useful to prove that a particular binary is visible and loadable on a workstation. That does **not** make arbitrary path/ProgID loading a production pattern.

Current 1C standards require controlled trust/storage for external code. When BSP is present, use its external-component APIs and do not bypass them with direct platform connection methods unless an authoritative project/version constraint proves an exception. Components shipped with the configuration belong in external-component layouts; third-party components require controlled administrator-managed storage/source and the applicable installation-consent flow.

## 2. Use a staged health ladder

Diagnose in this order and retain evidence per stage:

1. exact component artifact/build and trusted source/storage;
2. install/connect result in the target client/environment;
3. component object/instance creation;
4. smallest side-effect-light health/capability method;
5. native/embedded UI host, if any;
6. callback/event flow, if any;
7. external provider/network/business request.

Do not debug provider credentials, HTTP, HTML or JavaScript while component connect/instance/health is unresolved. Conversely, a provider failure must not cause a proven host layer to be rewritten without evidence.

## 3. Prove the execution/compatibility matrix

Record the exact 1C platform/client, OS, process architecture/bitness, component build, required native runtime and UI capability. Native API support varies by execution environment and UI/window support is narrower than basic component loading. Current 1C documentation explicitly states that component-created window support is unavailable in the Web client, so desktop success cannot be generalized to every client.

Exact component API names, constructor strings, directives and callback signatures remain `SOURCE_REQUIRED`: inspect the actual component contract and target/official source rather than copying a remembered example.

## 4. Every native resource needs a lifecycle owner

For each component instance, WebView/browser runtime, native window, event/callback subscription, timer/thread bridge or similar resource, name:

- who creates/attaches it;
- what form/session/application lifetime it belongs to;
- how duplicate initialization is prevented;
- who detaches/unsubscribes/closes/destroys it;
- what happens when initialization fails halfway;
- what happens during form close and application shutdown;
- whether reopen creates a fresh valid resource or safely reuses an existing one.

Creation without a symmetric destruction/owner contract is a blocking lifecycle gap because the observable failure may be a hung 1C client rather than a normal exception.

## 5. Native UI is more than 'window opened'

For component-created/embedded UI prove the actual parent/owner relationship and distinguish embedded child UI from an unrelated top-level window. Runtime acceptance should cover initial placement, activation/focus where material, resize/minimize, form close, application close and reopen.

Official 1C Native API documentation exposes parent-window integration concepts (`IExtWndsSupport`, application frame handles) and documents environment restrictions. Do not infer a WebView2-specific implementation API from that platform contract; the exact component implementation remains component-source evidence.

## 6. Async callbacks outlive synchronous call stacks

For every external event/async callback record:

`initiator → immediate return/operation identity → callback entrypoint → correlation/state owner → success/error completion → cleanup`.

Explicitly test the race where the form/resource is closed before completion. A late callback must not mutate disposed UI/state or call a released native resource. Re-entry and duplicate callback/subscription behavior need their own disposition.

External-component events can be routed by the platform (for example through `ОбработкаВнешнегоСобытия`); exact callback availability and signature still require current target/platform/component evidence.

## 7. Keep external I/O outside DB transaction ownership

Do not hold a database transaction/lock while waiting for an external component/provider when the operation can be split. If the business contract makes coupling unavoidable, state timeout, rollback/retry/idempotency and partial-failure semantics explicitly.

## 8. Runtime acceptance matrix

At minimum, when applicable:

- production package/storage path installs/connects successfully;
- component instance is created;
- minimal health call succeeds;
- UI host opens in the intended parent;
- host follows resize/minimize as required;
- form closes without a leaked window or hung client;
- the scenario can be reopened/repeated;
- normal callback succeeds;
- close while callback is pending is safe;
- provider/network/auth/schema failure is reported as downstream from an otherwise healthy host;
- client/application shutdown is clean.

A first successful display or one successful provider request is not a lifecycle acceptance oracle.

## Official evidence anchors

- 1C standard `std669`: https://its.1c.ru/db/content/v8std/src/600/i8100669.htm
- 1C standard `std700`: https://its.1c.ru/db/content/v8std/src/1%20200/900/i8100700.htm
- 1C standard `std794`: https://its.1c.ru/db/content/v8std/src/600/i8100794.htm
- Platform overview: https://v8.1c.ru/platforma/tehnologiya-vneshnih-komponentov/
- Native API/window contract: https://its.1c.ru/db/content/metod8dev/src/developers/platform/i8103221.htm

These sources prove platform/standard boundaries. They do not prove a third-party component's own methods or lifecycle implementation.
