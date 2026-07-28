# The policy engine

Zence decides with a predicate evaluator over typed metadata. A model may help
classify what a prompt is *about*; it never decides whether something is allowed.

That constraint is the reason the rest of this document is short. There is no
expression language to specify, no sandbox to reason about, and no prompt to
tune — a rule is a set of field/predicate pairs, and the engine is a few hundred
lines of comparison.

---

## Evaluating one action

```
Action  +  [Evidence]  +  WorkspaceContext  +  Policy   →   exactly one Decision
```

`evaluate()` is pure. Same inputs, same decision, every time — which is what
makes a denial arguable rather than merely assertive.

## Precedence

Strict order. The first match wins.

| | Step | Waivable? |
|---|---|---|
| 1 | **Tamper** — the action targets `.zence/**` or Claude Code's hook config | No |
| 2 | **Deny rules** | No |
| 3 | **Ask rules** — an active exception may downgrade to allow | By exception only |
| 4 | **Allow rules** | — |
| 5 | **The fail-safe matrix** | — |

Two of those placements are load-bearing.

**Tamper is first and is triggered by a hardcoded flag**, not by a policy
condition. It also survives audit mode. Without both properties, `mode: audit`
would be a one-line way to disable Zence from inside a session it governs.

**Exceptions sit at step 3, after deny.** They can soften an ask; they can never
unlock a deny. A cross-client PII read does not become acceptable because
somebody added a YAML entry, and `Policy._validate_exceptions` rejects an
exception targeting a deny rule at load time — so the constraint holds twice.

---

## Rules

```yaml
- id: ZR-001
  title: Cross-client PII access
  decision: deny
  risk: critical
  min_confidence: high
  when:
    asset.in_domain: { equals: false }
    asset.all_tags: { intersects: "$sensitive_tags" }
  explanation: >-
    {asset.name} belongs to {asset.domain_name}, but this session is bounded to
    {active_client}. It carries {matched_tags}, and columns {matched_columns}
    are classified at field level.
  remediation: >-
    Use an asset inside {active_client}.
```

Conditions are **ANDed**. There is no `or` — a rule that needs one is written as
two rules, which also makes the audit record say which branch fired.

`min_confidence` is how extraction quality reaches the decision. A dotted name
guessed from a shell argument arrives at `medium`; `ZR-001` demands `high`, so a
fuzzy guess can inform a decision without being able to trigger a denial on its
own.

`$name` dereferences a list declared at the top of the policy, so a workspace
maintains one list of sensitive tags rather than repeating it in twelve rules.
A `$name` that resolves to nothing is a load error, because a typo that silently
became an empty list would turn a deny rule into a no-op.

### Operators

`equals` · `not_equals` · `in` · `not_in` · `intersects` · `not_intersects` ·
`matches` · `gte` · `lte` · `exists`

**`None` never satisfies a predicate, except `exists`.** This is the single most
important line in the engine. The tempting alternative — letting `not_in`
succeed against a missing domain — would fire "asset is not in an allowed
domain" for every asset Zence failed to resolve, producing confident
cross-client denials built on no evidence at all. Missing information is handled
once, explicitly, by the fail-safe matrix. Never by accident inside an operator.

`matches` is anchored (`fullmatch`), patterns are capped at 200 characters and
compiled at load time, and subjects are truncated to 4096 characters before
matching. Python's `re` has no evaluation timeout, so the bound on inputs plus
the hook's own watchdog is the defence.

### Fields

Field paths are an **allowlist**, not a `getattr` chain. Two reasons:

- a chain would let a policy file reach anywhere in the object graph
- a typo would silently evaluate to `None`, which for `not_in` reads as a match
  and quietly inverts the rule

Unknown paths are rejected when the policy loads, with a spelling suggestion.

| Prefix | Examples |
|---|---|
| `asset.` | `in_domain`, `domain_urn`, `tags`, `all_tags`, `terms`, `owners`, `environment`, `lifecycle`, `downstream_critical_count`, `resolved`, `status`, `confidence` |
| `action.` | `intent`, `tool_name`, `tool_kind`, `is_sensitive`, `targets_zence_config` |
| `workspace.` | `mode`, `active_client`, `active_domain`, `allowed_domains` |

`asset.all_tags` flattens dataset tags with every column tag. Column-level
classification is the realistic case — the dataset is fine, one field is not —
and it is what lets a denial name the offending column.

**A rule that reads asset *properties* requires a resolved lookup.** When
DataHub is unreachable `domain_urn` is `None`, and a rule keyed on "not in
allowed_domains" would fire and report a cross-client finding while the honest
"could not reach DataHub" message never appeared. Rules keyed on resolution
*state* — `asset.resolved`, `asset.status` — are exempt, since reasoning about
not having resolved something is exactly their job.

---

## The fail-safe matrix

What happens when no rule matched. This is the part worth reading twice.

| Situation | Verdict |
|---|---|
| Lookup failed, any asset referenced | **ask**, degraded, naming the failure |
| Lookup failed, sensitive action | **ask**, degraded |
| Lookup failed, no references, no sensitive intent | allow, flagged degraded |
| Asset not in the catalog, during a write | **ask** |
| Asset not in the catalog, during a read | allow |
| Resolved, outside the boundary, no rule matched | **ask** |
| Asset has no domain at all | **ask** — unclassified data in a multi-client catalog is what to ask about |
| Nothing referenced, nothing sensitive | allow |
| Everything resolved and in bounds | allow |

The governing rule: **Zence never converts ignorance into permission.** A
degraded allow is only ever returned for actions that touched no data references
at all, and it says so.

`NOT_FOUND` and `LOOKUP_FAILED` are deliberately distinct. "DataHub says this
does not exist" and "Zence could not reach DataHub" lead to different decisions,
and collapsing them would let an outage read as a clean catalog.

---

## Modes

| | |
|---|---|
| `audit` | Evaluate and record everything; downgrade blocks to allows, keeping the original verdict in `would_have_been` so `zence audit` can report exactly what enforce would have stopped. **Tamper is not downgraded.** |
| `enforce` | Allow, ask and deny for real. |
| `demo` | The same engine and the same hook path, against synthetic metadata. Not a separate decision engine. |

`zence init` scaffolds in **audit**. Blocking a team's work on the first day is
how a guardrail gets uninstalled.

---

## The shipped rules

| Rule | Decision | Fires on |
|---|---|---|
| ZR-001 | deny | Cross-client asset carrying PII |
| ZR-002 | ask | Cross-client read of an unclassified asset |
| ZR-003 | deny | Write to another client's asset |
| ZR-004 | ask | Mutation in production |
| ZR-005 | deny | Destructive operation in production |
| ZR-006 | ask | Asset marked deprecated in DataHub |
| ZR-007 | ask | Sensitive asset with no owner recorded |
| ZR-008 | ask | Change reaching a critical downstream asset |
| ZR-009 | allow | In-boundary read in a permitted environment |
| ZR-010 | allow | In-boundary code generation, nothing sensitive |
| ZR-011 | ask | Unresolvable asset during a write |
| ZR-014 | deny | Edit to Zence or Claude Code hook configuration |

**ZR-012 and ZR-013 are reserved for exception semantics** — an active exception
downgrading an ask, and an expired one having no effect. They are implemented in
`engine.py` and pinned by `tests/unit/test_exceptions.py`. They are deliberately
*not* entries in `builtin_rules.yaml`: putting a rule in a file that does not
control the behaviour would be misleading.

The explicit allows (ZR-009, ZR-010) exist so the common safe path produces a
named rule in the audit trail. "Allowed by ZR-009" is a more useful record than
"nothing objected".

### Overriding

A workspace rule sharing an id replaces the built-in one, so a single rule can
be retuned without forking all twelve:

```yaml
rules:
  - id: ZR-006          # this workspace tolerates deprecated assets
    title: Deprecated assets are acceptable here
    decision: allow
    explanation: We are mid-migration and this is expected.
    when:
      asset.lifecycle: { equals: "deprecated" }
```

---

## Exceptions

```yaml
exceptions:
  - rule_id: ZR-002
    scope:
      urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,shared.dim_date,PROD)"
    expires_at: "2026-12-31T23:59:59+02:00"
    approver: "you@example.com"
    reason: >-
      Shared date dimension. Lives in another domain for historical reasons and
      contains no client data.
```

Three constraints, all enforced when the policy loads:

- **`expires_at` is mandatory and must carry a timezone offset.** An exception
  without an expiry is a policy change wearing a disguise; one without an offset
  is ambiguous, and ambiguity here is a security bug.
- **Only an ask rule may be targeted.** Attempting to waive a deny fails
  validation.
- **Scope selects exactly one of `urn` or `domain`.**

Expiry is exclusive: an exception expiring at exactly the moment of evaluation
has expired.

---

## Testing a policy

`zence evaluate` runs the real engine over a hypothetical tool call, so a rule
can be tested without provoking a violation in a live session. Its exit code
carries the verdict, which is what makes it usable from CI:

```bash
zence evaluate --tool Write --file models/x.sql \
  --content "SELECT email FROM bluepeak.patient_contacts"
# exit 0 allow · 6 deny · 7 ask
```

`zence policy validate` checks that a file loads, that every field path exists,
that every `$reference` resolves, and that no exception targets a deny rule.

---

## Adding a rule

1. Add it to `builtin_rules.yaml` (or your workspace policy) with a `ZR-` id
2. Write unit tests for the match, the **near-miss**, and precedence against
   neighbouring rules
3. Document it here

The near-miss test matters more than the match. A rule that fires on everything
is indistinguishable from a working one until somebody is drowning in approval
prompts — at which point they stop reading them, and the guardrail is gone.
