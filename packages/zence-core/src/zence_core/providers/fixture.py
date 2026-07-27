"""Replays evidence recorded from a real DataHub instance.

Used by unit tests, hook contract tests, CI, and the website replay. It exists so
that the great majority of Zence can be developed and verified without an 8 GB
catalog running — but it is never a stand-in for a live connection at runtime.

Fixtures are **recorded, not authored**. `zence demo record` captures real
responses from a seeded instance and writes them here, and the file carries the
endpoint, DataHub version and timestamp it came from. A hand-written fixture
would encode what the author assumed DataHub returns, which is precisely the
thing worth testing against reality.

Every `Evidence` this returns is stamped `ProviderKind.FIXTURE`, and that value
travels into the decision and the audit record.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zence_core.providers.base import (
    MetadataProvider,
    ProviderHealth,
    not_found_evidence,
)
from zence_core.schemas import (
    AssetRef,
    ColumnTags,
    Evidence,
    EvidenceStatus,
    Lifecycle,
    ProviderKind,
    WorkspaceContext,
)

FIXTURE_SCHEMA_VERSION = 1


class FixtureError(ValueError):
    """A fixture file is missing, malformed, or not a recording."""


def _parse_column_tags(raw: Any) -> tuple[ColumnTags, ...]:
    if not isinstance(raw, list):
        return ()
    columns: list[ColumnTags] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        columns.append(
            ColumnTags(
                field_path=str(item.get("field_path", "")),
                tags=frozenset(item.get("tags", []) or []),
                terms=frozenset(item.get("terms", []) or []),
            )
        )
    return tuple(columns)


class FixtureProvider(MetadataProvider):
    """Resolves references from a recorded snapshot."""

    kind = ProviderKind.FIXTURE

    def __init__(self, entities: dict[str, dict[str, Any]], *, meta: dict[str, Any]) -> None:
        # Indexed by both name and URN, lowercased, so a reference resolves the
        # same way whether the extractor produced a table name or a full URN.
        self._entities: dict[str, dict[str, Any]] = {}
        for key, payload in entities.items():
            self._entities[key.strip().lower()] = payload
            urn = payload.get("urn")
            if isinstance(urn, str):
                self._entities[urn.strip().lower()] = payload

        self._meta = meta

    # --- construction --------------------------------------------------------

    @classmethod
    def from_file(cls, path: Path) -> FixtureProvider:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise FixtureError(f"cannot read fixture {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FixtureError(f"fixture {path} is not valid JSON: {exc}") from exc

        return cls.from_dict(raw, origin=str(path))

    @classmethod
    def from_dict(cls, raw: Any, origin: str = "<dict>") -> FixtureProvider:
        if not isinstance(raw, dict):
            raise FixtureError(f"{origin}: expected an object at the top level")

        version = raw.get("schema_version")
        if version != FIXTURE_SCHEMA_VERSION:
            raise FixtureError(
                f"{origin}: fixture schema version {version!r}, expected "
                f"{FIXTURE_SCHEMA_VERSION}. Re-record with `zence demo record`."
            )

        # A recording says where it came from. Without that provenance there is
        # no way to tell a captured response from an invented one.
        for required in ("recorded_at", "source_endpoint"):
            if not raw.get(required):
                raise FixtureError(
                    f"{origin}: missing {required!r}. Fixtures must be recorded "
                    "from a real instance, not written by hand."
                )

        entities = raw.get("entities")
        if not isinstance(entities, dict):
            raise FixtureError(f"{origin}: `entities` must be an object")

        meta = {key: value for key, value in raw.items() if key != "entities"}
        return cls(entities, meta=meta)

    # --- resolution ----------------------------------------------------------

    def _evidence_from(self, ref: AssetRef, payload: dict[str, Any]) -> Evidence:
        return Evidence(
            status=EvidenceStatus.RESOLVED,
            provider=self.kind,
            fetched_at=datetime.now(UTC),
            ref=ref,
            urn=payload.get("urn"),
            name=payload.get("name"),
            domain_urn=payload.get("domain_urn"),
            domain_name=payload.get("domain_name"),
            owners=frozenset(payload.get("owners", []) or []),
            tags=frozenset(payload.get("tags", []) or []),
            terms=frozenset(payload.get("terms", []) or []),
            column_tags=_parse_column_tags(payload.get("column_tags")),
            lifecycle=Lifecycle(payload.get("lifecycle", "unknown")),
            environment=payload.get("environment"),
            downstream_critical=tuple(payload.get("downstream_critical", []) or []),
        )

    def resolve(self, refs: Sequence[AssetRef], workspace: WorkspaceContext) -> list[Evidence]:
        results: list[Evidence] = []
        for ref in refs:
            key = (ref.resolved_urn or ref.raw_text).strip().lower()
            payload = self._entities.get(key) or self._entities.get(ref.raw_text.strip().lower())

            if payload is None:
                results.append(not_found_evidence(ref, self.kind))
                continue

            evidence = self._evidence_from(ref, payload)

            # Downstream criticality is workspace-relative: a dashboard only
            # matters if *this* workspace declared it critical. Recording it
            # absolutely would bake one workspace's opinion into the fixture.
            if workspace.critical_downstream:
                evidence = evidence.model_copy(
                    update={
                        "downstream_critical": tuple(
                            urn
                            for urn in evidence.downstream_critical
                            if urn in workspace.critical_downstream
                        )
                    }
                )

            results.append(evidence)
        return results

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            reachable=True,
            kind=self.kind,
            detail=(
                f"recorded {self._meta.get('recorded_at')} from "
                f"{self._meta.get('source_endpoint')}"
                + (
                    f" (DataHub {self._meta['datahub_version']})"
                    if self._meta.get("datahub_version")
                    else ""
                )
            ),
            endpoint=self._meta.get("source_endpoint"),
        )

    @property
    def recorded_at(self) -> str | None:
        recorded = self._meta.get("recorded_at")
        return str(recorded) if recorded else None
