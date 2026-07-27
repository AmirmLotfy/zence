# northstar-analytics

A fictional analytics repository for **Northstar Commerce**, used to demonstrate
Zence. Everything here is synthetic.

Open Claude Code in this directory with the Zence plugin enabled, and the
session is bounded to Northstar. `../bluepeak-data` is the same laptop, a
different client, and out of reach.

## The three scenarios

| | Ask Claude to… | Zence |
|---|---|---|
| **A** | join `northstar.marketing_leads` with `bluepeak.patient_contacts` | **denies** — cross-client, PII at column level (ZR-001) |
| **B** | change the grain of `models/marts/revenue_daily.sql` | **asks** — DataHub lineage shows the executive dashboard downstream (ZR-008) |
| **C** | write a staging model over `northstar.marketing_leads` | **allows** — in domain, in DEV, silently (ZR-009) |

Scenario C is the one worth watching. A guardrail that interrupts safe work is a
guardrail that gets uninstalled, so an allow produces no prompt and no output at
all.

## Setup

From the repository root, with DataHub running:

```bash
zence demo seed && zence demo verify
```

Then check what this workspace is bound to:

```bash
zence status -C examples/clients/northstar-analytics
```
