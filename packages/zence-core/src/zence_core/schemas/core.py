"""The objects a policy decision is made from.

Four things go into every evaluation:

* :class:`Action`           — the normalized Claude Code tool call
* :class:`AssetRef`         — a reference extracted from that call
* :class:`Evidence`         — what DataHub says about a resolved reference
* :class:`WorkspaceContext` — which client the session is bounded to

All four are frozen. A decision is a pure function of its inputs, and an audit
record that could be mutated after the fact is not an audit record.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from zence_core.schemas.enums import (
    AssetKind,
    Confidence,
    EvidenceStatus,
    Intent,
    Lifecycle,
    Mode,
    ProviderKind,
    ToolKind,
)

#: Upper bound on any text Zence stores or matches against. Bounds both the audit
#: record size and the work a regex predicate can be asked to do.
MAX_EXCERPT_CHARS = 2_000


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ColumnTags(_Frozen):
    """Field-level classification for one column.

    Column-level PII is the common real-world case: the dataset is fine, one
    column is not. A rule that only looked at dataset tags would miss it.
    """

    field_path: str
    tags: frozenset[str] = frozenset()
    terms: frozenset[str] = frozenset()


class Action(_Frozen):
    """A Claude Code tool call, normalized into something policy can reason about."""

    tool_name: str
    tool_kind: ToolKind
    hook_event: str
    intents: frozenset[Intent] = frozenset()
    tool_use_id: str | None = None

    input_excerpt: str = Field(default="", max_length=MAX_EXCERPT_CHARS)
    """Redacted. Never the full command, file body, or tool payload."""

    target_paths: tuple[str, ...] = ()
    """Filesystem paths the action would touch, resolved and workspace-relative."""

    targets_zence_config: bool = False
    """True when the action would modify `.zence/**` or hook configuration.

    Evaluated first and separately from everything else — see ZR-014.
    """

    @property
    def is_sensitive(self) -> bool:
        from zence_core.schemas.enums import SENSITIVE_INTENTS

        return bool(self.intents & SENSITIVE_INTENTS)


class AssetRef(_Frozen):
    """Something in the action that looks like it names a data asset."""

    raw_text: str
    kind: AssetKind
    confidence: Confidence
    extractor: str
    """Which extractor produced this, e.g. `sql`, `dbt`, `shell`. Audited so a
    noisy extractor can be identified and tuned."""

    resolved_urn: str | None = None
    columns: tuple[str, ...] = ()
    """Columns named alongside this asset, when the extractor could see them."""


class Evidence(_Frozen):
    """What DataHub reports about one asset — or why it could not say.

    An Evidence object always exists for every reference Zence tried to resolve,
    including failures. Silence is never represented as absence.
    """

    status: EvidenceStatus
    provider: ProviderKind
    fetched_at: datetime
    ref: AssetRef

    urn: str | None = None
    name: str | None = None

    domain_urn: str | None = None
    domain_name: str | None = None

    owners: frozenset[str] = frozenset()
    tags: frozenset[str] = frozenset()
    terms: frozenset[str] = frozenset()
    column_tags: tuple[ColumnTags, ...] = ()

    lifecycle: Lifecycle = Lifecycle.UNKNOWN
    environment: str | None = None

    downstream_critical: tuple[str, ...] = ()
    """URNs of downstream assets the workspace has declared critical."""

    failure_reason: str | None = None
    """Populated when status is LOOKUP_FAILED. Surfaced in the decision so the
    user learns that Zence was blind, not that the asset was clean."""

    @property
    def is_resolved(self) -> bool:
        return self.status is EvidenceStatus.RESOLVED

    @property
    def all_tags(self) -> frozenset[str]:
        """Dataset tags plus every column tag, flattened.

        Rules asking "does this asset touch PII at all" want this. Rules that
        need to name the offending column read `column_tags` directly.
        """
        flattened = set(self.tags)
        for column in self.column_tags:
            flattened |= column.tags
        return frozenset(flattened)

    @property
    def all_terms(self) -> frozenset[str]:
        flattened = set(self.terms)
        for column in self.column_tags:
            flattened |= column.terms
        return frozenset(flattened)

    def columns_tagged(self, tags: frozenset[str]) -> tuple[str, ...]:
        """Column paths carrying any of `tags`. Used to build the denial message."""
        return tuple(column.field_path for column in self.column_tags if column.tags & tags)


class WorkspaceContext(_Frozen):
    """The boundary the current session is boxed into.

    Loaded from `.zence/project.yaml` and `.zence/policy.yaml` at SessionStart.
    """

    workspace_id: str
    root_path: str
    mode: Mode = Mode.ENFORCE

    active_client: str
    active_domain: str | None = None

    allowed_domains: frozenset[str] = frozenset()
    allowed_environments: frozenset[str] = frozenset()

    sensitive_tags: frozenset[str] = frozenset()
    protected_terms: frozenset[str] = frozenset()
    critical_downstream: frozenset[str] = frozenset()

    policy_version: str = "0.0.0"
    policy_sha256: str | None = None
    """Recorded per session so tampering between turns is visible in the audit."""

    def is_in_domain(self, domain_urn: str | None) -> bool:
        """Whether a domain is inside this workspace's boundary.

        An asset with no domain is *not* in-domain. Unclassified data in a
        multi-client catalog is exactly the case that should be asked about, not
        waved through.
        """
        if domain_urn is None:
            return False
        return domain_urn in self.allowed_domains
