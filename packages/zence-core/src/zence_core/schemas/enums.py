"""Enumerations shared across Zence's schemas.

Every enum here is part of the audit record and the policy file format, so the
string values are a compatibility surface. Renaming a value is a breaking change
to `policy_version`.
"""

from __future__ import annotations

from enum import StrEnum


class Verdict(StrEnum):
    """The only three outcomes Zence can produce.

    These map onto Claude Code's `permissionDecision` values exactly. There is no
    fourth state: an evaluation that cannot reach a conclusion resolves to ASK,
    never to "unknown".
    """

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class Risk(StrEnum):
    """Severity of the operation being evaluated, independent of the verdict.

    Risk describes the operation; the verdict describes what Zence did about it.
    A high-risk operation can still be ALLOW when it is in-bounds and approved.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolKind(StrEnum):
    """Normalized classification of the intercepted Claude Code tool call."""

    MCP_CATALOG = "mcp_catalog"
    """A DataHub MCP server tool — the catalog surface Zence intercepts."""

    SHELL = "shell"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    PROMPT = "prompt"
    OTHER = "other"


class Intent(StrEnum):
    """What the action is trying to do.

    An action may carry several intents at once: editing a dbt model that drops a
    table is both WRITE and DESTRUCTIVE.
    """

    READ = "read"
    SEARCH = "search"
    CODEGEN = "codegen"
    WRITE = "write"
    MUTATE = "mutate"
    """Mutating *metadata* — a DataHub tag, term, owner, or description change."""

    DESTRUCTIVE = "destructive"
    """DROP, TRUNCATE, DELETE without predicate, rm -rf, and friends."""

    UNKNOWN = "unknown"


#: Intents that make an operation "sensitive" for the fail-safe matrix. When
#: metadata cannot be resolved, an action carrying any of these must never be
#: allowed by default.
SENSITIVE_INTENTS: frozenset[Intent] = frozenset({Intent.WRITE, Intent.MUTATE, Intent.DESTRUCTIVE})


class AssetKind(StrEnum):
    """What sort of thing an extracted reference points at."""

    DATASET = "dataset"
    COLUMN = "column"
    DASHBOARD = "dashboard"
    URN = "urn"
    PATH = "path"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    """How sure the extractor is that this reference is real.

    Ordered. Rules can require a minimum confidence so that a MEDIUM-confidence
    guess from a shell command does not trigger the same response as an exact URN.
    """

    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Ascending severity order for comparisons. Higher index == less certain.
CONFIDENCE_ORDER: tuple[Confidence, ...] = (
    Confidence.EXACT,
    Confidence.HIGH,
    Confidence.MEDIUM,
    Confidence.LOW,
)


class EvidenceStatus(StrEnum):
    """Why a piece of evidence looks the way it does.

    The distinction between NOT_FOUND and LOOKUP_FAILED is load-bearing:
    "DataHub says this asset does not exist" and "Zence could not reach DataHub"
    lead to different decisions. Collapsing them would let an outage read as a
    clean catalog.
    """

    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    LOOKUP_FAILED = "lookup_failed"


class Lifecycle(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    UNKNOWN = "unknown"


class ProviderKind(StrEnum):
    """Where evidence came from.

    This is recorded on every decision and is never inferred. A fixture must
    never be able to present itself as a live catalog read.
    """

    LIVE = "live"
    FIXTURE = "fixture"


class Mode(StrEnum):
    """Enforcement posture."""

    AUDIT = "audit"
    """Evaluate and record everything; downgrade every block to a warning."""

    ENFORCE = "enforce"
    """Allow, ask, and deny for real."""

    DEMO = "demo"
    """Same engine and same hook path as ENFORCE, against synthetic metadata."""
