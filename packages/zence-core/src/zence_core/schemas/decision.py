"""The output of an evaluation.

A Decision is what the hook returns to Claude Code, what the audit log stores,
and what gets written back to DataHub. It carries not just the verdict but the
reasoning: which rule fired, what evidence it saw, and whether Zence was working
with degraded information at the time.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from zence_core.schemas.enums import Mode, ProviderKind, Risk, Verdict


class DecisionSource(StrEnum):
    """Why this verdict was reached. Distinct from *which* rule."""

    TAMPER = "tamper"
    """Zence's own configuration was the target. Evaluated before anything else."""

    RULE = "rule"
    EXCEPTION = "exception"
    """An ASK was downgraded to ALLOW by an active, unexpired exception."""

    SAFE_DEFAULT = "safe_default"
    """No rule matched. The fail-safe matrix decided."""

    MODE_DOWNGRADE = "mode_downgrade"
    """Audit mode turned a would-be block into a recorded warning."""


class Decision(BaseModel):
    """One verdict, with the reasoning that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    source: DecisionSource
    risk: Risk

    rule_id: str
    rule_title: str
    policy_version: str
    mode: Mode

    reason: str
    """Rendered, human-readable, and shown to the user. Never contains secrets or
    raw payloads."""

    remediation: str | None = None

    evidence_urns: tuple[str, ...] = ()
    matched_tags: frozenset[str] = frozenset()
    matched_terms: frozenset[str] = frozenset()
    matched_columns: tuple[str, ...] = ()
    downstream_critical: tuple[str, ...] = ()

    provider: ProviderKind | None = None
    """Where the evidence came from. `None` when no lookup was attempted."""

    degraded: bool = False
    """True when at least one lookup failed. A degraded ALLOW is always
    accompanied by a warning — Zence says when it was working blind."""

    degraded_reason: str | None = None

    exception_applied: str | None = None
    """Rule id whose ASK was waived, when source is EXCEPTION."""

    would_have_been: Verdict | None = None
    """In audit mode, the verdict enforce mode would have produced."""

    notes: tuple[str, ...] = Field(default_factory=tuple)

    @property
    def blocks(self) -> bool:
        return self.verdict is Verdict.DENY

    @property
    def needs_human(self) -> bool:
        return self.verdict is Verdict.ASK

    def summary_line(self) -> str:
        """One-line form used in terminal audit output."""
        mark = {Verdict.ALLOW: "✓", Verdict.ASK: "?", Verdict.DENY: "✗"}[self.verdict]
        return f"{mark} {self.verdict.value:5} {self.rule_id:8} {self.rule_title}"
