"""The metadata provider interface.

Two implementations, one contract:

* :class:`~zence_core.providers.live.LiveProvider` talks to a real DataHub
  instance through the Python SDK.
* :class:`~zence_core.providers.fixture.FixtureProvider` replays responses
  recorded from a real instance by `zence demo record`.

**A fixture may never present itself as a live connection.** Every `Evidence`
carries `provider`, that value reaches the audit record and the decision, and
nothing in this package will substitute one for the other. If the live provider
cannot reach DataHub it returns `LOOKUP_FAILED` evidence and the fail-safe matrix
takes over — it does not quietly fall back to recorded data, because a decision
made against yesterday's catalog and labelled "live" is worse than no decision.

The other invariant: **resolution never raises**. A provider that throws inside a
PreToolUse hook would either crash the session or, worse, be caught somewhere
that treats the failure as "nothing found". Failures are returned as evidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from zence_core.schemas import (
    AssetRef,
    Evidence,
    EvidenceStatus,
    ProviderKind,
    WorkspaceContext,
)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """What `zence doctor` reports."""

    reachable: bool
    kind: ProviderKind
    detail: str
    endpoint: str | None = None
    identity: str | None = None
    """The authenticated user, when the provider can determine it. Recorded on
    write-back so a decision document says who produced it."""


class MetadataProvider(ABC):
    """Resolves asset references into DataHub evidence."""

    kind: ProviderKind

    @abstractmethod
    def resolve(self, refs: Sequence[AssetRef], workspace: WorkspaceContext) -> list[Evidence]:
        """Resolve every reference. Never raises; failures come back as evidence.

        The returned list is parallel to `refs` — one Evidence per reference,
        including the ones that could not be resolved. Dropping a failed lookup
        would make "Zence could not see this" indistinguishable from "there was
        nothing to see".
        """

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Whether this provider can currently answer questions."""

    def close(self) -> None:  # noqa: B027 - concrete no-op, not an abstract method
        """Release any held connection.

        Deliberately concrete and empty: FixtureProvider holds nothing, and
        forcing every implementation to write an empty override would be noise.
        """


def failed_evidence(
    ref: AssetRef,
    kind: ProviderKind,
    reason: str,
    *,
    status: EvidenceStatus = EvidenceStatus.LOOKUP_FAILED,
) -> Evidence:
    """Evidence describing why a lookup did not produce an answer.

    `reason` reaches the user, so it should say what went wrong in terms they can
    act on — "connection refused", not "NoneType has no attribute".
    """
    return Evidence(
        status=status,
        provider=kind,
        fetched_at=datetime.now(UTC),
        ref=ref,
        failure_reason=reason,
    )


def not_found_evidence(ref: AssetRef, kind: ProviderKind) -> Evidence:
    """DataHub answered, and the asset is not in the catalog.

    Distinct from a failed lookup: this is information, not an absence of it.
    """
    return Evidence(
        status=EvidenceStatus.NOT_FOUND,
        provider=kind,
        fetched_at=datetime.now(UTC),
        ref=ref,
    )
