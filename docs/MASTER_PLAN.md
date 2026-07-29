# Zence — Master Implementation Plan

> Task-scoped context and policy firewall that keeps Claude Code inside the correct client,
> domain, and environment using DataHub's metadata graph.

---

> **This is the plan as written on 28 July 2026, kept unedited.** It is a record
> of what was intended, not a description of what exists — so parts of it are
> now out of date on purpose. Two that matter: it plans **14** rules, and 12
> shipped (exception handling moved into the precedence chain, where it belongs,
> rather than being two rules of its own); and it names `zence.vercel.app` as the
> submitted URL, a contingency for DNS still being pending at the deadline. DNS
> resolved, and the site is at **[zence.site](https://zence.site)**.
>
> For what was actually built and verified, see **[TASKS.md](../TASKS.md)**.
> Rewriting a plan after the fact to match the outcome would destroy the only
> useful thing about keeping one.

---

## 1. Context

**Why this is being built.** Freelancers, agencies, and consultancies run Claude Code across
multiple clients from one machine. Claude Code has no concept of "which client am I allowed to
touch right now." A single MCP catalog search, a `JOIN`, or a `Write` can pull Client B's PII
into Client A's repository — and nothing stops it, because every individual tool call is valid.

**What Zence does.** It sits in Claude Code's hook path, resolves referenced assets against
DataHub, evaluates deterministic policy, and returns `allow` / `ask` / `deny` with evidence and
remediation — then writes the decision back into DataHub as durable, idempotent knowledge.

**Submission target.** [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/),
category *Metadata-Aware Code Generation & Development*. Deadline **Aug 10 2026, 5:00 PM EDT**
(Aug 11, 12:00 AM Cairo). **13 days from today (Jul 28).**

**Confirmed second submission.** Rules permit multiple entries if "unique and substantially
different." Zence (agent-time access firewall for Claude Code) is categorically distinct from
Comgu (commerce change-impact CI). **Clean-room build — zero Comgu code reuse**, so the only
disclosure needed is AI-assisted development.

---

## 2. Verified facts (checked this session — do not re-derive)

### Environment

| Item | Verified value | Consequence |
|---|---|---|
| Working dir | `/Users/frameless/Desktop/Zence` — **empty** | True greenfield |
| Machine | Apple M1, **8 GB RAM**, **5.6 GiB free disk** | Cannot host DataHub |
| Docker | **Not installed** | Not installed locally; lives on the VM |
| `uv` | 0.9.26; has CPython 3.11.14 / 3.13.11 / 3.14.2 installed | Python toolchain ready |
| System `python3` | 3.9.6 | **Too old** — never use it; `uv` pins 3.11 |
| Node / pnpm | v22.13.1 / 11.17.0 | Web toolchain ready |
| `gh` | 2.92.0, authed `AmirmLotfy`, scopes `repo, workflow, gist, read:org` | Can create public repo + CI |
| `vercel` | 48.4.0, authed `mellardoo`, scope `mellardoos-projects`, **0 projects** | No overwrite risk |
| `gcloud` | 547.0.0, account `amirmolotfy@gmail.com`, project `goosecast` | Can create the VM |
| Existing VM | `comgu-datahub`, e2-standard-4, `europe-west1-b`, `35.240.72.53`, RUNNING | Proven pattern; **do not touch** |
| `zence.site` | **Available for registration** (confirmed via `whois.nic.site`) | User registers; see §14 |
| `claude` CLI | **Not on PATH** (desktop app session) | CI uses `npx @anthropic-ai/claude-code` |

### Pinned versions

| Package | Version | Source | Note |
|---|---|---|---|
| `mcp-server-datahub` | **0.6.0** | PyPI | `requires_python >=3.11`; mutations need ≥0.5.0 |
| `acryl-datahub` | **1.6.0.16** | PyPI | `requires_python >=3.10` |
| Python floor | **3.11** | Union of above | Pinned via `.python-version` |
| `next` | **16.2.12** | npm | App Router + static export |
| `react` | **19.2.8** | npm | |
| `@anthropic-ai/claude-code` | **2.1.220** | npm | CI plugin validation only |
| DataHub OSS | **1.6.x** | quickstart | Documents API present |

### DataHub requirements (official docs)

- Tested minimum: **2 CPU, 8 GB RAM, 2 GB swap, 13 GB disk** for Docker.
- Quickstart: `datahub docker quickstart` → UI `localhost:9002`, login `datahub`/`datahub`.
- Apple Silicon: `--arch m1` flag exists but **RAM is the blocker, not architecture.**
- → **Local DataHub on this Mac is not viable.** Freeing disk does not fix an 8 GB RAM ceiling.

### DataHub MCP Server — verified contract

```bash
# Self-hosted / OSS Core
claude mcp add datahub \
  -e DATAHUB_GMS_URL="<url>" -e DATAHUB_GMS_TOKEN="<token>" \
  -- uvx mcp-server-datahub@latest
```

| Env var | Default | Zence uses |
|---|---|---|
| `DATAHUB_GMS_URL` / `DATAHUB_GMS_TOKEN` | — | required |
| `TOOLS_IS_MUTATION_ENABLED` | `false` | **`true`** |
| `TOOLS_IS_USER_ENABLED` | `false` | `true` (for `get_me`) |
| `SAVE_DOCUMENT_TOOL_ENABLED` | `true` | keep |
| `TOOL_RESPONSE_TOKEN_LIMIT` | `80000` | default |

**Read tools:** `search`, `get_entities`, `get_lineage`, `get_lineage_paths_between`,
`list_schema_fields`, `get_dataset_queries`, `search_documents`, `grep_documents`, `get_me`.
**Write tools:** `add_tags`, `add_terms`, `add_owners`, `set_domains`, `update_description`,
`add_structured_properties`, `save_document` (+ `remove_*` variants).

### DataHub write-back — verified idempotent API

```python
from datahub.sdk import DataHubClient, Document

client = DataHubClient.from_env()  # reads DATAHUB_GMS_URL / DATAHUB_GMS_TOKEN
doc = Document.create_document(
    id="zence-session-<sha256[:16]>",  # deterministic id ⇒ upsert = idempotent
    title="Zence decision record — <session>",
    text="<markdown>",
    subtype="Decision Record",
    related_assets=["urn:li:dataset:(urn:li:dataPlatform:snowflake,…,PROD)"],
)
client.entities.upsert(doc)  # same id updates; new id creates
```

Same `id` ⇒ update, not duplicate. **This is the idempotency mechanism** — no bespoke dedup table
needed for correctness (the local `writeback` table records attempts for auditability).

### Claude Code hooks — verified contract

`PreToolUse` blocking response (exact schema):

```json
{ "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "<shown to user; required for deny>",
    "additionalContext": "<injected for Claude>" } }
```

`permissionDecision` ∈ `allow` | `deny` | `ask` | `defer`. `SessionStart` supports
`additionalContext`, `sessionTitle`, `watchPaths`. Exit `0` = parse stdout JSON; exit `2` =
blocking, stderr is the reason; any other code = non-blocking error.

MCP tool naming: `mcp__<server>__<tool>`; plugin-bundled: `mcp__plugin_<plugin>_<server>__<tool>`.
Matchers containing regex characters are treated as **unanchored JS regex**.

Default hook timeout 600 s — except **`UserPromptSubmit` = 30 s**. Zence budgets far below both.

### Plugin + marketplace schema (verified)

- Manifest: `.claude-plugin/plugin.json`; only `name` required. Components live at **plugin root**
  (`hooks/hooks.json`, `.mcp.json`, `skills/`, `commands/`), never inside `.claude-plugin/`.
- Marketplace: `.claude-plugin/marketplace.json`, requires `name`, `owner{name}`, `plugins[]`.
  Relative `source` must start with `./` and resolves from **marketplace root**.
- `userConfig` prompts at enable time; `sensitive: true` values go to **macOS Keychain**, and every
  value is exported to hooks as `CLAUDE_PLUGIN_OPTION_<KEY>`.
- **Constraint:** shell-form hook commands *reject* `${user_config.*}`. Use exec form with `args`,
  or read `CLAUDE_PLUGIN_OPTION_*` from the hook env. Zence reads the env var.
- Validation: `claude plugin validate ./plugins/zence --strict`.

---

## 3. Executive recommendation

Build a **Python 3.11 policy engine + Claude Code plugin**, with a **static Next.js site**, against
a **dedicated GCP VM running DataHub OSS**. Two decisions define the architecture:

**A. The DataHub MCP Server is the interception surface; the Python SDK is the enforcement path.**
Claude reads the catalog through the MCP server — that's what Zence hooks intercept
(`mcp__*datahub*__*`). Zence's *own* evidence lookups and write-backs go through `acryl-datahub`
directly, because a hook must be deterministic, fast, and cannot borrow Claude's MCP client. Both
halves are genuinely load-bearing, satisfying the mandatory-MCP requirement honestly.

**B. Live vs fixture is an explicit, never-silent boundary.** `LiveProvider` (SDK) and
`FixtureProvider` (recorded) implement one interface. Fixtures are **recorded from the real VM** by
`zence demo record` — never hand-written. Unit tests, CI, and the website replay run on fixtures;
E2E and the video run live. A degraded live connection **never** falls back to fixtures — it
returns `ask`/`deny` per policy and says so.

This decouples 90% of the build from VM availability and makes CI free and fast.

**Scope discipline.** 13 days, solo. The cut list in §21 is not optional — it is what makes the
remaining scope demonstrably real.

---

## 4. Final architecture

```
Claude Code session in ~/clients/northstar-analytics/
        │
        ├─ SessionStart ──────► zence-hook ──► resolve boundary ──► inject context + title
        ├─ UserPromptSubmit ──► zence-hook ──► intent flags ──► context (deny only if explicit)
        ├─ PreToolUse ────────► zence-hook ──► ①normalize ②extract ③resolve ④evaluate ⑤decide
        │     matchers: mcp__.*datahub.*__.* | Bash | Write|Edit|NotebookEdit
        │                                        │
        │                                        ├─ LiveProvider ──► DataHub GMS (SDK, cached)
        │                                        └─ decision → SQLite audit
        ├─ PostToolUse / PostToolUseFailure ──► outcome linked to decision
        └─ Stop / SessionEnd ─────────────────► finalize ──► Document.upsert (idempotent)
```

`zence-hook` is a POSIX shim at `${CLAUDE_PLUGIN_ROOT}/bin/zence-hook` that resolves an interpreter
in order: `$ZENCE_PYTHON` → venv at `${CLAUDE_PLUGIN_DATA}/venv` → creates it via
`uv venv && uv pip install -e ${CLAUDE_PLUGIN_ROOT}/runtime`. **Only prerequisite is `uv`.**
If bootstrap fails it emits valid fail-safe JSON (§9) — it never crashes the session.

### Decisions table

| Area | Decision | Rationale |
|---|---|---|
| Engine language | **Python 3.11** | `mcp-server-datahub` floor; `acryl-datahub` is Python-only |
| Python tooling | **uv** workspace, ruff, mypy, pytest | Already installed; fastest cold start |
| Web | **Next.js 16 App Router, `output: 'export'`** | Fully static ⇒ no server, no creds, top Lighthouse |
| Styling | **Tailwind v4 + CSS variables** | No runtime CSS-in-JS |
| JS tooling | **pnpm workspace** | Installed; no Turborepo (overkill solo) |
| SQL parsing | **sqlglot** | Pure Python, dialect-aware, no native deps |
| Policy format | **YAML → Pydantic v2 → JSON Schema** | Declarative predicates, **no `eval`**, schema-validatable |
| Persistence | **SQLite** (stdlib `sqlite3`, no ORM) + JSONL export | Zero deps; artifacts are the export |
| DataHub read/write | **`acryl-datahub` SDK** | Deterministic; MCP is the intercepted surface |
| Secrets | **Plugin `userConfig` → Keychain → `CLAUDE_PLUGIN_OPTION_*`** | No token ever in a file |
| Demo DataHub | **New GCP VM `zence-datahub`** | Isolated from Comgu's judged demo |
| Local dashboard | **Cut** — Rich terminal + hosted replay | Not worth 2 days |

---

## 5. Repository tree

```
zence/
├── .claude-plugin/marketplace.json      # marketplace catalog (repo root)
├── plugins/zence/
│   ├── .claude-plugin/plugin.json       # manifest + userConfig
│   ├── .mcp.json                        # bundles DataHub MCP server
│   ├── hooks/hooks.json                 # all hook wiring
│   ├── bin/zence-hook                   # POSIX shim (uv bootstrap, fail-safe)
│   ├── commands/                        # /zence:status, :explain, :audit, :finalize, :doctor, :demo
│   └── runtime/                         # bundled copy of zence-core (installed by shim)
├── packages/
│   ├── zence-core/src/zence_core/
│   │   ├── schemas/        # Pydantic: Action, AssetRef, Evidence, Rule, Decision, Exception
│   │   ├── extract/        # sql.py dbt.py shell.py yaml_recipe.py mcp_args.py paths.py
│   │   ├── providers/      # base.py live.py fixture.py cache.py
│   │   ├── policy/         # engine.py precedence.py defaults.py builtin_rules.yaml
│   │   ├── audit/          # db.py models.py redact.py export.py
│   │   ├── writeback/      # document.py properties.py idempotency.py
│   │   └── hooks/          # session_start.py pre_tool.py post_tool.py stop.py router.py
│   └── zence-cli/src/zence_cli/    # Typer + Rich
├── apps/web/               # Next.js 16 static site
│   ├── app/{page,demo,docs,architecture,security,open-source}
│   └── public/replays/     # REAL artifacts copied from examples/
├── datahub/demo/
│   ├── domains.yaml  datasets/  glossary.yaml  structured_properties.yaml
│   ├── seed.py  verify.py  lineage.yaml
├── examples/
│   ├── clients/northstar-analytics/     # fictional Client A repo (.zence/)
│   ├── clients/bluepeak-data/           # fictional Client B repo
│   ├── policies/                        # example policy files
│   └── artifacts/                       # REAL recorded decisions + fixtures
├── docs/                   # 13 planning/reference docs (§20)
├── scripts/                # provision-vm.sh, tunnel.sh, verify-clean-clone.sh
├── tests/{unit,contract,integration,e2e,security}/
├── .github/workflows/{ci.yml,integration.yml}
├── LICENSE (Apache-2.0)  README.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md
├── SECURITY.md  .env.example  .gitignore  TASKS.md
└── pyproject.toml  .python-version  pnpm-workspace.yaml
```

---

## 6. Data model (SQLite at `~/.zence/zence.db`)

| Table | PK | Key columns | FK |
|---|---|---|---|
| `workspace` | `id` | `root_path` UNIQUE, `active_client`, `active_domain_urn`, `policy_version`, `mode` | — |
| `session` | `id` | `claude_session_id` IDX, `started_at`, `ended_at`, `mode`, `writeback_dirty` | `workspace_id` |
| `action` | `id` | `tool_use_id` IDX, `tool_name`, `hook_event`, `input_redacted`, `created_at` | `session_id` |
| `asset_ref` | `id` | `raw_text`, `kind`, `resolved_urn`, `confidence`, `extractor` | `action_id` |
| `evidence` | `id` | `urn`, `domain_urn`, `owners`, `tags`, `terms`, `lifecycle`, `env`, `downstream_critical`, `provider`, `fetched_at` | `action_id` |
| `decision` | `id` | `decision`, `rule_id`, `policy_version`, `risk`, `reason`, `remediation`, `idempotency_key` | `action_id` |
| `approval` | `id` | `requested_at`, `resolved_at`, `outcome`, `approver` | `decision_id` |
| `outcome` | `id` | `executed`, `success`, `summary_redacted` | `decision_id` |
| `writeback` | `id` | `idempotency_key` **UNIQUE**, `kind`, `target_urn`, `datahub_urn`, `status`, `confirmed_at` | `session_id` |
| `exception` | `id` | `rule_id`, `scope`, `expires_at`, `approver`, `reason` | `workspace_id` |

**Indexes:** `session(claude_session_id)`, `action(session_id, created_at)`, `decision(action_id)`,
`writeback(idempotency_key)` UNIQUE, `asset_ref(resolved_urn)`.

**Migrations:** single `schema_version` table + ordered `migrations/NNN_*.sql`. No Alembic.

**Retention:** default 90 days; `zence audit prune`.

**Never stored:** DataHub tokens, full file contents, full command stdout/stderr, actual PII values,
raw prompt text beyond a redacted 200-char excerpt. Redaction happens **before** the DB write, not
on read.

**Local-only:** everything above. **Written to DataHub:** decision documents + `zence.*` structured
properties only (§8).

---

## 7. Policy model

### Precedence (strict order, first match wins)

1. **Tamper/bypass detected** → `deny` (rule `ZR-014`, always evaluated first, non-exemptible)
2. **Explicit deny rule** matches → `deny`
3. **Required-approval rule** matches → `ask`
4. **Valid unexpired exception** covering the action → `allow` (audited as `allow_via_exception`)
5. **Explicit allow rule** matches → `allow`
6. **Safe default** (§9 matrix)

### Rule file (`.zence/policy.yaml`) — canonical example

```yaml
policy_version: "1.0.0"
workspace_id: northstar-analytics
mode: enforce                       # audit | enforce | demo
active_client: "Northstar Commerce"
active_domain: "urn:li:domain:northstar-commerce"
allowed_domains:  ["urn:li:domain:northstar-commerce"]
allowed_environments: ["DEV", "QA"]
sensitive_tags:   ["urn:li:tag:PII", "urn:li:tag:Confidential"]
protected_terms:  ["urn:li:glossaryTerm:PersonalData"]
critical_downstream: ["urn:li:dashboard:(looker,northstar_revenue)"]

rules:
  - id: ZR-001
    title: Cross-client PII access
    decision: deny
    when:                            # all conditions AND-ed; declarative only, no eval
      asset.domain_urn: {not_in: "$allowed_domains"}
      asset.tags:       {intersects: "$sensitive_tags"}
    explanation: "{asset.name} belongs to {asset.domain_name} and carries {matched_tags}."
    remediation: "Use an in-domain equivalent, e.g. {suggest_in_domain_alternative}."

  - id: ZR-004
    title: Production mutation
    decision: ask
    when:
      asset.env: {equals: "PROD"}
      action.intent: {intersects: ["write", "mutate"]}
    required_approver: workspace_owner
    explanation: "Mutating {asset.name} in PROD."

exceptions:
  - rule_id: ZR-002
    scope: {urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.shared_dim_date,PROD)"}
    expires_at: "2026-08-11T00:00:00Z"
    approver: "amir@zence.site"
    reason: "Shared date dimension, no client data."
```

Supported operators: `equals`, `not_equals`, `in`, `not_in`, `intersects`, `not_intersects`,
`matches` (anchored regex, 100 ms timeout), `gte`, `lte`, `exists`. `$name` dereferences a
top-level list. **No arbitrary expressions — the engine is a predicate evaluator, not an
interpreter.**

### The 14 shipped rules

| ID | Condition | Decision |
|---|---|---|
| ZR-001 | Cross-client **+ PII** | `deny` |
| ZR-002 | Cross-client, non-sensitive **read** | `ask` |
| ZR-003 | Cross-client **write** | `deny` |
| ZR-004 | Production mutation | `ask` |
| ZR-005 | **Destructive** production mutation (`DROP`/`TRUNCATE`/`rm -rf`) | `deny` |
| ZR-006 | Deprecated / uncertified asset | `ask` |
| ZR-007 | Unowned **sensitive** asset | `ask` |
| ZR-008 | Critical downstream impact (lineage) | `ask` |
| ZR-009 | In-domain, allowed-env **read** | `allow` |
| ZR-010 | In-domain code generation, no sensitive refs | `allow` |
| ZR-011 | Unresolvable asset + sensitive operation | `ask` |
| ZR-012 | Valid unexpired exception | `allow` + audit |
| ZR-013 | Expired exception | falls through to base rule |
| ZR-014 | Edit/delete of `.zence/**` or hook config | `deny` + audit |

---

## 8. DataHub read/write matrix

### Read (Zence → DataHub via `acryl-datahub` SDK, 60 s TTL cache)

| Need | SDK/API surface | Used by |
|---|---|---|
| Resolve name → URN | search / `get_urns_by_filter` | extraction resolver |
| Domain, owners, tags, terms | `client.entities.get(urn)` | ZR-001..003, 007 |
| Schema fields + field tags | dataset schema aspect | column-level PII |
| Lifecycle / deprecation | deprecation aspect | ZR-006 |
| Downstream lineage (2 hops) | lineage API | ZR-008 |
| Structured properties | `structured_properties` | env, criticality |
| Current identity | `get_me` equivalent | audit attribution |

### Write (idempotent only — no destructive mutation, ever)

| Artifact | Method | Idempotency | Timing |
|---|---|---|---|
| **Session decision record** (primary) | `Document.create_document(id=…)` + `entities.upsert` | deterministic `id` = `zence-session-<sha256(workspace+session)[:16]>` | `Stop` when dirty, `/zence:finalize`, `SessionEnd` |
| **`zence.last_review`** structured property on each referenced dataset | `add_structured_properties` | value replace, not append | with the document |

Every write carries: decision id, timestamp (UTC), repository, active client, session id, policy
version, rule id, decision, referenced asset URNs, redacted evidence summary, outcome, idempotency
key, and a `Generated by Zence` provenance line.

**Not implemented (documented as future):** proposals API, tag/term mutation on real assets,
ownership changes. Zence proposes in prose; it does not reclassify a client's catalog.

---

## 9. Security model

### Fail-safe matrix (this is the heart of correctness)

| Situation | Decision |
|---|---|
| Explicit high-risk violation | `deny` |
| Ambiguous sensitive operation | `ask` |
| **DataHub unreachable during a sensitive operation** | `ask` (enforce) / `deny` (strict) — **never allow** |
| DataHub unreachable, clearly local & harmless | `allow` + degraded-mode warning in context |
| Asset referenced but unresolvable, sensitive op | `ask` |
| No asset reference, no sensitive intent | `allow` |
| **Hook itself crashes / times out** | emit `ask` for tool classes that can touch data; `allow` for read-only local tools; always emit valid JSON |
| Cross-client reference + metadata lookup failed | **`ask` minimum — never silently allow** |

### Threat model (documented in `docs/THREAT_MODEL.md`)

| Threat | Mitigation |
|---|---|
| Cross-client leakage | Core function; ZR-001..003 |
| **Prompt injection via DataHub descriptions/documents** | Metadata is rendered as quoted, escaped evidence; never concatenated as instructions. Engine decisions come from typed fields only, never free text |
| Untrusted MCP output | Response schema-validated; unexpected shapes → `ask` |
| Hook bypass / direct shell outside Claude Code | **Explicitly out of scope** — stated in README and site |
| Policy file tampering | ZR-014 denies edits to `.zence/**`; SHA recorded per session; drift flagged |
| Stolen DataHub token | Keychain storage; never in files/logs/git; `.env.example` only |
| Over-privileged service account | Demo token documented as read + limited-write |
| Shell injection | `shlex` parsing; exec-form hooks with `args`; no `shell=True` |
| Path traversal / symlink | `Path.resolve()` + `is_relative_to(workspace_root)`; symlinks escaping root rejected |
| Log leakage | Redaction before persistence; `tests/security/test_redaction.py` |
| Approval fatigue | `ask` only where policy demands; measured in demo (target ≤2 asks/scenario set) |
| TOCTOU between decide and execute | Acknowledged; decision pinned to `tool_use_id`; PostToolUse verifies the executed input matches |
| Duplicate write-back | Deterministic document `id` + UNIQUE `idempotency_key` |
| Malicious repo altering plugin behavior | `pluginConfigs` are ignored from project settings by Claude Code (verified); Zence additionally refuses `.zence/` files that are symlinks |

**Trust boundary (stated verbatim on the site and README):** *Zence reduces accidental and
agent-mediated mistakes inside the supported Claude Code workflow. It is not a kernel sandbox, not
an endpoint security product, and not a substitute for warehouse permissions.*

---

## 10. Hook matrix

| Event | Matcher | Does | Can block | Budget |
|---|---|---|---|---|
| `SessionStart` | `startup\|resume\|clear` | Load `.zence/*`, resolve boundary, inject context, set `sessionTitle` | No | 800 ms |
| `UserPromptSubmit` | — | Intent flags (client / prod / destructive / PII / cross-domain), add context; `deny` only for explicit prohibited phrasing | Yes | **1.5 s** (30 s cap) |
| `PreToolUse` | `mcp__.*datahub.*__.*` | Full evaluation on catalog ops | Yes | 2.5 s |
| `PreToolUse` | `Bash` | Destructive / prod / exfil detection | Yes | 2.5 s |
| `PreToolUse` | `Write\|Edit\|NotebookEdit` | Parse SQL/dbt/YAML content for asset refs | Yes | 2.5 s |
| `PostToolUse` | union of above | Record outcome, link to decision, flag write-back candidates | No | 1 s |
| `PostToolUseFailure` | union of above | Distinguish policy denial from tool failure | No | 1 s |
| `Stop` | — | If `writeback_dirty`, upsert decision document | Yes (unused) | 3 s |
| `SessionEnd` | — | Final flush + prune | No | 2 s |

The regex matcher `mcp__.*datahub.*__.*` deliberately covers **both** a user-configured
`mcp__datahub__*` server and Zence's bundled `mcp__plugin_zence_datahub__*`.

`UserPromptSubmit` classifies intent only — it **never** asserts an asset violation from prompt
text alone. Asset claims require resolved DataHub evidence.

### Plugin commands (7)

`/zence:init` · `/zence:status` · `/zence:explain <decision-id>` · `/zence:audit` ·
`/zence:finalize` · `/zence:doctor` · `/zence:demo`

---

## 11. Asset-reference extraction (MVP scope — explicitly bounded)

| Source | Method | Confidence |
|---|---|---|
| SQL tables/columns | `sqlglot` AST, alias resolution | high |
| dbt `ref()` / `source()` | regex + `sqlglot` | high |
| DataHub URNs | anchored regex | exact |
| MCP tool arguments | typed field read (`urn`, `query`, `filters`) | exact/high |
| Shell commands | `shlex` + pattern rules (`bq`, `snowsql`, `psql`, `dbt`, `aws s3`, `rm`) | medium |
| YAML ingestion recipes | safe-load + known key paths | high |
| File paths → client | `.zence/project.yaml` path mapping | medium |
| Env names | token match `PROD\|PRODUCTION\|DEV\|STAGING\|QA` | medium |

**Out of scope (stated in README):** general Python/TypeScript/Java source analysis, ORM call
graphs, dynamically constructed identifiers. Unresolved-but-suspicious references route to `ask`
(ZR-011), never a silent allow.

**False-positive controls:** SQL keyword/CTE denylist, minimum identifier length, `confidence`
threshold per rule, and a per-workspace `ignore_patterns` list.

---

## 12. Demo environment

### Two fictional clients (all synthetic, safe to publish)

**Northstar Commerce** (`urn:li:domain:northstar-commerce`) — active client
`marketing_leads` (DEV+PROD) · `campaign_performance` · `crm_opportunities` ·
`dim_customer_legacy` *(deprecated)* · `dim_customer` *(approved alternative)* ·
`fct_revenue_daily` *(shared transform)* → **`northstar_revenue` dashboard (critical)**

**BluePeak Health** (`urn:li:domain:bluepeak-health`) — out of bounds
`patient_contacts` (PROD, `PII` tag, `PersonalData` term, columns `email`/`phone` field-tagged) ·
`member_export` (PROD-only) · restricted ownership, no Northstar owners

Provides: 2 domains, ownership, PII tags at dataset **and column** level, glossary terms, DEV/PROD
split, full schemas, upstream+downstream lineage, one critical dashboard, one deprecated dataset
with an approved alternative, one shared transform with real downstream impact.

### Commands

```bash
zence demo up       # provision/verify VM + DataHub reachable
zence demo seed     # idempotent metadata seed (re-runnable)
zence demo verify   # assert every entity/tag/lineage edge exists  → exit 0/1
zence demo record   # capture LIVE responses → examples/artifacts/fixtures/
zence demo run      # execute scenarios A–D, emit artifacts
zence demo down     # stop VM (data preserved)
```

### Scenarios

| # | Prompt (inside `examples/clients/northstar-analytics/`) | Expected |
|---|---|---|
| **A** | "Join our leads with the BluePeak patient contacts export" | `deny` ZR-001 before execution; domain mismatch + PII evidence + URNs + in-domain remediation |
| **B** | "Update `fct_revenue_daily` to change the revenue grain" | `ask` ZR-008; 2-hop lineage names `northstar_revenue`; approve/decline both audited |
| **C** | "Write a dbt model over `dim_customer` for DEV" | `allow` ZR-009/010; executes; outcome recorded |
| **D** | `/zence:finalize` | Document appears in DataHub; **re-run creates no duplicate**; same artifact drives the website replay |

---

## 13. Website

**Stack:** Next.js 16 App Router, `output: 'export'` (fully static), Tailwind v4,
`next/font/local` self-hosting **Inter** + **JetBrains Mono** (both SIL OFL — no external requests,
CSP-clean).

**Routes:** `/` · `/demo` · `/docs` · `/architecture` · `/security` · `/open-source`

**Homepage:** hero → the multi-client problem → real decision replay → how the boundary works →
DataHub context graph → Claude Code hook path → allow/ask/deny → three real scenarios →
architecture diagram → install → hackathon attribution → GitHub + Docs CTAs.

**Visual system**

| Token | Value | Use |
|---|---|---|
| `--bg` | `#FAF9F6` | warm off-white |
| `--fg` | `#111110` | near-black |
| `--accent` | `#2F6F4E` | muted green — brand / allow |
| `--warn` | `#B4761E` | amber — ask |
| `--deny` | `#9B3B33` | muted red — deny only |
| `--rule` | `#E4E1DA` | hairlines |

Light-first, editorial, generous spacing, hairline rules, crisp SVG diagrams. **No** gradients,
glassmorphism, glow grids, AI sparkles, fake 3D, stock photos, or a shield logo. Responsive from
320 px, WCAG AA contrast, full keyboard access, `prefers-reduced-motion` honored, dark mode via
`prefers-color-scheme` + `[data-theme]`.

**Interactive replay** at `/demo` reads `public/replays/*.json`, copied verbatim from
`examples/artifacts/`. Steps: prompt → tool attempt → DataHub evidence → policy evaluation →
decision → safe alternative → outcome → write-back. Labeled **"Synthetic demo scenario — recorded
from a real Zence run"**. No fake testimonials, logos, metrics, or certifications.

---

## 14. Deployment

### DataHub VM (one-time, ~30 min — **you run this; I cannot create infrastructure**)

```bash
gcloud compute instances create zence-datahub \
  --project=goosecast --zone=europe-west1-b \
  --machine-type=e2-standard-4 \
  --boot-disk-size=50GB --boot-disk-type=pd-balanced \
  --image-family=ubuntu-2404-lts --image-project=ubuntu-os-cloud \
  --tags=zence-datahub
```

Then on the VM: install Docker + `uv`, `uv tool install acryl-datahub`, `datahub docker quickstart`,
create a PAT in the UI (`localhost:9002`, `datahub`/`datahub`).

**Access — SSH tunnel by default, no public exposure:**
```bash
gcloud compute ssh zence-datahub --zone=europe-west1-b --tunnel-through-iap -- \
  -L 8080:localhost:8080 -L 9002:localhost:9002
```
`DATAHUB_GMS_URL=http://localhost:8080`. Optional public HTTPS (Caddy + sslip.io) is added **only**
for video capture, token-gated, and torn down after.

**Cost:** e2-standard-4 ≈ $0.13/hr. `gcloud compute instances stop zence-datahub` when idle;
`zence demo down` wraps this. Expect **< $40** for the whole window.

### Website (Vercel CLI, scope `mellardoos-projects`, 0 existing projects ⇒ no overwrite risk)

1. `vercel whoami` → confirm `mellardoo` · 2. `vercel link --yes --project zence` ·
3. `pnpm -C apps/web build` locally first · 4. `vercel deploy` (preview) → verify all 6 routes,
console clean · 5. `vercel deploy --prod` · 6. `vercel domains add zence.site` ·
7. `vercel domains inspect zence.site` → **report exact DNS records to set at the registrar** ·
8. Re-verify HTTPS after propagation.

**The submitted URL is `zence.vercel.app`** — it can never be broken by pending DNS. `zence.site`
is attached as soon as it resolves and becomes the canonical link. **The plan never claims the
custom domain is live while DNS is pending.** The site requires no DataHub credentials.

### GitHub

Public repo `AmirmLotfy/zence`, Apache-2.0 (detected in About), description + topics
(`claude-code`, `datahub`, `mcp`, `data-governance`, `policy-engine`, `ai-agents`), conventional
commits, CI green, branch `main`.

---

## 15. Testing strategy

| Layer | Runs on | Contents |
|---|---|---|
| **Unit** (~120) | fixtures, CI | policy schema, precedence, exceptions/expiry, extraction per format, normalization, risk calc, redaction, serialization, idempotency-key stability |
| **Hook contract** (~40) | fixtures, CI | Real JSON payloads → each hook. Asserts **exact** output schema, allow/ask/deny, `additionalContext`, timeout, missing config, DataHub down, malformed input, no secrets in stdout/stderr |
| **Integration** | live VM, manual/nightly | search, entity, schema, domain, tags, ownership, lineage, path-between, write-back, **duplicate write-back prevention**, auth failure, network failure |
| **E2E** | live VM | Scenarios A–D, plugin install, marketplace validation, clean-clone setup, teardown + repeat |
| **Web** | CI | tsc, eslint, vitest, axe a11y, responsive snapshots, Playwright smoke, prod build, link check, zero console errors, Lighthouse ≥95 |
| **Security** | CI | gitleaks, `pip-audit`, `pnpm audit`, command-injection, path-traversal, malicious policy YAML, malicious tool payload, redaction, symlink handling, plugin-bypass attempts, fail-safe assertions |

**Hook contract tests are the highest-value suite** — they are the only thing that proves Zence
actually blocks rather than merely claiming to. Every payload is captured from a real session.

### CI (`.github/workflows/ci.yml`, every PR — no Docker)

ruff · mypy · pytest (unit+contract) · pnpm lint/typecheck/test/build · Playwright ·
`npx @anthropic-ai/claude-code@2.1.220 plugin validate ./plugins/zence --strict` ·
policy JSON-Schema validation · gitleaks · license check · artifact-shape validation.
Caches: `uv`, `pnpm`, Playwright browsers.

`integration.yml` — `workflow_dispatch` + nightly, uses repo secrets, hits the live VM.

---

## 16. Implementation phases

Each phase: **Goal · Files · Tests · Acceptance · Commit**. Rollback = the phase is one branch;
`git revert` the merge. All work on `main` via short-lived branches.

| # | Phase | Days | Acceptance criterion | Commit |
|---|---|---|---|---|
| 0 | **VM + DataHub live** *(you)* | Jul 28 | `curl $GMS/config` returns 200 through the tunnel; PAT stored in Keychain | — |
| 1 | Repo foundation, license, CI skeleton, docs stubs | 28 | `gh repo view` public, Apache-2.0 detected, CI green on empty suite | `chore: scaffold monorepo, Apache-2.0, CI` |
| 2 | Schemas + policy engine + 14 rules | 28–29 | 60+ unit tests pass; precedence + expiry proven; JSON Schema emitted | `feat(core): deterministic policy engine` |
| 3 | DataHub provider (live + fixture + cache) | 29–30 | Live reads against VM succeed; fixture parity test passes | `feat(core): DataHub metadata providers` |
| 4 | Asset extraction (SQL/dbt/shell/YAML/MCP/paths) | 30–31 | Table-driven tests per format; FP controls verified | `feat(core): asset reference extraction` |
| 5 | Plugin + all hooks + shim | 31–Aug 1 | `plugin validate --strict` passes; contract tests green; shim bootstraps from cold | `feat(plugin): Claude Code hooks and manifest` |
| 6 | Synthetic metadata + seed/verify | Aug 1–2 | `zence demo verify` exits 0 on a fresh DataHub | `feat(demo): synthetic two-client catalog` |
| 7 | End-to-end decision flows A–C | Aug 2–3 | A denies, B asks, C allows — **in a real Claude Code session** | `feat: end-to-end allow/ask/deny flows` |
| 8 | Audit persistence + write-back (D) | Aug 3–4 | Document upserts; second finalize creates no duplicate | `feat(core): audit trail and DataHub write-back` |
| 9 | CLI + setup wizard + doctor | Aug 4 | All commands have `--help`, `--json`, stable exit codes | `feat(cli): zence command line interface` |
| 10 | Website + replay from real artifacts | Aug 5–6 | 6 routes build statically; replay renders recorded JSON | `feat(web): marketing site and decision replay` |
| 11 | Testing, hardening, security suite | Aug 6–7 | Full matrix green; gitleaks clean | `test: complete test matrix and hardening` |
| 12 | Docs ×13 + README + examples committed | Aug 7 | Clean-clone instructions followed verbatim by `scripts/verify-clean-clone.sh` | `docs: complete documentation set` |
| 13 | Vercel preview → prod → domain | Aug 8 | `zence.vercel.app` live; `zence.site` attached or DNS reported accurately | `chore(web): production deployment` |
| 14 | Video (<3 min) + Devpost package | Aug 8–9 | Script timed under 3:00; all fields drafted | `docs: devpost submission package` |
| 15 | Clean-room verification + submit | Aug 9–10 | Fresh clone → documented setup → scenarios reproduce | `chore: v0.1.0 release` |

**Buffer:** Aug 10 is reserved entirely for submission and overrun. Phases 10 and 14 are the
compressible ones if slippage occurs.

---

## 17. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **VM/DataHub setup consumes day 1** | Medium | Phase 0 is isolated and yours; Phases 1–2 need no DataHub and proceed in parallel |
| Hook latency degrades the session | Medium | 60 s TTL cache, budgets in §10, `zence doctor --bench` asserts p95 |
| Cold-start `uv` bootstrap inside a hook feels slow | Medium | `/zence:doctor` and `zence init` pre-warm the venv; shim is fail-safe |
| DataHub Documents API shape differs from docs | Low-Med | Phase 3 spikes the write **first**; structured properties are the proven fallback |
| MCP tool-name matcher misses | Low | Regex covers both bundled and user-configured servers; contract test asserts both |
| 13-day scope overrun | **High** | §21 cut list is pre-committed, not deferred |
| `zence.site` DNS pending at deadline | Medium | `zence.vercel.app` is the submitted URL from day one |
| 8 GB Mac struggles with Next dev + Python + tunnel | Medium | Static export, no local Docker, no watch-mode on both stacks simultaneously |
| Judge cannot reproduce | Medium | Documented path is **local `datahub docker quickstart`** (any 16 GB laptop) — the VM is a dev convenience, not a requirement |

---

## 18. Definition of done (verbatim acceptance)

- [ ] Clean clone → documented setup succeeds in a fresh directory
- [ ] DataHub OSS starts (`datahub docker quickstart`) and `zence demo seed && zence demo verify` exit 0
- [ ] DataHub MCP server connected and its tools intercepted
- [ ] `claude plugin validate ./plugins/zence --strict` passes; plugin installs locally **and** from the GitHub marketplace
- [ ] Claude Code receives active-client context at `SessionStart`
- [ ] Scenario C **allows**, B **asks**, A **denies** — observed in a real session
- [ ] All evidence in the denial originates from DataHub (URNs shown)
- [ ] At least one lineage-aware decision (B) works
- [ ] A decision document is written to DataHub; **re-running finalize creates no duplicate**
- [ ] `zence audit list` / `show` output is readable and redacted
- [ ] Full automated test matrix passes; gitleaks finds nothing in history
- [ ] Website builds statically and deploys via Vercel CLI; 6 routes verified
- [ ] `zence.site` configured **or** its exact pending DNS requirement reported accurately
- [ ] Public repo, Apache-2.0 detected, example artifacts committed
- [ ] Video script times under 3:00; Devpost package complete
- [ ] **No mocked path is presented as the real integration** anywhere in repo, site, or video

---

## 19. Open-source & submission strategy

**OSS contribution** (a stated judging bonus). Highest-value, lowest-risk: contribute a
**`datahub-policy-context` skill** to `datahub-project/datahub-skills` (already forked as
`AmirmLotfy/datahub-skills`) covering domain-boundary and PII-aware asset selection, plus a
documentation PR on self-hosted MCP mutation configuration if a genuine gap is found while
building. Both are byproducts of real work, not manufactured contributions.

**Devpost package** — name *Zence*; tagline **"Keep every client in bounds."**; sections for
problem, solution, how it works, DataHub technologies used, architecture, what was built,
challenges, accomplishments, lessons, what's next, built-with, repo URL, live URL, artifact URL,
testing instructions, judge quickstart. Emphasis: DataHub as the source of organizational context ·
real interception of Claude Code operations · explainable decisions · cross-client prevention ·
lineage-aware approval · durable write-back.

**Video (<3:00):** 0:00 problem · 0:25 setup + boundary injection · 0:50 **Scenario A deny** with
evidence · 1:25 Scenario B lineage-aware ask · 1:55 Scenario C allow · 2:15 finalize → document in
the DataHub UI + duplicate-prevention proof · 2:45 repo/license/site.

---

## 20. Documentation set

`docs/`: `MASTER_PLAN.md` (this file, committed) · `PRD.md` · `ARCHITECTURE.md` ·
`THREAT_MODEL.md` · `POLICY_ENGINE.md` · `DATAHUB_INTEGRATION.md` · `CLAUDE_CODE_PLUGIN.md` ·
`DEMO_ENVIRONMENT.md` · `WEB_DESIGN_SYSTEM.md` · `TEST_STRATEGY.md` · `DEPLOYMENT.md` ·
`DEVPOST_SUBMISSION_PLAN.md` · `TROUBLESHOOTING.md`; plus root `TASKS.md`.

Each is authored in its owning phase (§16), not batched at the end — except `DEVPOST_SUBMISSION_PLAN.md`.

---

## 21. Deliberately excluded from the MVP

Stated plainly in `README.md` so nothing is over-claimed:

| Cut | Reason |
|---|---|
| **Local web dashboard** | Rich terminal + hosted replay covers it; saves ~2 days |
| **Plugin sub-agents** | No workflow benefit over hooks + commands |
| Proposals API write-back | Documents + structured properties already prove durable write-back |
| Tag/term mutation on client assets | Zence advises; it does not reclassify a client's catalog |
| General Python/TS/Java source parsing | Cannot be done honestly in 13 days; SQL/dbt/shell/YAML/MCP is the promise |
| Managed DataHub OAuth | Documented, not implemented or tested |
| Windows support | macOS + Linux only |
| Multi-user approval workflow / RBAC | Single-operator model |
| Full MDX docs system | Small curated static pages |
| Hook bypass prevention outside Claude Code | Out of trust boundary — stated, not hidden |

---

## 22. TASKS.md (to be committed at repo root)

```markdown
# Zence — Task Checklist

## Phase 0 — Infrastructure (human)
- [ ] Register zence.site at registrar
- [ ] Create GCP VM `zence-datahub` (e2-standard-4, europe-west1-b, 50 GB)
- [ ] Install Docker + uv on VM; `uv tool install acryl-datahub`
- [ ] `datahub docker quickstart`; verify localhost:9002
- [ ] Create DataHub PAT; store via plugin userConfig (Keychain)
- [ ] Verify IAP tunnel: GMS 200 on localhost:8080

## Phase 1 — Foundation
- [ ] uv + pnpm workspaces, .python-version=3.11
- [ ] LICENSE (Apache-2.0), README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, .env.example, .gitignore
- [ ] ruff/mypy/pytest + eslint/tsc config
- [ ] .github/workflows/ci.yml + integration.yml, issue/PR templates
- [ ] gh repo create AmirmLotfy/zence --public; topics + description
- [ ] CI green

## Phase 2 — Policy engine
- [ ] Pydantic schemas: Action, AssetRef, Evidence, Rule, Exception, Decision, RepoContext
- [ ] Emit JSON Schema for policy.yaml
- [ ] Predicate evaluator (10 operators, no eval, regex timeout)
- [ ] Precedence chain incl. tamper-first
- [ ] builtin_rules.yaml — ZR-001..ZR-014
- [ ] Fail-safe default matrix
- [ ] Exception expiry + timezone handling
- [ ] 60+ unit tests

## Phase 3 — DataHub providers
- [ ] MetadataProvider interface
- [ ] LiveProvider (acryl-datahub SDK) — entity, schema, domain, owners, tags, terms, lifecycle, lineage, structured props
- [ ] TTL cache (60 s) + negative caching
- [ ] FixtureProvider + `zence demo record`
- [ ] Fixture/live parity test
- [ ] **Spike Document.upsert write early**
- [ ] Auth failure + network failure paths → fail-safe

## Phase 4 — Extraction
- [ ] sql.py (sqlglot, aliases, CTEs) / dbt.py / shell.py (shlex) / yaml_recipe.py / mcp_args.py / paths.py / env.py
- [ ] Confidence scoring + FP controls + ignore_patterns
- [ ] Name→URN resolver with ambiguity handling
- [ ] Table-driven tests per format

## Phase 5 — Plugin & hooks
- [ ] .claude-plugin/plugin.json (+ userConfig: datahub_url, datahub_token[sensitive], mode)
- [ ] .mcp.json bundling mcp-server-datahub (TOOLS_IS_MUTATION_ENABLED=true)
- [ ] bin/zence-hook shim (uv bootstrap, fail-safe JSON, never crashes)
- [ ] hooks/hooks.json — 9 wirings per §10
- [ ] session_start / user_prompt / pre_tool / post_tool / post_tool_failure / stop / session_end
- [ ] 7 commands
- [ ] .claude-plugin/marketplace.json
- [ ] `claude plugin validate --strict` passes
- [ ] 40+ contract tests incl. malformed input, DataHub down, timeout, no-secrets

## Phase 6 — Demo catalog
- [ ] domains.yaml, datasets, glossary, structured properties, lineage
- [ ] Northstar (6 datasets, 1 critical dashboard, 1 deprecated + alternative)
- [ ] BluePeak (2 datasets, PII dataset + column tags, restricted owners)
- [ ] seed.py idempotent; verify.py exits 0/1
- [ ] examples/clients/{northstar-analytics,bluepeak-data} with .zence/

## Phase 7 — E2E flows
- [ ] Scenario A deny — in a real session
- [ ] Scenario B ask (2-hop lineage → critical dashboard)
- [ ] Scenario C allow
- [ ] Artifacts emitted to examples/artifacts/

## Phase 8 — Audit & write-back
- [ ] SQLite schema + migrations + indexes
- [ ] Redaction before persistence
- [ ] Document upsert with deterministic id
- [ ] zence.last_review structured property
- [ ] Scenario D + duplicate-prevention test
- [ ] JSONL/JSON export

## Phase 9 — CLI
- [ ] init, connect datahub, status, doctor, policy validate, inspect, evaluate
- [ ] audit list/show/export/prune
- [ ] demo up/seed/verify/record/run/down
- [ ] --json everywhere, stable exit codes, no secrets printed, Rich output

## Phase 10 — Website
- [ ] Next 16 static export, Tailwind v4, self-hosted Inter + JetBrains Mono
- [ ] 6 routes; homepage sections per §13
- [ ] Replay component over real artifacts + synthetic label
- [ ] Dark mode, reduced motion, 320px, WCAG AA, keyboard nav
- [ ] Lighthouse ≥95

## Phase 11 — Hardening
- [ ] Security suite (injection, traversal, symlink, malicious YAML/payload, redaction, bypass)
- [ ] gitleaks history scan, pip-audit, pnpm audit
- [ ] Latency benchmark vs §10 budgets

## Phase 12 — Docs
- [ ] 13 docs + README with cut list and trust boundary
- [ ] AI-assisted development disclosure
- [ ] scripts/verify-clean-clone.sh passes

## Phase 13 — Deploy
- [ ] vercel link/deploy preview → verify → --prod
- [ ] vercel domains add zence.site → report exact DNS records
- [ ] Re-verify HTTPS post-propagation

## Phase 14 — Submission
- [ ] Video script <3:00, shot list, VO, thumbnail brief
- [ ] Record + upload (public, YouTube)
- [ ] Devpost fields, screenshots, judge quickstart
- [ ] OSS contribution PR to datahub-skills

## Phase 15 — Final verification
- [ ] Fresh clone in clean directory → full documented setup
- [ ] Scenarios A–D reproduce
- [ ] Definition of Done (§18) fully ticked
- [ ] Submit before Aug 10, 5:00 PM EDT
```

---

## 23. Verification (how to prove this works end to end)

1. **Fail-safe first:** `pytest tests/contract -k "datahub_down or malformed or timeout"` — proves
   Zence never silently allows when it cannot see metadata.
2. **Real interception:** open Claude Code in `examples/clients/northstar-analytics/` and run
   Scenario A. The denial must appear *before* the tool executes, with DataHub URNs in the reason.
3. **Idempotency:** `/zence:finalize` twice, then `search_documents` in DataHub → exactly one
   document, `updated_at` advanced.
4. **Reproducibility:** `scripts/verify-clean-clone.sh` in an empty directory — clone, install,
   `datahub docker quickstart`, seed, verify, run scenarios.
5. **No over-claiming:** grep repo/site/video script for any capability not covered by a passing
   test; anything unproven moves to the §21 cut list.

---

## Human dependencies (only these — everything else is autonomous)

| # | Needs you | When |
|---|---|---|
| 1 | Register **zence.site** at a registrar | Before Phase 13 |
| 2 | Create the **GCP VM** and run DataHub quickstart (needs your gcloud session) | **Phase 0 — today** |
| 3 | Generate the **DataHub PAT** in the DataHub UI | Phase 0 |
| 4 | Set **DNS records** at the registrar after `vercel domains add` | Phase 13 |
| 5 | **Record and upload** the demo video | Phase 14 |
| 6 | **Submit** on Devpost | Phase 15 |
