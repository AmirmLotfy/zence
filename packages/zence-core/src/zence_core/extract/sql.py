"""SQL extraction via sqlglot.

Three things make this more than a regex over `FROM`:

* **CTE names are not tables.** `WITH recent AS (...) SELECT * FROM recent`
  references one real asset, not two. Reporting `recent` would put an
  unresolvable name in front of the policy engine on almost every real query.
* **Aliases are not tables.** `FROM northstar.leads l` must yield
  `northstar.leads`, never `l`. A two-character alias reaching the engine is a
  guaranteed false positive.
* **Columns belong to specific tables.** `SELECT p.phone` attributes `phone` to
  whatever `p` aliases, which is what lets a denial say *which column* was the
  problem rather than just naming the dataset.

When parsing fails — a fragment, a dialect quirk, a templated model — extraction
falls back to a conservative regex scan at reduced confidence. Failing to parse
must not mean failing to notice `bluepeak.patient_contacts`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from zence_core.extract.base import (
    IDENTIFIER_PATTERN,
    dedupe,
    extract_urns,
    is_plausible_asset_name,
    make_ref,
)
from zence_core.schemas import AssetRef, Confidence, Intent

EXTRACTOR = "sql"

#: Tried in order. Snowflake first because it is the most common warehouse in
#: the agency/consultancy setting Zence targets; `None` is sqlglot's permissive
#: generic dialect and catches most of the rest.
DIALECTS: tuple[str | None, ...] = ("snowflake", "bigquery", "postgres", None)

_DESTRUCTIVE_NODES = (exp.Drop, exp.TruncateTable)
_WRITE_NODES = (exp.Insert, exp.Update, exp.Create, exp.Merge, exp.Alter)


@dataclass(slots=True)
class SqlExtraction:
    refs: list[AssetRef] = field(default_factory=list)
    intents: set[Intent] = field(default_factory=set)
    parsed: bool = False
    """False when every dialect failed and the regex fallback was used. Recorded
    so a decision can say its evidence came from a degraded read of the SQL."""


def _qualified_name(table: exp.Table) -> str:
    parts = [part for part in (table.catalog, table.db, table.name) if part]
    return ".".join(parts)


def _statement_intents(statement: exp.Expression) -> set[Intent]:
    intents: set[Intent] = set()

    if isinstance(statement, _DESTRUCTIVE_NODES):
        intents.add(Intent.DESTRUCTIVE)
    elif isinstance(statement, exp.Delete):
        # A DELETE without a WHERE clause empties the table. Treat it as
        # destructive; a targeted delete is an ordinary write.
        intents.add(Intent.DESTRUCTIVE if statement.args.get("where") is None else Intent.WRITE)
    elif isinstance(statement, _WRITE_NODES):
        intents.add(Intent.WRITE)
    elif isinstance(statement, exp.Select):
        intents.add(Intent.READ)

    return intents


def _columns_by_source(statement: exp.Expression) -> dict[str, set[str]]:
    """Map each table alias (or bare name) to the columns referenced through it."""
    columns: dict[str, set[str]] = {}
    for column in statement.find_all(exp.Column):
        qualifier = column.table
        if not qualifier:
            continue
        columns.setdefault(qualifier, set()).add(column.name)
    return columns


def _extract_statement(statement: exp.Expression) -> tuple[list[AssetRef], set[Intent]]:
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    columns_by_source = _columns_by_source(statement)

    refs: list[AssetRef] = []
    for table in statement.find_all(exp.Table):
        name = _qualified_name(table)
        if not name or name.lower() in cte_names:
            continue
        if not is_plausible_asset_name(name):
            continue

        # Columns arrive keyed by whatever the query used to refer to the table:
        # its alias when it has one, otherwise its bare name.
        key = table.alias or table.name
        attributed = columns_by_source.get(key, set())

        refs.append(
            make_ref(
                name,
                extractor=EXTRACTOR,
                columns=tuple(sorted(attributed)),
            )
        )

    return refs, _statement_intents(statement)


def _fallback(text: str) -> SqlExtraction:
    """Regex scan for qualified identifiers when the parser gives up.

    Only dotted names are considered. A bare identifier in unparseable text is
    far more likely to be a variable or a fragment than a table, and the cost of
    guessing wrong is an approval prompt the user did not need.
    """
    refs: list[AssetRef] = []
    for match in IDENTIFIER_PATTERN.finditer(text):
        name = match.group(0)
        if "." not in name or not is_plausible_asset_name(name):
            continue
        refs.append(make_ref(name, extractor=f"{EXTRACTOR}:fallback", confidence=Confidence.MEDIUM))

    return SqlExtraction(refs=dedupe(refs), intents=set(), parsed=False)


def extract_sql(text: str, dialect: str | None = None) -> SqlExtraction:
    """Pull asset references and intent out of a SQL statement or script."""
    if not text or not text.strip():
        return SqlExtraction(parsed=True)

    dialects = (dialect, *DIALECTS) if dialect else DIALECTS

    for candidate in dialects:
        try:
            raw = sqlglot.parse(text, dialect=candidate)
        except Exception:  # noqa: S112 - trying the next dialect IS the handling
            # sqlglot raises ParseError, TokenError, and occasionally RecursionError
            # on pathological input. Any failure means "this dialect cannot read it";
            # the loop falls through to the regex scan once all of them have failed.
            continue

        statements = [item for item in raw if isinstance(item, exp.Expression)]
        if not statements:
            continue

        refs: list[AssetRef] = []
        intents: set[Intent] = set()
        for statement in statements:
            statement_refs, statement_intents = _extract_statement(statement)
            refs.extend(statement_refs)
            intents |= statement_intents

        refs.extend(extract_urns(text, extractor=EXTRACTOR))
        return SqlExtraction(refs=dedupe(refs), intents=intents, parsed=True)

    result = _fallback(text)
    result.refs.extend(extract_urns(text, extractor=EXTRACTOR))
    result.refs = dedupe(result.refs)
    return result
