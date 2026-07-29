"""The real DataHub connection, via the `acryl-datahub` Python SDK.

Zence reads the catalog through the SDK rather than through the MCP server it
intercepts, for two reasons. A hook cannot borrow Claude's MCP client — that
connection belongs to the agent, not to us. And enforcement has to be
deterministic: the SDK returns typed aspects, where an MCP round trip returns
text shaped for a model to read.

The MCP server remains central. It is the surface Claude uses and the surface
Zence's PreToolUse hook matches on. This module is what makes the resulting
decision defensible.

**Nothing here raises.** A provider that throws inside a hook either crashes the
session or gets swallowed somewhere that reads the failure as "nothing found" —
which would turn an outage into a silent allow. Every failure comes back as
`LOOKUP_FAILED` evidence carrying a reason the user can act on.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from zence_core.providers.base import (
    MetadataProvider,
    ProviderHealth,
    failed_evidence,
    not_found_evidence,
)
from zence_core.providers.cache import EvidenceCache
from zence_core.schemas import (
    AssetRef,
    ColumnTags,
    Evidence,
    EvidenceStatus,
    Lifecycle,
    ProviderKind,
    WorkspaceContext,
)

#: How far downstream to look for critical assets. Two hops covers
#: table → transform → dashboard, which is the shape ZR-008 is written for, and
#: keeps the lineage call inside the hook's latency budget.
DOWNSTREAM_HOPS = 2

#: Dataset URNs end with their environment:
#: `urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.leads,PROD)`
_URN_ENV = re.compile(r",\s*([A-Z][A-Z0-9_]*)\s*\)\s*$")

#: Structured property that may carry an environment when the URN does not.
ENVIRONMENT_PROPERTY_HINTS = ("environment", "env", "zence.environment")

#: The dataset name inside a URN: the middle component of
#: `urn:li:dataset:(urn:li:dataPlatform:snowflake,NAME,ENV)`.
_URN_NAME = re.compile(r"urn:li:dataset:\([^,]+,([^,]+),[^,)]+\)")


def name_from_urn(urn: str | None) -> str | None:
    """The human-readable dataset name carried in a URN.

    DataHub does not always populate `qualifiedName`, and without this a denial
    read "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)
    belongs to BluePeak Health" — technically correct and unreadable at the
    moment somebody is deciding whether to trust the refusal.
    """
    if not urn:
        return None
    match = _URN_NAME.search(urn)
    return match.group(1) if match else None


#: Seconds before a single DataHub call is abandoned. The SDK's default retries
#: with backoff, which takes ~30s to fail — far past a PreToolUse hook's budget,
#: and long enough that a DataHub outage would feel like Claude Code hanging.
#: Retries are disabled for the same reason: the hook is the retry.
DEFAULT_TIMEOUT_SECONDS = 4.0


class DataHubUnavailableError(RuntimeError):
    """The SDK is not installed, or a client could not be constructed."""


class LookupFailure(RuntimeError):
    """A call to DataHub failed in transport.

    Distinct from "the asset is not in the catalog". Collapsing the two would let
    an outage read as a clean catalog, which is the failure mode that turns a
    guardrail into a liability.
    """


def _import_sdk() -> Any:
    """Import the SDK lazily, with a message that says how to fix it.

    `acryl-datahub` is an optional dependency: unit tests, contract tests and the
    website replay all run on fixtures, and requiring a 200 MB install to run the
    test suite would push most contributors away.
    """
    try:
        with warnings.catch_warnings():
            # The new SDK emits an ExperimentalWarning on import. Hooks must keep
            # stdout clean for JSON; warnings go to stderr, but silencing it also
            # keeps `zence doctor` output readable.
            warnings.simplefilter("ignore")
            from datahub import sdk
    except ImportError as exc:  # pragma: no cover - exercised by test_live_provider
        raise DataHubUnavailableError(
            "the DataHub SDK is not installed. Install it with "
            "`uv sync --extra datahub` or `pip install 'acryl-datahub>=1.6.0'`."
        ) from exc
    return sdk


def environment_from_urn(urn: str | None) -> str | None:
    if not urn:
        return None
    match = _URN_ENV.search(urn)
    return match.group(1) if match else None


class LiveProvider(MetadataProvider):
    """Resolves references against a running DataHub instance."""

    kind = ProviderKind.LIVE

    def __init__(
        self,
        server: str,
        token: str | None = None,
        *,
        cache: EvidenceCache | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._server = server
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._cache = cache if cache is not None else EvidenceCache()
        self._client: Any | None = None
        self._client_error: str | None = None
        self._domain_names: dict[str, str | None] = {}

    # --- connection ----------------------------------------------------------

    def _ensure_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._client_error is not None:
            return None

        try:
            sdk = _import_sdk()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from datahub.ingestion.graph.client import (
                    DatahubClientConfig,
                )

                # Explicit timeout and no retries. The SDK defaults to retrying
                # with backoff, which turns an unreachable catalog into a ~30s
                # stall inside a hook that has ~2.5s to answer.
                self._client = sdk.DataHubClient(
                    config=DatahubClientConfig(
                        server=self._server,
                        token=self._token,
                        timeout_sec=self._timeout_seconds,
                        retry_max_times=0,
                    )
                )
        except DataHubUnavailableError as exc:
            self._client_error = str(exc)
            return None
        except Exception as exc:
            self._client_error = f"could not connect to {self._server}: {exc}"
            return None

        return self._client

    def health(self) -> ProviderHealth:
        client = self._ensure_client()
        if client is None:
            return ProviderHealth(
                reachable=False,
                kind=self.kind,
                detail=self._client_error or "no client",
                endpoint=self._server,
            )

        try:
            client.test_connection()
        except Exception as exc:
            return ProviderHealth(
                reachable=False,
                kind=self.kind,
                detail=f"connection test failed: {exc}",
                endpoint=self._server,
            )

        return ProviderHealth(
            reachable=True,
            kind=self.kind,
            detail="connected",
            endpoint=self._server,
            identity=self._identity(client),
        )

    def _identity(self, client: Any) -> str | None:
        """Who Zence is authenticated as. Recorded on write-back."""
        try:
            graph = client._graph
            actor = getattr(graph, "get_actor_urn", None)
            return str(actor()) if callable(actor) else None
        except Exception:
            return None

    # --- resolution ----------------------------------------------------------

    def _find_urn(self, client: Any, ref: AssetRef) -> str | None:
        """Turn a reference into a URN, by search when it is not one already."""
        if ref.resolved_urn:
            return ref.resolved_urn
        if ref.raw_text.startswith("urn:li:"):
            return ref.raw_text

        try:
            urns = list(client.search.get_urns(query=ref.raw_text))
        except Exception as exc:
            # Do NOT return None here. None means "the catalog does not have it",
            # and a connection error is not evidence about the catalog's contents.
            raise LookupFailure(f"search failed: {exc}") from exc

        if not urns:
            return None

        # Prefer an exact tail match on the qualified name. Search is fuzzy, and
        # accepting its first result would let `leads` resolve to whichever
        # client's `leads` table happens to rank highest — the precise mistake
        # Zence exists to prevent.
        wanted = ref.raw_text.strip().lower()
        for urn in urns:
            text = str(urn).lower()
            if f",{wanted}," in text or text.endswith(f",{wanted})"):
                return str(urn)
        return None

    def _downstream_critical(
        self, client: Any, urn: str, workspace: WorkspaceContext
    ) -> tuple[str, ...]:
        if not workspace.critical_downstream:
            return ()

        try:
            results = client.lineage.get_lineage(
                source_urn=urn, direction="downstream", max_hops=DOWNSTREAM_HOPS
            )
        except Exception:
            return ()

        return tuple(
            str(result.urn)
            for result in results
            if str(result.urn) in workspace.critical_downstream
        )

    @staticmethod
    def _urns(values: Any) -> frozenset[str]:
        """Pull URN strings out of whatever shape the SDK returned.

        This exists because of a bug that only a live catalog could reveal.
        `Dataset.tags` does not return URN strings — it returns
        `TagAssociationClass` objects, and `str()` on one gives
        ``TagAssociationClass({'tag': 'urn:li:tag:PII', ...})``. That never
        equals ``urn:li:tag:PII``, so **ZR-001 could not fire against a real
        DataHub**: the cross-client PII denial, the thing this project is for,
        silently did nothing outside of tests.

        Fixtures hid it, because a recording stores plain strings. The lesson is
        in `docs/TEST_STRATEGY.md`; the fix is to read the association's field.

        Each association type names its URN differently — `tag` for tags, `urn`
        for glossary terms, `owner` for ownership — so all three are tried, and
        a plain string still passes through for the fixture path.
        """
        if not values:
            return frozenset()

        found: set[str] = set()
        for value in values:
            if isinstance(value, str):
                found.add(value)
                continue
            for attribute in ("tag", "urn", "owner"):
                candidate = getattr(value, attribute, None)
                if candidate:
                    found.add(str(candidate))
                    break
            else:
                # An unrecognised shape. Better a useless entry the rules will
                # not match than a silently dropped classification.
                found.add(str(value))
        return frozenset(found)

    def _domain_name(self, client: Any, domain_urn: str | None) -> str | None:
        """The domain's display name, for the sentence a human reads.

        The URN is what the boundary is decided on; this is only for the
        message. But "belongs to (no domain)" in a denial reads as though Zence
        did not know why it refused, which undermines the one output that has to
        be convincing.

        Cached per provider: a session touches few domains and this would
        otherwise be a round trip per asset.
        """
        if not domain_urn:
            return None
        if domain_urn in self._domain_names:
            return self._domain_names[domain_urn]

        name: str | None = None
        try:
            from datahub.metadata.schema_classes import DomainPropertiesClass

            aspect = client._graph.get_aspect(
                entity_urn=domain_urn, aspect_type=DomainPropertiesClass
            )
            if aspect is not None:
                name = str(aspect.name)
        except Exception:
            name = None

        self._domain_names[domain_urn] = name
        return name

    def _lifecycle(self, client: Any, urn: str) -> Lifecycle:
        """Deprecation is not surfaced on the SDK entity yet; read the aspect."""
        try:
            from datahub.metadata.schema_classes import DeprecationClass

            aspect = client._graph.get_aspect(entity_urn=urn, aspect_type=DeprecationClass)
        except Exception:
            return Lifecycle.UNKNOWN

        if aspect is None:
            return Lifecycle.ACTIVE
        return Lifecycle.DEPRECATED if aspect.deprecated else Lifecycle.ACTIVE

    def _environment(self, entity: Any, urn: str) -> str | None:
        from_urn = environment_from_urn(urn)
        if from_urn:
            return from_urn

        try:
            properties = dict(entity.structured_properties or {})
        except Exception:
            return None

        for hint in ENVIRONMENT_PROPERTY_HINTS:
            for key, value in properties.items():
                if str(key).lower().endswith(hint):
                    values = value if isinstance(value, list) else [value]
                    if values:
                        return str(values[0]).upper()
        return None

    def _column_tags(self, entity: Any) -> tuple[ColumnTags, ...]:
        try:
            fields = entity.schema
        except Exception:
            return ()

        columns: list[ColumnTags] = []
        for field in fields or []:
            try:
                tags = self._urns(field.tags)
                terms = self._urns(field.terms)
            except Exception:  # noqa: S112 - skipping the field IS the handling
                # One unreadable field must not cost the whole schema. Logging
                # here would write to a stream the hook harness parses as JSON.
                continue
            if tags or terms:
                columns.append(ColumnTags(field_path=str(field.field_path), tags=tags, terms=terms))
        return tuple(columns)

    def _evidence_for(self, client: Any, ref: AssetRef, workspace: WorkspaceContext) -> Evidence:
        urn = self._find_urn(client, ref)
        if urn is None:
            return not_found_evidence(ref, self.kind)

        try:
            entity = client.entities.get(urn)
        except Exception as exc:
            message = str(exc).lower()
            if "not found" in message or "404" in message:
                return not_found_evidence(ref, self.kind)
            return failed_evidence(ref, self.kind, f"entity lookup failed: {exc}")

        def safe(getter: str, default: Any = None) -> Any:
            try:
                return getattr(entity, getter, default)
            except Exception:
                return default

        domain = safe("domain")
        owners = safe("owners") or []

        return Evidence(
            status=EvidenceStatus.RESOLVED,
            provider=self.kind,
            fetched_at=datetime.now(UTC),
            ref=ref,
            urn=str(urn),
            name=str(
                safe("qualified_name")
                or safe("display_name")
                or name_from_urn(str(urn))
                or ref.raw_text
            ),
            domain_urn=str(domain) if domain else None,
            domain_name=self._domain_name(client, str(domain) if domain else None),
            owners=self._urns(owners),
            tags=self._urns(safe("tags")),
            terms=self._urns(safe("terms")),
            column_tags=self._column_tags(entity),
            lifecycle=self._lifecycle(client, str(urn)),
            environment=self._environment(entity, str(urn)),
            downstream_critical=self._downstream_critical(client, str(urn), workspace),
        )

    def resolve(self, refs: Sequence[AssetRef], workspace: WorkspaceContext) -> list[Evidence]:
        client = self._ensure_client()
        if client is None:
            reason = self._client_error or "DataHub is not reachable"
            return [failed_evidence(ref, self.kind, reason) for ref in refs]

        results: list[Evidence] = []
        for ref in refs:
            cached = self._cache.get(ref.resolved_urn or ref.raw_text)
            if cached is not None:
                # Re-attach this reference: the cached evidence was fetched for an
                # equivalent name, but the extractor and columns may differ.
                results.append(cached.model_copy(update={"ref": ref}))
                continue

            try:
                evidence = self._evidence_for(client, ref, workspace)
            except Exception as exc:
                evidence = failed_evidence(ref, self.kind, f"unexpected error: {exc}")

            self._cache.put(ref.resolved_urn or ref.raw_text, evidence)
            results.append(evidence)

        return results

    def close(self) -> None:
        self._client = None
