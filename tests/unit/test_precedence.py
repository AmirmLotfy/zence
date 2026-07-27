"""Decision precedence.

Order is: tamper, then deny, then ask (exceptions may soften it), then allow,
then the fail-safe default. These tests pin that order by constructing inputs
that satisfy two rules at once and asserting which one wins.
"""

from __future__ import annotations

from tests.conftest import (
    BLUEPEAK_DOMAIN,
    PII_TAG,
    REVENUE_DASHBOARD,
    bluepeak_pii_evidence,
    make_action,
    make_evidence,
    make_policy,
    make_workspace,
)
from zence_core.policy import evaluate
from zence_core.schemas import DecisionSource, Intent, Mode, Verdict


def test_tamper_beats_every_other_rule() -> None:
    """Editing `.zence/**` is denied even when the action would otherwise be allowed."""
    action = make_action(
        tool_name="Edit",
        intents={Intent.WRITE},
        targets_zence_config=True,
        target_paths=(".zence/policy.yaml",),
    )
    decision = evaluate(action, [], make_workspace(), make_policy())

    assert decision.verdict is Verdict.DENY
    assert decision.source is DecisionSource.TAMPER
    assert decision.rule_id == "ZR-014"


def test_tamper_survives_audit_mode() -> None:
    """Audit mode downgrades blocks — but not this one.

    If audit mode could soften tamper protection, enabling audit mode would be a
    one-line way to disable Zence from inside a session it governs.
    """
    action = make_action(targets_zence_config=True, target_paths=(".zence/policy.yaml",))
    decision = evaluate(action, [], make_workspace(mode=Mode.AUDIT), make_policy(mode="audit"))

    assert decision.verdict is Verdict.DENY
    assert decision.source is DecisionSource.TAMPER


def test_deny_beats_ask_on_the_same_asset() -> None:
    """A cross-client PII read satisfies both ZR-001 (deny) and ZR-002 (ask)."""
    evidence = bluepeak_pii_evidence()
    decision = evaluate(
        make_action(intents={Intent.READ}), [evidence], make_workspace(), make_policy()
    )

    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-001"


def test_deny_beats_ask_across_different_assets() -> None:
    """One in-bounds asset does not dilute a violation on another in the same call."""
    safe = make_evidence(name="northstar.dim_customer", environment="DEV")
    unsafe = bluepeak_pii_evidence()

    decision = evaluate(
        make_action(intents={Intent.READ}),
        [safe, unsafe],
        make_workspace(),
        make_policy(),
    )
    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-001"


def test_ask_beats_allow() -> None:
    """A deprecated in-domain asset satisfies ZR-006 (ask) and ZR-009 (allow)."""
    from zence_core.schemas import Lifecycle

    evidence = make_evidence(environment="DEV", lifecycle=Lifecycle.DEPRECATED)
    decision = evaluate(
        make_action(intents={Intent.READ}), [evidence], make_workspace(), make_policy()
    )

    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-006"


def test_allow_beats_the_safe_default() -> None:
    """An explicit allow names a rule; the default would only say 'nothing objected'."""
    evidence = make_evidence(environment="DEV")
    decision = evaluate(
        make_action(intents={Intent.READ}), [evidence], make_workspace(), make_policy()
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.rule_id == "ZR-009"
    assert decision.source is DecisionSource.RULE


def test_safe_default_applies_when_no_rule_matches() -> None:
    policy = make_policy(extends_builtin=False, rules=[])
    decision = evaluate(make_action(intents={Intent.READ}), [], make_workspace(), policy)

    assert decision.source is DecisionSource.SAFE_DEFAULT
    assert decision.rule_id == "ZR-000"


def test_audit_mode_downgrades_a_deny_but_records_it() -> None:
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [bluepeak_pii_evidence()],
        make_workspace(mode=Mode.AUDIT),
        make_policy(mode="audit"),
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.would_have_been is Verdict.DENY
    assert decision.source is DecisionSource.MODE_DOWNGRADE
    assert decision.rule_id == "ZR-001"
    assert any("audit mode" in note for note in decision.notes)


def test_audit_mode_leaves_a_genuine_allow_alone() -> None:
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [make_evidence(environment="DEV")],
        make_workspace(mode=Mode.AUDIT),
        make_policy(mode="audit"),
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.would_have_been is None
    assert decision.source is DecisionSource.RULE


def test_decision_carries_the_evidence_that_justified_it() -> None:
    evidence = bluepeak_pii_evidence()
    decision = evaluate(
        make_action(intents={Intent.READ}), [evidence], make_workspace(), make_policy()
    )

    assert decision.evidence_urns == (evidence.urn,)
    assert PII_TAG in decision.matched_tags
    assert set(decision.matched_columns) == {"email", "phone"}
    assert BLUEPEAK_DOMAIN in decision.reason or "BluePeak" in decision.reason


def test_lineage_evidence_reaches_the_decision() -> None:
    evidence = make_evidence(
        name="northstar.fct_revenue_daily",
        environment="DEV",
        downstream_critical=(REVENUE_DASHBOARD,),
    )
    decision = evaluate(
        make_action(tool_name="Edit", intents={Intent.WRITE}),
        [evidence],
        make_workspace(),
        make_policy(),
    )

    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-008"
    assert decision.downstream_critical == (REVENUE_DASHBOARD,)
    assert REVENUE_DASHBOARD in decision.reason


def test_min_confidence_suppresses_a_low_confidence_match() -> None:
    """ZR-001 demands HIGH confidence; a MEDIUM guess must not trigger a denial."""
    from tests.conftest import make_ref
    from zence_core.schemas import Confidence

    evidence = bluepeak_pii_evidence(
        ref=make_ref("patient_contacts", confidence=Confidence.MEDIUM, extractor="shell")
    )
    decision = evaluate(
        make_action(intents={Intent.READ}), [evidence], make_workspace(), make_policy()
    )

    assert decision.verdict is not Verdict.DENY
    assert decision.rule_id != "ZR-001"
