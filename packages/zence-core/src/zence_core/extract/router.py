"""Turning a Claude Code tool call into an Action plus asset references.

One entry point, :func:`normalize`, called by every PreToolUse hook. It decides
which extractors apply, merges their results, and produces the `Action` the
policy engine evaluates.

Redaction happens here, at the boundary, before anything is stored or logged.
Doing it later would mean the raw payload had already been written somewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zence_core.extract.base import dedupe
from zence_core.extract.dbt import extract_dbt, looks_like_dbt
from zence_core.extract.mcp_args import datahub_tool_name, extract_mcp
from zence_core.extract.paths import targets_zence_config, workspace_relative
from zence_core.extract.shell import extract_shell
from zence_core.extract.sql import extract_sql
from zence_core.extract.yaml_recipe import extract_yaml
from zence_core.schemas import MAX_EXCERPT_CHARS, Action, AssetRef, Intent, ToolKind

#: Tools that write to disk, and the argument holding the target path.
FILE_TOOLS: dict[str, str] = {
    "Write": "file_path",
    "Edit": "file_path",
    "NotebookEdit": "notebook_path",
    "MultiEdit": "file_path",
}

#: Tools that only read.
READ_TOOLS: frozenset[str] = frozenset({"Read", "Glob", "Grep", "NotebookRead"})

#: Words that mark the thing next to them as a credential.
# The suppression on the next line is for bandit, which sees a variable whose
# name contains "secret" holding a string literal and assumes a hardcoded
# credential. It is the opposite: this is the pattern that finds and removes them.
_SECRET_WORD = r"(?:password|passwd|secret|token|api[_\-]?key|apikey|credential|auth)"  # noqa: S105

#: Values matching these are replaced before the excerpt is stored. Zence's audit
#: trail must never become the place a leaked token lives.
#:
#: Ordered: specific token *shapes* first, then key/value forms, then the flag
#: form. Three of these exist because an adversarial test found the naive
#: versions leaking — `Authorization: Bearer <token>` redacted the word "Bearer"
#: and left the token intact, `--api-key <token>` was not covered at all, and a
#: quoted key (`'token': '<value>'`) broke the key/value pattern.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Recognisable shapes, regardless of what they are assigned to.
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{16,})\b"), "«github-token»"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"), "«api-key»"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"), "«jwt»"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "«slack-token»"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "«aws-key-id»"),
    # `Authorization: Bearer <token>` and bare `Bearer <token>`. The scheme is
    # kept so the shape stays readable; the credential after it is what matters.
    (
        re.compile(r"(?i)\b(bearer|basic|token)\s+[A-Za-z0-9._\-+/=]{8,}"),
        r"\1 «redacted»",
    ),
    (re.compile(r"(?i)\bauthorization\s*[:=]\s*\S+"), "authorization: «redacted»"),
    # `token=x`, `"token": "x"`, `'api_key' => 'x'` — the key may be quoted, and
    # the separator may be `:`, `=`, or `=>`.
    #
    # Every quantifier here is bounded. Unbounded `[\w.\-]*` on both sides of the
    # alternation makes the engine try every split point at every position, which
    # is superlinear: 10 KB of ordinary text took 2.4 seconds, and this runs on
    # every tool call. A credential key longer than 32 characters either side of
    # the word is not a real thing.
    (
        re.compile(
            rf"(?i)([\"']?)([\w.\-]{{0,32}}{_SECRET_WORD}[\w.\-]{{0,32}})\1"
            r"[ \t]*(?::|=>?)[ \t]*"
            r"[\"']?[^\s\"',;)}\]]{1,512}[\"']?"
        ),
        r"\2=«redacted»",
    ),
    # `--api-key <value>`: a flag whose name says credential.
    (
        re.compile(
            rf"(?i)(--?[\w-]{{0,32}}{_SECRET_WORD}[\w-]{{0,32}})[=\s]{{1,4}}[^\s\"',;]{{1,512}}"
        ),
        r"\1 «redacted»",
    ),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "«email»"),
)

_SQL_HINT = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|TRUNCATE|ALTER|WITH)\b",
    re.IGNORECASE,
)


#: Hard cap on what the redaction patterns are allowed to scan.
#:
#: Redaction runs before truncation on purpose — truncating to the excerpt
#: length first could sever a secret's terminator and defeat the pattern. But
#: "before truncation" cannot mean "unbounded": these patterns contain
#: quantifiers that backtrack, and a 200 KB file content made `redact` hang.
#: This is generous enough that no realistic credential spans it, and small
#: enough that the scan stays linear in practice.
MAX_REDACTION_SCAN_CHARS = 64 * 1024


def redact(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    """Strip credentials and personal data, then truncate.

    Order matters in both directions. Truncating to the excerpt length first
    would leave a secret's prefix intact with its terminator cut off, so
    redaction goes first — but only over a bounded window, because the patterns
    themselves are not free on arbitrarily long input.
    """
    if not text:
        return ""

    # Bound the work before the patterns see it. Anything past this window is
    # discarded rather than scanned; the excerpt is truncated far shorter anyway.
    cleaned = text[:MAX_REDACTION_SCAN_CHARS]
    for pattern, replacement in _REDACTIONS:
        cleaned = pattern.sub(replacement, cleaned)

    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1] + "…"
    return cleaned


@dataclass(slots=True)
class Normalized:
    action: Action
    refs: list[AssetRef] = field(default_factory=list)
    degraded_parse: bool = False
    """True when a parser failed and a weaker fallback was used. Surfaced so a
    decision can admit its evidence was incomplete."""


def _classify(tool_name: str) -> ToolKind:
    if datahub_tool_name(tool_name):
        return ToolKind.MCP_CATALOG
    if tool_name == "Bash":
        return ToolKind.SHELL
    if tool_name in FILE_TOOLS:
        return ToolKind.FILE_EDIT if tool_name != "Write" else ToolKind.FILE_WRITE
    if tool_name in READ_TOOLS:
        return ToolKind.OTHER
    return ToolKind.OTHER


def _file_content(tool_name: str, tool_input: dict[str, Any]) -> str:
    """The text a file tool would write."""
    for key in ("content", "new_string", "new_source", "replace_all_string"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _extract_file(path: str, content: str) -> tuple[list[AssetRef], set[Intent], bool]:
    refs: list[AssetRef] = []
    intents: set[Intent] = set()
    degraded = False

    suffix = Path(path).suffix.lower()

    if looks_like_dbt(content, path):
        result = extract_dbt(content, path)
        refs.extend(result.refs)
        intents |= result.intents

    if suffix in {".sql"} or _SQL_HINT.search(content):
        sql = extract_sql(content)
        refs.extend(sql.refs)
        intents |= sql.intents
        degraded = degraded or not sql.parsed

    if suffix in {".yaml", ".yml"}:
        recipe = extract_yaml(content)
        refs.extend(recipe.refs)
        intents |= recipe.intents
        degraded = degraded or not recipe.parsed

    return refs, intents, degraded


def normalize(
    tool_name: str,
    tool_input: dict[str, Any],
    workspace_root: Path,
    *,
    hook_event: str = "PreToolUse",
    tool_use_id: str | None = None,
) -> Normalized:
    """Normalize one tool call into an Action and its asset references."""
    tool_kind = _classify(tool_name)
    refs: list[AssetRef] = []
    intents: set[Intent] = set()
    raw_paths: list[str] = []
    excerpt_source = ""
    degraded = False

    if tool_kind is ToolKind.MCP_CATALOG:
        result = extract_mcp(tool_name, tool_input)
        refs.extend(result.refs)
        intents |= result.intents
        excerpt_source = str(tool_input)

    elif tool_kind is ToolKind.SHELL:
        command = str(tool_input.get("command", ""))
        shell = extract_shell(command)
        refs.extend(shell.refs)
        intents |= shell.intents
        raw_paths.extend(shell.paths)
        excerpt_source = command

    elif tool_name in FILE_TOOLS:
        path = str(tool_input.get(FILE_TOOLS[tool_name], ""))
        if path:
            raw_paths.append(path)
        content = _file_content(tool_name, tool_input)
        excerpt_source = content or path

        file_refs, file_intents, file_degraded = _extract_file(path, content)
        refs.extend(file_refs)
        intents |= file_intents
        degraded = degraded or file_degraded

        # Writing a file is a write even when its content names no assets.
        intents.add(Intent.CODEGEN if file_refs else Intent.WRITE)

    else:
        for key in ("file_path", "path", "pattern", "prompt"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                excerpt_source = value
                if key in {"file_path", "path"}:
                    raw_paths.append(value)
                break
        intents.add(Intent.READ)

    if not intents:
        intents.add(Intent.UNKNOWN)

    relative_paths = tuple(workspace_relative(workspace_root, path) or path for path in raw_paths)

    action = Action(
        tool_name=tool_name,
        tool_kind=tool_kind,
        hook_event=hook_event,
        intents=frozenset(intents),
        tool_use_id=tool_use_id,
        input_excerpt=redact(excerpt_source),
        target_paths=relative_paths,
        targets_zence_config=targets_zence_config(workspace_root, tuple(raw_paths)),
    )

    return Normalized(action=action, refs=dedupe(refs), degraded_parse=degraded)
