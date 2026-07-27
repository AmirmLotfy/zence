"""JSON Schema generation for policy files.

Emitted so editors can autocomplete and validate `.zence/policy.yaml`, and so CI
can check every shipped policy without importing the engine.

The generated schema is deliberately augmented with the field-path allowlist:
Pydantic knows `when` is a mapping of strings to predicates, but only
`policy.fields` knows which strings are real. Folding that in means an editor
flags `asset.doamin_urn` as you type it rather than at load time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zence_core.policy.fields import FIELDS
from zence_core.schemas import Policy

SCHEMA_ID = "https://zence.site/schema/policy-v1.json"


def policy_json_schema() -> dict[str, Any]:
    """The JSON Schema for a `.zence/policy.yaml` document."""
    schema = Policy.model_json_schema(mode="validation")

    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = SCHEMA_ID
    schema["title"] = "Zence policy"
    schema["description"] = (
        "A Zence workspace policy. Conditions are ANDed; there is no expression "
        "language. See https://github.com/AmirmLotfy/zence/blob/main/docs/POLICY_ENGINE.md"
    )

    _constrain_rule_field_paths(schema)
    return schema


def _constrain_rule_field_paths(schema: dict[str, Any]) -> None:
    """Restrict `Rule.when` keys to the allowlisted field paths."""
    rule = schema.get("$defs", {}).get("Rule")
    if not isinstance(rule, dict):
        return

    when = rule.get("properties", {}).get("when")
    if not isinstance(when, dict):
        return

    when["propertyNames"] = {
        "enum": sorted(FIELDS),
        "description": "An allowlisted policy field path.",
    }


def write_schema(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(policy_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination
