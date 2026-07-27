"""CI entry point: every policy file in the repository must load.

Run as `python -m zence_core.policy.validate_all`.

A policy that cannot be parsed is a policy that cannot be enforced, and the
failure mode is silent — Zence would fall back to the safe default on every
action and the workspace would look like it was protected. This check makes that
class of mistake fail the build instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

from zence_core.policy.loader import PolicyError, builtin_rules, load_policy_file

#: Where policy files live in this repository.
SEARCH_GLOBS = (
    "examples/**/.zence/policy.yaml",
    "examples/policies/*.yaml",
    "demo/**/policy.yaml",
    ".zence/policy.yaml",
)


def repo_root() -> Path:
    """Walk up to the directory holding pyproject.toml."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").exists() and (candidate / ".git").exists():
            return candidate
    return Path.cwd()


def discover(root: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in SEARCH_GLOBS:
        found.extend(sorted(root.glob(pattern)))
    return sorted(set(found))


def main() -> int:
    root = repo_root()

    try:
        rules = builtin_rules()
    except PolicyError as exc:
        print(f"FAIL  builtin_rules.yaml\n      {exc}", file=sys.stderr)
        return 1
    print(f"ok    builtin_rules.yaml ({len(rules)} rules)")

    policies = discover(root)
    if not policies:
        print("note  no workspace policy files found yet")
        return 0

    failures = 0
    for path in policies:
        relative = path.relative_to(root)
        try:
            policy = load_policy_file(path)
        except PolicyError as exc:
            failures += 1
            print(f"FAIL  {relative}\n      {exc}", file=sys.stderr)
            continue
        print(
            f"ok    {relative} "
            f"(v{policy.policy_version}, {len(policy.rules)} rules, "
            f"{len(policy.exceptions)} exceptions)"
        )

    if failures:
        print(f"\n{failures} policy file(s) failed validation", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
