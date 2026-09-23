# ROLE_RIGHTS_STRUCTURE

Activate for `Roles/*/Ext/Rights.xml` or XML in namespace `http://v8.1c.ru/8.2/roles`.

## Contract

- Parse the exact final `Rights.xml`; do not infer role permissions from object names, right names or remembered platform behavior.
- Validate global role flags, object/right structure, duplicate rights, RLS condition containers and restriction templates structurally.
- Bind `Rights.xml` to the companion `Roles/<Role>.xml` when present and verify role identity from actual metadata.
- Interpret absence of `<right>` version-aware. For Rights format 2.19+ the dump may omit rights whose value equals `setForNewObjects`; therefore an absent node is not evidence of an explicit denial or an explicit granted right.
- Structural presence of RLS is not proof that the condition is semantically correct, performant, or produces the intended effective access.
- Do not map a human-readable right name directly to the requested user behavior. For changed access behavior build an explicit user-action matrix and prove the effective result for every material action separately: programmatic data read, reference presentation, input-by-string/autocomplete, opening a selection form, viewing a list, selecting a value, opening an object/card and editing.
- A recipe such as “grant X / deny Y” is not universal platform evidence. When different interactive routes are expected to have different outcomes, prove that the actual target configuration/platform combination supports that distinction.
- Effective authorization changes require Configurator/runtime evidence under representative users/roles; static XML PASS is only structural evidence.

## Evidence

Run `TOOLS/analyze_onec_xml.py` on the smallest role/configuration directory or ZIP that preserves `Rights.xml` and its companion role metadata. For access conclusions also inspect the target configuration's actual access model and representative runtime behavior. Record the requested user-action matrix and its runtime/Configurator result instead of inferring behavior from right labels.
