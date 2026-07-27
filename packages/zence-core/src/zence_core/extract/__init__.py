"""Asset-reference extraction.

`normalize` is the entry point used by the hooks: it takes a Claude Code tool
call and returns the Action plus every asset reference found in it.

Supported surfaces are deliberately bounded — SQL, dbt, shell, YAML recipes,
DataHub MCP arguments, and file paths. General source-code analysis is out of
scope and stated as such in the README, because an extractor that claims to
understand arbitrary Python would be guessing, and a guess that reaches the
policy engine is either a false deny or a false allow.
"""

from zence_core.extract.base import (
    STOPWORDS,
    canonical_environment,
    dedupe,
    extract_urns,
    is_plausible_asset_name,
)
from zence_core.extract.dbt import extract_dbt, looks_like_dbt
from zence_core.extract.mcp_args import datahub_tool_name, extract_mcp
from zence_core.extract.paths import (
    escapes_workspace,
    resolve_within,
    targets_zence_config,
    workspace_relative,
)
from zence_core.extract.router import Normalized, normalize, redact
from zence_core.extract.shell import extract_shell
from zence_core.extract.sql import extract_sql
from zence_core.extract.yaml_recipe import extract_yaml

__all__ = [
    "STOPWORDS",
    "Normalized",
    "canonical_environment",
    "datahub_tool_name",
    "dedupe",
    "escapes_workspace",
    "extract_dbt",
    "extract_mcp",
    "extract_shell",
    "extract_sql",
    "extract_urns",
    "extract_yaml",
    "is_plausible_asset_name",
    "looks_like_dbt",
    "normalize",
    "redact",
    "resolve_within",
    "targets_zence_config",
    "workspace_relative",
]
