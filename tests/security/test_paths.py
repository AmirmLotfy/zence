"""Path containment and tamper detection.

The threat is a tool call that writes somewhere Zence did not expect: outside the
workspace entirely, or to Zence's own configuration via a route that does not
look like `.zence/`.

Every check runs against the **resolved** path. Checking the string before
resolution is the classic mistake — `notes.md` symlinked to `.zence/policy.yaml`
passes a string check and fails a resolved one.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from zence_core.extract import (
    escapes_workspace,
    normalize,
    resolve_within,
    targets_zence_config,
    workspace_relative,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / ".zence").mkdir()
    (tmp_path / ".zence" / "policy.yaml").write_text("policy_version: '1.0.0'\n")
    (tmp_path / ".claude").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "revenue.sql").write_text("SELECT 1\n")
    return tmp_path


# --- Containment -------------------------------------------------------------


def test_ordinary_path_resolves_inside(workspace: Path) -> None:
    assert resolve_within(workspace, "models/revenue.sql") is not None
    assert workspace_relative(workspace, "models/revenue.sql") == "models/revenue.sql"


def test_traversal_is_rejected(workspace: Path) -> None:
    assert escapes_workspace(workspace, "../../../etc/passwd")
    assert resolve_within(workspace, "../outside.txt") is None


def test_deep_traversal_that_lands_back_inside_is_accepted(workspace: Path) -> None:
    """`models/../models/x.sql` is inside; containment is about the destination."""
    assert resolve_within(workspace, "models/../models/revenue.sql") is not None


def test_absolute_path_outside_the_workspace_is_rejected(workspace: Path) -> None:
    assert escapes_workspace(workspace, "/etc/passwd")


def test_nonexistent_path_is_still_containment_checked(workspace: Path) -> None:
    """A Write creates its target, so the file need not exist yet."""
    assert resolve_within(workspace, "models/not-yet.sql") is not None
    assert escapes_workspace(workspace, "../not-yet.sql")


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_symlink_pointing_outside_is_rejected(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    (workspace / "escape").symlink_to(outside)

    assert escapes_workspace(workspace, "escape/secrets.txt")


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_symlink_loop_does_not_hang(workspace: Path) -> None:
    a = workspace / "loop-a"
    b = workspace / "loop-b"
    a.symlink_to(b)
    b.symlink_to(a)

    assert resolve_within(workspace, "loop-a") is None


def test_embedded_null_byte_is_rejected(workspace: Path) -> None:
    assert resolve_within(workspace, "models/\x00evil.sql") is None


# --- Tamper detection --------------------------------------------------------


def test_direct_policy_edit_is_flagged(workspace: Path) -> None:
    assert targets_zence_config(workspace, (".zence/policy.yaml",))


def test_any_file_under_zence_is_flagged(workspace: Path) -> None:
    assert targets_zence_config(workspace, (".zence/project.yaml",))
    assert targets_zence_config(workspace, (".zence/nested/anything.txt",))


def test_claude_settings_are_flagged(workspace: Path) -> None:
    """Disabling the hooks achieves the same end as editing the policy."""
    assert targets_zence_config(workspace, (".claude/settings.json",))
    assert targets_zence_config(workspace, (".claude/settings.local.json",))
    assert targets_zence_config(workspace, (".mcp.json",))


def test_traversal_into_zence_is_flagged(workspace: Path) -> None:
    assert targets_zence_config(workspace, ("models/../.zence/policy.yaml",))


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_symlink_to_the_policy_is_flagged(workspace: Path) -> None:
    """The reason containment is checked after resolution, not before."""
    (workspace / "innocent-notes.md").symlink_to(workspace / ".zence" / "policy.yaml")
    assert targets_zence_config(workspace, ("innocent-notes.md",))


def test_a_path_outside_the_workspace_is_treated_as_tampering(workspace: Path) -> None:
    """Zence will not permit a write it cannot locate. Refusing is cheaper than
    being wrong about where the bytes land."""
    assert targets_zence_config(workspace, ("../../../etc/crontab",))


def test_ordinary_files_are_not_flagged(workspace: Path) -> None:
    assert not targets_zence_config(workspace, ("models/revenue.sql",))
    assert not targets_zence_config(workspace, ("README.md",))
    assert not targets_zence_config(workspace, ())


def test_zence_as_a_substring_is_not_enough(workspace: Path) -> None:
    """`.zence` must be a path component, not a prefix of some other name."""
    assert not targets_zence_config(workspace, ("zence-notes.md",))
    assert not targets_zence_config(workspace, ("docs/.zencerc-example.md",))


# --- End to end through the router -------------------------------------------


def test_normalize_marks_a_traversal_write_as_tampering(workspace: Path) -> None:
    result = normalize("Write", {"file_path": "../../evil.sh", "content": "#!/bin/sh"}, workspace)
    assert result.action.targets_zence_config is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_normalize_catches_a_symlinked_policy_edit(workspace: Path) -> None:
    (workspace / "notes.md").symlink_to(workspace / ".zence" / "policy.yaml")
    result = normalize("Edit", {"file_path": "notes.md", "new_string": "mode: audit"}, workspace)
    assert result.action.targets_zence_config is True


def test_command_injection_attempt_is_parsed_not_executed(workspace: Path) -> None:
    """Zence reads commands the way a linter does. Nothing is ever run."""
    marker = workspace / "pwned.txt"
    result = normalize("Bash", {"command": f"echo hi; touch {marker}"}, workspace)

    assert not marker.exists()
    assert result.action.tool_kind.value == "shell"
