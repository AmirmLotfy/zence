"""Packaging invariants.

These are cheap, but they catch a real class of release mistake: a workspace that
imports locally and breaks once installed, or a version that drifts between the
two packages and the plugin manifest.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import zence_cli
import zence_core

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pyproject(relative: str) -> dict[str, object]:
    with (REPO_ROOT / relative).open("rb") as handle:
        return tomllib.load(handle)


def test_packages_import() -> None:
    assert zence_core.__version__
    assert zence_cli.__version__


def test_versions_agree() -> None:
    """zence-cli depends on zence-core; a version skew between them is a bug."""
    assert zence_core.__version__ == zence_cli.__version__


def test_declared_versions_match_runtime() -> None:
    core = _pyproject("packages/zence-core/pyproject.toml")["project"]
    cli = _pyproject("packages/zence-cli/pyproject.toml")["project"]
    assert isinstance(core, dict)
    assert isinstance(cli, dict)

    assert core["version"] == zence_core.__version__
    assert cli["version"] == zence_cli.__version__


def test_every_package_is_apache_licensed() -> None:
    """The hackathon requires Apache-2.0 to be detectable, and consistency is cheap."""
    for relative in (
        "pyproject.toml",
        "packages/zence-core/pyproject.toml",
        "packages/zence-cli/pyproject.toml",
    ):
        project = _pyproject(relative)["project"]
        assert isinstance(project, dict)
        assert project["license"] == "Apache-2.0", relative


def test_license_is_canonical_apache_text() -> None:
    """GitHub only detects Apache-2.0 from the unmodified text.

    Editing the appendix placeholders to insert a copyright line is the common
    mistake — it silently breaks detection, and the hackathon requires the
    license to be visible in the repository's About section. Attribution goes in
    NOTICE instead, which is what Apache-2.0 actually prescribes.
    """
    license_text = (REPO_ROOT / "LICENSE").read_text()

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Copyright [yyyy] [name of copyright owner]" in license_text

    notice = (REPO_ROOT / "NOTICE").read_text()
    assert "Copyright 2026 Amir Lotfy" in notice


def test_python_floor_is_311() -> None:
    """mcp-server-datahub requires >=3.11; dropping below it silently breaks the demo."""
    for relative in (
        "pyproject.toml",
        "packages/zence-core/pyproject.toml",
        "packages/zence-cli/pyproject.toml",
    ):
        project = _pyproject(relative)["project"]
        assert isinstance(project, dict)
        assert project["requires-python"] == ">=3.11", relative

    assert (REPO_ROOT / ".python-version").read_text().strip() == "3.11"


def test_env_example_contains_no_populated_secrets() -> None:
    """`.env.example` is tracked. It must never carry a real value."""
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    secret_keys = {"DATAHUB_GMS_TOKEN"}

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() in secret_keys:
            assert value.strip() == "", f"{key} must be empty in .env.example"
