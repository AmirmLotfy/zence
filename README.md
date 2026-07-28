<div align="center">
  <h1>Zence</h1>
  <p><strong>Keep every client in bounds.</strong></p>
  <p>
    A task-scoped context and policy firewall that keeps Claude Code inside the correct
    client, domain, and environment — using DataHub's metadata graph as the source of truth.
  </p>
</div>

---

> **Live:** [zence.site](https://zence.site) · **Status: in active development** for
> [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/).
> This README documents intended behaviour. Anything not yet covered by a passing test is
> marked **(not yet implemented)**. Nothing here is claimed as working before it is demonstrated.

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
| DataHub | OSS/Core — `datahub docker quickstart` (needs ~8 GB RAM, 13 GB disk for Docker) |
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

## License

[Apache License 2.0](LICENSE).

## Disclosure

Built for the DataHub Agent Hackathon and developed with AI assistance (Claude Code). No
pre-existing project code was incorporated; standard open-source frameworks and libraries are
declared in `pyproject.toml` and `package.json`.
