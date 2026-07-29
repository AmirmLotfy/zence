# Architecture

Everything runs on your machine. There is no Zence service, no hosted backend,
and nothing that phones home. The website is static and knows nothing about you.

---

## The path of one tool call

```
Claude Code session in ~/clients/northstar-analytics/
  │
  ├─ SessionStart ──────► resolve boundary ──► inject context + session title
  ├─ UserPromptSubmit ──► classify intent (never decides on prose alone)
  ├─ PreToolUse ────────► normalize ─ extract ─ resolve ─ evaluate ─ decide
  │      matchers: mcp__.*datahub.*__.*  |  Bash  |  Write|Edit|NotebookEdit
  │                             │
  │                             ├─ LiveProvider ──► DataHub GMS (SDK, cached)
  │                             └─ decision ─────► SQLite audit
  ├─ PostToolUse ───────► record what actually happened
  └─ Stop / SessionEnd ─► finalize ──► DataHub document (idempotent upsert)
```

**Latency, measured on an Apple M1, and what each number covers.** A full warm
`PreToolUse` — parse, extract, resolve, evaluate, decide, emit — takes **0.20–0.28s**
against a recorded catalog, including interpreter startup. The first call after
install builds the runtime virtualenv and takes **~14s**, inside a 30s timeout.

Live-catalog latency is **not** quoted here, because the only instance available
to measure was reached over an SSH tunnel to a remote VM, where the first request
alone costs ~11s of connection setup and the SDK's 4s read timeout is exceeded
often enough that lookups intermittently degrade to `ask`. That number would say
more about the tunnel than about Zence. Against a local `datahub docker
quickstart` it should be far lower — untested, so unclaimed.

## Layout

```
packages/zence-core/src/zence_core/
  schemas/     Pydantic models — Action, AssetRef, Evidence, Decision, Policy
  extract/     SQL, dbt, shell, YAML, MCP arguments, paths  → AssetRef
  providers/   LiveProvider (SDK) and FixtureProvider (recordings)
  policy/      the predicate evaluator, precedence, fail-safe matrix, rules
  audit/       SQLite persistence
  writeback/   DataHub decision documents
  hooks/       protocol, handlers, and the fail-safe entry point

packages/zence-cli/    the `zence` command
bin/zence-hook         POSIX shim — bootstraps a venv, fails safe without it
hooks/hooks.json       hook wiring
.claude-plugin/        plugin + marketplace manifests
apps/web/              the static site
demo/catalog/          the synthetic two-client catalog
examples/clients/      two workspaces with opposite boundaries
examples/artifacts/    real decisions, rendered on the website
```

The repository root **is** the plugin (`source: "./"` in the marketplace entry),
so `${CLAUDE_PLUGIN_ROOT}` resolves here and the shim can reach `packages/`. A
`plugins/zence/` subdirectory would have required either publishing to PyPI or
committing a duplicate copy of the runtime, since the plugin cache only copies
the source directory.

---

## Decisions that shaped the rest

### The MCP server is the interception surface; the SDK is the enforcement path

Claude reads the catalog through the DataHub MCP server, so that is where a
cross-client lookup first becomes visible, and what the `PreToolUse` matcher
keys on. Zence's own evidence goes through the Python SDK, because a hook cannot
borrow the agent's MCP connection and enforcement needs typed aspects rather
than prose. See [DATAHUB_INTEGRATION.md](DATAHUB_INTEGRATION.md).

### Policy is data, not code

A rule is field/predicate pairs. No expression language, no `eval`, no shell —
so a policy file from a cloned repository cannot execute anything. Field paths
are an allowlist, so a typo fails at load rather than silently evaluating to
`None` and inverting a rule. See [POLICY_ENGINE.md](POLICY_ENGINE.md).

### Live and fixture are never silently interchanged

One interface, two implementations, and every piece of evidence carries which
produced it. A fixture is only used when a workspace points at one explicitly —
never as a fallback for an unreachable catalog, because a decision made against
a recording and presented as live is worse than no decision.

### The hook always answers

`main.run` guarantees one valid JSON object and exit 0. A watchdog fires before
Claude Code's own timeout, because a hook that times out emits nothing — and
nothing means the normal permission flow proceeds, a silent allow arrived at by
accident. See [THREAT_MODEL.md](THREAT_MODEL.md#zences-own-failure).

### Recording never breaks a session

Audit writes swallow their own errors. The decision has already been delivered
by then, so a full disk costs a row, not a developer's afternoon.

---

## Data model

SQLite at `~/.zence/zence.db`, nine tables, stdlib only.

```
workspace ─┬─ session ─┬─ action ─┬─ asset_ref
           │           │          ├─ evidence
           │           │          └─ decision ── outcome
           │           └─ writeback (idempotency_key UNIQUE)
           └─ (policy_sha256 recorded per session)
```

Retention defaults to 90 days (`zence audit prune`). **Never stored:** tokens,
full file contents, full command output, actual PII values, or raw prompt text
beyond a redacted excerpt. Redaction happens at the extraction boundary, before
anything reaches the database — there is no redact-on-read path, which would
mean the raw value was on disk all along.

---

## Runtime

| | | |
|---|---|---|
| Engine | Python 3.11 | `mcp-server-datahub`'s floor; `acryl-datahub` is Python-only |
| Tooling | uv, ruff, mypy strict, pytest | |
| SQL | sqlglot | dialect-aware, pure Python, no native deps |
| Persistence | SQLite, no ORM | nine tables and simple queries |
| Website | Next.js 16 static export, Tailwind v4 | no server, no secrets, no external requests |
| DataHub SDK | optional extra | so the test suite runs without a 200 MB install |
