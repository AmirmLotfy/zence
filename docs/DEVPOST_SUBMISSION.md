# Devpost submission — Zence

Copy-ready text for [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/).
Deadline **10 August 2026, 5:00 PM EDT**.

---

## Project name

**Zence**

## Tagline

Keep every client in bounds — a task-scoped policy firewall for Claude Code,
powered by DataHub's context graph.

## Challenge category

Metadata-Aware Code Generation & Development

## Links

| | |
|---|---|
| Repository | https://github.com/AmirmLotfy/zence |
| Live site | https://zence.site |
| Real decision artifacts | https://zence.site/demo |
| Sample outputs (in repo) | `examples/artifacts/decisions/` |
| Demo video | *(fill in after upload — YouTube, public, under 3:00)* |

---

## The problem

Freelancers, agencies and consultancies run Claude Code across several clients
from one laptop. Claude Code has no concept of *which client is in scope right
now*.

So this happens:

```sql
SELECT l.email, p.phone
FROM   northstar.marketing_leads  l   -- Client A (you are here)
JOIN   bluepeak.patient_contacts  p   -- Client B (you are not)
  ON   l.email = p.email
```

Every individual part of that is valid. The SQL parses. Both tables exist. The
developer has credentials for both — that is why they were hired. A linter sees
well-formed SQL, the warehouse sees an authorised user, and the agent sees a
reasonable way to answer the question it was asked.

The only place it is visibly wrong is in the metadata: those tables sit in
different domains, and one carries personal data at column level.

That is a question a catalog can answer. Nothing was asking it.

## The solution

Zence sits in Claude Code's hook path. Before a tool call runs it normalizes the
call, extracts the assets it touches, resolves them against DataHub, evaluates
deterministic policy against the returned metadata, and returns exactly one of
**allow / ask / deny** — with the evidence and a safe alternative.

Then it writes the decision back into DataHub as a durable document, so the
catalog learns something it did not know.

## How it works

1. **Normalize** — the tool call becomes an action with an intent (read, write,
   mutate, destructive)
2. **Extract** — SQL through a real parser (sqlglot), plus dbt `ref()`/
   `source()`, shell commands, YAML ingestion recipes, and DataHub MCP tool
   arguments. CTE names and table aliases are excluded; columns are attributed
   through aliases, which is what lets a denial name the offending field
3. **Resolve** — domain, ownership, dataset *and column-level* tags, glossary
   terms, lifecycle, environment, and two hops of downstream lineage
4. **Evaluate** — rules are field/predicate pairs over that evidence. No
   expression language, no `eval`, and no model in the decision path
5. **Decide** — one verdict, with the rule that fired, the evidence URNs, and a
   remediation
6. **Record** — locally in SQLite, and back into DataHub at session end

## How DataHub is used

DataHub is the source of truth on **both** the read and the write path, through
two surfaces that are each load-bearing.

**The MCP Server is what Zence intercepts.** Claude reads the catalog through
`mcp-server-datahub`, so a cross-client lookup shows up there first — before the
metadata reaches context. `PreToolUse` matches `mcp__.*datahub.*__.*`, covering
both a user-configured server and the one the plugin bundles.

**The Python SDK is what Zence reasons from.** A hook cannot borrow the agent's
MCP connection, and enforcement needs typed aspects rather than text shaped for
a model to read.

**Read:** domain, ownership, dataset and column-level tags, glossary terms,
lifecycle/deprecation, environment, structured properties, 2-hop downstream
lineage.

**Write:** at session end, one decision document upserted with a deterministic
id — `sha256(workspace::session)` — linked to every asset the session touched,
plus a `zence.last_review` structured property. Finalize ten times, get one
document. Idempotency is structural, not a check that can lose a race.

Zence does **not** retag, reclassify, or reassign ownership of a client's
assets. Those are your team's decisions; an agent guardrail that quietly edits
someone's catalog has become a different and worse product.

## What makes it different

Not a DataHub chatbot, catalog UI, or lineage visualiser. It is the first thing
I know of that combines repository identity, task identity, the catalog's
context graph, and Claude Code's hook path into a decision made **before** a
tool call runs.

Three design choices carry it:

- **The engine is deterministic.** A model may classify what a prompt is about;
  it never decides what is allowed. A denial is therefore arguable rather than
  merely asserted — same inputs, same decision, every time.
- **Ignorance never becomes permission.** A transport failure is never reported
  as "not in the catalog." A rule that reads asset properties will not fire
  against evidence that failed to resolve. When Zence cannot see, it asks, and
  says why.
- **An allow is invisible.** No prompt, no transcript noise, nothing. A
  guardrail that announces itself on safe work is one people uninstall.

## What I built

- A deterministic policy engine — 12 rules, 10 operators, an allowlisted field
  resolver, and an explicit fail-safe matrix
- Asset extraction across SQL, dbt, shell, YAML recipes, MCP arguments, and
  paths, with confidence levels that gate which rules may fire
- Two DataHub providers behind one interface — live (SDK) and fixture
  (recordings), never silently interchanged
- A real Claude Code plugin: 9 hook wirings, a POSIX shim that fails safe
  without parsing JSON, and a marketplace manifest
- A SQLite audit trail and idempotent DataHub write-back
- A CLI: `status`, `doctor`, `inspect`, `evaluate`, `policy validate`, `audit`,
  `demo`, `finalize`
- A synthetic two-client catalog shaped so each rule is demonstrable with a
  realistic asset
- A static site at zence.site rendering **real** engine output, kept honest by a
  CI check
- 341 tests, mypy strict, seven CI jobs, secret scanning with no allowlist

## Challenges

**Getting the failure modes right was most of the work.** Three of the worst
bugs were found by tests rather than by inspection, and all sat on the same
fault line — something that could not be looked up being treated as something
that was:

- `_find_urn` caught a connection error and returned `None`, which the caller
  read as "not in the catalog." An outage was indistinguishable from a clean
  catalog. That is the exact failure the product exists to prevent, sitting in
  my own code.
- Rules fired against unresolved evidence. A failed lookup leaves `domain_urn`
  as `None`, which satisfies "not in allowed_domains" — so a confident
  cross-client finding was produced from no evidence, while the honest "could
  not reach DataHub" message never appeared.
- The SDK's default retry-with-backoff took **28 seconds** to fail against a
  dead endpoint, in a hook with a 2.5-second budget. A DataHub outage would
  have read as Claude Code hanging.

**Precision as a safety property.** An extractor that reports table aliases and
CTE names produces a prompt on every action, people learn to approve
reflexively, and the guardrail becomes a formality. The must-not-find tests
outnumber the must-find ones.

**Not over-claiming.** The threat model opens with what Zence is *not*. It does
not intercept a shell, it is not a sandbox, and it does not replace warehouse
grants. Stating that plainly costs nothing and is the difference between a tool
you can trust and one you have to second-guess.

## Accomplishments

Scenario A — the cross-client PII join — is denied **before execution**, with
the offending columns named, the DataHub URN as evidence, and an in-domain
alternative offered. Every claim on the website is a JSON artifact from
`zence evaluate --json`, and CI fails the build if one is edited by hand.

Warm hook calls land at 0.6–0.8s against a 2.5s budget.

## What I learned

Most of a guardrail's value is in what it does when it is broken. Getting
`allow` right is easy; getting *"I could not check, so I am asking"* right —
without being so noisy that people stop reading — was the hard part, and it is
where nearly all the design effort went.

Also: verify the platform rather than remembering it. `astral-sh/setup-uv` has
no moving `v9` tag. `claude plugin validate` silently skips `plugin.json` when a
marketplace manifest sits beside it. Tailwind v4 dropped the arbitrary-value
colour shorthand, so an entire palette rendered as nothing while the build
stayed green. None of those would have been caught by assuming.

## What's next

- Approval workflows for teams, so an ask can route to an owner
- More extractors — currently SQL, dbt, shell, YAML and MCP arguments, and the
  README says so rather than implying more
- Proposals API write-back, so Zence can suggest a classification it inferred
  rather than only recording its own decision

## Built with

`python` · `datahub` · `acryl-datahub` · `mcp` · `claude-code` · `sqlglot` ·
`pydantic` · `sqlite` · `typer` · `rich` · `uv` · `nextjs` · `react` ·
`typescript` · `tailwindcss` · `vercel` · `github-actions`

---

## Judge quickstart

Everything below works from a clean clone. No account, no signup, no hosted
service.

**Without DataHub** — the engine, extraction, hooks, and 341 tests:

```bash
git clone https://github.com/AmirmLotfy/zence && cd zence
uv sync --all-packages
uv run pytest -m "not integration and not e2e"
```

**The decisions themselves**, against the recorded catalog:

```bash
uv run zence evaluate --tool Write --file models/blend.sql \
  --content "SELECT l.email, p.phone
             FROM northstar.marketing_leads l
             JOIN bluepeak.patient_contacts p ON p.email = l.email" \
  -C examples/clients/northstar-analytics
# exit 7 — ASK. Without a catalog Zence cannot see the domains, so it refuses
# to guess and says so. With DataHub running this is exit 6, DENY, ZR-001.
```

That difference is worth a moment: the same command gives a different — and
correct — answer depending on whether the catalog is reachable. Zence never
converts ignorance into permission.

**With DataHub**, for the full loop including write-back:

```bash
datahub docker quickstart
export DATAHUB_GMS_URL=http://localhost:8080 DATAHUB_GMS_TOKEN=<pat>
uv run zence demo seed && uv run zence demo verify
```

Then open Claude Code in `examples/clients/northstar-analytics/` with the plugin
installed and ask it to join the Northstar leads with the BluePeak patient
contacts.

## Open-source contribution

A `datahub-policy-context` skill contributed to `datahub-project/datahub-skills`,
covering domain-boundary and PII-aware asset selection — a byproduct of building
this, not a manufactured contribution.

## Disclosure

Newly created during the submission period. Developed with AI assistance (Claude
Code); no pre-existing project code was incorporated. Third-party frameworks are
declared in `pyproject.toml` and `package.json`. The clients, datasets and people
in the demo catalog are fictional.
