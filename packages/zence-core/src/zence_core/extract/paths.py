"""Filesystem path handling.

Security-relevant. Two questions are asked here and both have to be answered
conservatively:

1. **Is this path inside the workspace?** Answered after full resolution, so
   `../../../etc/passwd` and a symlink pointing outside the root are both caught.
   Resolution happens before the containment check, never after.

2. **Does this path touch Zence's own configuration?** This is the ZR-014
   trigger, and it is matched on the *resolved* path so a symlink named
   `notes.md` pointing at `.zence/policy.yaml` cannot slip through.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

#: Everything under here configures Zence itself.
ZENCE_CONFIG_DIR = ".zence"

#: Claude Code configuration that can disable or reroute the hooks. Editing any
#: of these from inside a governed session is the same class of action as
#: editing the policy.
GUARDED_RELATIVE_PATHS: frozenset[str] = frozenset(
    {
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".mcp.json",
    }
)


def resolve_within(root: Path, candidate: str | Path) -> Path | None:
    """Resolve `candidate` and return it only if it stays inside `root`.

    Returns None when the path escapes, which callers treat as "refuse to reason
    about this" rather than "this is fine".
    """
    try:
        root_resolved = root.resolve()
        # strict=False: the file may not exist yet (a Write creates it), and a
        # non-existent path is still worth containment-checking.
        target = (root_resolved / candidate).resolve()
    except (OSError, RuntimeError, ValueError):
        # RuntimeError covers symlink loops; ValueError covers embedded nulls.
        return None

    if target == root_resolved or root_resolved in target.parents:
        return target
    return None


def escapes_workspace(root: Path, candidate: str | Path) -> bool:
    return resolve_within(root, candidate) is None


def targets_zence_config(root: Path, candidates: tuple[str, ...]) -> bool:
    """Whether any path would modify Zence's or Claude Code's configuration.

    A path that escapes the workspace also returns True. Zence will not silently
    permit a write it cannot locate, and refusing is cheaper than being wrong.
    """
    for candidate in candidates:
        resolved = resolve_within(root, candidate)
        if resolved is None:
            return True

        try:
            relative = resolved.relative_to(root.resolve())
        except ValueError:  # pragma: no cover — resolve_within already excluded this
            return True

        posix = PurePosixPath(relative.as_posix())
        if ZENCE_CONFIG_DIR in posix.parts:
            return True
        if posix.as_posix() in GUARDED_RELATIVE_PATHS:
            return True

    return False


def workspace_relative(root: Path, candidate: str | Path) -> str | None:
    """A workspace-relative string for display and audit, or None if outside."""
    resolved = resolve_within(root, candidate)
    if resolved is None:
        return None
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:  # pragma: no cover
        return None
