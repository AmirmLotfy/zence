"""Policy loading, validation, and schema generation.

Most of these assert that a *broken* policy fails loudly. That is the point: a
policy which loads but does not mean what its author intended is worse than one
that refuses to load, because the workspace still looks protected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import BASE_POLICY, NORTHSTAR_DOMAIN, make_policy
from zence_core.policy import (
    PolicyError,
    builtin_rules,
    load_policy_file,
    load_policy_text,
    policy_json_schema,
    policy_sha256,
    workspace_from_policy,
)
from zence_core.schemas import Verdict

MINIMAL = """
policy_version: "1.0.0"
workspace_id: acme
active_client: Acme
extends_builtin: false
rules: []
"""


def rule_with(when: str, *, rule_id: str = "ZR-100") -> dict[str, object]:
    import yaml

    return {
        "id": rule_id,
        "title": "Test rule",
        "decision": "ask",
        "explanation": "test",
        "remediation": "test",
        "when": yaml.safe_load(when),
    }


# --- Happy path --------------------------------------------------------------


def test_minimal_policy_loads() -> None:
    policy = load_policy_text(MINIMAL)
    assert policy.workspace_id == "acme"
    assert policy.rules == []


def test_policy_inherits_builtin_rules_by_default() -> None:
    policy = make_policy()
    assert {rule.id for rule in policy.rules} == {rule.id for rule in builtin_rules()}


def test_workspace_rule_overrides_the_builtin_of_the_same_id() -> None:
    policy = make_policy(
        rules=[
            {
                "id": "ZR-006",
                "title": "Deprecated assets are fine here",
                "decision": "allow",
                "explanation": "This workspace tolerates deprecated assets.",
                "when": {"asset.lifecycle": {"equals": "deprecated"}},
            }
        ]
    )
    overridden = next(rule for rule in policy.rules if rule.id == "ZR-006")

    assert overridden.decision is Verdict.ALLOW
    assert sum(rule.id == "ZR-006" for rule in policy.rules) == 1


def test_rules_are_ordered_deny_then_ask_then_allow() -> None:
    order = [rule.decision.value for rule in make_policy().rules]
    rank = {"deny": 0, "ask": 1, "allow": 2}
    assert order == sorted(order, key=lambda decision: rank[decision])


def test_workspace_context_is_derived_from_the_policy() -> None:
    policy = make_policy()
    workspace = workspace_from_policy(policy, Path("/tmp/northstar"))

    assert workspace.active_client == "Northstar Commerce"
    assert workspace.allowed_domains == frozenset({NORTHSTAR_DOMAIN})
    assert workspace.is_in_domain(NORTHSTAR_DOMAIN)
    assert not workspace.is_in_domain("urn:li:domain:other")


# --- Field-path validation ---------------------------------------------------


def test_unknown_field_path_is_rejected_with_a_suggestion() -> None:
    with pytest.raises(PolicyError) as excinfo:
        make_policy(rules=[rule_with('{"asset.doamin_urn": {"equals": "x"}}')])

    message = str(excinfo.value)
    assert "unknown policy field" in message
    assert "asset.domain_urn" in message


def test_attribute_traversal_is_not_a_field_path() -> None:
    with pytest.raises(PolicyError, match="unknown policy field"):
        make_policy(rules=[rule_with('{"asset.__class__": {"equals": "x"}}')])


def test_set_operator_on_a_scalar_field_is_rejected() -> None:
    with pytest.raises(PolicyError, match="needs a set-valued field"):
        make_policy(rules=[rule_with('{"asset.environment": {"intersects": ["PROD"]}}')])


def test_scalar_operator_on_a_set_field_is_rejected() -> None:
    with pytest.raises(PolicyError, match="needs a single value"):
        make_policy(rules=[rule_with('{"asset.tags": {"matches": "PII"}}')])


def test_reference_to_an_undeclared_list_is_rejected() -> None:
    with pytest.raises(PolicyError, match=r"\$nonexistent"):
        make_policy(rules=[rule_with('{"asset.tags": {"intersects": "$nonexistent"}}')])


# --- Structural validation ---------------------------------------------------


def test_duplicate_rule_ids_are_rejected() -> None:
    with pytest.raises(PolicyError, match="duplicate rule id"):
        make_policy(
            extends_builtin=False,
            rules=[
                rule_with('{"asset.environment": {"equals": "PROD"}}', rule_id="ZR-100"),
                rule_with('{"asset.environment": {"equals": "DEV"}}', rule_id="ZR-100"),
            ],
        )


def test_rule_without_conditions_is_rejected() -> None:
    with pytest.raises(PolicyError, match="no conditions"):
        make_policy(rules=[rule_with("{}")])


def test_malformed_rule_id_is_rejected() -> None:
    with pytest.raises(PolicyError, match="must look like"):
        make_policy(rules=[rule_with('{"asset.environment": {"equals": "DEV"}}', rule_id="rule-1")])


def test_unknown_top_level_key_is_rejected() -> None:
    """`extra="forbid"` turns a typo into an error instead of a silent no-op."""
    with pytest.raises(PolicyError):
        make_policy(sensitive_tag=["urn:li:tag:PII"])  # singular typo


def test_invalid_yaml_is_reported_with_the_origin() -> None:
    with pytest.raises(PolicyError, match="invalid YAML"):
        load_policy_text("policy_version: [unclosed", origin="policy.yaml")


def test_non_mapping_document_is_rejected() -> None:
    with pytest.raises(PolicyError, match="expected a mapping"):
        load_policy_text("- just\n- a list\n")


def test_missing_file_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="cannot read policy"):
        load_policy_file(tmp_path / "does-not-exist.yaml")


# --- Round trip --------------------------------------------------------------


def test_policy_loads_from_disk_and_hashes_stably(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(BASE_POLICY), encoding="utf-8")

    policy = load_policy_file(path)
    assert policy.active_client == "Northstar Commerce"

    first = policy_sha256(path)
    assert first == policy_sha256(path)

    path.write_text(yaml.safe_dump({**BASE_POLICY, "policy_version": "1.0.1"}))
    assert policy_sha256(path) != first


# --- JSON Schema -------------------------------------------------------------


def test_json_schema_is_generated_with_an_id() -> None:
    schema = policy_json_schema()
    assert schema["$id"].endswith("policy-v1.json")
    assert schema["$schema"].startswith("https://json-schema.org/")


def test_json_schema_constrains_rule_field_paths() -> None:
    """Editors should flag a bad field path while typing, not at load time."""
    schema = policy_json_schema()
    names = schema["$defs"]["Rule"]["properties"]["when"]["propertyNames"]

    assert "asset.domain_urn" in names["enum"]
    assert "asset.__class__" not in names["enum"]


def test_json_schema_is_serializable() -> None:
    import json

    assert json.loads(json.dumps(policy_json_schema()))
