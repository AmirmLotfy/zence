"""Terminal and JSON output.

Every command supports `--json`. That is not decoration: the CLI is meant to be
usable from a script, from CI, and from the hook path, and a tool that only emits
prettified tables forces callers to parse them.

Exit codes are stable and documented, because the whole point of a policy tool is
that something else can act on its answer.
"""

from __future__ import annotations

import json
import sys
from enum import IntEnum
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

from zence_core.schemas import Verdict

#: Matched to the website palette so a screenshot and the terminal agree.
THEME = Theme(
    {
        "allow": "green",
        "ask": "yellow",
        "deny": "red",
        "muted": "dim",
        "heading": "bold",
        "urn": "cyan",
    }
)

VERDICT_STYLE = {Verdict.ALLOW: "allow", Verdict.ASK: "ask", Verdict.DENY: "deny"}
VERDICT_MARK = {Verdict.ALLOW: "✓", Verdict.ASK: "?", Verdict.DENY: "✗"}


class ExitCode(IntEnum):
    """Stable exit codes. Callers depend on these."""

    OK = 0
    ERROR = 1
    """Something went wrong that is not covered more specifically below."""

    NOT_GOVERNED = 3
    """No `.zence/policy.yaml` was found."""

    POLICY_INVALID = 4
    """A policy exists but does not load."""

    DATAHUB_UNREACHABLE = 5
    """The catalog could not be reached."""

    BLOCKED = 6
    """An evaluation returned deny. Used by `zence evaluate` so a script can
    branch on the verdict without parsing output."""

    NEEDS_APPROVAL = 7
    """An evaluation returned ask."""


console = Console(theme=THEME, stderr=False)
err_console = Console(theme=THEME, stderr=True)


def emit_json(payload: Any) -> None:
    """Write a JSON document to stdout.

    `default=str` so a datetime or enum degrades to a readable string rather
    than raising after the command has already done its work.
    """
    sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")


def error(message: str) -> None:
    err_console.print(f"[deny]error[/deny] {message}")


def warn(message: str) -> None:
    err_console.print(f"[ask]warning[/ask] {message}")


def note(message: str) -> None:
    console.print(f"[muted]{message}[/muted]")


def heading(text: str) -> None:
    console.print()
    console.print(f"[heading]{text}[/heading]")


def field_table(rows: list[tuple[str, str]], *, title: str | None = None) -> None:
    """A borderless two-column layout. Reads as prose, not as a spreadsheet."""
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0), title=title)
    table.add_column(style="muted", justify="right", no_wrap=True)
    table.add_column()
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


def verdict_banner(verdict: Verdict, rule_id: str, title: str) -> None:
    style = VERDICT_STYLE[verdict]
    mark = VERDICT_MARK[verdict]
    console.print(f"[{style}]{mark} {verdict.value.upper()}[/{style}]  {rule_id}  {title}")
