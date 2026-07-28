# Troubleshooting

Start with `zence doctor`. It checks `uv`, the workspace policy, the token, and
whether DataHub is reachable — and it never prints the token, because its output
is the first thing anyone pastes into an issue.

---

### Nothing happens — no context, no decisions

Zence only acts in a governed workspace.

```bash
zence status
```

`no .zence/policy.yaml found` means this repository is not governed. Run
`zence init --client "…" --domain "urn:li:domain:…"`.

If `status` works but hooks do not fire, the plugin is not enabled: check
`/plugin`, and remember that changes to `hooks/` need `/reload-plugins` or a
restart.

### "Zence could not start (uv is not installed)"

The shim needs `uv` to build its runtime. Install it
([docs.astral.sh/uv](https://docs.astral.sh/uv/)) and start a new session.

Note what happened when it could not start: a `PreToolUse` returned **ask**, not
silence. That is deliberate — silence reads to Claude Code as "no opinion".

### The first tool call is slow

Expected once. The shim builds a virtualenv on first use, around 7.7 seconds
against a 30-second timeout. Subsequent calls are 0.6–0.8s. Run `zence doctor`
after installing to warm it before you need it.

### Everything is being asked about

Usually the catalog is unreachable, and Zence is refusing to convert ignorance
into permission.

```bash
zence doctor          # is DataHub reachable?
zence audit list      # are the reasons all "could not reach DataHub"?
```

If DataHub is fine, the assets may genuinely be unclassified — an asset with no
domain is not in-domain, because unclassified data in a multi-client catalog is
exactly what to ask about. `zence inspect <asset>` shows what DataHub returned.

### A decision looks wrong

```bash
zence audit list
zence audit show <id>
```

That shows the rule, the references extracted with their confidence, the
evidence, and which provider it came from. If `metadata from` says `fixture`,
the workspace is pointing at a recording rather than a live catalog — check
`.zence/project.yaml`.

To test a change without provoking a violation in a live session:

```bash
zence evaluate --tool Write --file x.sql --content "SELECT …"
```

### A policy will not load

```bash
zence policy validate
```

Common causes, all rejected at load time on purpose:

- an unknown field path — the error suggests the closest real one
- a `$reference` to a list that is not declared
- an exception targeting a **deny** rule; only asks can be waived
- `expires_at` without a timezone offset

### Editing `.zence/policy.yaml` is denied

Working as intended. Changing the boundary from inside the session it governs is
refused by ZR-014, which is triggered by a hardcoded flag rather than a policy
condition and is not downgraded by audit mode.

Edit the file outside a governed session.

### The write-back did nothing

`zence finalize` writes only when something was decided since the last write —
otherwise every session would produce a document recording that nothing
happened.

```bash
zence audit list --here      # was anything blocked or asked about?
```

If decisions exist but the write failed, `zence audit show` carries the reason;
usually the token lacks mutation rights, or `TOOLS_IS_MUTATION_ENABLED` is unset
on the MCP server.

### Two finalizations, two documents?

They should not be. The document id is `sha256(workspace::session)`, so the
second upsert updates the first. If you see two, the session id changed between
runs — check that `--session` matches.

### Where is my data?

`~/.zence/zence.db`. Move it with `ZENCE_DB_PATH`, trim it with
`zence audit prune --older-than 30`, or delete it; nothing outside your machine
holds a copy.

---

Still stuck? [Open an issue](https://github.com/AmirmLotfy/zence/issues) with
`zence doctor` output and a redacted `zence audit show`. For anything
security-relevant, please use a
[private advisory](https://github.com/AmirmLotfy/zence/security/advisories/new)
instead.
