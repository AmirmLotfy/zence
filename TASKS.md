# Zence — build status

Against the 15-phase plan in [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md).

## Complete

- [x] **1 · Foundation** — uv + pnpm workspaces, Apache-2.0, eight CI jobs
- [x] **2 · Policy engine** — 12 rules, 10 operators, allowlisted fields, fail-safe matrix
- [x] **3 · Providers** — live (SDK) and fixture, never silently interchanged
- [x] **4 · Extraction** — SQL, dbt, shell, YAML recipes, MCP arguments, paths
- [x] **5 · Plugin** — 9 hook wirings, POSIX shim, both manifests validated in CI
- [x] **6 · Demo catalog** — seeded and verified against live DataHub
- [x] **7 · End-to-end scenarios** — all four run against a real catalog
- [x] **8 · Audit + write-back** — SQLite trail, idempotent decision documents
- [x] **9 · CLI** — status, doctor, inspect, evaluate, policy, audit, demo, finalize
- [x] **10 · Website** — seven static routes rendering real engine output
- [x] **11 · Hardening** — 64 adversarial tests, dependency audit, Dependabot
- [x] **12 · Docs** — eight documents, link-checked in CI
- [x] **13 · Deploy** — live at [zence.site](https://zence.site)
- [x] **14 · Submission** — Devpost text, judge quickstart, video script
- [x] **15 · Clean-room verification** — `scripts/verify-clean-clone.sh` passes

## Verified against live DataHub

DataHub OSS 1.5.0.6 on a dedicated VM, catalog seeded and `zence demo verify`
green. 15 integration tests, marked so CI still needs no catalog.

| | |
|---|---|
| **A** cross-client PII join | **deny** ZR-001 — names `email`, `phone`, `postcode` from real column-level tags |
| **B** change to a shared model | **ask** ZR-008 — from real two-hop lineage to the revenue dashboard |
| **C** in-boundary DEV work | **allow** ZR-009 — silently, no prompt |
| deprecated asset | **ask** ZR-006 — from the real deprecation aspect |
| **D** write-back | document upserted; a second finalize leaves the count unchanged |

Every artifact rendered on the website reports `provider: live`.

## Reproducible without a catalog

The demo workspace ships the recording those runs produced, so the cross-client
denial reproduces on a fresh clone with no DataHub, no Docker and no account —
`uv run zence evaluate … -C examples/clients/northstar-analytics` exits 6.
Decisions made that way report `provider: fixture`; a catalog named in the
environment takes precedence over the recording. The commands, and a link into
the code behind each claim, are at [zence.site/verify](https://zence.site/verify/).

A workspace with neither a recording nor a reachable catalog still exits 7 —
ASK — which is the behaviour that matters and is pinned by a contract test.

## Remaining — yours

- [ ] Record and upload the demo video ([docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md), timed at 2:45)
- [ ] Submit on Devpost ([docs/DEVPOST_SUBMISSION.md](docs/DEVPOST_SUBMISSION.md) is copy-ready)
- [ ] Decide the challenge category — the submission currently names *Metadata-Aware
      Code Generation & Development*, but Zence governs generated code rather than
      generating it. *Agents That Do Real Work* matches the wording more closely
- [x] Bonus criterion: [datahub-project/datahub#18726](https://github.com/datahub-project/datahub/issues/18726) — the SDK
      association-wrapper silent failure, reported with a repro and four fixes
- [ ] Stop the VM when not demoing: `gcloud compute instances stop zence-datahub --zone=europe-west1-b`
      (nothing a judge needs depends on it — the recording covers the read path,
      and the website is static)

## Deliberately not built

Recorded in the README so nothing is over-claimed: general Python/TS/Java source
analysis, hook-bypass prevention outside Claude Code, tag/term mutation on real
client assets, multi-user approval workflows, and Windows support.
