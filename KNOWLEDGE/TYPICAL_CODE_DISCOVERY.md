# TYPICAL CODE DISCOVERY — analog before invention

`KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md` is authoritative for the word «типовой». In this document, a typical 1C implementation means firm-1C-authored material from an official released 1C program/configuration; project/partner/vendor adaptations are customizations, not another kind of typical code.

## Hard rule

If the exact implementation contract is not known, do not turn uncertainty into custom code. Search for the nearest proven implementation first.

Before searching only for a code analog, ask a more basic question: does the target configuration/platform/BSP/vendor already provide a supported capability or configuration path that satisfies the requested outcome **without source-code customization**? This is an engineering discovery rule derived from the preference for supported/documented platform and library mechanisms; do not misquote it as the literal wording of one standard.

Preferred evidence order:

```text
supported target capability / setting / existing standard mechanism that needs no customization
→ exact target source / exact form or module
→ same mechanism in the exact/proven firm-1C release baseline relevant to the target
→ BSP discovery locator + exact BSP source + real call site
→ vendor/Cleverence stock implementation
→ official documentation / standards / examples
→ custom implementation only with explicit evidence that no supported capability or analog fits
```

The purpose is not blind copy/paste. Compare architecture and contract:
- input/output and side effects;
- client/server context;
- how the typical code obtains the object/query/form element;
- how it preserves settings, transactions and identity;
- error/cancel/retry behavior;
- query constructor/runtime validity;
- caller/callee signatures.

If the capability/analog is only partially applicable, state exactly which observable requirement it satisfies, which requirement remains unmet, and what evidence proves the gap. “The standard feature exists” is not proof that it covers the task; “we need customization” is not proof that it does not.

If the analog is only structurally similar, record what is proven and what remains `EVIDENCE_REQUIRED`.

## Typical 1C discovery: locator first, exact source second

For reusable/public work, do not treat a retained typical-configuration index or snapshot as the current implementation contract.

Use this flow:

```text
task intent
→ search the supplied target configuration first
→ REFERENCE/CATALOGS/typical_onec_discovery.json
→ identify likely common modules/mechanism family
→ acquire exact target source and/or exact official firm-1C release source
→ build a LOCAL_EXACT_SOURCE_INDEX when useful
→ inspect exact form/module/call site
→ apply only the mechanism details actually proved for that version
```

`REFERENCE/CATALOGS/typical_onec_discovery.json` is `DISCOVERY_ONLY`. Candidate module names are search/request hints learned from an authorized analog corpus. A hit does **not** prove that the current configuration contains the module, that a particular procedure exists, or that the analog is applicable.

The internal repository may retain `REFERENCE/INDEXES/dynamic_list_analog_index.csv` and `REFERENCE/SOURCES/TYPICAL_DYNAMIC_LIST_ANALOGS.zip` for migration regression/forensics. They are INTERNAL_FULL evidence and are not the normal public path. The derived CSV is a `NON_AUTHORITATIVE_DERIVED_CACHE`; exact target/user-authorized source wins on contradiction.

Known reusable DynamicList/query mechanism classes worth searching for include:
- complete DynamicList query returned/assigned as ordinary query language;
- exact full-query variants selected by conditions;
- controlled `СтрЗаменить` of a known fragment in a complete query;
- construction of explicit valid subqueries via arrays/`СтрСоединить` in a concrete typical mechanism;
- application of DynamicList properties through a supported BSP/target mechanism.

Do **not** infer a universal recipe from one typical example. A direct assignment or concatenation proven in one firm-1C release mechanism does not automatically justify doing the same elsewhere. Prefer the closest target/release analog and re-run standards/constructor/performance review.

## DynamicList mechanism learned from an authorized analog

One retained authorized typical snapshot contains a useful analog in the common module `КонтрольВеденияУчета`. Treat this module name as a **discovery hint**, not as a cross-version contract.

When exact target/user-authorized source proves an equivalent mechanism, the reusable pattern is:

1. Resolve the form table and the DynamicList actually bound to it.
2. Obtain the **effective query**. For a custom query this may be the DynamicList query text; for a standard/non-custom list the target implementation may obtain the executable DCS and its query. Use the exact mechanism proven by the supplied source/version.
3. Modify only a narrowly proved query shape. The retained analog demonstrates line-oriented insertion into a known simple shape, but that implementation detail is not universal.
4. Apply the changed query/properties through the supported DynamicList property mechanism used by the target/BSP version. If exact BSP routines are used, verify their exported declarations and signatures from exact source before calling them.

For a target-specific root/source modification, platform `СхемаЗапроса` may be used read-only to prove package/operator/source/alias before a narrow text insertion. This is materially different from mutating `СхемаЗапроса`: read-only topology proof does not trigger auto-join side effects. If the proved simple shape or exact source line is absent, fail closed and do not guess.

## Cleverence parity

The same evidence escalation applies to Mobile SMARTS. First check whether the accepted target/vendor configuration already exposes the needed supported setting/Business Process/hook. When an Action, writer/router, document mapping or Business Process behavior is uncertain, inspect the nearest stock operation in the accepted/reference Cleverence configuration first and compare its full execution graph, not just one XML node.

Use `KNOWLEDGE/REFERENCE_SOURCE_ARCHITECTURE.md` for the shared `DISCOVERY_ONLY → EXACT_TARGET_SOURCE → LOCAL_EXACT_SOURCE_INDEX → PROOF` contract.
