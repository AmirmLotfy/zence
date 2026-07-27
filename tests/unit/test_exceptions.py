"""Exceptions — the ZR-012 and ZR-013 semantics.

Those two identifiers are reserved for engine behaviour rather than rule
entries, because the behaviour lives in `engine.py` and putting a rule in YAML
that does not control it would be misleading. They are pinned here instead:

* **ZR-012** an active, unexpired exception downgrades a matched ASK to ALLOW
* **ZR-013** an expired exception has no effect, and the underlying rule applies

The hard constraint, tested twice, is that an exception can never waive a DENY.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import (
    BLUEPEAK_DOMAIN,
    FIXED_NOW,
    bluepeak_pii_evidence,
    dataset_urn,
    make_action,
    make_evidence,
    make_policy,
    make_workspace,
)
from zence_core.policy import PolicyError, evaluate
from zence_core.schemas import DecisionSource, Evidence, Intent, Verdict

SHARED_DIM = "bluepeak.shared_dim_date"
SHARED_DIM_URN = dataset_urn(SHARED_DIM, "PROD")


def exception_entry(
    *,
    rule_id: str = "ZR-002",
    urn: str | None = SHARED_DIM_URN,
    domain: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    scope: dict[str, str] = {}
    if urn is not None:
        scope["urn"] = urn
    if domain is not None:
        scope["domain"] = domain

    return {
        "rule_id": rule_id,
        "scope": scope,
        "expires_at": (expires_at or (FIXED_NOW + timedelta(days=7))).isoformat(),
        "approver": "amir@zence.site",
        "reason": "Shared date dimension, carries no client data.",
    }


def shared_dim_evidence() -> Evidence:
    """An out-of-domain but genuinely harmless asset — the case exceptions exist for."""
    return make_evidence(
        name=SHARED_DIM,
        domain=BLUEPEAK_DOMAIN,
        domain_name="BluePeak Health",
        environment="PROD",
        tags=set(),
    )


# --- ZR-012: an active exception softens an ASK ------------------------------


def test_active_exception_downgrades_ask_to_allow() -> None:
    policy = make_policy(exceptions=[exception_entry()])
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.verdict is Verdict.ALLOW
    assert decision.source is DecisionSource.EXCEPTION
    assert decision.exception_applied == "ZR-002"
    assert decision.rule_id == "ZR-002"


def test_exception_is_recorded_not_hidden() -> None:
    """A waived ASK must still name the rule it waived, for the audit trail."""
    policy = make_policy(exceptions=[exception_entry()])
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.exception_applied is not None
    assert decision.rule_title == "Cross-client read"


def test_domain_scoped_exception_covers_every_asset_in_that_domain() -> None:
    policy = make_policy(exceptions=[exception_entry(urn=None, domain=BLUEPEAK_DOMAIN)])
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.verdict is Verdict.ALLOW


def test_exception_does_not_leak_to_a_different_asset() -> None:
    policy = make_policy(exceptions=[exception_entry(urn=dataset_urn("something.else"))])
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.verdict is Verdict.ASK
    assert decision.exception_applied is None


# --- ZR-013: an expired exception does nothing -------------------------------


def test_expired_exception_has_no_effect() -> None:
    policy = make_policy(exceptions=[exception_entry(expires_at=FIXED_NOW - timedelta(seconds=1))])
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.verdict is Verdict.ASK
    assert decision.exception_applied is None


def test_expiry_boundary_is_exclusive() -> None:
    """An exception expiring exactly now is expired, not still valid."""
    policy = make_policy(exceptions=[exception_entry(expires_at=FIXED_NOW)])
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.verdict is Verdict.ASK


def test_expiry_is_compared_across_timezones_correctly() -> None:
    """Stored in +04:00, evaluated in UTC — still one moment in time."""
    tehran = datetime(2026, 8, 1, 15, 0, 0, tzinfo=UTC).astimezone()
    policy = make_policy(exceptions=[exception_entry(expires_at=tehran)])

    before = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=datetime(2026, 8, 1, 14, 59, tzinfo=UTC),
    )
    after = evaluate(
        make_action(intents={Intent.READ}),
        [shared_dim_evidence()],
        make_workspace(),
        policy,
        now=datetime(2026, 8, 1, 15, 1, tzinfo=UTC),
    )

    assert before.verdict is Verdict.ALLOW
    assert after.verdict is Verdict.ASK


def test_naive_expiry_is_rejected() -> None:
    """A timestamp without an offset is ambiguous, and ambiguity here is a security bug."""
    with pytest.raises(PolicyError):
        make_policy(
            exceptions=[
                {
                    "rule_id": "ZR-002",
                    "scope": {"urn": SHARED_DIM_URN},
                    "expires_at": "2026-08-11T00:00:00",  # no timezone
                    "approver": "amir@zence.site",
                    "reason": "no offset",
                }
            ]
        )


# --- The hard constraint -----------------------------------------------------


def test_exception_cannot_target_a_deny_rule() -> None:
    """Rejected at load time, so the mistake surfaces in `zence policy validate`."""
    with pytest.raises(PolicyError, match="Exceptions may only downgrade ASK"):
        make_policy(exceptions=[exception_entry(rule_id="ZR-001")])


def test_no_exception_can_unlock_cross_client_pii() -> None:
    """The end-to-end version of the same guarantee."""
    policy = make_policy(
        exceptions=[exception_entry(rule_id="ZR-002", domain=BLUEPEAK_DOMAIN, urn=None)]
    )
    decision = evaluate(
        make_action(intents={Intent.READ}),
        [bluepeak_pii_evidence()],
        make_workspace(),
        policy,
        now=FIXED_NOW,
    )

    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-001"
    assert decision.exception_applied is None


def test_exception_referencing_an_unknown_rule_is_rejected() -> None:
    with pytest.raises(PolicyError, match="unknown rule"):
        make_policy(exceptions=[exception_entry(rule_id="ZR-999")])


def test_exception_scope_requires_exactly_one_selector() -> None:
    with pytest.raises(PolicyError):
        make_policy(exceptions=[exception_entry(urn=SHARED_DIM_URN, domain=BLUEPEAK_DOMAIN)])

    with pytest.raises(PolicyError):
        make_policy(exceptions=[exception_entry(urn=None, domain=None)])
