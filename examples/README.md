# Examples — what Zence produces, without running anything

Everything in this folder is **output from real runs**, not written by hand. It
is here so the quality of Zence's decisions can be judged by reading, with no
setup at all.

If you would rather run it, [zence.site/verify](https://zence.site/verify/) has
a one-minute path that needs only `uv`.

---

## `artifacts/decisions/` — the decisions themselves

Six records emitted by `zence evaluate --json`. Each carries the verdict, the
rule that fired, the DataHub URNs that were the evidence, the columns that
mattered, a remediation, and which provider answered.

| File | Verdict | Rule | What it shows |
|---|---|---|---|
| [`scenario-a-deny.json`](artifacts/decisions/scenario-a-deny.json) | **deny** | ZR-001 | A cross-client join blocked before it runs. The reason names `email`, `phone` and `postcode` because those columns are tagged PII at field level in the catalog — not because they look like PII |
| [`scenario-b-ask.json`](artifacts/decisions/scenario-b-ask.json) | **ask** | ZR-008 | A change to a shared model that feeds a critical dashboard two lineage hops downstream. Zence found the dashboard; it was not configured |
| [`scenario-c-allow.json`](artifacts/decisions/scenario-c-allow.json) | **allow** | ZR-009 | In-boundary work in DEV. Note the hook emits `{}` for this — an allow is silent |
| [`deprecated-ask.json`](artifacts/decisions/deprecated-ask.json) | **ask** | ZR-006 | A deprecated asset, read from the real deprecation aspect, with the approved alternative offered |
| [`mcp-deny.json`](artifacts/decisions/mcp-deny.json) | **deny** | ZR-001 | The same boundary enforced on a **DataHub MCP tool call** — catalog reads are intercepted before the metadata reaches the model's context |
| [`tamper-deny.json`](artifacts/decisions/tamper-deny.json) | **deny** | ZR-014 | An edit to `.zence/` itself. Checked before every other rule and not exemptible — its `provider` is `null` because no catalog lookup happens or is needed |

Two fields worth looking at in any of them:

- **`provider`** — `live` for a decision made against a running DataHub,
  `fixture` for one made against a recording. A recording is never allowed to
  present itself as a catalog.
- **`degraded`** / **`degraded_reason`** — set when Zence could not see
  something. A rule that reads asset properties will not fire against evidence
  that failed to resolve, so the honest "I could not check" is never dressed up
  as a finding.

## `artifacts/writeback/` — what goes *back* into DataHub

Zence does not only read the catalog. At session end it writes one decision
document back, so the catalog learns something it did not know.

| File | |
|---|---|
| [`session-document.md`](artifacts/writeback/session-document.md) | The rendered document, as it appears in DataHub |
| [`session-document.json`](artifacts/writeback/session-document.json) | The raw `documentInfo` aspect, read back out of a live instance |

Both were produced by running a real session, calling `zence finalize`, and then
fetching the aspect from DataHub — not by rendering a template locally.

The document id is `sha256(workspace::session)[:16]`, which is what makes the
upsert idempotent: the write path was driven three times against the live
instance and the document count stayed at one. Idempotency is structural rather
than a read-check-write that can lose a race.

What Zence does **not** write is as deliberate: it never retags, reclassifies,
or reassigns ownership of a client's assets. Those are your team's decisions.

## `clients/` — two governed workspaces

[`northstar-analytics/`](clients/northstar-analytics) is the workspace the demo
runs in — the client the session is bounded to. It has:

- [`.zence/policy.yaml`](clients/northstar-analytics/.zence/policy.yaml) — the
  boundary and the rules, meant to be committed and code-reviewed
- [`.zence/catalog.json`](clients/northstar-analytics/.zence/catalog.json) — a
  recording captured from a live DataHub by `zence demo record`, which is what
  lets a fresh clone produce a real decision with no catalog running
- [`models/`](clients/northstar-analytics/models) — ordinary dbt-style SQL, the
  kind of file an agent is asked to write

[`bluepeak-data/`](clients/bluepeak-data) is the other client — the one this
session must not touch.

Both companies are fictional. A tool about not leaking client data should not
ship anyone's.

## `policies/` — a fuller policy

[`northstar-analytics.yaml`](policies/northstar-analytics.yaml) shows the parts
the demo policy does not need: a time-boxed exception with an approver and a
reason, and a rule added on top of the twelve built in.

Policy is data — ten operators over an allowlisted set of evidence fields. There
is no expression language and no `eval`, which is what makes a denial something
you can argue with rather than something you have to accept.
