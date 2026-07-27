"""Loading and validating policy documents.

Field-path validation lives here rather than on the `Policy` model to keep the
schema layer free of any dependency on the evaluator. The practical effect is
the same: a policy with a misspelled field path fails to load, loudly, instead of
silently evaluating to `None` and inverting a rule.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from zence_core.policy.fields import FIELDS, SET_VALUED_FIELDS, UnknownFieldError
from zence_core.schemas import Policy, Rule, WorkspaceContext

BUILTIN_RULES_RESOURCE = "builtin_rules.yaml"

#: Operators that only make sense against a set-valued field, and vice versa.
_SET_ONLY_OPERATORS = frozenset({"intersects", "not_intersects"})
_SCALAR_ONLY_OPERATORS = frozenset({"matches", "gte", "lte"})


class PolicyError(ValueError):
    """A policy file could not be loaded or is not internally consistent."""


def _read_yaml(text: str, origin: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PolicyError(f"{origin}: invalid YAML — {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PolicyError(
            f"{origin}: expected a mapping at the top level, got {type(data).__name__}"
        )
    return data


def builtin_rules() -> list[Rule]:
    """Zence's shipped rule set."""
    package = resources.files("zence_core.policy")
    text = (package / BUILTIN_RULES_RESOURCE).read_text(encoding="utf-8")
    data = _read_yaml(text, BUILTIN_RULES_RESOURCE)

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise PolicyError(f"{BUILTIN_RULES_RESOURCE}: `rules` must be a list")

    try:
        return [Rule.model_validate(entry) for entry in raw_rules]
    except ValidationError as exc:
        raise PolicyError(f"{BUILTIN_RULES_RESOURCE}: {exc}") from exc


def _merge_rules(workspace_rules: list[Rule], inherited: list[Rule]) -> list[Rule]:
    """Workspace rules win on id collision; inherited rules keep their order."""
    overridden = {rule.id for rule in workspace_rules}
    merged = [rule for rule in inherited if rule.id not in overridden]
    merged.extend(workspace_rules)

    # Keep deny before ask before allow so the engine's partitioning is stable
    # regardless of the order a workspace happened to write its overrides in.
    order = {"deny": 0, "ask": 1, "allow": 2}
    return sorted(merged, key=lambda rule: order[rule.decision.value])


def validate_field_paths(policy: Policy) -> None:
    """Every path a rule reads must exist, and its operator must suit the type."""
    for rule in policy.rules:
        for path, predicate in rule.when.items():
            if path not in FIELDS:
                raise PolicyError(str(UnknownFieldError(path)))

            is_set_field = path in SET_VALUED_FIELDS
            operator = predicate.operator

            if operator in _SET_ONLY_OPERATORS and not is_set_field:
                raise PolicyError(
                    f"rule {rule.id}: `{operator}` needs a set-valued field, but "
                    f"{path!r} holds a single value. Use `equals` or `in`."
                )
            if operator in _SCALAR_ONLY_OPERATORS and is_set_field:
                raise PolicyError(
                    f"rule {rule.id}: `{operator}` needs a single value, but "
                    f"{path!r} holds a set. Use `intersects`."
                )


def load_policy_data(data: dict[str, Any], origin: str = "<dict>") -> Policy:
    """Build a validated `Policy` from an already-parsed mapping."""
    payload = dict(data)
    extends = payload.get("extends_builtin", True)

    try:
        workspace_rules = [Rule.model_validate(entry) for entry in payload.pop("rules", []) or []]
    except ValidationError as exc:
        raise PolicyError(f"{origin}: {exc}") from exc

    payload["rules"] = (
        _merge_rules(workspace_rules, builtin_rules()) if extends else workspace_rules
    )

    try:
        policy = Policy.model_validate(payload)
    except ValidationError as exc:
        raise PolicyError(f"{origin}: {exc}") from exc

    validate_field_paths(policy)
    return policy


def load_policy_text(text: str, origin: str = "<string>") -> Policy:
    return load_policy_data(_read_yaml(text, origin), origin)


def load_policy_file(path: Path) -> Policy:
    """Load `.zence/policy.yaml`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PolicyError(f"cannot read policy at {path}: {exc}") from exc
    return load_policy_text(text, origin=str(path))


def policy_sha256(path: Path) -> str:
    """Digest of the policy file as loaded.

    Recorded on every session so a mid-session edit is visible in the audit trail
    even though ZR-014 already refuses to make one from inside the session.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_from_policy(
    policy: Policy,
    root_path: Path,
    policy_path: Path | None = None,
) -> WorkspaceContext:
    """Derive the session boundary from a loaded policy."""
    return WorkspaceContext(
        workspace_id=policy.workspace_id,
        root_path=str(root_path),
        mode=policy.mode,
        active_client=policy.active_client,
        active_domain=policy.active_domain,
        allowed_domains=frozenset(policy.allowed_domains),
        allowed_environments=frozenset(policy.allowed_environments),
        sensitive_tags=frozenset(policy.sensitive_tags),
        protected_terms=frozenset(policy.protected_terms),
        critical_downstream=frozenset(policy.critical_downstream),
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256(policy_path) if policy_path else None,
    )
