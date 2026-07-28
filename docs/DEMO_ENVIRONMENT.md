# The demo environment

Two fictional clients sharing one DataHub instance. Everything is synthetic — a
tool about not leaking client data should not ship anyone's data.

## The fiction

**Northstar Commerce** (`urn:li:domain:northstar-commerce`) — the client the
demo workspace is bounded to. Marketing leads, campaign performance, CRM
opportunities, a conformed customer dimension, a deprecated one it replaced, and
a revenue fact table feeding an executive dashboard.

**BluePeak Health** (`urn:li:domain:bluepeak-health`) — a healthcare client on
the same instance, and out of bounds. Patient contacts with PII at column level,
a member export, and a shared date dimension that is genuinely harmless.

The catalog is shaped so each rule is demonstrable with a realistic asset rather
than a contrived one:

| Asset | Demonstrates |
|---|---|
| `bluepeak.patient_contacts` | ZR-001 — cross-client, PII on `email` and `phone` |
| `bluepeak.shared_dim_date` | ZR-002, and why time-boxed exceptions exist |
| `northstar.dim_customer_legacy` | ZR-006 — deprecated, with a named replacement |
| `northstar.campaign_costs` | ZR-007 — sensitive and deliberately unowned |
| `northstar.fct_revenue_daily` | ZR-008 — real lineage to a critical dashboard |
| `northstar.marketing_leads` | ZR-009 — the ordinary case that stays silent |

## Setup

```bash
datahub docker quickstart          # ~8 GB RAM, 13 GB disk
export DATAHUB_GMS_URL=http://localhost:8080
export DATAHUB_GMS_TOKEN=<PAT from Settings → Access Tokens>

uv run zence demo seed
uv run zence demo verify
```

`verify` matters more than it looks. Seeding is a batch of upserts that mostly
succeed, and "mostly" is how a demo fails in front of an audience: one missing
column tag and Scenario A quietly stops denying. `verify` re-reads everything
through the same provider a hook uses — checking what Zence will actually see
rather than what was sent — and exits non-zero on the first gap.

## The scenarios

Open Claude Code in `examples/clients/northstar-analytics/`.

### A — cross-client PII → **deny**

> Blend our Northstar leads with the BluePeak patient contact export.

Zence resolves both tables, sees the domain mismatch and the field-level PII,
and denies before the write happens — naming the columns and offering an
in-domain alternative.

### B — lineage-aware approval → **ask**

> Change the revenue model to report gross instead of net.

In bounds, and still worth a pause: DataHub lineage shows the executive
dashboard two hops downstream. Zence asks rather than blocks, because the change
may well be correct.

### C — ordinary work → **allow**

> Write a staging model over the last 30 days of leads.

The most important scenario. In domain, in DEV, nothing sensitive — so Zence
returns an empty response and you see nothing at all.

### D — write-back

```bash
zence finalize --session <id>
```

A decision document appears in DataHub, linked to the assets involved. Run it
again: the same document updates, because the id is
`sha256(workspace::session)`. One record, later `updated_at`.

## Reproducing the artifacts

The decisions rendered on [zence.site/demo](https://zence.site/demo) are real
output, not prose:

```bash
uv run zence evaluate --tool Write --file models/blend.sql \
  --content "SELECT l.email, p.phone
             FROM northstar.marketing_leads l
             JOIN bluepeak.patient_contacts p ON p.email = l.email" \
  -C examples/clients/northstar-analytics --json
```

`scripts/sync-artifacts.sh` copies them into the site, and CI checks
`git diff --exit-code` afterwards — so an artifact edited by hand fails the
build rather than quietly becoming a mock-up.

## Teardown

```bash
datahub docker nuke      # removes containers and volumes
```

Seeding is idempotent, so re-running it after a nuke rebuilds the same catalog.

## Running DataHub elsewhere

DataHub needs ~8 GB of RAM for Docker, which is more than many laptops can
spare alongside a browser and an editor. Any reachable instance works — set
`DATAHUB_GMS_URL` to it. For a remote instance, an SSH tunnel keeps the catalog
off the public internet:

```bash
gcloud compute ssh <vm> --tunnel-through-iap -- -L 8080:localhost:8080
```
