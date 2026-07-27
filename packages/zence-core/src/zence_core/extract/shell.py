"""Shell command analysis.

Commands are tokenized with `shlex`, never executed and never passed to a shell.
Zence reads them the way a linter does.

Two jobs:

* **Intent.** `rm -rf`, `DROP TABLE`, `TRUNCATE`, `bq rm` are destructive;
  `psql -c "INSERT ..."` is a write. This is what feeds ZR-004 and ZR-005.
* **Embedded SQL.** `bq query '...'`, `snowsql -q '...'`, `psql -c '...'` carry a
  full statement in an argument, which is handed to the SQL extractor.

Confidence is capped at MEDIUM for anything inferred from a bare argument. Shell
arguments are ambiguous by nature — a path, a flag value and a table name all
look alike — and a MEDIUM reference cannot trigger a deny rule on its own.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from zence_core.extract.base import (
    canonical_environment,
    dedupe,
    extract_urns,
    is_plausible_asset_name,
    make_ref,
)
from zence_core.schemas import AssetRef, Confidence, Intent

EXTRACTOR = "shell"

#: Commands whose arguments may contain SQL, mapped to the flags that carry it.
SQL_CARRYING: dict[str, tuple[str, ...]] = {
    "bq": ("query",),
    "snowsql": ("-q", "--query"),
    "psql": ("-c", "--command"),
    "mysql": ("-e", "--execute"),
    "duckdb": ("-c",),
    "clickhouse-client": ("-q", "--query"),
}

#: Destructive shell verbs, matched on the command token.
DESTRUCTIVE_COMMANDS: frozenset[str] = frozenset({"rm", "rmdir", "shred", "truncate"})

#: Destructive subcommands for cloud CLIs, matched as `<command> <subcommand>`.
DESTRUCTIVE_SUBCOMMANDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("bq", "rm"),
        ("aws", "rb"),
        ("gsutil", "rm"),
        ("gcloud", "sql"),
        ("dbt", "run-operation"),
    }
)

_DESTRUCTIVE_SQL = re.compile(
    r"\b(DROP\s+(TABLE|SCHEMA|DATABASE|VIEW)|TRUNCATE\s+TABLE|DELETE\s+FROM)\b",
    re.IGNORECASE,
)
_WRITE_SQL = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\w|MERGE\s+INTO|CREATE\s+(OR\s+REPLACE\s+)?(TABLE|VIEW))\b",
    re.IGNORECASE,
)
_RECURSIVE_FORCE = re.compile(r"^-{1,2}[a-zA-Z]*[rRf][a-zA-Z]*$")


@dataclass(slots=True)
class ShellExtraction:
    refs: list[AssetRef] = field(default_factory=list)
    intents: set[Intent] = field(default_factory=set)
    environment: str | None = None
    embedded_sql: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)


def _tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        # Unbalanced quotes. Fall back to whitespace splitting rather than
        # returning nothing — a malformed command still deserves inspection.
        return command.split()


def _split_pipeline(tokens: list[str]) -> list[list[str]]:
    """Break on shell operators so each sub-command is judged on its own."""
    separators = {"&&", "||", ";", "|", "&"}
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in separators:
            segments.append([])
        else:
            segments[-1].append(token)
    return [segment for segment in segments if segment]


def _embedded_sql(segment: list[str]) -> list[str]:
    if not segment:
        return []

    command = segment[0].rsplit("/", 1)[-1]
    flags = SQL_CARRYING.get(command)
    if flags is None:
        return []

    found: list[str] = []
    # Named `arg` rather than `token`: bandit's S105 flags any variable called
    # `token` compared against a literal as a possible hardcoded credential.
    for index, arg in enumerate(segment[1:], start=1):
        # `bq query '<sql>'` — the SQL is the first non-flag after the subcommand.
        if arg in flags or (command == "bq" and arg == "query"):
            for candidate in segment[index + 1 :]:
                if not candidate.startswith("-"):
                    found.append(candidate)
                    break
    return found


def _segment_intents(segment: list[str]) -> set[Intent]:
    intents: set[Intent] = set()
    if not segment:
        return intents

    command = segment[0].rsplit("/", 1)[-1]
    rest = segment[1:]

    if command in DESTRUCTIVE_COMMANDS:
        # Plain `rm file` is ordinary; `rm -rf dir` is what ZR-005 is about.
        if command != "rm" or any(_RECURSIVE_FORCE.match(token) for token in rest):
            intents.add(Intent.DESTRUCTIVE)
        else:
            intents.add(Intent.WRITE)

    if rest and (command, rest[0]) in DESTRUCTIVE_SUBCOMMANDS:
        intents.add(Intent.DESTRUCTIVE)

    joined = " ".join(segment)
    if _DESTRUCTIVE_SQL.search(joined):
        intents.add(Intent.DESTRUCTIVE)
    elif _WRITE_SQL.search(joined):
        intents.add(Intent.WRITE)

    if command in {"cp", "mv", "tee", "curl", "scp", "rsync"}:
        intents.add(Intent.WRITE)

    return intents


def _candidate_assets(segment: list[str]) -> list[AssetRef]:
    """Dotted identifiers in arguments — table-shaped, at capped confidence."""
    refs: list[AssetRef] = []
    for token in segment[1:]:
        if token.startswith("-") or "/" in token:
            continue
        if "." not in token or not is_plausible_asset_name(token):
            continue
        refs.append(make_ref(token, extractor=EXTRACTOR, confidence=Confidence.MEDIUM))
    return refs


def extract_shell(command: str) -> ShellExtraction:
    """Analyse a shell command without running it."""
    if not command or not command.strip():
        return ShellExtraction()

    tokens = _tokenize(command)
    segments = _split_pipeline(tokens)

    refs: list[AssetRef] = []
    intents: set[Intent] = set()
    embedded: list[str] = []
    paths: list[str] = []

    for segment in segments:
        intents |= _segment_intents(segment)
        embedded.extend(_embedded_sql(segment))
        refs.extend(_candidate_assets(segment))
        paths.extend(token for token in segment[1:] if "/" in token and not token.startswith("-"))

    # Anything the embedded SQL names is a far stronger signal than an argument.
    for statement in embedded:
        from zence_core.extract.sql import extract_sql

        inner = extract_sql(statement)
        refs.extend(inner.refs)
        intents |= inner.intents

    refs.extend(extract_urns(command, extractor=EXTRACTOR))

    if not intents:
        intents.add(Intent.READ)

    return ShellExtraction(
        refs=dedupe(refs),
        intents=intents,
        environment=canonical_environment(command),
        embedded_sql=embedded,
        paths=paths,
    )
