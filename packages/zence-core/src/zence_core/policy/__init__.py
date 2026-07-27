"""The deterministic policy engine.

`evaluate` is the entry point. Everything it depends on is pure: given the same
action, evidence, workspace, and policy, it returns the same decision.
"""

from zence_core.policy.defaults import DEFAULT_RULE_ID, apply_mode, safe_default
from zence_core.policy.engine import TAMPER_RULE_ID, evaluate, render, rule_matches
from zence_core.policy.fields import FIELDS, EvalContext, UnknownFieldError, resolve
from zence_core.policy.loader import (
    PolicyError,
    builtin_rules,
    load_policy_data,
    load_policy_file,
    load_policy_text,
    policy_sha256,
    validate_field_paths,
    workspace_from_policy,
)
from zence_core.policy.predicates import evaluate_predicate
from zence_core.policy.schema import policy_json_schema, write_schema

__all__ = [
    "DEFAULT_RULE_ID",
    "FIELDS",
    "TAMPER_RULE_ID",
    "EvalContext",
    "PolicyError",
    "UnknownFieldError",
    "apply_mode",
    "builtin_rules",
    "evaluate",
    "evaluate_predicate",
    "load_policy_data",
    "load_policy_file",
    "load_policy_text",
    "policy_json_schema",
    "policy_sha256",
    "render",
    "resolve",
    "rule_matches",
    "safe_default",
    "validate_field_paths",
    "workspace_from_policy",
    "write_schema",
]
