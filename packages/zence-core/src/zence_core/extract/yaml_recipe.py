"""DataHub ingestion recipes and other data-bearing YAML.

An ingestion recipe is a compact description of exactly which assets a pipeline
will touch — `table_pattern.allow`, `database`, `schema_pattern` — which makes it
unusually high-signal for something that is, on its face, a config file. It is
also the file most likely to carry a credential, so values under any key that
looks secret are never read into a reference.

Parsed with `yaml.safe_load` only. A recipe from a cloned repository is untrusted
input, and `yaml.load` would let it construct arbitrary Python objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from zence_core.extract.base import canonical_environment, dedupe, is_plausible_asset_name, make_ref
from zence_core.schemas import AssetRef, Confidence, Intent

EXTRACTOR = "yaml"

#: Keys whose values name assets.
ASSET_KEYS: frozenset[str] = frozenset(
    {
        "table",
        "tables",
        "dataset",
        "datasets",
        "table_pattern",
        "dataset_pattern",
        "schema_pattern",
        "database_pattern",
        "view_pattern",
        "allow",
        "deny",
    }
)

#: Keys whose values are never read. Recipes routinely carry credentials, and a
#: password has no business appearing in an audit record.
SECRET_KEYS = re.compile(
    r"password|secret|token|key|credential|auth|private|passphrase|sas|conn", re.IGNORECASE
)

#: A recipe has a `source` block with a `type`; that is the reliable marker.
_RECIPE_MARKERS = ("source", "sink", "pipeline_name", "transformers")


@dataclass(slots=True)
class YamlExtraction:
    refs: list[AssetRef] = field(default_factory=list)
    intents: set[Intent] = field(default_factory=set)
    environment: str | None = None
    is_recipe: bool = False
    parsed: bool = True


def _walk(node: Any, key: str | None, refs: list[AssetRef]) -> None:
    if isinstance(node, dict):
        for child_key, child in node.items():
            name = str(child_key)
            if SECRET_KEYS.search(name):
                continue
            _walk(child, name, refs)
        return

    if isinstance(node, list | tuple):
        for child in node:
            _walk(child, key, refs)
        return

    if not isinstance(node, str) or not node:
        return
    if key is None or key not in ASSET_KEYS:
        return
    if SECRET_KEYS.search(key):
        return

    # Recipe patterns are regexes: `northstar\.leads.*`. Strip the obvious regex
    # furniture so the remaining literal can be resolved against the catalog.
    literal = node.strip().strip("^$").replace("\\", "").rstrip(".*").rstrip(".")
    if not literal or not is_plausible_asset_name(literal):
        return

    refs.append(make_ref(literal, extractor=EXTRACTOR, confidence=Confidence.HIGH))


def looks_like_recipe(data: Any) -> bool:
    return isinstance(data, dict) and any(marker in data for marker in _RECIPE_MARKERS)


def extract_yaml(text: str) -> YamlExtraction:
    """Extract asset references from a YAML document."""
    if not text or not text.strip():
        return YamlExtraction()

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        # Malformed YAML yields nothing rather than a regex guess. A broken
        # config file is not evidence of anything.
        return YamlExtraction(parsed=False)

    if data is None:
        return YamlExtraction()

    refs: list[AssetRef] = []
    _walk(data, None, refs)

    is_recipe = looks_like_recipe(data)
    intents: set[Intent] = set()
    if is_recipe:
        # A recipe moves data into the catalog, which is a metadata mutation.
        intents.add(Intent.MUTATE)
    elif refs:
        intents.add(Intent.READ)

    return YamlExtraction(
        refs=dedupe(refs),
        intents=intents,
        environment=canonical_environment(text),
        is_recipe=is_recipe,
        parsed=True,
    )
