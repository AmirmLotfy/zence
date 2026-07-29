"""Against a live DataHub instance.

Marked `integration`, so `pytest -m "not integration"` skips them and CI needs no
catalog. Run with a seeded instance:

    export DATAHUB_GMS_URL=http://localhost:8080
    uv run zence demo seed && uv run zence demo verify
    uv run pytest -m integration

These exist because fixtures cannot catch a whole class of bug. The worst one
found in this project was invisible to every unit test: `Dataset.tags` returns
`TagAssociationClass` objects, not URN strings, so `str(tag)` produced
``TagAssociationClass({'tag': 'urn:li:tag:PII', ...})`` — which never equals
``urn:li:tag:PII``. ZR-001 could not fire against a real catalog. A recording
stores plain strings, so the fixtures agreed with the broken code.
"""

from __future__ import annotations

import os

import pytest

from zence_core.extract.base import make_ref
from zence_core.policy import evaluate, load_policy_file, workspace_from_policy
from zence_core.providers import LiveProvider
from zence_core.schemas import (
    EvidenceStatus,
    Intent,
    Policy,
    ProviderKind,
    Verdict,
    WorkspaceContext,
)

pytestmark = pytest.mark.integration

PATIENT = "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)"
LEADS = "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.marketing_leads,DEV)"
REVENUE = "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.fct_revenue_daily,DEV)"
LEGACY = "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.dim_customer_legacy,DEV)"
DASHBOARD = "urn:li:dashboard:(looker,northstar_revenue)"


def _server() -> str:
    url = os.environ.get("DATAHUB_GMS_URL")
    if not url:
        pytest.skip("DATAHUB_GMS_URL not set")
    return url


@pytest.fixture(scope="module")
def provider() -> LiveProvider:
    live = LiveProvider(
        server=_server(),
        token=os.environ.get("DATAHUB_GMS_TOKEN"),
        timeout_seconds=30,
    )
    if not live.health().reachable:
        pytest.skip("DataHub is not reachable")
    return live


@pytest.fixture(scope="module")
def workspace() -> WorkspaceContext:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "examples/clients/northstar-analytics"
    policy_path = root / ".zence" / "policy.yaml"
    return workspace_from_policy(load_policy_file(policy_path), root, policy_path)


@pytest.fixture(scope="module")
def policy() -> Policy:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "examples/clients/northstar-analytics"
    return load_policy_file(root / ".zence" / "policy.yaml")


def resolve(provider: LiveProvider, workspace, urn: str):  # type: ignore[no-untyped-def]
    [evidence] = provider.resolve([make_ref(urn, extractor="integration")], workspace)
    return evidence


# --- Reading the catalog -----------------------------------------------------


def test_the_catalog_is_reachable(provider: LiveProvider) -> None:
    health = provider.health()
    assert health.reachable
    assert health.kind is ProviderKind.LIVE


def test_an_asset_resolves_with_its_domain(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    evidence = resolve(provider, workspace, PATIENT)

    assert evidence.status is EvidenceStatus.RESOLVED
    assert evidence.domain_urn == "urn:li:domain:bluepeak-health"
    assert evidence.domain_name == "BluePeak Health", "display name, for the denial text"


def test_dataset_tags_come_back_as_urns(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    """The regression. `str(TagAssociationClass(...))` is not a URN, and every
    fixture agreed with the broken code because a recording stores strings."""
    evidence = resolve(provider, workspace, PATIENT)

    assert "urn:li:tag:PII" in evidence.tags
    assert not any("TagAssociationClass" in tag for tag in evidence.tags)


def test_column_tags_come_back_as_urns(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    evidence = resolve(provider, workspace, PATIENT)
    tagged = evidence.columns_tagged(frozenset({"urn:li:tag:PII"}))

    assert set(tagged) >= {"email", "phone"}


def test_glossary_terms_come_back_as_urns(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    evidence = resolve(provider, workspace, PATIENT)
    assert "urn:li:glossaryTerm:PersonalData" in evidence.terms


def test_owners_come_back_as_urns(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    evidence = resolve(provider, workspace, PATIENT)
    assert any(owner.startswith("urn:li:corpuser:") for owner in evidence.owners)


def test_deprecation_is_read_from_the_aspect(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    assert resolve(provider, workspace, LEGACY).lifecycle.value == "deprecated"
    assert resolve(provider, workspace, LEADS).lifecycle.value == "active"


def test_environment_is_read_from_the_urn(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    assert resolve(provider, workspace, LEADS).environment == "DEV"
    assert resolve(provider, workspace, PATIENT).environment == "PROD"


def test_downstream_lineage_reaches_the_critical_dashboard(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    """Two hops, from real lineage — this is what makes ZR-008 a decision rather
    than a configured constant."""
    evidence = resolve(provider, workspace, REVENUE)
    assert DASHBOARD in evidence.downstream_critical


def test_an_absent_asset_is_not_found_not_failed(provider, workspace) -> None:  # type: ignore[no-untyped-def]
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,nowhere.nothing,PROD)"
    assert resolve(provider, workspace, urn).status is EvidenceStatus.NOT_FOUND


# --- The four scenarios ------------------------------------------------------


def make_action(tool: str, intents: set[Intent]):  # type: ignore[no-untyped-def]
    from zence_core.schemas import Action, ToolKind

    return Action(
        tool_name=tool,
        tool_kind=ToolKind.FILE_WRITE,
        hook_event="PreToolUse",
        intents=frozenset(intents),
    )


def test_scenario_a_cross_client_pii_is_denied(provider, workspace, policy) -> None:  # type: ignore[no-untyped-def]
    evidences = provider.resolve(
        [make_ref(LEADS, extractor="sql"), make_ref(PATIENT, extractor="sql")], workspace
    )
    decision = evaluate(make_action("Write", {Intent.READ}), evidences, workspace, policy)

    assert decision.verdict is Verdict.DENY
    assert decision.rule_id == "ZR-001"
    assert decision.provider is ProviderKind.LIVE
    assert "BluePeak Health" in decision.reason
    assert set(decision.matched_columns) >= {"email", "phone"}


def test_scenario_b_critical_downstream_asks(provider, workspace, policy) -> None:  # type: ignore[no-untyped-def]
    evidences = provider.resolve([make_ref(REVENUE, extractor="sql")], workspace)
    decision = evaluate(make_action("Edit", {Intent.WRITE}), evidences, workspace, policy)

    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-008"
    assert DASHBOARD in decision.downstream_critical


def test_scenario_c_in_boundary_work_is_allowed(provider, workspace, policy) -> None:  # type: ignore[no-untyped-def]
    evidences = provider.resolve([make_ref(LEADS, extractor="sql")], workspace)
    decision = evaluate(make_action("Write", {Intent.READ}), evidences, workspace, policy)

    assert decision.verdict is Verdict.ALLOW
    assert decision.rule_id == "ZR-009"
    assert not decision.degraded


def test_a_deprecated_asset_asks(provider, workspace, policy) -> None:  # type: ignore[no-untyped-def]
    evidences = provider.resolve([make_ref(LEGACY, extractor="sql")], workspace)
    decision = evaluate(make_action("Write", {Intent.READ}), evidences, workspace, policy)

    assert decision.verdict is Verdict.ASK
    assert decision.rule_id == "ZR-006"


# --- Scenario D: write-back --------------------------------------------------


def test_scenario_d_write_back_is_idempotent(workspace) -> None:  # type: ignore[no-untyped-def]
    """Finalizing twice must leave one document, not two.

    The id is `sha256(workspace::session)`, so the second upsert updates the
    first. Structural rather than a check that could lose a race.
    """
    from zence_core.writeback import idempotency_key, write_session_document

    session = "integration-idempotency"
    decisions = [
        {
            "verdict": "deny",
            "rule_id": "ZR-001",
            "rule_title": "Cross-client PII access",
            "reason": "integration test",
            "remediation": "use an in-domain asset",
            "evidence_urns": f'["{PATIENT}"]',
            "degraded": 0,
            "would_have_been": None,
        }
    ]
    common = {
        "server": _server(),
        "token": os.environ.get("DATAHUB_GMS_TOKEN"),
        "client_name": "Northstar Commerce",
        "workspace_id": workspace.workspace_id,
        "session_id": session,
        "repository": "northstar-analytics",
        "policy_version": "1.0.0",
        "decisions": decisions,
        "related_urns": [PATIENT],
    }

    def document_count() -> int:
        """Every Zence document in the catalog.

        Counted rather than searched by session name: DataHub's document search
        matches on body text, and these documents are similar enough that a
        session-scoped query returns other sessions too. The precise question is
        whether the *total* moves when the same session is finalized twice.
        """
        import requests

        response = requests.post(
            f"{_server()}/api/graphql",
            json={
                "query": '{ search(input:{type:DOCUMENT, query:"*", start:0, count:100}) '
                "{ searchResults { entity { urn } } } }"
            },
            timeout=30,
        )
        results = response.json()["data"]["search"]["searchResults"]
        return sum(1 for r in results if "zence-session-" in r["entity"]["urn"])

    first = write_session_document(**common)
    assert first.ok, first.detail
    after_first = document_count()

    second = write_session_document(**common)
    assert second.ok, second.detail
    after_second = document_count()

    assert first.idempotency_key == second.idempotency_key
    assert first.idempotency_key == idempotency_key(workspace.workspace_id, session)

    # The whole point: a second finalize updates, it does not create.
    assert after_second == after_first, (
        f"document count moved from {after_first} to {after_second} — "
        "the second finalize created a duplicate"
    )
