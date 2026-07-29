<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/zence-mark-on-dark.svg">
    <img src="brand/zence-mark-on-light.svg" alt="Zence" width="132">
  </picture>
  <h1>Zence</h1>
  <p><strong>Keep every client in bounds.</strong></p>
  <p>
    A task-scoped context and policy firewall that keeps Claude Code inside the correct
    client, domain, and environment — using DataHub's metadata graph as the source of truth.
  </p>
</div>

---

> **Live:** [zence.site](https://zence.site) · Built for
> [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/).
>
> Everything described below is implemented and covered by tests — 401 of them, plus fifteen
> run against a live DataHub instance. What Zence deliberately does *not* do has its own
> section, and the boundary is stated rather than implied. You can check any of it in about a
> minute at [zence.site/verify](https://zence.site/verify/).

## The problem

Freelancers, agencies and consultancies run Claude Code across several clients from one machine.
Claude Code has no concept of *which client am I allowed to touch right now*.

A single catalog search, a `JOIN`, or one `Write` can pull Client B's PII into Client A's
repository — and nothing stops it, because every individual tool call is perfectly valid. The
mistake only exists at the level of *boundary*, and nothing in the loop is tracking that.

```sql
-- Perfectly valid SQL. Catastrophic in a consultancy.
SELECT l.email, p.phone
FROM   northstar.marketing_leads  l          -- Client A  (you are here)
JOIN   bluepeak.patient_contacts  p          -- Client B  (you are not)
  ON   l.email = p.email
```

## What Zence does

Zence sits in Claude Code's hook path. Before a tool runs, it:

1. **Normalizes** the tool call into a Zence action
2. **Extracts** dataset, table, column, path and environment references
3. **Resolves** those references against DataHub
4. **Evaluates** deterministic policy against the returned metadata
5. **Returns** exactly one decision — `allow`, `ask`, or `deny` — with evidence and remediation
6. **Records** the decision, and writes a durable decision document back into DataHub

The evidence is real DataHub metadata: domains, ownership, tags, glossary terms, lifecycle
status, schemas and lineage. Not a guess from the prompt text.

```
✗ Denied by Zence — ZR-001 Cross-client PII access

  bluepeak.patient_contacts belongs to domain "BluePeak Health"
  Your active boundary is  "Northstar Commerce"
  Asset carries            urn:li:tag:PII, urn:li:glossaryTerm:PersonalData
  Columns email, phone     tagged PII at field level
  Evidence                 urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)

  → Northstar has an in-domain equivalent: northstar.dim_customer (DEV)
```

## Three decisions, not two

| | | |
|---|---|---|
| **allow** | In-domain, allowed environment, no sensitive references | Runs, and is recorded |
| **ask** | Ambiguous, production, deprecated, or critical downstream impact | You decide; both outcomes audited |
| **deny** | Cross-client PII, cross-client write, destructive production mutation | Blocked before execution |

Zence never silently allows a cross-client operation because a metadata lookup failed. When it
cannot see, it asks — or it stops.

## How DataHub is used

DataHub is foundational, not decorative. It is used on both the read and the write path.

**Read** — domain, ownership, tags, glossary terms, schema fields (including field-level tags),
lifecycle/deprecation status, structured properties, and 2-hop downstream lineage.

**Write** — at session finalization, Zence upserts a **decision document** into DataHub linked to
the assets involved, plus a `zence.last_review` structured property. The document `id` is
deterministic, so re-running finalization updates the record rather than duplicating it.

The **DataHub MCP Server** is the surface Zence intercepts: Claude reads the catalog through it,
and Zence's `PreToolUse` hook matches on those tool calls. Zence's own evidence lookups and
write-backs go through the DataHub Python SDK directly, because a hook must be deterministic and
cannot borrow Claude's MCP client.

## Requirements

| | |
|---|---|
| Python | 3.11+ (managed by [`uv`](https://docs.astral.sh/uv/)) |
| DataHub | OSS/Core — `datahub docker quickstart` (needs ~8 GB RAM, 13 GB disk for Docker). **Optional** for the recorded path below |
| Claude Code | 2.1.x |
| OS | macOS or Linux |

## Trust boundary

Zence reduces **accidental and agent-mediated mistakes inside the supported Claude Code
workflow**. It is not a kernel sandbox, not an endpoint security product, and not a substitute for
warehouse permissions. A user who runs the same query directly in a shell is outside its scope,
and it says so rather than pretending otherwise.

## Deliberately out of scope

Stated up front so nothing is over-claimed:

- General Python/TypeScript/Java source analysis — extraction covers SQL, dbt, shell, YAML
  recipes, and MCP tool arguments
- Hook bypass prevention outside Claude Code
- Tag/term mutation on real client assets — Zence advises, it does not reclassify your catalog
- Multi-user approval workflows and RBAC
- Windows support

## Documentation

| | |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | How the pieces fit |
| [Policy engine](docs/POLICY_ENGINE.md) | Rules, precedence, the fail-safe matrix |
| [DataHub integration](docs/DATAHUB_INTEGRATION.md) | What is read, what is written |
| [Claude Code plugin](docs/CLAUDE_CODE_PLUGIN.md) | Hooks, the shim, validation |
| [Threat model](docs/THREAT_MODEL.md) | What this protects against, and what it does not |
| [Demo environment](docs/DEMO_ENVIRONMENT.md) | The synthetic catalog and four scenarios |
| [Test strategy](docs/TEST_STRATEGY.md) | What is tested and why |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | When something misbehaves |
| [Brand](brand/README.md) | The mark, which file to use where, and how it is generated |

## See a real decision in one minute

No DataHub, no Docker, no account. The demo workspace ships a catalog recording
captured from a live instance, so a fresh clone produces the real thing:

```bash
git clone https://github.com/AmirmLotfy/zence && cd zence
uv sync --all-packages

uv run zence evaluate --tool Write --file models/blend.sql \
  --content "SELECT l.email, p.phone
             FROM northstar.marketing_leads l
             JOIN bluepeak.patient_contacts p ON p.email = l.email" \
  -C examples/clients/northstar-analytics
# ✗ DENY  ZR-001  Cross-client PII access        (exit 6)
```

Every decision produced that way is stamped `provider: fixture` — a recording
can never present itself as a live read. Export `DATAHUB_GMS_URL` and it takes
precedence over the recording, because someone who names a catalog means it.

More paths to check this yourself, and direct links into the code behind each
claim, are at **[zence.site/verify](https://zence.site/verify/)**.

## Quick start

```bash
/plugin marketplace add AmirmLotfy/zence
/plugin install zence@zence
```

Then, in each client repository:

```bash
zence init --client "Northstar Commerce" --domain "urn:li:domain:northstar-commerce"
```

That scaffolds `.zence/policy.yaml` in **audit mode** — every decision recorded,
nothing blocked. Watch `zence audit list` for a few days, then switch to
`enforce`. Blocking a team's work on day one is how a guardrail gets uninstalled.

## License

[Apache License 2.0](LICENSE).

## Disclosure

Built for the DataHub Agent Hackathon and developed with AI assistance (Claude Code). No
pre-existing project code was incorporated; standard open-source frameworks and libraries are
declared in `pyproject.toml` and `package.json`.
