# Zence — build status

Against the 15-phase plan in [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md).

## Done

- [x] **1 · Foundation** — uv + pnpm workspaces, Apache-2.0, eight CI jobs
- [x] **2 · Policy engine** — 12 rules, 10 operators, allowlisted fields, fail-safe matrix
- [x] **3 · Providers** — live (SDK) and fixture, never silently interchanged
- [x] **4 · Extraction** — SQL, dbt, shell, YAML recipes, MCP arguments, paths
- [x] **5 · Plugin** — 9 hook wirings, POSIX shim, both manifests validated in CI
- [x] **6 · Demo catalog** — two-client synthetic catalog, seed/verify/record
- [x] **8 · Audit + write-back** — SQLite trail, idempotent decision documents
- [x] **9 · CLI** — status, doctor, inspect, evaluate, policy, audit, demo, finalize
- [x] **10 · Website** — six static routes rendering real engine output
- [x] **11 · Hardening** — 64 adversarial tests, dependency audit, Dependabot
- [x] **12 · Docs** — eight documents, link-checked in CI
- [x] **13 · Deploy** — live at [zence.site](https://zence.site)
- [x] **14 · Submission** — Devpost text, judge quickstart, video script
- [x] **15 · Clean-room verification** — `scripts/verify-clean-clone.sh` passes

## Blocked on a live DataHub instance

Everything below is written, type-checked and lint-clean, and none of it has
been executed against a real catalog. That is stated here rather than implied
by a tick.

- [ ] **7 · End-to-end scenarios A–D in a real Claude Code session**
  - [ ] A — cross-client PII join denied *(verified against a fixture; not yet live)*
  - [ ] B — lineage-aware approval from real DataHub lineage
  - [ ] C — in-boundary work allowed silently
  - [ ] D — decision document written back, and a second finalize not duplicating it
- [ ] `zence demo seed` / `verify` / `record` run against a live instance
- [ ] Fixtures re-recorded from that instance and committed
- [ ] `pytest -m integration` green
- [ ] Demo video recorded and uploaded
- [ ] Devpost form submitted

### What is needed

A reachable DataHub OSS instance and a personal access token. The plan's
Phase 0:

```bash
gcloud compute instances create zence-datahub \
  --project=goosecast --zone=europe-west1-b --machine-type=e2-standard-4 \
  --boot-disk-size=50GB --boot-disk-type=pd-balanced \
  --image-family=ubuntu-2404-lts --image-project=ubuntu-os-cloud
```

Then Docker, `uv tool install acryl-datahub`, `datahub docker quickstart`, and a
token from Settings → Access Tokens.

## Deliberately not built

Recorded in the README so nothing is over-claimed: general Python/TS/Java source
analysis, hook-bypass prevention outside Claude Code, tag/term mutation on real
client assets, multi-user approval workflows, and Windows support.
