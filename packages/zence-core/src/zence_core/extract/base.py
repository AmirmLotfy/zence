"""Shared machinery for asset-reference extraction.

Extractors turn raw tool input — SQL, a shell command, a dbt model, an MCP call —
into :class:`AssetRef` objects. They deliberately do **not** decide anything. An
extractor's only job is "this text mentions something that looks like a data
asset, and here is how sure I am".

Confidence is the contract between this layer and the policy engine. A rule can
demand HIGH confidence before it will deny, so a fuzzy guess from a shell command
can inform a decision without being able to block one on its own.

False positives are the failure mode that matters here. An extractor that
over-reports produces approval fatigue, users start clicking through prompts, and
the whole tool stops working. Every extractor filters aggressively and every
extractor has false-positive tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from zence_core.schemas import AssetKind, AssetRef, Confidence

#: A DataHub URN. Matched exactly, so anything that parses is EXACT confidence.
URN_PATTERN = re.compile(r"urn:li:[a-zA-Z]+:\([^)]*\)|urn:li:[a-zA-Z]+:[\w.\-]+")

#: Bare or dotted identifiers: `orders`, `analytics.orders`, `db.schema.orders`.
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*){0,3}")

#: Environment names as they appear in identifiers, paths, and command flags.
ENVIRONMENT_PATTERN = re.compile(
    r"\b(PROD|PRODUCTION|PRE?PROD|STAGING|STAGE|DEV|DEVELOPMENT|QA|TEST|SANDBOX)\b",
    re.IGNORECASE,
)

_ENVIRONMENT_CANONICAL = {
    "PROD": "PROD",
    "PRODUCTION": "PROD",
    "PREPROD": "STAGING",
    "PPROD": "STAGING",
    "STAGING": "STAGING",
    "STAGE": "STAGING",
    "DEV": "DEV",
    "DEVELOPMENT": "DEV",
    "QA": "QA",
    "TEST": "QA",
    "SANDBOX": "DEV",
}

#: Identifiers that are never data assets. Without this, `SELECT ... FROM` yields
#: a reference to `select`, every rule fires, and the tool is unusable.
STOPWORDS: frozenset[str] = frozenset(
    {
        # SQL keywords that survive naive tokenizing
        "select",
        "from",
        "where",
        "join",
        "inner",
        "left",
        "right",
        "full",
        "outer",
        "cross",
        "on",
        "using",
        "group",
        "order",
        "by",
        "having",
        "limit",
        "offset",
        "union",
        "all",
        "distinct",
        "as",
        "and",
        "or",
        "not",
        "in",
        "is",
        "null",
        "case",
        "when",
        "then",
        "else",
        "end",
        "with",
        "insert",
        "into",
        "values",
        "update",
        "set",
        "delete",
        "create",
        "table",
        "view",
        "drop",
        "alter",
        "add",
        "column",
        "index",
        "if",
        "exists",
        "cast",
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "coalesce",
        "over",
        "partition",
        "asc",
        "desc",
        "between",
        "like",
        "ilike",
        "true",
        "false",
        # Shell and tooling noise
        "echo",
        "cat",
        "grep",
        "awk",
        "sed",
        "cd",
        "ls",
        "rm",
        "cp",
        "mv",
        "python",
        "python3",
        "pip",
        "uv",
        "npm",
        "pnpm",
        "node",
        "git",
        "docker",
        "dbt",
        "run",
        "build",
        "test",
        "compile",
        "seed",
        "snapshot",
        # Common local file/dir names that look like dotted identifiers
        "self",
        "none",
        "this",
        "args",
        "kwargs",
    }
)

#: File extensions that make a dotted token a filename, not a table.
_FILE_EXTENSIONS: frozenset[str] = frozenset(
    {
        "py",
        "ts",
        "tsx",
        "js",
        "jsx",
        "sql",
        "yaml",
        "yml",
        "json",
        "toml",
        "md",
        "txt",
        "csv",
        "tsv",
        "sh",
        "bash",
        "zsh",
        "env",
        "lock",
        "cfg",
        "ini",
        "log",
        "html",
        "css",
        "png",
        "jpg",
        "svg",
        "parquet",
        "avro",
    }
)

#: Shortest plausible asset name. One- and two-character identifiers are almost
#: always table aliases (`l`, `p`, `t1`) rather than real assets.
MIN_IDENTIFIER_CHARS = 3


def canonical_environment(text: str) -> str | None:
    """Extract a canonical environment name, if the text names one."""
    match = ENVIRONMENT_PATTERN.search(text)
    if match is None:
        return None
    return _ENVIRONMENT_CANONICAL.get(match.group(1).upper())


def is_plausible_asset_name(name: str) -> bool:
    """Filter obvious non-assets before they reach the policy engine."""
    if not name:
        return False

    parts = name.split(".")
    last = parts[-1].lower()

    # `models/orders.sql` — a file, not a table.
    if len(parts) > 1 and last in _FILE_EXTENSIONS:
        return False

    # Stopwords are applied strictly to bare identifiers and loosely to qualified
    # ones. The list exists to stop `FROM northstar` yielding a reference to
    # `from` in the fallback regex and in shell arguments — but `db.schema.table`
    # is a perfectly ordinary warehouse path, and rejecting any qualified name
    # containing a SQL keyword would silently drop real assets. Qualification is
    # itself evidence, so only an all-stopword name is discarded.
    lowered = [part.lower() for part in parts]
    if len(parts) == 1:
        if lowered[0] in STOPWORDS:
            return False
        return len(name) >= MIN_IDENTIFIER_CHARS and not name.isdigit()

    if all(part in STOPWORDS for part in lowered):
        return False

    return all(part for part in parts)


def confidence_for_name(name: str) -> Confidence:
    """More qualification means more confidence.

    `analytics.orders` is far more likely to be a real table than `orders`,
    which could be a variable, a CTE, or an alias.
    """
    depth = name.count(".")
    if depth >= 2:
        return Confidence.HIGH
    if depth == 1:
        return Confidence.HIGH
    return Confidence.MEDIUM


def make_ref(
    raw_text: str,
    *,
    extractor: str,
    kind: AssetKind = AssetKind.DATASET,
    confidence: Confidence | None = None,
    columns: tuple[str, ...] = (),
) -> AssetRef:
    return AssetRef(
        raw_text=raw_text,
        kind=kind,
        confidence=confidence or confidence_for_name(raw_text),
        extractor=extractor,
        columns=columns,
    )


def extract_urns(text: str, *, extractor: str) -> list[AssetRef]:
    """DataHub URNs appearing verbatim. Unambiguous, so EXACT confidence."""
    refs: list[AssetRef] = []
    for match in URN_PATTERN.finditer(text):
        urn = match.group(0)
        kind = AssetKind.URN
        if urn.startswith("urn:li:dataset:"):
            kind = AssetKind.DATASET
        elif urn.startswith(("urn:li:dashboard:", "urn:li:chart:")):
            kind = AssetKind.DASHBOARD

        refs.append(
            AssetRef(
                raw_text=urn,
                kind=kind,
                confidence=Confidence.EXACT,
                extractor=extractor,
                resolved_urn=urn,
            )
        )
    return refs


def dedupe(refs: Iterable[AssetRef]) -> list[AssetRef]:
    """Collapse duplicates, keeping the most confident mention of each name.

    The same table named three times in one query is one reference. Merging the
    column lists matters: a rule that reports which columns triggered it should
    see every column the statement touched, not just those in the first clause.
    """
    best: dict[str, AssetRef] = {}
    order: list[str] = []

    for ref in refs:
        key = ref.raw_text.lower()
        existing = best.get(key)
        if existing is None:
            best[key] = ref
            order.append(key)
            continue

        columns = tuple(sorted(set(existing.columns) | set(ref.columns)))
        winner = (
            ref
            if _confidence_rank(ref.confidence) < _confidence_rank(existing.confidence)
            else existing
        )
        best[key] = winner.model_copy(update={"columns": columns})

    return [best[key] for key in order]


def _confidence_rank(confidence: Confidence) -> int:
    from zence_core.schemas import CONFIDENCE_ORDER

    return CONFIDENCE_ORDER.index(confidence)
