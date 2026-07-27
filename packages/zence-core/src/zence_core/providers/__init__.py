"""Metadata providers.

`LiveProvider` reads a real DataHub instance; `FixtureProvider` replays responses
recorded from one. They implement the same interface and are never silently
interchanged — every piece of evidence carries which produced it, and that value
reaches the decision and the audit record.
"""

from zence_core.providers.base import (
    MetadataProvider,
    ProviderHealth,
    failed_evidence,
    not_found_evidence,
)
from zence_core.providers.cache import (
    DEFAULT_NEGATIVE_TTL_SECONDS,
    DEFAULT_TTL_SECONDS,
    EvidenceCache,
)
from zence_core.providers.fixture import (
    FIXTURE_SCHEMA_VERSION,
    FixtureError,
    FixtureProvider,
)
from zence_core.providers.live import (
    DOWNSTREAM_HOPS,
    DataHubUnavailableError,
    LiveProvider,
    environment_from_urn,
)

__all__ = [
    "DEFAULT_NEGATIVE_TTL_SECONDS",
    "DEFAULT_TTL_SECONDS",
    "DOWNSTREAM_HOPS",
    "FIXTURE_SCHEMA_VERSION",
    "DataHubUnavailableError",
    "EvidenceCache",
    "FixtureError",
    "FixtureProvider",
    "LiveProvider",
    "MetadataProvider",
    "ProviderHealth",
    "environment_from_urn",
    "failed_evidence",
    "not_found_evidence",
]
