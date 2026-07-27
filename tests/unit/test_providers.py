"""Metadata providers.

The theme running through this file is the one invariant that matters most:
**a provider never lies about what it knows.** It does not raise inside a hook,
it does not report a fixture as a live read, and it does not let a failed lookup
look like an empty catalog.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import (
    BLUEPEAK_DOMAIN,
    NORTHSTAR_DOMAIN,
    PII_TAG,
    REVENUE_DASHBOARD,
    make_ref,
    make_workspace,
)
from zence_core.policy import evaluate
from zence_core.providers import (
    FIXTURE_SCHEMA_VERSION,
    EvidenceCache,
    FixtureError,
    FixtureProvider,
    LiveProvider,
    environment_from_urn,
)
from zence_core.schemas import EvidenceStatus, Intent, ProviderKind, Verdict

PATIENT_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)"
LEADS_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.marketing_leads,DEV)"
REVENUE_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.fct_revenue_daily,DEV)"


def recording(entities: dict[str, Any]) -> dict[str, Any]:
    """A well-formed recording envelope."""
    return {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "recorded_at": "2026-08-01T12:00:00Z",
        "source_endpoint": "http://localhost:8080",
        "datahub_version": "1.6.0",
        "entities": entities,
    }


ENTITIES: dict[str, Any] = {
    "bluepeak.patient_contacts": {
        "urn": PATIENT_URN,
        "name": "bluepeak.patient_contacts",
        "domain_urn": BLUEPEAK_DOMAIN,
        "domain_name": "BluePeak Health",
        "owners": ["urn:li:corpuser:priya"],
        "tags": [PII_TAG],
        "terms": ["urn:li:glossaryTerm:PersonalData"],
        "column_tags": [
            {"field_path": "email", "tags": [PII_TAG]},
            {"field_path": "phone", "tags": [PII_TAG]},
        ],
        "lifecycle": "active",
        "environment": "PROD",
        "downstream_critical": [],
    },
    "northstar.marketing_leads": {
        "urn": LEADS_URN,
        "name": "northstar.marketing_leads",
        "domain_urn": NORTHSTAR_DOMAIN,
        "domain_name": "Northstar Commerce",
        "owners": ["urn:li:corpuser:dana"],
        "tags": [],
        "terms": [],
        "column_tags": [],
        "lifecycle": "active",
        "environment": "DEV",
        "downstream_critical": [],
    },
    "northstar.fct_revenue_daily": {
        "urn": REVENUE_URN,
        "name": "northstar.fct_revenue_daily",
        "domain_urn": NORTHSTAR_DOMAIN,
        "domain_name": "Northstar Commerce",
        "owners": ["urn:li:corpuser:dana"],
        "tags": [],
        "terms": [],
        "column_tags": [],
        "lifecycle": "active",
        "environment": "DEV",
        "downstream_critical": [REVENUE_DASHBOARD, "urn:li:dashboard:(looker,scratch)"],
    },
}


@pytest.fixture
def provider() -> FixtureProvider:
    return FixtureProvider.from_dict(recording(ENTITIES))


# =============================================================================
# FixtureProvider
# =============================================================================


def test_resolves_by_name(provider: FixtureProvider) -> None:
    [evidence] = provider.resolve([make_ref("bluepeak.patient_contacts")], make_workspace())

    assert evidence.status is EvidenceStatus.RESOLVED
    assert evidence.urn == PATIENT_URN
    assert evidence.domain_urn == BLUEPEAK_DOMAIN
    assert PII_TAG in evidence.tags


def test_resolves_by_urn(provider: FixtureProvider) -> None:
    """The same entity, whether the extractor produced a name or a full URN."""
    [evidence] = provider.resolve([make_ref(PATIENT_URN)], make_workspace())
    assert evidence.urn == PATIENT_URN


def test_resolution_is_case_insensitive(provider: FixtureProvider) -> None:
    [evidence] = provider.resolve([make_ref("BluePeak.Patient_Contacts")], make_workspace())
    assert evidence.status is EvidenceStatus.RESOLVED


def test_column_level_tags_survive_the_round_trip(provider: FixtureProvider) -> None:
    [evidence] = provider.resolve([make_ref("bluepeak.patient_contacts")], make_workspace())
    assert set(evidence.columns_tagged(frozenset({PII_TAG}))) == {"email", "phone"}


def test_unknown_asset_is_not_found_rather_than_failed(provider: FixtureProvider) -> None:
    """A catalog that answered "no such asset" is information, not an outage."""
    [evidence] = provider.resolve([make_ref("nowhere.nothing")], make_workspace())

    assert evidence.status is EvidenceStatus.NOT_FOUND
    assert evidence.failure_reason is None


def test_one_evidence_per_reference(provider: FixtureProvider) -> None:
    """Dropping unresolved refs would hide them from the fail-safe matrix."""
    results = provider.resolve(
        [make_ref("bluepeak.patient_contacts"), make_ref("nowhere.nothing")],
        make_workspace(),
    )
    assert len(results) == 2


def test_every_result_is_stamped_as_a_fixture(provider: FixtureProvider) -> None:
    """The value that stops a recording ever passing as a live read."""
    results = provider.resolve([make_ref("northstar.marketing_leads")], make_workspace())
    assert all(evidence.provider is ProviderKind.FIXTURE for evidence in results)


def test_downstream_criticality_is_filtered_to_this_workspace(
    provider: FixtureProvider,
) -> None:
    """A dashboard only matters if *this* workspace declared it critical."""
    [evidence] = provider.resolve([make_ref("northstar.fct_revenue_daily")], make_workspace())

    assert evidence.downstream_critical == (REVENUE_DASHBOARD,)
    assert "urn:li:dashboard:(looker,scratch)" not in evidence.downstream_critical


def test_health_reports_the_recording_provenance(provider: FixtureProvider) -> None:
    health = provider.health()
    assert health.kind is ProviderKind.FIXTURE
    assert "2026-08-01" in health.detail
    assert "localhost:8080" in health.detail


# --- Fixture validation ------------------------------------------------------


def test_fixture_without_provenance_is_rejected() -> None:
    """Fixtures must be recorded. A hand-written one encodes an assumption."""
    payload = recording(ENTITIES)
    del payload["recorded_at"]

    with pytest.raises(FixtureError, match="recorded_at"):
        FixtureProvider.from_dict(payload)


def test_fixture_without_a_source_endpoint_is_rejected() -> None:
    payload = recording(ENTITIES)
    payload["source_endpoint"] = ""

    with pytest.raises(FixtureError, match="source_endpoint"):
        FixtureProvider.from_dict(payload)


def test_stale_schema_version_is_rejected_with_the_fix() -> None:
    payload = recording(ENTITIES)
    payload["schema_version"] = 0

    with pytest.raises(FixtureError, match="zence demo record"):
        FixtureProvider.from_dict(payload)


def test_malformed_fixture_file_is_reported_clearly(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json")

    with pytest.raises(FixtureError, match="not valid JSON"):
        FixtureProvider.from_file(path)


def test_missing_fixture_file_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(FixtureError, match="cannot read fixture"):
        FixtureProvider.from_file(tmp_path / "absent.json")


def test_fixture_round_trips_through_a_file(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(recording(ENTITIES)), encoding="utf-8")

    loaded = FixtureProvider.from_file(path)
    [evidence] = loaded.resolve([make_ref("bluepeak.patient_contacts")], make_workspace())
    assert evidence.urn == PATIENT_URN


# =============================================================================
# Cache
# =============================================================================


def test_cache_returns_a_stored_entry() -> None:
    from tests.conftest import make_evidence

    cache = EvidenceCache()
    evidence = make_evidence()
    cache.put("northstar.leads", evidence)

    assert cache.get("northstar.leads") is evidence
    assert cache.hits == 1


def test_cache_key_is_normalized() -> None:
    from tests.conftest import make_evidence

    cache = EvidenceCache()
    cache.put("  Northstar.Leads  ", make_evidence())
    assert cache.get("northstar.leads") is not None


def test_cache_entry_expires() -> None:
    from tests.conftest import make_evidence

    cache = EvidenceCache(ttl_seconds=0.01)
    cache.put("x", make_evidence())
    time.sleep(0.02)

    assert cache.get("x") is None


def test_failures_expire_far_sooner_than_successes() -> None:
    """A recovered DataHub should be noticed within a turn, not a minute later."""
    from tests.conftest import make_evidence

    cache = EvidenceCache(ttl_seconds=10.0, negative_ttl_seconds=0.01)
    cache.put(
        "down",
        make_evidence(status=EvidenceStatus.LOOKUP_FAILED, failure_reason="refused"),
    )
    cache.put("up", make_evidence())
    time.sleep(0.02)

    assert cache.get("down") is None
    assert cache.get("up") is not None


def test_cache_miss_is_counted() -> None:
    cache = EvidenceCache()
    assert cache.get("absent") is None
    assert cache.misses == 1


# =============================================================================
# LiveProvider — degradation, without needing a live instance
# =============================================================================


def test_unreachable_server_yields_failed_evidence_not_an_exception() -> None:
    """The invariant. A raise here would crash the hook or be read as "nothing found"."""
    provider = LiveProvider(server="http://127.0.0.1:1", token="unused")
    results = provider.resolve([make_ref("northstar.marketing_leads")], make_workspace())

    assert len(results) == 1
    assert results[0].status is EvidenceStatus.LOOKUP_FAILED
    assert results[0].provider is ProviderKind.LIVE
    assert results[0].failure_reason


def test_unreachable_server_reports_unhealthy_with_a_reason() -> None:
    provider = LiveProvider(server="http://127.0.0.1:1", token="unused")
    health = provider.health()

    assert health.reachable is False
    assert health.endpoint == "http://127.0.0.1:1"
    assert health.detail


def test_a_failed_lookup_drives_the_engine_to_ask_not_allow() -> None:
    """The end-to-end consequence: an outage cannot become a silent allow."""
    from tests.conftest import make_action, make_policy

    provider = LiveProvider(server="http://127.0.0.1:1", token="unused")
    workspace = make_workspace()
    evidences = provider.resolve([make_ref("bluepeak.patient_contacts")], workspace)

    decision = evaluate(make_action(intents={Intent.READ}), evidences, workspace, make_policy())

    assert decision.verdict is not Verdict.ALLOW
    assert decision.degraded is True


def test_live_provider_never_reports_itself_as_a_fixture() -> None:
    provider = LiveProvider(server="http://127.0.0.1:1")
    results = provider.resolve([make_ref("anything")], make_workspace())
    assert all(evidence.provider is ProviderKind.LIVE for evidence in results)


@pytest.mark.parametrize(
    ("urn", "expected"),
    [
        (PATIENT_URN, "PROD"),
        (LEADS_URN, "DEV"),
        ("urn:li:dataset:(urn:li:dataPlatform:bigquery,proj.ds.tbl,STAGING)", "STAGING"),
        ("urn:li:dashboard:(looker,northstar_revenue)", None),
        (None, None),
        ("not-a-urn", None),
    ],
)
def test_environment_is_read_from_the_urn(urn: str | None, expected: str | None) -> None:
    assert environment_from_urn(urn) == expected


# =============================================================================
# Regressions
# =============================================================================


def test_a_transport_failure_is_never_reported_as_not_found() -> None:
    """`_find_urn` used to catch the connection error and return None, which the
    caller turned into NOT_FOUND — making an outage indistinguishable from a
    catalog that simply does not contain the asset. That is the single most
    dangerous confusion this codebase can make.
    """
    provider = LiveProvider(server="http://127.0.0.1:1", token="unused")
    [evidence] = provider.resolve([make_ref("northstar.marketing_leads")], make_workspace())

    # LOOKUP_FAILED, specifically — NOT_FOUND here would mean Zence had decided
    # the catalog does not contain this asset, having never reached the catalog.
    assert evidence.status is EvidenceStatus.LOOKUP_FAILED
    assert evidence.failure_reason


def test_lookups_are_bounded_and_do_not_retry() -> None:
    """The SDK retries with backoff by default, which took ~28s to fail against a
    dead endpoint — an order of magnitude past a PreToolUse hook's budget, and
    long enough that a DataHub outage reads as Claude Code hanging.
    """
    provider = LiveProvider(server="http://127.0.0.1:1", token="unused", timeout_seconds=1.0)

    started = time.monotonic()
    provider.resolve([make_ref("northstar.marketing_leads")], make_workspace())
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"resolution took {elapsed:.1f}s; retries are not disabled"
