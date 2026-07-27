## What changed

<!-- One or two sentences. What does this do that the codebase did not do before? -->

## Why

<!-- The problem this solves. Link an issue if there is one. -->

## How it was verified

<!-- Commands run, tests added, and what you observed. "CI is green" alone is not verification
     for behaviour changes. -->

```
$
```

## Checklist

- [ ] `uv run ruff format --check . && uv run ruff check . && uv run mypy` passes
- [ ] `uv run pytest -m "not integration and not e2e"` passes
- [ ] New behaviour has tests, including the failure path
- [ ] No secrets in code, tests, fixtures, or commit messages
- [ ] No fixture is presented as a live DataHub connection at runtime
- [ ] Any new fallible code path has a documented decision for its failure case

## Policy or extraction changes only

- [ ] Rule documented in `docs/POLICY_ENGINE.md` with its `ZR-` id
- [ ] Precedence against neighbouring rules is tested
- [ ] Extractors include **false-positive** test cases
