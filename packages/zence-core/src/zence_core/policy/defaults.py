"""The fail-safe matrix — what Zence does when no rule matched.

This file is the answer to "what happens when something goes wrong", and it is
the part of the engine most worth reading carefully. Rules describe the cases
someone anticipated. This describes everything else.

The governing principle: **Zence never converts ignorance into permission.** If a
lookup failed, if a reference could not be resolved, if an asset turned out to
sit outside the client boundary and no rule happened to cover it — the answer is
ASK, not ALLOW. A degraded ALLOW is only ever returned for actions that touched
no data references at all, and it says so out loud.
"""

from __future__ import annotations

from collections.abc import Sequence

from zence_core.schemas import (
    Action,
    Decision,
    DecisionSource,
    Evidence,
    EvidenceStatus,
    Mode,
    ProviderKind,
    Risk,
    Verdict,
    WorkspaceContext,
)

DEFAULT_RULE_ID = "ZR-000"


def _provider_of(evidences: Sequence[Evidence]) -> ProviderKind | None:
    """The provider that produced this evidence.

    Mixed providers should be impossible — one provider serves one evaluation —
    but if it ever happens, report nothing rather than report a comforting lie.
    """
    providers = {evidence.provider for evidence in evidences}
    if len(providers) == 1:
        return next(iter(providers))
    return None


def safe_default(
    action: Action,
    evidences: Sequence[Evidence],
    workspace: WorkspaceContext,
    policy_version: str,
) -> Decision:
    """Decide when no rule fired."""
    failed = [e for e in evidences if e.status is EvidenceStatus.LOOKUP_FAILED]
    missing = [e for e in evidences if e.status is EvidenceStatus.NOT_FOUND]
    resolved = [e for e in evidences if e.status is EvidenceStatus.RESOLVED]

    out_of_domain = [e for e in resolved if not workspace.is_in_domain(e.domain_urn)]

    common = {
        "policy_version": policy_version,
        "mode": workspace.mode,
        "provider": _provider_of(evidences),
        "evidence_urns": tuple(e.urn for e in evidences if e.urn),
    }

    # 1. Zence could not see. The most dangerous state to get wrong.
    if failed:
        reasons = sorted({e.failure_reason or "lookup failed" for e in failed})
        detail = "; ".join(reasons)

        if evidences or action.is_sensitive:
            return Decision(
                verdict=Verdict.ASK,
                source=DecisionSource.SAFE_DEFAULT,
                risk=Risk.HIGH,
                rule_id=DEFAULT_RULE_ID,
                rule_title="Metadata unavailable for a data operation",
                reason=(
                    f"Zence could not reach DataHub to check "
                    f"{len(evidences)} referenced asset(s), so it cannot confirm this "
                    f"stays inside {workspace.active_client}. Reason: {detail}."
                ),
                remediation=(
                    "Confirm DataHub is reachable (`zence doctor`), then retry. "
                    "Approve only if you already know this asset is in-bounds."
                ),
                degraded=True,
                degraded_reason=detail,
                **common,  # type: ignore[arg-type]
            )

        return Decision(
            verdict=Verdict.ALLOW,
            source=DecisionSource.SAFE_DEFAULT,
            risk=Risk.LOW,
            rule_id=DEFAULT_RULE_ID,
            rule_title="Local operation, catalog unavailable",
            reason=(
                "No data assets referenced. Allowed, but DataHub is unreachable so "
                "Zence is not currently able to check asset boundaries."
            ),
            degraded=True,
            degraded_reason=detail,
            **common,  # type: ignore[arg-type]
        )

    # 2. Named something the catalog does not know, while doing something risky.
    if missing and action.is_sensitive:
        names = ", ".join(sorted({e.ref.raw_text for e in missing})[:5])
        return Decision(
            verdict=Verdict.ASK,
            source=DecisionSource.SAFE_DEFAULT,
            risk=Risk.MEDIUM,
            rule_id=DEFAULT_RULE_ID,
            rule_title="Unrecognized asset in a write operation",
            reason=(
                f"{names} could not be found in DataHub, and this operation writes "
                "or mutates data. Zence cannot confirm which client it belongs to."
            ),
            remediation=(
                "Check the identifier, or register the asset in DataHub so future "
                "operations can be evaluated automatically."
            ),
            **common,  # type: ignore[arg-type]
        )

    # 3. Resolved cleanly, but outside the boundary and no rule covered it.
    if out_of_domain:
        first = out_of_domain[0]
        return Decision(
            verdict=Verdict.ASK,
            source=DecisionSource.SAFE_DEFAULT,
            risk=Risk.HIGH,
            rule_id=DEFAULT_RULE_ID,
            rule_title="Asset outside the active client boundary",
            reason=(
                f"{first.name or first.ref.raw_text} belongs to "
                f"{first.domain_name or 'another domain'}, but this session is "
                f"bounded to {workspace.active_client}."
            ),
            remediation=(
                f"Use an asset inside {workspace.active_client}, or switch workspace "
                "if you intended to work on the other client."
            ),
            **common,  # type: ignore[arg-type]
        )

    # 4. Nothing referenced, nothing sensitive.
    if not evidences and not action.is_sensitive:
        return Decision(
            verdict=Verdict.ALLOW,
            source=DecisionSource.SAFE_DEFAULT,
            risk=Risk.NONE,
            rule_id=DEFAULT_RULE_ID,
            rule_title="No data assets referenced",
            reason="No DataHub assets referenced and no write or destructive intent.",
            **common,  # type: ignore[arg-type]
        )

    # 5a. A sensitive action that named no catalog asset at all — `rm -rf build/`,
    # a local script, a migration file. Saying "all 0 assets resolve inside the
    # client" would be a true sentence that means nothing.
    if not resolved:
        return Decision(
            verdict=Verdict.ALLOW,
            source=DecisionSource.SAFE_DEFAULT,
            risk=Risk.LOW,
            rule_id=DEFAULT_RULE_ID,
            rule_title="No catalog assets involved",
            reason=(
                "This operation references no assets known to DataHub, so there is "
                "no client boundary for it to cross. Zence does not govern local "
                "files or infrastructure."
            ),
            **common,  # type: ignore[arg-type]
        )

    # 5b. Everything resolved, in-domain, no rule objected.
    return Decision(
        verdict=Verdict.ALLOW,
        source=DecisionSource.SAFE_DEFAULT,
        risk=Risk.LOW,
        rule_id=DEFAULT_RULE_ID,
        rule_title="In-boundary operation",
        reason=(
            f"All {len(resolved)} referenced asset(s) resolve inside "
            f"{workspace.active_client} and no rule objected."
        ),
        **common,  # type: ignore[arg-type]
    )


def apply_mode(decision: Decision) -> Decision:
    """Downgrade blocking verdicts in audit mode.

    Audit mode must never silently drop a finding: the original verdict is kept in
    `would_have_been` so `zence audit` can report exactly what enforce mode would
    have stopped.
    """
    if decision.mode is not Mode.AUDIT:
        return decision
    if decision.verdict is Verdict.ALLOW:
        return decision

    return decision.model_copy(
        update={
            "verdict": Verdict.ALLOW,
            "source": DecisionSource.MODE_DOWNGRADE,
            "would_have_been": decision.verdict,
            "notes": (
                *decision.notes,
                f"audit mode: enforce would have returned {decision.verdict.value}",
            ),
        }
    )
