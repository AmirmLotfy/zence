"""Decision precedence.

Order, strictly:

1. **Tamper** — the action targets Zence's own configuration. Checked before
   anything else and not waivable by an exception.
2. **Deny rules** — a matching deny ends the evaluation.
3. **Ask rules**, with exceptions able to downgrade a matched ASK to ALLOW.
4. **Allow rules**.
5. **The fail-safe matrix** in `defaults.py`.

Exceptions sit at step 3 on purpose. They can soften an ASK, never a DENY: a
cross-client PII read does not become acceptable because somebody added a YAML
entry. `Policy._validate_exceptions` rejects an exception targeting a deny rule
at load time, so the constraint is enforced twice.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime

from zence_core.policy.defaults import apply_mode, safe_default
from zence_core.policy.fields import EvalContext
from zence_core.policy.predicates import evaluate_predicate
from zence_core.schemas import (
    CONFIDENCE_ORDER,
    Action,
    Decision,
    DecisionSource,
    Evidence,
    Policy,
    Risk,
    Rule,
    Verdict,
    WorkspaceContext,
)

#: The trigger for this rule is a hardcoded flag on the action, not a policy
#: condition, so a workspace cannot disable protection of Zence's own config by
#: editing the rule. The policy entry supplies only the wording.
TAMPER_RULE_ID = "ZR-014"

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_.]*)\}")


def render(template: str, values: Mapping[str, str]) -> str:
    """Substitute `{placeholders}` from an explicit mapping.

    Regex substitution rather than `str.format`, because `format` on
    user-supplied templates exposes attribute traversal (`{0.__class__}`) and
    turns a policy file into a small information-disclosure primitive.
    Unknown placeholders are left visible so the authoring mistake is obvious.
    """

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return _PLACEHOLDER.sub(replace, template)


def _render_values(
    context: EvalContext, workspace: WorkspaceContext, policy: Policy
) -> dict[str, str]:
    values: dict[str, str] = {
        "active_client": workspace.active_client,
        "active_domain": workspace.active_domain or "(none)",
    }
    evidence = context.evidence
    if evidence is None:
        return values

    sensitive = frozenset(policy.sensitive_tags)
    protected = frozenset(policy.protected_terms)

    values.update(
        {
            "asset.name": evidence.name or evidence.ref.raw_text,
            "asset.raw": evidence.ref.raw_text,
            "asset.urn": evidence.urn or "(unresolved)",
            "asset.domain_name": evidence.domain_name or "(no domain)",
            "asset.domain_urn": evidence.domain_urn or "(no domain)",
            "asset.environment": evidence.environment or "(unknown)",
            "asset.lifecycle": evidence.lifecycle.value,
            "asset.owners": ", ".join(sorted(evidence.owners)) or "(unowned)",
            "matched_tags": ", ".join(sorted(evidence.all_tags & sensitive)) or "(none)",
            "matched_terms": ", ".join(sorted(evidence.all_terms & protected)) or "(none)",
            "matched_columns": ", ".join(evidence.columns_tagged(sensitive)) or "(none)",
            "downstream_critical": ", ".join(evidence.downstream_critical) or "(none)",
            "downstream_critical_count": str(len(evidence.downstream_critical)),
        }
    )
    return values


def _confidence_permits(rule: Rule, context: EvalContext) -> bool:
    """Reject matches from extractors less certain than the rule demands."""
    if context.evidence is None:
        return True
    actual = CONFIDENCE_ORDER.index(context.evidence.ref.confidence)
    floor = CONFIDENCE_ORDER.index(rule.min_confidence)
    return actual <= floor


def rule_matches(rule: Rule, context: EvalContext, policy: Policy) -> bool:
    """Whether every condition on `rule` holds for `context`."""
    if not rule.enabled:
        return False
    if rule.references_asset_fields and context.evidence is None:
        return False
    if not _confidence_permits(rule, context):
        return False

    return all(
        evaluate_predicate(path, predicate, context, policy.list_for)
        for path, predicate in rule.when.items()
    )


def _decision_from_rule(
    rule: Rule,
    context: EvalContext,
    workspace: WorkspaceContext,
    policy: Policy,
    source: DecisionSource = DecisionSource.RULE,
    verdict: Verdict | None = None,
    exception_applied: str | None = None,
) -> Decision:
    values = _render_values(context, workspace, policy)
    evidence = context.evidence

    sensitive = frozenset(policy.sensitive_tags)
    protected = frozenset(policy.protected_terms)

    return Decision(
        verdict=verdict if verdict is not None else rule.decision,
        source=source,
        risk=rule.risk,
        rule_id=rule.id,
        rule_title=rule.title,
        policy_version=policy.policy_version,
        mode=workspace.mode,
        reason=render(rule.explanation, values),
        remediation=render(rule.remediation, values) if rule.remediation else None,
        evidence_urns=(evidence.urn,) if evidence and evidence.urn else (),
        matched_tags=(evidence.all_tags & sensitive) if evidence else frozenset(),
        matched_terms=(evidence.all_terms & protected) if evidence else frozenset(),
        matched_columns=evidence.columns_tagged(sensitive) if evidence else (),
        downstream_critical=evidence.downstream_critical if evidence else (),
        provider=evidence.provider if evidence else None,
        degraded=False,
        exception_applied=exception_applied,
    )


def _tamper_decision(action: Action, workspace: WorkspaceContext, policy: Policy) -> Decision:
    configured = next((r for r in policy.rules if r.id == TAMPER_RULE_ID), None)

    title = configured.title if configured else "Attempt to modify Zence configuration"
    explanation = (
        configured.explanation
        if configured
        else (
            "This action modifies Zence's own policy or hook configuration. "
            "Changing the boundary from inside a session it governs is not permitted."
        )
    )
    remediation = (
        configured.remediation
        if configured
        else "Edit `.zence/policy.yaml` outside a governed session, and review the diff."
    )
    values = {
        "active_client": workspace.active_client,
        "paths": ", ".join(action.target_paths) or "(unknown)",
    }

    return Decision(
        verdict=Verdict.DENY,
        source=DecisionSource.TAMPER,
        risk=Risk.CRITICAL,
        rule_id=TAMPER_RULE_ID,
        rule_title=title,
        policy_version=policy.policy_version,
        mode=workspace.mode,
        reason=render(explanation, values),
        remediation=render(remediation, values) if remediation else None,
        notes=("tamper protection is not waivable by exception or audit mode",),
    )


def _contexts(
    action: Action, evidences: Sequence[Evidence], workspace: WorkspaceContext
) -> list[EvalContext]:
    if not evidences:
        return [EvalContext(action=action, workspace=workspace, evidence=None)]
    return [
        EvalContext(action=action, workspace=workspace, evidence=evidence) for evidence in evidences
    ]


def _matching_exception(
    rule: Rule, context: EvalContext, policy: Policy, now: datetime | None
) -> str | None:
    evidence = context.evidence
    urn = evidence.urn if evidence else None
    domain = evidence.domain_urn if evidence else None

    for exception in policy.active_exceptions(now):
        if exception.rule_id == rule.id and exception.covers(urn, domain):
            return exception.rule_id
    return None


def evaluate(
    action: Action,
    evidences: Sequence[Evidence],
    workspace: WorkspaceContext,
    policy: Policy,
    now: datetime | None = None,
) -> Decision:
    """Produce exactly one decision for one intercepted action."""
    # 1. Tamper — before rules, before exceptions, before mode.
    if action.targets_zence_config:
        return _tamper_decision(action, workspace, policy)

    contexts = _contexts(action, evidences, workspace)

    denies = [r for r in policy.rules if r.decision is Verdict.DENY]
    asks = [r for r in policy.rules if r.decision is Verdict.ASK]
    allows = [r for r in policy.rules if r.decision is Verdict.ALLOW]

    # 2. Deny wins outright.
    for rule in denies:
        for context in contexts:
            if rule_matches(rule, context, policy):
                return apply_mode(_decision_from_rule(rule, context, workspace, policy))

    # 3. Ask, unless an active exception covers this exact asset or domain.
    for rule in asks:
        for context in contexts:
            if not rule_matches(rule, context, policy):
                continue
            waived = _matching_exception(rule, context, policy, now)
            if waived is not None:
                return _decision_from_rule(
                    rule,
                    context,
                    workspace,
                    policy,
                    source=DecisionSource.EXCEPTION,
                    verdict=Verdict.ALLOW,
                    exception_applied=waived,
                )
            return apply_mode(_decision_from_rule(rule, context, workspace, policy))

    # 4. An explicit allow.
    for rule in allows:
        for context in contexts:
            if rule_matches(rule, context, policy):
                return _decision_from_rule(rule, context, workspace, policy)

    # 5. Nothing matched.
    return apply_mode(safe_default(action, evidences, workspace, policy.policy_version))
