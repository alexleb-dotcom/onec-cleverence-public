# Comment intent policy

Comments are contracts, not narration. A useful comment explains information that is not reliably recoverable from the next statement: the reason for a decision, a business invariant, a platform/vendor limitation, a non-obvious side effect or the contract of a public interface.

## Acquisition gate for a new project/chat

Do not treat comment style as a universal default. Before the first **final code output** for a new target project, resolve from actual project context/source or ask the user about these independent contracts when they affect the change:

```text
AUTHOR_MARKER
→ how changed/new code is attributed; author/company/task/date/opening/closing syntax

TECHNICAL_COMMENT
→ when why/invariant/constraint comments are expected and what style is considered redundant

EXISTING_COMMENT_POLICY
→ whether existing comments/history markers may be edited, normalized or removed

PUBLIC_INTERFACE_COMMENT
→ required only when the task creates/changes a public/exported interface
```

`METADATA_ATTRIBUTION` is a separate contract for metadata `Comment` / `Комментарий` and is not a substitute for code-comment policy.

Mine the supplied source/project context first. If the policy is already evidenced, do not ask again. If it is unresolved, one concise user question may collect several answers, but persist the fields independently. An answer such as “специальных требований нет” is a valid explicit project decision; silence is not.

Unresolved `AUTHOR_MARKER`, `TECHNICAL_COMMENT` or `EXISTING_COMMENT_POLICY` blocks final implementation output for changed code, while unaffected analysis may continue. `PUBLIC_INTERFACE_COMMENT` becomes blocking only when a public/exported interface is actually created or changed.

Never infer an author/company/date/task-marker format from another project, universal examples or one isolated historical marker.

## Three independent classes

```text
AUTHOR_MARKER
→ who/which delivery changed typical or vendor code

TECHNICAL_COMMENT
→ why the algorithm is shaped this way and which invariant/constraint it preserves

PUBLIC_INTERFACE_COMMENT
→ parameters, result, allowed values, side effects, execution context and limitations
```

`AUTHOR_MARKER` syntax belongs to project context. Never invent or universalize an author, company, prefix, task number, date or marker format from one example.

## COMMENT_INTENT

Add or retain a technical comment when code depends on a non-obvious business invariant; rounding/order/identity/concurrency/retry reason; platform/BSP/Cleverence limitation; deliberate deviation from an obvious/typical solution; or compatibility/migration/partial-failure constraint.

Do not comment a literal restatement of the next line. Prefer naming and structure for obvious mechanics. Update or remove comments that no longer match behavior only when `EXISTING_COMMENT_POLICY` permits it; historical attribution markers are not automatically normalizable comments.

For every changed comment or public interface ask:

1. Which class does it implement?
2. What fact cannot be recovered reliably from code alone?
3. Is that fact current and supported by source, project context, standard or runtime evidence?
4. Does it explain why/invariant/constraint/contract rather than what the next line does?
5. Are project author markers separate from technical/public documentation?
6. Does the current project comment contract permit changing/removing the existing comment?

Comment quality is semantic. Static matching may route the profile but cannot prove prose intent.
