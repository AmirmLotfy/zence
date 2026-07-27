"""DataHub MCP tool arguments.

This is the highest-signal extractor by a wide margin, and the one that makes
Zence's interception of the catalog meaningful. Every other extractor is reading
text and inferring. Here the arguments are structured: when a tool is called with
`urn="urn:li:dataset:(...)"`, that is not a guess, it is the asset.

Tool names are matched loosely (`.*datahub.*`) so this works whether the server
is configured by the user as `mcp__datahub__*` or bundled by the Zence plugin as
`mcp__plugin_zence_datahub__*`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from zence_core.extract.base import (
    dedupe,
    extract_urns,
    is_plausible_asset_name,
    make_ref,
)
from zence_core.schemas import AssetKind, AssetRef, Confidence, Intent

EXTRACTOR = "mcp"

#: Matches a DataHub MCP tool however the server happens to be registered.
DATAHUB_TOOL = re.compile(r"^mcp__.*datahub.*__(?P<tool>.+)$", re.IGNORECASE)

#: Argument keys that hold a URN outright.
URN_KEYS: frozenset[str] = frozenset(
    {
        "urn",
        "urns",
        "entity_urn",
        "entity_urns",
        "dataset_urn",
        "dataset_urns",
        "asset_urn",
        "asset_urns",
        "source_urn",
        "target_urn",
        "related_assets",
    }
)

#: Argument keys that hold a free-text query or a dataset name.
NAME_KEYS: frozenset[str] = frozenset(
    {"query", "keyword", "keywords", "name", "dataset", "table", "search"}
)

#: Tools that change catalog state. Anything here carries MUTATE intent, which is
#: what stops an agent quietly reclassifying another client's assets.
MUTATION_TOOLS: frozenset[str] = frozenset(
    {
        "add_tags",
        "remove_tags",
        "add_terms",
        "remove_terms",
        "add_owners",
        "remove_owners",
        "set_domains",
        "remove_domains",
        "update_description",
        "add_structured_properties",
        "remove_structured_properties",
        "set_lifecycle_stage",
        "save_document",
        "create_glossary_term",
        "create_glossary_term_version",
        "add_related_terms",
        "accept_or_reject_proposals",
    }
)

#: Read-only catalog tools.
READ_TOOLS: frozenset[str] = frozenset(
    {
        "search",
        "get_entities",
        "get_lineage",
        "get_lineage_paths_between",
        "list_schema_fields",
        "get_dataset_queries",
        "search_documents",
        "grep_documents",
        "get_me",
        "list_lifecycle_stages",
        "find_sql_context",
        "draft_sql_for_tables",
        "list_pending_proposals",
    }
)


@dataclass(slots=True)
class McpExtraction:
    refs: list[AssetRef] = field(default_factory=list)
    intents: set[Intent] = field(default_factory=set)
    tool: str | None = None
    is_datahub: bool = False


def datahub_tool_name(tool_name: str) -> str | None:
    """The bare tool name if this is a DataHub MCP call, else None."""
    match = DATAHUB_TOOL.match(tool_name)
    return match.group("tool") if match else None


def _walk(value: Any, key: str | None, refs: list[AssetRef]) -> None:
    """Recurse through the argument tree collecting anything asset-shaped."""
    if isinstance(value, dict):
        for child_key, child in value.items():
            _walk(child, str(child_key), refs)
        return

    if isinstance(value, list | tuple):
        for child in value:
            _walk(child, key, refs)
        return

    if not isinstance(value, str) or not value:
        return

    if value.startswith("urn:li:"):
        refs.extend(extract_urns(value, extractor=EXTRACTOR))
        return

    if key in URN_KEYS:
        # Declared as a URN key but not URN-shaped — still worth resolving.
        if is_plausible_asset_name(value):
            refs.append(make_ref(value, extractor=EXTRACTOR, confidence=Confidence.HIGH))
        return

    if key in NAME_KEYS:
        # A search query is a weaker signal than an explicit identifier: users
        # type prose into `query`. Only structured-looking values are kept, and
        # only at MEDIUM, so a search phrase cannot trigger a deny on its own.
        for token in re.split(r"[\s,;]+", value):
            token = token.strip("\"'`()")
            if "." in token and is_plausible_asset_name(token):
                refs.append(make_ref(token, extractor=EXTRACTOR, confidence=Confidence.MEDIUM))
        return

    # Any other field may still embed a URN.
    if "urn:li:" in value:
        refs.extend(extract_urns(value, extractor=EXTRACTOR))


def extract_mcp(tool_name: str, tool_input: dict[str, Any]) -> McpExtraction:
    """Extract asset references and intent from a DataHub MCP tool call."""
    tool = datahub_tool_name(tool_name)
    if tool is None:
        return McpExtraction(is_datahub=False)

    refs: list[AssetRef] = []
    _walk(tool_input, None, refs)

    intents: set[Intent] = set()
    if tool in MUTATION_TOOLS:
        intents.add(Intent.MUTATE)
    elif tool in READ_TOOLS:
        intents.add(Intent.SEARCH if "search" in tool else Intent.READ)
    else:
        # An unrecognized tool is not assumed harmless. READ keeps it visible to
        # the engine without inventing a write intent that is not evidenced.
        intents.add(Intent.READ)

    # `search` returns candidates rather than naming one asset, so a query that
    # mentions no identifier yields no reference — and the engine's safe default
    # takes over rather than a rule firing on a phrase.
    refs = [ref for ref in refs if ref.kind is not AssetKind.UNKNOWN]

    return McpExtraction(refs=dedupe(refs), intents=intents, tool=tool, is_datahub=True)
