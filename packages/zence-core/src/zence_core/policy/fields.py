"""The field paths a policy rule may read.

This is an allowlist, deliberately. Resolving `asset.domain_urn` through a
`getattr` chain would let a policy file reach anywhere in the object graph and
would turn a typo into a silent `None` — which, for a `not_in` predicate, reads
as a match and quietly inverts a rule's meaning.

Every path here is explicit, typed, and validated when the policy loads.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from zence_core.schemas import (
    Action,
    Evidence,
    EvidenceStatus,
    WorkspaceContext,
)

#: What a resolver may return. Sets are compared with the `intersects` family;
#: everything else with the scalar operators.
FieldValue = str | int | bool | None | frozenset[str]


@dataclass(frozen=True, slots=True)
class EvalContext:
    """Everything a rule is allowed to see.

    `evidence` is None when the action carried no resolvable asset reference —
    a destructive shell command, for instance. Rules that read `asset.*` simply
    do not fire in that case; see `Rule.references_asset_fields`.
    """

    action: Action
    workspace: WorkspaceContext
    evidence: Evidence | None = None


# --- asset.* -----------------------------------------------------------------


def _asset_in_domain(context: EvalContext) -> FieldValue:
    """Whether the asset sits inside the workspace's client boundary.

    Unresolved evidence is *not* in-domain. This is the single most important
    default in the file: an asset Zence could not classify must never read as
    "belongs to the client I'm working for".
    """
    if context.evidence is None:
        return None
    return context.workspace.is_in_domain(context.evidence.domain_urn)


def _asset_downstream_critical_count(context: EvalContext) -> FieldValue:
    if context.evidence is None:
        return None
    return len(context.evidence.downstream_critical)


ASSET_FIELDS: Mapping[str, Callable[[EvalContext], FieldValue]] = {
    "asset.urn": lambda c: c.evidence.urn if c.evidence else None,
    "asset.name": lambda c: c.evidence.name if c.evidence else None,
    "asset.kind": lambda c: c.evidence.ref.kind.value if c.evidence else None,
    "asset.confidence": lambda c: c.evidence.ref.confidence.value if c.evidence else None,
    "asset.extractor": lambda c: c.evidence.ref.extractor if c.evidence else None,
    "asset.status": lambda c: c.evidence.status.value if c.evidence else None,
    "asset.domain_urn": lambda c: c.evidence.domain_urn if c.evidence else None,
    "asset.domain_name": lambda c: c.evidence.domain_name if c.evidence else None,
    "asset.in_domain": _asset_in_domain,
    "asset.owners": lambda c: c.evidence.owners if c.evidence else None,
    "asset.tags": lambda c: c.evidence.tags if c.evidence else None,
    "asset.all_tags": lambda c: c.evidence.all_tags if c.evidence else None,
    "asset.terms": lambda c: c.evidence.terms if c.evidence else None,
    "asset.all_terms": lambda c: c.evidence.all_terms if c.evidence else None,
    "asset.lifecycle": lambda c: c.evidence.lifecycle.value if c.evidence else None,
    "asset.environment": lambda c: c.evidence.environment if c.evidence else None,
    "asset.downstream_critical_count": _asset_downstream_critical_count,
    "asset.resolved": lambda c: (
        c.evidence.status is EvidenceStatus.RESOLVED if c.evidence else None
    ),
}


# --- action.* ----------------------------------------------------------------

ACTION_FIELDS: Mapping[str, Callable[[EvalContext], FieldValue]] = {
    "action.tool_name": lambda c: c.action.tool_name,
    "action.tool_kind": lambda c: c.action.tool_kind.value,
    "action.hook_event": lambda c: c.action.hook_event,
    "action.intent": lambda c: frozenset(i.value for i in c.action.intents),
    "action.is_sensitive": lambda c: c.action.is_sensitive,
    "action.targets_zence_config": lambda c: c.action.targets_zence_config,
    "action.target_paths": lambda c: frozenset(c.action.target_paths),
}


# --- workspace.* -------------------------------------------------------------

WORKSPACE_FIELDS: Mapping[str, Callable[[EvalContext], FieldValue]] = {
    "workspace.mode": lambda c: c.workspace.mode.value,
    "workspace.active_client": lambda c: c.workspace.active_client,
    "workspace.active_domain": lambda c: c.workspace.active_domain,
    "workspace.allowed_domains": lambda c: c.workspace.allowed_domains,
    "workspace.allowed_environments": lambda c: c.workspace.allowed_environments,
}


FIELDS: Mapping[str, Callable[[EvalContext], FieldValue]] = {
    **ASSET_FIELDS,
    **ACTION_FIELDS,
    **WORKSPACE_FIELDS,
}

#: Fields whose natural type is a set. Used to give a clear validation error when
#: a policy applies a scalar operator to a set, or vice versa.
SET_VALUED_FIELDS: frozenset[str] = frozenset(
    {
        "asset.owners",
        "asset.tags",
        "asset.all_tags",
        "asset.terms",
        "asset.all_terms",
        "action.intent",
        "action.target_paths",
        "workspace.allowed_domains",
        "workspace.allowed_environments",
    }
)


class UnknownFieldError(KeyError):
    """Raised when a policy references a field path that does not exist."""

    def __init__(self, path: str) -> None:
        suggestion = _closest(path)
        hint = f" Did you mean {suggestion!r}?" if suggestion else ""
        super().__init__(
            f"unknown policy field {path!r}.{hint} Available fields: {', '.join(sorted(FIELDS))}"
        )
        self.path = path


def _closest(path: str) -> str | None:
    """Cheap nearest-name hint. A typo in a field path can invert a rule, so it
    is worth spending a little effort making the error actionable."""
    import difflib

    matches = difflib.get_close_matches(path, list(FIELDS), n=1, cutoff=0.75)
    return matches[0] if matches else None


def resolve(path: str, context: EvalContext) -> FieldValue:
    """Read one allowlisted field from the evaluation context."""
    resolver = FIELDS.get(path)
    if resolver is None:
        raise UnknownFieldError(path)
    return resolver(context)
