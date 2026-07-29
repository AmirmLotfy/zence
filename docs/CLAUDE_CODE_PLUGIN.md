# The Claude Code plugin

## Install

```
/plugin marketplace add AmirmLotfy/zence
/plugin install zence@zence
```

You are prompted for your DataHub URL and token at enable time. The token goes
to your system keychain via `userConfig` — never to a workspace file, never to
the repository.

For local development:

```bash
git clone https://github.com/AmirmLotfy/zence
/plugin marketplace add ./zence
/plugin install zence@zence
```

## Hooks

| Event | Matcher | Does | Blocks |
|---|---|---|---|
| `SessionStart` | `startup\|resume\|clear` | Resolve the boundary, inject it, set the session title | no |
| `UserPromptSubmit` | — | Flag intent (production, destructive, PII) | no |
| `PreToolUse` | `mcp__.*datahub.*__.*` | Evaluate catalog access | **yes** |
| `PreToolUse` | `Bash` | Evaluate the command | **yes** |
| `PreToolUse` | `Write\|Edit\|MultiEdit\|NotebookEdit` | Parse content for asset references | **yes** |
| `PostToolUse` | union | Record what actually happened | no |
| `PostToolUseFailure` | union | Record a failure, distinctly from a denial | no |
| `Stop` | — | Write the session document to DataHub, if anything changed | no |
| `SessionEnd` | — | Flush | no |

The MCP matcher is a regex covering **both** `mcp__datahub__*` and
`mcp__plugin_zence_datahub__*`. Matching only one would leave a hole depending
on how the server happened to be registered.

`UserPromptSubmit` classifies intent and nothing more. It sees a sentence, not a
resolved URN, and a rule that fired on prose would produce false denies on the
first ambiguous phrasing. Asset decisions belong to `PreToolUse`, where there is
evidence.

## Responses

An **allow** returns `{}` — no prompt, no transcript noise, nothing. A guardrail
that announces itself on safe work is one people turn off.

A **deny** or **ask** returns:

```json
{"hookSpecificOutput": {
  "hookEventName": "PreToolUse",
  "permissionDecision": "deny",
  "permissionDecisionReason": "…shown to you…",
  "additionalContext": "…shown to Claude, including the remediation…"
}}
```

The remediation is the point. A bare refusal invites the model to retry a
variation; naming the in-domain alternative turns a refusal into a redirect.

Zence never uses exit code 2 to block. The JSON form carries
`additionalContext`, which the exit-code form cannot.

## The shim

`bin/zence-hook` is POSIX `sh`. It resolves an interpreter in order:

1. `$ZENCE_PYTHON`
2. a `zence-hook` already on `PATH`
3. a venv at `$CLAUDE_PLUGIN_DATA/venv`
4. builds that venv with `uv` — first run only

**`uv` is the only prerequisite.** The venv lives in `CLAUDE_PLUGIN_DATA` rather
than `CLAUDE_PLUGIN_ROOT` because the root changes on every plugin update and is
cleaned up behind you.

The shim fails safe **without parsing JSON**: the event name arrives as `$1`, so
a missing `uv` returns `ask` on a `PreToolUse` rather than staying silent.
Silence reads to Claude Code as "no opinion", which would let the very operation
Zence exists to check proceed unexamined.

Cold start ~14s (30s timeout) — it builds the runtime venv. Warm 0.20–0.28s
against a recording.

## Timeouts

A watchdog fires inside the handler before Claude Code's own limit — 4s on
`UserPromptSubmit`, 8s elsewhere — so a slow decision is still *our* decision.
A hook that times out emits nothing, and nothing means the normal permission
flow proceeds.

Override with `ZENCE_HOOK_DEADLINE_SECONDS`.

## Validation

```bash
./scripts/validate-plugin.sh
```

Validates both manifests. `claude plugin validate` stops at the marketplace
manifest when both live in the same `.claude-plugin/` directory, so a plain
invocation leaves `plugin.json` unchecked behind a green tick — the script
validates it from an isolated copy. CI runs this on every push.

## Uninstall

```
/plugin uninstall zence@zence
```

Removes hooks and the bundled MCP server. `.zence/` files and `~/.zence/zence.db`
are yours and are left alone; delete them if you want the history gone.
