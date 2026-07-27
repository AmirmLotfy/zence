# Contributing to Zence

Thanks for taking a look. Zence is a solo-maintained open-source project; issues and pull
requests are welcome.

## Setup

Zence needs [`uv`](https://docs.astral.sh/uv/) for Python and
[`pnpm`](https://pnpm.io/) for the website.

```bash
git clone https://github.com/AmirmLotfy/zence.git
cd zence
uv sync --all-packages      # Python workspace (pins 3.11)
pnpm install                # website workspace
```

Most of the codebase runs without DataHub. Unit tests and hook contract tests use recorded
fixtures, so you can contribute to the policy engine, extraction, or the website without standing
up a catalog.

## Running checks

```bash
uv run ruff format --check .        # formatting
uv run ruff check .                 # lint
uv run mypy                         # types (strict)
uv run pytest -m "not integration and not e2e"
```

Integration and end-to-end tests need a live DataHub instance and are excluded by default. See
[`docs/DEMO_ENVIRONMENT.md`](docs/DEMO_ENVIRONMENT.md) to stand one up.

## Ground rules

**Never fake an integration.** A fixture may stand in for DataHub in a test. A fixture must never
be presented as a live connection at runtime. If DataHub is unreachable, the code says so and the
fail-safe matrix applies — it does not quietly fall back to recorded data.

**The policy engine stays deterministic.** A model may help classify intent. It must never be the
thing that decides `allow` / `ask` / `deny`. No `eval`, no arbitrary expressions in policy files.

**Fail safe, not open.** Any new code path that can fail must have a documented decision for the
failure case, and a test asserting it. When in doubt: `ask`.

**No secrets, ever.** Not in code, tests, fixtures, commit messages, or example files.

## Adding a policy rule

1. Add the rule to `packages/zence-core/src/zence_core/policy/builtin_rules.yaml` with a `ZR-` id
2. Add unit tests covering match, non-match, and precedence against neighbouring rules
3. Document it in `docs/POLICY_ENGINE.md`

## Adding an extractor

Extractors live in `packages/zence-core/src/zence_core/extract/`. Each returns `AssetRef` objects
with an explicit `confidence`. Add table-driven tests including **false-positive cases** — an
extractor that over-reports causes approval fatigue, which is its own failure mode.

## Commits and pull requests

Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`), present tense.

Keep pull requests focused. CI must be green: lint, types, tests, plugin validation, policy schema
validation, secret scanning, and the website build.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).

## License

Contributions are licensed under [Apache License 2.0](LICENSE).
