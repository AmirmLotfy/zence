"""The fail-safe matrix.

Every test here answers one question: when Zence cannot see clearly, does it
still refuse to say yes? A regression in this file is the difference between a
guardrail and a decoration, so the assertions are deliberately blunt.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    BLUEPEAK_DOMAIN,
    make_action,
    make_evidence,
    make_policy,
    make_workspace,
)
from zence_core.policy import evaluate
from zence_core.schemas import (
    DecisionSource,
    EvidenceStatus,
    Intent,
    ProviderKind,
    Verdict,
)

#: No rules at all, so every case falls through to the fail-safe matrix.
EMPTY_POLICY = dict(extends_builtin=False, rules=[])


def test_lookup_failure_on_a_data_operation_asks() -> None:
    evidence = make_evidence(
        status=EvidenceStatus.LOOKUP_FAILED,
        failure_reason="connection refused",
    )
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ASK
    assert decision.degraded is True
    assert decision.degraded_reason == "connection refused"
    assert "could not reach DataHub" in decision.reason


def test_lookup_failure_never_allows_a_write() -> None:
    evidence = make_evidence(status=EvidenceStatus.LOOKUP_FAILED, failure_reason="502 from gateway")
    decision = evaluate(
        make_action(tool_name="Write", intents={Intent.WRITE}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is not Verdict.ALLOW


def test_cross_client_reference_with_a_failed_lookup_still_asks() -> None:
    """The case the README promises: an outage must not read as a clean catalog."""
    evidence = make_evidence(
        name="bluepeak.patient_contacts",
        domain=BLUEPEAK_DOMAIN,
        status=EvidenceStatus.LOOKUP_FAILED,
        failure_reason="timeout",
    )
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ASK
    assert decision.degraded is True


def test_harmless_local_action_is_allowed_but_flagged_when_datahub_is_down() -> None:
    """No asset references and no write intent: allowed, and told it was blind."""
    decision = evaluate(
        make_action(tool_name="Read", intents={Intent.READ}),
        [],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.degraded is False  # nothing was looked up, so nothing failed


def test_unknown_asset_in_a_write_asks() -> None:
    evidence = make_evidence(status=EvidenceStatus.NOT_FOUND)
    decision = evaluate(
        make_action(tool_name="Write", intents={Intent.WRITE}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ASK
    assert "could not be found" in decision.reason


def test_unknown_asset_in_a_plain_read_does_not_ask() -> None:
    """Not every unresolved name is a risk; over-asking causes approval fatigue."""
    evidence = make_evidence(status=EvidenceStatus.NOT_FOUND)
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ALLOW


def test_resolved_out_of_domain_asset_asks_even_with_no_rules() -> None:
    """Belt and braces: the default catches cross-client access on its own."""
    evidence = make_evidence(
        name="bluepeak.member_export",
        domain=BLUEPEAK_DOMAIN,
        domain_name="BluePeak Health",
    )
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ASK
    assert "BluePeak Health" in decision.reason
    assert "Northstar Commerce" in decision.reason


def test_asset_with_no_domain_is_not_treated_as_in_domain() -> None:
    """Unclassified data in a multi-client catalog is exactly what to ask about."""
    evidence = make_evidence(domain=None, domain_name=None)
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ASK


def test_clean_in_domain_action_is_allowed() -> None:
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [make_evidence(environment="DEV")],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.degraded is False


def test_no_references_and_no_sensitivity_is_allowed() -> None:
    decision = evaluate(
        make_action(tool_name="Read", intents={Intent.READ}),
        [],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.risk.value == "none"


def test_provider_is_recorded_and_never_guessed() -> None:
    """A decision must say where its evidence came from — fixture or live."""
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [make_evidence(environment="DEV", provider=ProviderKind.FIXTURE)],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.provider is ProviderKind.FIXTURE


def test_mixed_providers_report_nothing_rather_than_a_comforting_default() -> None:
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [
            make_evidence(name="a", environment="DEV", provider=ProviderKind.LIVE),
            make_evidence(name="b", environment="DEV", provider=ProviderKind.FIXTURE),
        ],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.provider is None


@pytest.mark.parametrize(
    "intent",
    [Intent.WRITE, Intent.MUTATE, Intent.DESTRUCTIVE],
)
def test_every_sensitive_intent_blocks_a_degraded_allow(intent: Intent) -> None:
    evidence = make_evidence(status=EvidenceStatus.LOOKUP_FAILED, failure_reason="down")
    decision = evaluate(
        make_action(intents={intent}),
        [evidence],
        make_workspace(),
        make_policy(**EMPTY_POLICY),
    )

    assert decision.verdict is Verdict.ASK
    assert decision.source is DecisionSource.SAFE_DEFAULT
