"""Shared builders.

The demo fiction is used throughout the tests so failures read like real
scenarios: **Northstar Commerce** is the client the session is bounded to, and
**BluePeak Health** is the client it must never touch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from zence_core.policy import load_policy_data
from zence_core.schemas import (
    Action,
    AssetKind,
    AssetRef,
    ColumnTags,
    Confidence,
    Evidence,
    EvidenceStatus,
    Intent,
    Lifecycle,
    Mode,
    Policy,
    ProviderKind,
    ToolKind,
    WorkspaceContext,
)

#: Anything that names a catalog. `build_provider` gives these precedence over
#: `.zence/project.yaml` on purpose — someone who exported `DATAHUB_GMS_URL`
#: means it. That is right in production and wrong in a test: a developer with a
#: live catalog in their shell would run a different program than CI does, and
#: the suite would pass or fail for reasons unrelated to the change. Integration
#: tests are exempt; a live catalog is the entire point of those.
CATALOG_ENV_VARS = (
    "DATAHUB_GMS_URL",
    "DATAHUB_GMS_TOKEN",
    "CLAUDE_PLUGIN_OPTION_DATAHUB_URL",
    "CLAUDE_PLUGIN_OPTION_DATAHUB_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic_catalog_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every non-integration test as though no catalog were configured."""
    if request.node.get_closest_marker("integration") or request.node.get_closest_marker("e2e"):
        return
    for name in CATALOG_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


NORTHSTAR_DOMAIN = "urn:li:domain:northstar-commerce"
BLUEPEAK_DOMAIN = "urn:li:domain:bluepeak-health"

PII_TAG = "urn:li:tag:PII"
CONFIDENTIAL_TAG = "urn:li:tag:Confidential"
PERSONAL_DATA_TERM = "urn:li:glossaryTerm:PersonalData"

REVENUE_DASHBOARD = "urn:li:dashboard:(looker,northstar_revenue)"

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def dataset_urn(name: str, env: str = "PROD") -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:snowflake,{name},{env})"


def make_action(
    *,
    tool_name: str = "mcp__datahub__search",
    tool_kind: ToolKind = ToolKind.MCP_CATALOG,
    hook_event: str = "PreToolUse",
    intents: set[Intent] | None = None,
    targets_zence_config: bool = False,
    target_paths: tuple[str, ...] = (),
    input_excerpt: str = "",
) -> Action:
    return Action(
        tool_name=tool_name,
        tool_kind=tool_kind,
        hook_event=hook_event,
        intents=frozenset(intents or {Intent.READ}),
        targets_zence_config=targets_zence_config,
        target_paths=target_paths,
        input_excerpt=input_excerpt,
    )


def make_ref(
    raw_text: str = "northstar.marketing_leads",
    *,
    kind: AssetKind = AssetKind.DATASET,
    confidence: Confidence = Confidence.HIGH,
    extractor: str = "sql",
    columns: tuple[str, ...] = (),
) -> AssetRef:
    return AssetRef(
        raw_text=raw_text,
        kind=kind,
        confidence=confidence,
        extractor=extractor,
        columns=columns,
    )


def make_evidence(
    *,
    name: str = "northstar.marketing_leads",
    domain: str | None = NORTHSTAR_DOMAIN,
    domain_name: str | None = "Northstar Commerce",
    environment: str | None = "DEV",
    tags: set[str] | None = None,
    terms: set[str] | None = None,
    owners: set[str] | None = None,
    column_tags: tuple[ColumnTags, ...] = (),
    lifecycle: Lifecycle = Lifecycle.ACTIVE,
    downstream_critical: tuple[str, ...] = (),
    status: EvidenceStatus = EvidenceStatus.RESOLVED,
    provider: ProviderKind = ProviderKind.FIXTURE,
    failure_reason: str | None = None,
    ref: AssetRef | None = None,
) -> Evidence:
    return Evidence(
        status=status,
        provider=provider,
        fetched_at=FIXED_NOW,
        ref=ref or make_ref(name),
        urn=dataset_urn(name, environment or "PROD") if status is EvidenceStatus.RESOLVED else None,
        name=name if status is EvidenceStatus.RESOLVED else None,
        domain_urn=domain,
        domain_name=domain_name,
        # `is None`, not `or` — an explicitly empty set is a meaningful value here
        # (an unowned asset is what ZR-007 keys on) and must not fall back to a default.
        owners=frozenset({"urn:li:corpuser:dana"} if owners is None else owners),
        tags=frozenset(tags if tags is not None else set()),
        terms=frozenset(terms if terms is not None else set()),
        column_tags=column_tags,
        lifecycle=lifecycle,
        environment=environment,
        downstream_critical=downstream_critical,
        failure_reason=failure_reason,
    )


def bluepeak_pii_evidence(**overrides: Any) -> Evidence:
    """The asset Scenario A must never be allowed to touch."""
    defaults: dict[str, Any] = {
        "name": "bluepeak.patient_contacts",
        "domain": BLUEPEAK_DOMAIN,
        "domain_name": "BluePeak Health",
        "environment": "PROD",
        "tags": {PII_TAG},
        "terms": {PERSONAL_DATA_TERM},
        "owners": {"urn:li:corpuser:priya"},
        "column_tags": (
            ColumnTags(field_path="email", tags=frozenset({PII_TAG})),
            ColumnTags(field_path="phone", tags=frozenset({PII_TAG})),
        ),
    }
    defaults.update(overrides)
    return make_evidence(**defaults)


def make_workspace(
    *,
    mode: Mode = Mode.ENFORCE,
    allowed_domains: set[str] | None = None,
    allowed_environments: set[str] | None = None,
) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id="northstar-analytics",
        root_path="/tmp/northstar-analytics",
        mode=mode,
        active_client="Northstar Commerce",
        active_domain=NORTHSTAR_DOMAIN,
        allowed_domains=frozenset(allowed_domains or {NORTHSTAR_DOMAIN}),
        allowed_environments=frozenset(allowed_environments or {"DEV", "QA"}),
        sensitive_tags=frozenset({PII_TAG, CONFIDENTIAL_TAG}),
        protected_terms=frozenset({PERSONAL_DATA_TERM}),
        critical_downstream=frozenset({REVENUE_DASHBOARD}),
        policy_version="1.0.0",
    )


BASE_POLICY: dict[str, Any] = {
    "policy_version": "1.0.0",
    "workspace_id": "northstar-analytics",
    "mode": "enforce",
    "active_client": "Northstar Commerce",
    "active_domain": NORTHSTAR_DOMAIN,
    "allowed_domains": [NORTHSTAR_DOMAIN],
    "allowed_environments": ["DEV", "QA"],
    "sensitive_tags": [PII_TAG, CONFIDENTIAL_TAG],
    "protected_terms": [PERSONAL_DATA_TERM],
    "critical_downstream": [REVENUE_DASHBOARD],
}


def make_policy(**overrides: Any) -> Policy:
    """A policy inheriting the full built-in rule set."""
    data = dict(BASE_POLICY)
    data.update(overrides)
    return load_policy_data(data, origin="<test>")


@pytest.fixture
def policy() -> Policy:
    return make_policy()


@pytest.fixture
def workspace() -> WorkspaceContext:
    return make_workspace()
