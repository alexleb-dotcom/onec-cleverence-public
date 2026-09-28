# Comment intent policy

Comments are contracts, not narration. A useful comment explains information that is not reliably recoverable from the next statement: the reason for a decision, a business invariant, a platform/vendor limitation, a non-obvious side effect or the contract of a public interface.

## Canonical 1C AUTHOR_MARKER

For 1C delivery, the Skill owns the default AUTHOR_MARKER shape. Absence of a project/user override must **not** cause a question about marker syntax.

The fixed field order is:

1. `ФамилияИО`
2. `ПервыйБит`
3. `Дата`
4. `НомерТЗ`
5. `пункты ТЗ`

`ПервыйБит` is the fixed organization marker.

### Changed / added code region

Opening marker:

```bsl
// ++ ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ
```

Closing marker:

```bsl
// -- ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ
```

Canonical region form:

```bsl
// ++ ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ
...
// -- ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ
```

### One-line change

```bsl
// ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ
```

### Object-property / metadata comment attribution

When AUTHOR_MARKER attribution is written into an object property / metadata comment field, use the same one-line form:

```text
// ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ
```

`METADATA_ATTRIBUTION` remains a separate project contract for whether/where metadata attribution is required and for any project-specific metadata-comment policy. It does not own the default 1C AUTHOR_MARKER shape.

A project/user may explicitly override the shape. Preserve that explicit override exactly when bound. Do not infer an override from one isolated historical marker.

The Skill default fixes the structure only. It does **not** invent:
- exact rendering of `Дата`;
- spelling/abbreviation rules for `ФамилияИО`;
- syntax for one or multiple `пункты ТЗ`;
- task-specific values.

## AUTHOR_MARKER pre-development gate

For an applicable 1C implementation task, AUTHOR_MARKER is a mandatory development-entry condition, not a final-output decoration.

Canonical projection:

```text
AUTHOR_MARKER_READY
→ implementation may proceed

AUTHOR_MARKER_BLOCKED
→ implementation must not begin
```

Before implementation starts, enough bound information must exist to render the applicable marker:

- `ФамилияИО`;
- a date value/policy sufficient to render `Дата`;
- `НомерТЗ`;
- applicable `пункты ТЗ`.

`ПервыйБит` is already fixed by the Skill contract and must not be requested.

Reuse valid values from current task context / Project Context. If only some values are missing, ask only for those values. Do not ask again for values already bound, and do not ask for the default marker syntax.

While `AUTHOR_MARKER_BLOCKED`:
- business/requirements clarification may continue;
- source inspection may continue;
- evidence acquisition may continue;
- architecture/design analysis and exact change-location discovery may continue;
- source mutation must not start;
- final implementation code generation must not start;
- patch/diff construction intended for delivery must not start;
- manual-transfer implementation steps containing changed code must not start;
- implementation artifacts requiring attribution markers must not be generated.

This projection uses the existing requirements / Project Context / project-bootstrap capability gate. It is not a second workflow engine, requirements gate or persistent state machine.

## Acquisition gate for a new project/chat

Do not treat arbitrary comment style as a universal default. The canonical 1C AUTHOR_MARKER above is the explicit Skill-owned exception.

Before implementation/final changed-code output, resolve from actual project context/source or ask only the still-unresolved independent contracts that affect the task:

```text
AUTHOR_MARKER
→ use the canonical Skill shape for 1C unless an explicit project/user override is bound;
  resolve only missing task values before development

TECHNICAL_COMMENT
→ when why/invariant/constraint comments are expected and what style is considered redundant

EXISTING_COMMENT_POLICY
→ whether existing comments/history markers may be edited, normalized or removed

PUBLIC_INTERFACE_COMMENT
→ required only when the task creates/changes a public/exported interface
```

Mine the supplied source/project context first. If a valid value/policy is already bound, do not ask again. One concise user question may collect several still-missing values, but persist the independent contracts separately. Silence is not evidence for an arbitrary override.

AUTHOR_MARKER value gaps block 1C implementation start. Unresolved `TECHNICAL_COMMENT` or `EXISTING_COMMENT_POLICY` continues to block final changed-code output under the existing policy. `PUBLIC_INTERFACE_COMMENT` becomes blocking only when a public/exported interface is actually created or changed.

Never invent missing author/date/task/TZ-point values or arbitrary marker syntax. For 1C, use the canonical Skill shape unless an explicit bound override says otherwise.

## Three independent classes

```text
AUTHOR_MARKER
→ who/which delivery changed code; canonical 1C shape is Skill-owned, values/explicit override are task/project context

TECHNICAL_COMMENT
→ why the algorithm is shaped this way and which invariant/constraint it preserves

PUBLIC_INTERFACE_COMMENT
→ parameters, result, allowed values, side effects, execution context and limitations
```

Keep AUTHOR_MARKER separate from technical/public documentation. A historical attribution marker is not automatically a technical comment and must not be normalized under technical-comment cleanup.

## COMMENT_INTENT

Add or retain a technical comment when code depends on a non-obvious business invariant; rounding/order/identity/concurrency/retry reason; platform/BSP/Cleverence limitation; deliberate deviation from an obvious/typical solution; or compatibility/migration/partial-failure constraint.

Do not comment a literal restatement of the next line. Prefer naming and structure for obvious mechanics. Update or remove comments that no longer match behavior only when `EXISTING_COMMENT_POLICY` permits it; historical attribution markers are not automatically normalizable comments.

For every changed comment or public interface ask:

1. Which class does it implement?
2. What fact cannot be recovered reliably from code alone?
3. Is that fact current and supported by source, project context, standard or runtime evidence?
4. Does it explain why/invariant/constraint/contract rather than what the next line does?
5. Are AUTHOR_MARKER attribution and technical/public documentation kept separate?
6. Does the current project comment contract permit changing/removing the existing comment?

Comment quality is semantic. Static matching may route the profile but cannot prove prose intent.
