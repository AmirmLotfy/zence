# Security Policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub Security Advisories](https://github.com/AmirmLotfy/zence/security/advisories/new)
rather than opening a public issue.

Include the affected version or commit, reproduction steps, and the impact you observed. Expect an
acknowledgement within 72 hours.

## What Zence protects against

Zence is a **guardrail inside the Claude Code workflow**. It reduces accidental and
agent-mediated mistakes: cross-client data access, PII leakage into generated code, unreviewed
changes to assets with critical downstream impact, and destructive operations against production.

## What Zence does not protect against

Stated plainly, because a security tool that overstates its boundary is worse than none:

- **Anything outside Claude Code.** A user running the same query in a shell, a notebook, or a
  BI tool is not intercepted.
- **A determined operator.** Policy files live in the workspace. Zence denies edits to `.zence/**`
  from within a session and audits the attempt, but it does not defend against a user who edits
  them out-of-band.
- **Warehouse permissions.** Zence is not a replacement for correct grants in Snowflake,
  BigQuery, or Postgres. It is a second line of defence, not the first.
- **Kernel or process isolation.** Zence is not a sandbox.

## Threat model highlights

| Threat | Mitigation |
|---|---|
| Prompt injection via DataHub descriptions or documents | Metadata is rendered as quoted, escaped evidence and never concatenated as instructions. Policy decisions read typed fields only, never free text. |
| Untrusted MCP tool output | Responses are schema-validated; unexpected shapes route to `ask`. |
| DataHub token theft | Stored in the macOS Keychain via plugin `userConfig`, never written to a file, never logged, never printed by the CLI. |
| Shell injection | Commands are parsed with `shlex`; hooks use exec form with `args`; no `shell=True`. |
| Path traversal / symlinks | Paths are resolved and confirmed inside the workspace root; symlinks escaping the root are rejected. |
| Log leakage | Redaction runs before persistence, not on read. Covered by `tests/security/`. |
| Duplicate or replayed write-back | Deterministic DataHub document `id` plus a UNIQUE local idempotency key. |
| Fail-open on metadata lookup failure | Explicitly prevented — a cross-client reference with a failed lookup is never allowed. |

The full model lives in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Secrets

No secret is ever committed. `.env` is gitignored, only `.env.example` is tracked, and CI runs
secret scanning over the full history on every pull request.
