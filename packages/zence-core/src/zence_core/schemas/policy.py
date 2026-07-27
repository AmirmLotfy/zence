"""The policy file format.

Policy is data, not code. A rule is a set of field/predicate pairs that are
ANDed together — there is no expression language, no `eval`, and no way for a
policy file to execute anything. A rule that needs OR is written as two rules,
which also makes the audit trail say which branch fired.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from zence_core.schemas.enums import Confidence, Mode, Risk, Verdict

Operator = Literal[
    "equals",
    "not_equals",
    "in",
    "not_in",
    "intersects",
    "not_intersects",
    "matches",
    "gte",
    "lte",
    "exists",
]

OPERATORS: frozenset[str] = frozenset(
    (
        "equals",
        "not_equals",
        "in",
        "not_in",
        "intersects",
        "not_intersects",
        "matches",
        "gte",
        "lte",
        "exists",
    )
)

#: Regex predicates are compiled at load time and bounded in length. Python's `re`
#: has no evaluation timeout, so the defence is: reject long patterns, bound the
#: subject string, and rely on the hook's own timeout plus the fail-safe matrix as
#: the backstop. See docs/THREAT_MODEL.md.
MAX_PATTERN_CHARS = 200
MAX_SUBJECT_CHARS = 4_096

RULE_ID_PATTERN = re.compile(r"^[A-Z]{2,6}-\d{3}$")


class Predicate(BaseModel):
    """One operator applied to one field.

    Written in YAML as a single-key mapping::

        asset.tags: {intersects: "$sensitive_tags"}

    A `$name` value dereferences a list declared at the top of the policy, so a
    workspace maintains one list of sensitive tags rather than repeating it in
    every rule.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    operator: Operator
    value: Any = None

    @model_validator(mode="before")
    @classmethod
    def _from_single_key_mapping(cls, data: Any) -> Any:
        """Accept `{"intersects": [...]}` as well as the explicit long form."""
        if not isinstance(data, dict):
            return data
        if "operator" in data:
            return data

        keys = list(data.keys())
        if len(keys) != 1:
            raise ValueError(
                f"a predicate must be a single-key mapping, got keys {sorted(keys)}. "
                "Two conditions on one field need two entries or two rules."
            )
        operator = keys[0]
        if operator not in OPERATORS:
            raise ValueError(
                f"unknown operator {operator!r}. Supported: {', '.join(sorted(OPERATORS))}"
            )
        return {"operator": operator, "value": data[operator]}

    @model_validator(mode="after")
    def _check_value_shape(self) -> Self:
        if self.operator == "exists" and not isinstance(self.value, bool):
            raise ValueError("`exists` takes a boolean")
        if self.operator == "matches":
            if not isinstance(self.value, str):
                raise ValueError("`matches` takes a string pattern")
            if len(self.value) > MAX_PATTERN_CHARS:
                raise ValueError(
                    f"regex pattern exceeds {MAX_PATTERN_CHARS} characters; "
                    "long patterns are rejected to bound backtracking"
                )
            try:
                re.compile(self.value)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}") from exc
        elif self.operator in {"in", "not_in", "intersects", "not_intersects"}:
            if not isinstance(self.value, str | list):
                raise ValueError(f"`{self.operator}` takes a list or a $reference to one")
        return self

    @property
    def reference_name(self) -> str | None:
        """The `$name` this predicate defers to, if any."""
        if isinstance(self.value, str) and self.value.startswith("$"):
            return self.value[1:]
        return None


class Rule(BaseModel):
    """A single policy rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    decision: Verdict
    risk: Risk = Risk.MEDIUM

    when: dict[str, Predicate] = Field(default_factory=dict)
    """Field path to predicate. All entries must hold for the rule to fire."""

    explanation: str
    """Shown to the user and to Claude. May reference `{placeholders}` filled
    from the evidence at render time."""

    remediation: str | None = None
    required_approver: str | None = None

    min_confidence: Confidence = Confidence.LOW
    """Reject matches from extractors less certain than this. Guards against
    approval fatigue caused by a noisy shell-command heuristic."""

    enabled: bool = True

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not RULE_ID_PATTERN.match(value):
            raise ValueError(
                f"rule id {value!r} must look like 'ZR-001' — two to six capitals, "
                "a hyphen, three digits"
            )
        return value

    @model_validator(mode="after")
    def _require_conditions(self) -> Self:
        if not self.when:
            raise ValueError(
                f"rule {self.id} has no conditions; a rule that matches everything "
                "is a mode setting, not a rule"
            )
        return self

    @property
    def references_asset_fields(self) -> bool:
        return any(path.startswith("asset.") for path in self.when)


class ExceptionScope(BaseModel):
    """What an exception applies to. Exactly one selector must be set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    urn: str | None = None
    domain: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        selectors = [self.urn, self.domain]
        if sum(selector is not None for selector in selectors) != 1:
            raise ValueError("scope must set exactly one of: urn, domain")
        return self


class PolicyException(BaseModel):
    """A time-boxed downgrade of one ASK rule for one asset or domain.

    Exceptions can only soften an ASK into an ALLOW. They can never unlock a
    DENY — a cross-client PII read does not become acceptable because someone
    signed off on it in a YAML file. That constraint is enforced in
    :meth:`Policy._validate_exceptions`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    scope: ExceptionScope
    expires_at: AwareDatetime
    """Timezone-aware and mandatory. An exception without an expiry is a policy
    change wearing a disguise."""

    approver: str
    reason: str

    def is_active(self, now: datetime | None = None) -> bool:
        moment = now if now is not None else datetime.now(UTC)
        return moment < self.expires_at

    def covers(self, urn: str | None, domain_urn: str | None) -> bool:
        if self.scope.urn is not None:
            return urn is not None and urn == self.scope.urn
        return domain_urn is not None and domain_urn == self.scope.domain


class Policy(BaseModel):
    """A complete, validated policy document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    workspace_id: str

    mode: Mode = Mode.ENFORCE

    active_client: str
    active_domain: str | None = None

    extends_builtin: bool = True
    """Inherit Zence's shipped rule set. A workspace rule sharing an id replaces
    the built-in one, so a single rule can be retuned without forking all of them."""

    allowed_domains: list[str] = Field(default_factory=list)
    allowed_environments: list[str] = Field(default_factory=list)
    sensitive_tags: list[str] = Field(default_factory=list)
    protected_terms: list[str] = Field(default_factory=list)
    critical_downstream: list[str] = Field(default_factory=list)

    rules: list[Rule] = Field(default_factory=list)
    exceptions: list[PolicyException] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> Self:
        self._validate_unique_rule_ids()
        self._validate_references()
        self._validate_exceptions()
        return self

    def _validate_unique_rule_ids(self) -> None:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id {rule.id}")
            seen.add(rule.id)

    def _validate_references(self) -> None:
        """Every `$name` must resolve to a declared list.

        Caught at load time rather than at decision time: a typo that silently
        evaluated to an empty list would turn a deny rule into a no-op.
        """
        available = {
            "allowed_domains",
            "allowed_environments",
            "sensitive_tags",
            "protected_terms",
            "critical_downstream",
        }
        for rule in self.rules:
            for path, predicate in rule.when.items():
                name = predicate.reference_name
                if name is not None and name not in available:
                    raise ValueError(
                        f"rule {rule.id} field {path!r} references ${name}, which is not "
                        f"declared. Available: {', '.join(sorted(available))}"
                    )

    def _validate_exceptions(self) -> None:
        by_id = {rule.id: rule for rule in self.rules}
        for exception in self.exceptions:
            rule = by_id.get(exception.rule_id)
            if rule is None:
                raise ValueError(f"exception references unknown rule {exception.rule_id}")
            if rule.decision is not Verdict.ASK:
                raise ValueError(
                    f"exception targets {rule.id}, which is a {rule.decision.value} rule. "
                    "Exceptions may only downgrade ASK to ALLOW — a DENY cannot be "
                    "waived in a policy file."
                )

    def list_for(self, name: str) -> list[str]:
        """Resolve a `$name` reference to its declared list."""
        value = getattr(self, name, None)
        if not isinstance(value, list):
            raise KeyError(f"unknown policy list ${name}")
        return value

    def active_exceptions(self, now: datetime | None = None) -> list[PolicyException]:
        return [exception for exception in self.exceptions if exception.is_active(now)]
