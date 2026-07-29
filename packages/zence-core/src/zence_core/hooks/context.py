"""Assembling everything a hook needs, from a workspace and the environment.

Two files describe a governed workspace:

* `.zence/policy.yaml` — the boundary and the rules. Required.
* `.zence/project.yaml` — how to reach DataHub, and local preferences. Optional.

The split is deliberate: policy is what is allowed, project is how to connect.
Policy is meant to be committed and reviewed; project holds machine-specific
settings that differ between a laptop and CI.

**No secret is ever read from either file.** The DataHub token comes from the
environment — set by the plugin's `userConfig`, which Claude Code stores in the
macOS Keychain and exports as `CLAUDE_PLUGIN_OPTION_DATAHUB_TOKEN`. A token in a
workspace file would be a token in someone's git history.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from zence_core.policy import PolicyError, load_policy_file, workspace_from_policy
from zence_core.providers import (
    FixtureProvider,
    LiveProvider,
    MetadataProvider,
)
from zence_core.schemas import Mode, Policy, WorkspaceContext

ZENCE_DIR = ".zence"
POLICY_FILENAME = "policy.yaml"
PROJECT_FILENAME = "project.yaml"

#: Checked in order. The plugin option wins because it is the one the user set
#: through Claude Code's own configuration dialog.
URL_ENV_VARS = ("CLAUDE_PLUGIN_OPTION_DATAHUB_URL", "DATAHUB_GMS_URL")
TOKEN_ENV_VARS = ("CLAUDE_PLUGIN_OPTION_DATAHUB_TOKEN", "DATAHUB_GMS_TOKEN")
MODE_ENV_VARS = ("ZENCE_MODE", "CLAUDE_PLUGIN_OPTION_MODE")

#: How far up the tree to look for `.zence/`. Bounded so a session started in an
#: unrelated directory does not silently adopt a policy from several levels up.
MAX_PARENT_SEARCH = 8


class NotGovernedError(RuntimeError):
    """No `.zence/policy.yaml` was found. This workspace is not governed."""


@dataclass(frozen=True, slots=True)
class ProjectSettings:
    """Non-policy settings from `.zence/project.yaml`."""

    datahub_url: str | None = None
    fixture_path: str | None = None
    ignore_patterns: tuple[str, ...] = ()
    client_paths: dict[str, str] | None = None

    @classmethod
    def load(cls, path: Path) -> ProjectSettings:
        if not path.exists():
            return cls()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            # A broken project file is not worth failing a session over; the
            # policy file is what actually governs. Connection falls back to env.
            return cls()

        if not isinstance(data, dict):
            return cls()

        datahub = data.get("datahub")
        url = datahub.get("url") if isinstance(datahub, dict) else None

        return cls(
            datahub_url=str(url) if url else None,
            fixture_path=(str(data["fixture"]) if data.get("fixture") else None),
            ignore_patterns=tuple(data.get("ignore_patterns", []) or []),
            client_paths=data.get("client_paths")
            if isinstance(data.get("client_paths"), dict)
            else None,
        )


@dataclass(frozen=True, slots=True)
class ZenceContext:
    """Everything a hook needs to make and record a decision."""

    root: Path
    policy: Policy
    workspace: WorkspaceContext
    settings: ProjectSettings
    provider: MetadataProvider

    @property
    def policy_path(self) -> Path:
        return self.root / ZENCE_DIR / POLICY_FILENAME

    @property
    def watch_paths(self) -> list[str]:
        """Files whose change should re-run SessionStart."""
        return [
            f"{ZENCE_DIR}/{POLICY_FILENAME}",
            f"{ZENCE_DIR}/{PROJECT_FILENAME}",
        ]


def find_workspace_root(start: Path) -> Path | None:
    """Walk up looking for `.zence/policy.yaml`."""
    try:
        current = start.resolve()
    except (OSError, RuntimeError):
        return None

    for _ in range(MAX_PARENT_SEARCH):
        if (current / ZENCE_DIR / POLICY_FILENAME).is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return None


def resolve_mode(policy: Policy) -> Mode:
    """Environment beats the policy file, so a session can be run in audit mode
    without editing a committed file."""
    override = _first_env(MODE_ENV_VARS)
    if override:
        try:
            return Mode(override.lower())
        except ValueError:
            pass
    return policy.mode


def build_provider(root: Path, settings: ProjectSettings, mode: Mode) -> MetadataProvider:
    """Choose a provider.

    Order, and the reasoning for it:

    1. **A catalog named in the environment always wins.** If someone exported
       `DATAHUB_GMS_URL`, they mean it, and quietly reading a recording instead
       would be the exact dishonesty this codebase refuses.
    2. **Otherwise a recording, if the workspace ships one.** This is what lets
       the demo workspaces produce a real decision on a fresh clone with nothing
       installed — the recording came from a live instance via
       `zence demo record`, and every decision it produces is stamped
       `provider: fixture` so nobody can mistake it for a live read.
    3. **Otherwise live**, at whatever the workspace or the default names.

    A fixture is still never a *fallback*: it is chosen up front and declared,
    not substituted when a lookup fails. When a live catalog goes down mid-run,
    `LiveProvider` says so and the fail-safe matrix decides.
    """
    if _first_env(URL_ENV_VARS):
        return LiveProvider(server=_first_env(URL_ENV_VARS) or "", token=_first_env(TOKEN_ENV_VARS))

    if settings.fixture_path:
        candidate = root / settings.fixture_path
        if candidate.is_file():
            return FixtureProvider.from_file(candidate)

    url = settings.datahub_url or "http://localhost:8080"
    return LiveProvider(server=url, token=_first_env(TOKEN_ENV_VARS))


def load_context(cwd: Path) -> ZenceContext:
    """Locate the workspace and assemble its context.

    Raises `NotGovernedError` when there is no policy, and `PolicyError` when
    there is one that does not load. Callers turn both into a hook response —
    the first is a no-op, the second is worth telling the user about, because a
    workspace with a broken policy is a workspace that is not protected.
    """
    root = find_workspace_root(cwd)
    if root is None:
        raise NotGovernedError(f"no {ZENCE_DIR}/{POLICY_FILENAME} found at or above {cwd}")

    policy_path = root / ZENCE_DIR / POLICY_FILENAME
    policy = load_policy_file(policy_path)

    settings = ProjectSettings.load(root / ZENCE_DIR / PROJECT_FILENAME)
    mode = resolve_mode(policy)

    workspace = workspace_from_policy(policy, root, policy_path)
    if workspace.mode is not mode:
        workspace = workspace.model_copy(update={"mode": mode})

    return ZenceContext(
        root=root,
        policy=policy,
        workspace=workspace,
        settings=settings,
        provider=build_provider(root, settings, mode),
    )


def describe_load_failure(exc: Exception) -> str:
    """A one-line explanation suitable for showing in a session."""
    if isinstance(exc, PolicyError):
        return f"Zence policy failed to load: {exc}"
    return f"Zence could not start: {exc}"


__all__ = [
    "MAX_PARENT_SEARCH",
    "POLICY_FILENAME",
    "PROJECT_FILENAME",
    "ZENCE_DIR",
    "NotGovernedError",
    "ProjectSettings",
    "ZenceContext",
    "build_provider",
    "describe_load_failure",
    "find_workspace_root",
    "load_context",
    "resolve_mode",
]
