"""dbt model references.

`ref()` and `source()` are the two ways a dbt model names an upstream asset, and
both are far more reliable signals than a bare identifier — they are declarations,
not guesses. That is why they resolve at HIGH confidence even when unqualified.

The surrounding SQL is still parsed separately: a dbt model can reference a raw
table directly, and Jinja templating frequently defeats the SQL parser, in which
case `extract_sql`'s fallback picks up what it can.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from zence_core.extract.base import dedupe, is_plausible_asset_name, make_ref
from zence_core.schemas import AssetRef, Confidence, Intent

EXTRACTOR = "dbt"

#: {{ ref('model') }} and {{ ref('package', 'model') }}
REF_PATTERN = re.compile(
    r"""\{\{-?\s*ref\s*\(\s*
        (['"])(?P<first>[\w.\-]+)\1
        (?:\s*,\s*(['"])(?P<second>[\w.\-]+)\3)?
        \s*\)\s*-?\}\}""",
    re.VERBOSE,
)

#: {{ source('source_name', 'table_name') }}
SOURCE_PATTERN = re.compile(
    r"""\{\{-?\s*source\s*\(\s*
        (['"])(?P<source>[\w.\-]+)\1
        \s*,\s*
        (['"])(?P<table>[\w.\-]+)\3
        \s*\)\s*-?\}\}""",
    re.VERBOSE,
)

#: A dbt model file is itself a materialization, so editing one is a write.
_MODEL_PATH = re.compile(r"(^|/)models/.+\.sql$")


@dataclass(slots=True)
class DbtExtraction:
    refs: list[AssetRef] = field(default_factory=list)
    intents: set[Intent] = field(default_factory=set)
    is_dbt: bool = False


def looks_like_dbt(text: str, path: str | None = None) -> bool:
    if path and _MODEL_PATH.search(path):
        return True
    return bool(REF_PATTERN.search(text) or SOURCE_PATTERN.search(text))


def extract_dbt(text: str, path: str | None = None) -> DbtExtraction:
    """Pull `ref()` and `source()` targets out of a dbt model."""
    if not text:
        return DbtExtraction()

    refs: list[AssetRef] = []

    for match in REF_PATTERN.finditer(text):
        # Two arguments means (package, model); the model is the second.
        name = match.group("second") or match.group("first")
        if is_plausible_asset_name(name):
            refs.append(make_ref(name, extractor=EXTRACTOR, confidence=Confidence.HIGH))

    for match in SOURCE_PATTERN.finditer(text):
        name = f"{match.group('source')}.{match.group('table')}"
        if is_plausible_asset_name(name):
            refs.append(make_ref(name, extractor=EXTRACTOR, confidence=Confidence.HIGH))

    intents: set[Intent] = set()
    if refs:
        intents.add(Intent.READ)
    if path and _MODEL_PATH.search(path):
        # Writing a model file defines a table; that is codegen with a write
        # behind it, not a read.
        intents.add(Intent.CODEGEN)

    return DbtExtraction(
        refs=dedupe(refs),
        intents=intents,
        is_dbt=looks_like_dbt(text, path),
    )
