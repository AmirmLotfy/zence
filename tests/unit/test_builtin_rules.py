"""Each shipped rule, fired and not fired.

Every rule gets a positive case and at least one near-miss. The near-misses
matter more than the hits: a rule that fires on everything is indistinguishable
from a broken one until someone is drowning in approval prompts.
"""

from __future__ import annotations

from collections.abc import Sequence

from tests.conftest import (
    BLUEPEAK_DOMAIN,
    CONFIDENTIAL_TAG,
    PII_TAG,
    REVENUE_DASHBOARD,
    bluepeak_pii_evidence,
    make_action,
    make_evidence,
    make_policy,
    make_ref,
    make_workspace,
)
from zence_core.policy import builtin_rules, evaluate
from zence_core.schemas import (
    Action,
    ColumnTags,
    Confidence,
    Decision,
    Evidence,
    EvidenceStatus,
    Intent,
    Lifecycle,
    Verdict,
)


def decide(action: Action, evidences: Sequence[Evidence]) -> Decision:
    return evaluate(action, evidences, make_workspace(), make_policy())


# --- Coverage ----------------------------------------------------------------


def test_every_builtin_rule_has_a_unique_id_and_an_explanation() -> None:
    rules = builtin_rules()
    ids = [rule.id for rule in rules]

    assert len(ids) == len(set(ids))
    for rule in rules:
        assert rule.explanation.strip(), f"{rule.id} has no explanation"
        if rule.decision is not Verdict.ALLOW:
            assert rule.remediation, f"{rule.id} blocks or asks but offers no remediation"


def test_blocking_rules_demand_at_least_medium_confidence() -> None:
    """A LOW-confidence guess must never be able to deny an operation."""
    for rule in builtin_rules():
        if rule.decision is Verdict.DENY and rule.references_asset_fields:
            assert rule.min_confidence is not Confidence.LOW, rule.id


# --- ZR-001 cross-client PII → deny -----------------------------------------


def test_zr001_denies_cross_client_pii() -> None:
    decision = decide(make_action(intents={Intent.READ}), [bluepeak_pii_evidence()])
    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-001"


def test_zr001_fires_on_column_level_pii_alone() -> None:
    evidence = bluepeak_pii_evidence(
        tags=set(),
        column_tags=(ColumnTags(field_path="email", tags=frozenset({PII_TAG})),),
    )
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id == "ZR-001"
    assert decision.matched_columns == ("email",)


def test_zr001_does_not_fire_in_domain() -> None:
    """PII inside your own client is not a boundary violation."""
    evidence = make_evidence(environment="DEV", tags={PII_TAG})
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-001"
    assert decision.verdict is not Verdict.DENY


# --- ZR-002 cross-client read → ask -----------------------------------------


def test_zr002_asks_for_a_clean_cross_client_read() -> None:
    evidence = make_evidence(name="bluepeak.shared_dim_date", domain=BLUEPEAK_DOMAIN, tags=set())
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-002"


# --- ZR-003 cross-client write → deny ---------------------------------------


def test_zr003_denies_a_cross_client_write_even_without_pii() -> None:
    evidence = make_evidence(name="bluepeak.staging_table", domain=BLUEPEAK_DOMAIN, tags=set())
    decision = decide(make_action(tool_name="Write", intents={Intent.WRITE}), [evidence])
    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-003"


# --- ZR-004 production mutation → ask ---------------------------------------


def test_zr004_asks_before_mutating_production() -> None:
    evidence = make_evidence(environment="PROD")
    decision = decide(make_action(tool_name="Edit", intents={Intent.WRITE}), [evidence])
    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-004"


def test_zr004_does_not_fire_on_a_production_read() -> None:
    evidence = make_evidence(environment="PROD")
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-004"


# --- ZR-005 destructive production → deny -----------------------------------


def test_zr005_denies_destructive_production_work() -> None:
    evidence = make_evidence(environment="PROD")
    decision = decide(make_action(tool_name="Bash", intents={Intent.DESTRUCTIVE}), [evidence])
    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-005"


def test_zr005_does_not_fire_in_dev() -> None:
    evidence = make_evidence(environment="DEV")
    decision = decide(make_action(tool_name="Bash", intents={Intent.DESTRUCTIVE}), [evidence])
    assert decision.rule_id != "ZR-005"


# --- ZR-006 deprecated asset → ask ------------------------------------------


def test_zr006_asks_before_building_on_a_deprecated_asset() -> None:
    evidence = make_evidence(
        name="northstar.dim_customer_legacy",
        environment="DEV",
        lifecycle=Lifecycle.DEPRECATED,
    )
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-006"


def test_zr006_does_not_fire_on_an_active_asset() -> None:
    evidence = make_evidence(environment="DEV", lifecycle=Lifecycle.ACTIVE)
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-006"


# --- ZR-007 unowned sensitive → ask -----------------------------------------


def test_zr007_asks_when_sensitive_data_has_no_owner() -> None:
    evidence = make_evidence(environment="DEV", tags={CONFIDENTIAL_TAG}, owners=set())
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-007"


def test_zr007_does_not_fire_when_an_owner_exists() -> None:
    evidence = make_evidence(
        environment="DEV", tags={CONFIDENTIAL_TAG}, owners={"urn:li:corpuser:dana"}
    )
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-007"


def test_zr007_does_not_fire_on_unowned_but_unclassified_data() -> None:
    evidence = make_evidence(environment="DEV", tags=set(), owners=set())
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-007"


# --- ZR-008 critical downstream → ask ---------------------------------------


def test_zr008_asks_before_changing_something_a_critical_dashboard_depends_on() -> None:
    evidence = make_evidence(
        name="northstar.fct_revenue_daily",
        environment="DEV",
        downstream_critical=(REVENUE_DASHBOARD,),
    )
    decision = decide(make_action(tool_name="Edit", intents={Intent.WRITE}), [evidence])

    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-008"
    assert REVENUE_DASHBOARD in decision.reason


def test_zr008_does_not_fire_on_a_read() -> None:
    evidence = make_evidence(environment="DEV", downstream_critical=(REVENUE_DASHBOARD,))
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-008"


def test_zr008_does_not_fire_without_critical_downstream() -> None:
    evidence = make_evidence(environment="DEV", downstream_critical=())
    decision = decide(make_action(tool_name="Edit", intents={Intent.WRITE}), [evidence])
    assert decision.rule_id != "ZR-008"


# --- ZR-009 / ZR-010 allow ---------------------------------------------------


def test_zr009_allows_an_in_domain_development_read() -> None:
    evidence = make_evidence(environment="DEV")
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.verdict is Verdict.ALLOW
    assert decision.rule_id == "ZR-009"


def test_zr009_does_not_allow_a_production_read_implicitly() -> None:
    """PROD is not in allowed_environments, so the named allow must not apply."""
    evidence = make_evidence(environment="PROD")
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-009"


def test_zr010_allows_in_domain_code_generation() -> None:
    evidence = make_evidence(environment="DEV", tags=set())
    decision = decide(make_action(tool_name="Write", intents={Intent.CODEGEN}), [evidence])
    assert decision.verdict is Verdict.ALLOW
    assert decision.rule_id == "ZR-010"


def test_zr010_does_not_allow_codegen_over_sensitive_data() -> None:
    evidence = make_evidence(environment="DEV", tags={PII_TAG})
    decision = decide(make_action(tool_name="Write", intents={Intent.CODEGEN}), [evidence])
    assert decision.rule_id != "ZR-010"


# --- ZR-011 unresolved + sensitive → ask ------------------------------------


def test_zr011_asks_when_a_write_names_something_datahub_does_not_know() -> None:
    evidence = make_evidence(
        status=EvidenceStatus.NOT_FOUND,
        ref=make_ref("northstar.typo_table", confidence=Confidence.HIGH),
    )
    decision = decide(make_action(tool_name="Write", intents={Intent.WRITE}), [evidence])

    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-011"
    assert "northstar.typo_table" in decision.reason


def test_zr011_does_not_fire_on_a_read() -> None:
    evidence = make_evidence(status=EvidenceStatus.NOT_FOUND)
    decision = decide(make_action(intents={Intent.READ}), [evidence])
    assert decision.rule_id != "ZR-011"


# --- ZR-014 tamper → deny ----------------------------------------------------


def test_zr014_denies_edits_to_zence_config() -> None:
    action = make_action(
        tool_name="Edit",
        intents={Intent.WRITE},
        targets_zence_config=True,
        target_paths=(".zence/policy.yaml",),
    )
    decision = decide(action, [])

    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-014"
    assert ".zence/policy.yaml" in decision.reason


def test_zr014_does_not_fire_on_ordinary_edits() -> None:
    action = make_action(
        tool_name="Edit", intents={Intent.WRITE}, target_paths=("models/revenue.sql",)
    )
    decision = decide(action, [])
    assert decision.rule_id != "ZR-014"
