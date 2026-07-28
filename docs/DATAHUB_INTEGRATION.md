# DataHub integration

Zence has no opinions of its own about your data. Every boundary it enforces is
something DataHub already knows — which domain an asset belongs to, what it is
classified as, who owns it, and what breaks downstream if it changes.

It uses DataHub on both the read and the write path.

---

## Two surfaces, on purpose

This is the design decision the rest of the integration follows from.

**The MCP Server is what Zence intercepts.** Claude reads the catalog through
`mcp-server-datahub`, so a cross-client lookup shows up there first — before the
metadata is in context, before it informs a query. `PreToolUse` matches on
`mcp__.*datahub.*__.*`, which covers both a user-configured `mcp__datahub__*`
server and the `mcp__plugin_zence_datahub__*` one the plugin bundles. Matching
only one would leave a hole depending on how the server happened to be
registered.

**The Python SDK is what Zence reasons from.** A hook cannot borrow Claude's MCP
connection — it belongs to the agent — and enforcement needs typed aspects, not
text shaped for a model to read. So evidence and write-back go through
`acryl-datahub` directly.

Both halves are load-bearing. Remove the MCP server and Zence stops seeing
catalog access; remove the SDK and its decisions stop being defensible.

---

## Read path

Per asset, on every intercepted call, through `LiveProvider`:

| What | Used by |
|---|---|
| Domain | ZR-001, ZR-002, ZR-003 — the boundary itself |
| Ownership | ZR-007, and named in the remediation so you know who to ask |
| Dataset tags | sensitivity |
| **Column-level tags** | the realistic case: dataset is fine, one field is not |
| Glossary terms | protected classifications |
| Lifecycle / deprecation | ZR-006 |
| Environment | ZR-004, ZR-005, ZR-009 |
| **Downstream lineage, 2 hops** | ZR-008 |
| Structured properties | environment fallback |

Two hops covers `table → transform → dashboard`, which is the shape ZR-008 is
written for, and keeps the call inside the hook's latency budget.

### Resolution

A reference becomes a URN either directly (the extractor found one) or through
search. Search results are **not** taken on trust: Zence requires an exact tail
match on the qualified name, because accepting the top hit would let `leads`
resolve to whichever client's `leads` table ranks highest — precisely the
mistake this tool exists to prevent.

### Performance

- 60-second TTL cache, in-process only. Nothing is cached to disk; a stale
  catalog on disk is exactly the failure Zence is meant to prevent.
- Failures cache for 5 seconds, so a recovered DataHub is noticed within a turn
  rather than a minute.
- **Retries disabled, 4-second timeout.** The SDK's defaults retry with backoff
  and take ~28 seconds to fail against a dead endpoint — an order of magnitude
  past a hook's budget, and long enough that an outage reads as Claude Code
  hanging.

### When it fails

`LOOKUP_FAILED` and `NOT_FOUND` are different states and always stay that way.
"DataHub says this does not exist" and "Zence could not reach DataHub" lead to
different decisions, and collapsing them lets an outage read as a clean catalog.
See [THREAT_MODEL.md](THREAT_MODEL.md#failing-open-on-an-outage).

---

## Write path

Zence writes what it learned back. This is the "beyond reading metadata" half:
the catalog gains something it did not have, and the next person to open
`bluepeak.patient_contacts` can see that an agent session was stopped from
reaching it, when, and under which rule.

### The session decision document

At `Stop`, and on `/zence:finalize`, Zence upserts one document:

```python
Document.create_document(
    id="zence-session-<sha256(workspace::session)[:16]>",
    title="Zence session review — Northstar Commerce",
    text=markdown_body,
    subtype="Decision Record",
    related_assets=[...],          # every asset the session touched
    custom_properties={...},       # workspace, session, policy version, key
)
client.entities.upsert(document)
```

The body leads with what was **blocked**, then what needed approval, then a
count of what was allowed grouped by rule. It is written for the person who
finds it six weeks later with no memory of the session.

### Idempotency

The id is derived from workspace and session, so upserting twice updates one
record. **Structural, not defensive** — there is no "check if it exists" round
trip to lose a race against, and no retry path that can produce a second
document. Finalize ten times, get one document with a later `updated_at`.

Locally, a `UNIQUE` constraint on the idempotency key records each attempt, so
the audit trail shows that a repeat was recognised rather than silently ignored.

### What Zence will not write

It does not retag, reclassify, reassign ownership, or change lifecycle on your
assets. Those are your team's decisions about your data, and an agent guardrail
that quietly edits a client's catalog has become a different and worse product.
Zence records its own findings alongside them, stamped with its own provenance.

---

## Connecting

```bash
# The plugin prompts for these at enable time and stores the token in your
# system keychain. Nothing is written to a workspace file.
DATAHUB_GMS_URL=http://localhost:8080
DATAHUB_GMS_TOKEN=<personal access token>
```

Resolution order — plugin option, then environment, then
`.zence/project.yaml`, then `http://localhost:8080`. The token is **only** ever
read from the first two. A token in a workspace file is a token in someone's git
history.

The bundled MCP server is configured with mutation tools enabled, which is what
makes the write-back demonstrable:

```json
{
  "TOOLS_IS_MUTATION_ENABLED": "true",
  "TOOLS_IS_USER_ENABLED": "true"
}
```

Check the connection with `zence doctor`. It reports the token as present or
absent and never prints it.

---

## Versions

| | |
|---|---|
| DataHub | OSS/Core, 1.6.x. `datahub docker quickstart` needs ~8 GB RAM and 13 GB disk |
| `acryl-datahub` | ≥1.6.0 — an optional extra, so unit and contract tests run without it |
| `mcp-server-datahub` | 0.6.0, pinned in `.mcp.json`. Mutation tools need ≥0.5.0 |
| Python | ≥3.11 (`mcp-server-datahub`'s floor) |

The SDK is optional deliberately. Most of the codebase — the engine, extraction,
the hooks, the website — is developed and tested against recorded fixtures, and
requiring a 200 MB install to run the test suite would push contributors away.

Two SDK details worth knowing, both verified against the installed package
rather than assumed:

- `datahub.sdk` has no `Domain` entity yet, so demo seeding emits
  `DomainPropertiesClass` directly.
- The simple `(name, type)` schema-field form cannot carry tags, so columns with
  field-level classification are built as full `SchemaFieldClass` objects.

---

## Fixtures

Every fixture in this repository is a **capture of a real response**, produced
by `zence demo record` and carrying the endpoint, DataHub version and timestamp
it came from. `FixtureProvider` refuses a file without that provenance.

A hand-written fixture encodes what its author assumed DataHub returns, which is
exactly the thing worth testing against reality.

**A fixture is never a fallback for an unreachable catalog.** They are used only
when a workspace points at one explicitly. Every piece of evidence carries
`provider: live | fixture`, and that value reaches the decision, the audit
record, and `zence status`. A decision made against a recording and presented as
live would be worse than no decision at all.

---

## The demo catalog

```bash
zence demo seed      # idempotent; safe to re-run
zence demo verify    # exits non-zero on the first gap
zence demo record    # capture responses into a fixture
```

`verify` matters more than it looks. Seeding is a batch of upserts that mostly
succeed, and "mostly" is how a demo fails in front of an audience: one missing
column tag and Scenario A quietly stops denying. So `verify` re-reads everything
through the same provider a hook uses — checking what Zence will actually see,
not what was sent — and fails on the first discrepancy.

See [DEMO_ENVIRONMENT.md](DEMO_ENVIRONMENT.md).
