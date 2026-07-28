# Test strategy

```bash
uv run pytest -m "not integration and not e2e"    # everything below except live
uv run ruff check . && uv run mypy
```

Unit and contract tests run on recorded fixtures, so CI needs no catalog and a
contributor needs no 8 GB Docker stack.

## The suites

| Suite | Runs on | Asserts |
|---|---|---|
| **Contract** | fixtures | The hook's exact wire format — allow, ask, deny, malformed input, internal failure, timeout, no secrets in output |
| **Unit** | fixtures | Operators, precedence, exceptions and expiry, extraction per format, the fail-safe matrix, redaction, audit persistence, idempotency |
| **Security** | fixtures | Traversal, symlinks, symlink loops, command injection, tamper detection |
| **Integration** | live DataHub | Search, entities, lineage, write-back, duplicate prevention, auth and network failure |
| **Website** | CI | Types, lint, static export, all six routes, no external font requests |

## The contract suite matters most

Every other test proves Zence reached the right conclusion. The contract tests
prove the conclusion actually reaches Claude Code in a form it acts on.

A hook that returns a subtly wrong shape does not error — it is **ignored**. And
an ignored security control is worse than an absent one, because the user
believes it ran. So those tests assert exact field names from the published
hooks reference, not merely that something came back.

## What is worth testing

**Near-misses over matches.** A rule that fires on everything is
indistinguishable from a working one until somebody is drowning in prompts. Each
built-in rule has a positive case and at least one case where it must *not*
fire.

**False positives in extraction.** An extractor that reports table aliases, CTE
names, SQL keywords and filenames produces a prompt on every action, and people
learn to approve reflexively. Precision is a safety property here.

**The failure path, always.** Any code path that can fail needs a documented
decision for the failure and a test asserting it. When in doubt: `ask`.

**Bounds, not just behaviour.** Two of the worst bugs found so far were latency,
not logic — a 28-second write-back and a 28-second resolve, both from the SDK's
default retry-with-backoff, both inside a hook. Those are pinned by tests that
assert an elapsed-time bound.

## Regressions worth reading

Each of these was found by a test rather than by inspection, and each is pinned:

- A transport failure reported as `NOT_FOUND`, making an outage
  indistinguishable from a clean catalog.
- Rules firing against unresolved evidence, producing a confident cross-client
  finding built on no evidence while the honest message never appeared.
- Write-back stalling the Stop hook for 28 seconds when DataHub was down.
- CI type-checking a *different program* than developers, because it synced
  without the optional DataHub extra.

## Secrets in tests

There is **no allowlist**. Credential-shaped fixtures are assembled from
fragments at runtime, so nothing in the repository looks like a secret and
scanning keeps its full default ruleset. Exempting the test directory would
create exactly the place a real credential tends to end up.

## Live tests

```bash
export DATAHUB_GMS_URL=... DATAHUB_GMS_TOKEN=...
uv run zence demo seed && uv run zence demo verify
uv run pytest -m integration
```

These run on demand and nightly, not on every pull request. Standing up an 8 GB
catalog per PR would be slow and would make the suite flaky for reasons
unrelated to the change.
