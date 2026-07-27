"""What each hook event does.

Every handler returns a plain dict. None of them touch stdout, exit, or raise on
purpose — `main.run` owns all three, so that a bug in any single handler degrades
into a fail-safe response instead of a broken session.
"""

from __future__ import annotations

from pathlib import Path

from zence_core.extract import normalize
from zence_core.hooks.context import (
    NotGovernedError,
    ZenceContext,
    load_context,
)
from zence_core.hooks.protocol import (
    HookInput,
    empty_output,
    post_tool_use_output,
    pre_tool_use_output,
    session_start_output,
    stop_output,
    user_prompt_submit_output,
)
from zence_core.policy import evaluate
from zence_core.schemas import Decision, Verdict

#: Phrases in a prompt that describe intent, not assets. They add context for
#: Claude; they never produce a decision on their own. Claiming an asset
#: violation from prompt text alone would be guessing, and a guess that blocks is
#: a false deny.
_INTENT_HINTS: tuple[tuple[str, str], ...] = (
    ("production", "This mentions production."),
    ("prod ", "This mentions production."),
    ("drop table", "This describes a destructive operation."),
    ("truncate", "This describes a destructive operation."),
    ("delete from", "This describes a destructive operation."),
    ("pii", "This mentions personal data."),
    ("personal data", "This mentions personal data."),
)


def _quote(text: str) -> str:
    """Render untrusted text as an inert, single-line quotation.

    Domain names, asset names and owners come from DataHub, which is data — not
    instructions. Newlines are collapsed so a crafted description cannot open a
    new section in the context block and address the model directly.
    """
    flattened = " ".join(str(text).split())
    return flattened[:200]


def boundary_context(context: ZenceContext) -> str:
    """The text injected at SessionStart.

    Deliberately short. This is prepended to every turn's context, so it earns
    its tokens by stating only what changes Claude's behaviour: which client is
    in scope, which environments, and what will be refused.
    """
    workspace = context.workspace
    domains = ", ".join(sorted(_quote(d) for d in workspace.allowed_domains)) or "(none)"
    environments = ", ".join(sorted(workspace.allowed_environments)) or "(none)"

    lines = [
        "## Zence — active data boundary",
        "",
        f"This workspace is scoped to **{_quote(workspace.active_client)}**.",
        "",
        f"- Permitted DataHub domain(s): {domains}",
        f"- Permitted environment(s): {environments}",
        f"- Enforcement mode: {workspace.mode.value}",
        f"- Policy version: {workspace.policy_version}",
        "",
        "Data operations are checked against DataHub before they run. Assets "
        "belonging to another client, production mutations, and changes with "
        "critical downstream impact will be refused or sent for approval, with "
        "the reason and a safe alternative.",
        "",
        "Prefer assets inside this client's domain. If an operation is refused, "
        "read the reason rather than retrying a variation of the same call.",
    ]
    return "\n".join(lines)


def _decision_context(decision: Decision) -> str:
    """What Claude is told alongside a decision.

    The remediation is the point. A bare refusal invites the model to try a
    slight variation of the same call; naming the in-domain alternative turns the
    refusal into a redirect.
    """
    # Naive `verdict + "ed"` produced "denyed". English past tenses are worth
    # spelling out for text a user reads on every refusal.
    phrasing = {
        Verdict.ALLOW: "allowed this operation",
        Verdict.ASK: "is asking you to approve this operation",
        Verdict.DENY: "denied this operation",
    }[decision.verdict]

    parts = [f"Zence {phrasing} ({decision.rule_id})."]
    parts.append(decision.reason)

    if decision.remediation:
        parts.append(f"Suggested next step: {decision.remediation}")
    if decision.evidence_urns:
        parts.append("Evidence: " + ", ".join(decision.evidence_urns))
    if decision.degraded:
        parts.append(
            "Note: this decision was made with incomplete metadata because "
            "DataHub could not be reached."
        )
    if decision.verdict is Verdict.DENY:
        parts.append(
            "Do not retry this call in a modified form. Choose an in-boundary "
            "asset or ask the user how to proceed."
        )
    return "\n\n".join(parts)


# --- SessionStart ------------------------------------------------------------


def handle_session_start(payload: HookInput) -> dict[str, object]:
    try:
        context = load_context(payload.workspace_root)
    except NotGovernedError:
        # Not every repository is governed. Saying nothing is correct.
        return empty_output()
    except Exception as exc:
        # A workspace with a broken policy is a workspace that is not protected,
        # and the user needs to know that rather than assume it is working.
        return session_start_output(
            additional_context=(
                "## Zence\n\nZence is installed but its policy failed to load, so "
                f"no data boundary is being enforced in this session.\n\nError: {exc}\n\n"
                "Run `zence policy validate` to see the problem."
            )
        )

    return session_start_output(
        additional_context=boundary_context(context),
        session_title=f"{context.workspace.active_client} — {context.root.name}",
        watch_paths=context.watch_paths,
    )


# --- UserPromptSubmit --------------------------------------------------------


def handle_user_prompt_submit(payload: HookInput) -> dict[str, object]:
    """Classify intent only.

    This hook never blocks on the basis of an asset claim. It sees a sentence,
    not a resolved URN, and a rule that fired on prose would produce false denies
    on the first ambiguous phrasing. Asset decisions belong to PreToolUse, where
    there is DataHub evidence to reason from.
    """
    prompt = payload.prompt.lower()
    if not prompt:
        return empty_output()

    seen: list[str] = []
    for needle, note in _INTENT_HINTS:
        if needle in prompt and note not in seen:
            seen.append(note)

    if not seen:
        return empty_output()

    return user_prompt_submit_output(
        additional_context=(
            "Zence: " + " ".join(seen) + " Any data operation will still be checked "
            "against DataHub before it runs."
        )
    )


# --- PreToolUse --------------------------------------------------------------


def handle_pre_tool_use(payload: HookInput) -> dict[str, object]:
    try:
        context = load_context(payload.workspace_root)
    except NotGovernedError:
        return empty_output()

    normalized = normalize(
        payload.tool_name,
        payload.tool_input,
        context.root,
        hook_event="PreToolUse",
        tool_use_id=payload.tool_use_id,
    )

    evidences = context.provider.resolve(normalized.refs, context.workspace)
    decision = evaluate(normalized.action, evidences, context.workspace, context.policy)

    if decision.verdict is Verdict.ALLOW and not decision.degraded:
        # Nothing to say. Returning an empty object keeps the transcript clean
        # and leaves the normal permission flow untouched.
        return empty_output()

    return pre_tool_use_output(
        decision,
        additional_context=_decision_context(decision),
    )


# --- PostToolUse / PostToolUseFailure ----------------------------------------


def handle_post_tool_use(payload: HookInput) -> dict[str, object]:
    """Record the outcome.

    Persistence lands in Phase 8; until then this is a well-formed no-op so the
    hook wiring can be tested end to end without pretending an audit trail exists.
    """
    return post_tool_use_output()


def handle_post_tool_use_failure(payload: HookInput) -> dict[str, object]:
    return empty_output()


# --- Stop / SessionEnd -------------------------------------------------------


def handle_stop(payload: HookInput) -> dict[str, object]:
    """Finalize the session.

    Write-back lands in Phase 8. Returning a valid empty response now keeps the
    contract stable so the plugin manifest does not change later.
    """
    return stop_output()


def handle_session_end(payload: HookInput) -> dict[str, object]:
    return empty_output()


HANDLERS = {
    "SessionStart": handle_session_start,
    "UserPromptSubmit": handle_user_prompt_submit,
    "PreToolUse": handle_pre_tool_use,
    "PostToolUse": handle_post_tool_use,
    "PostToolUseFailure": handle_post_tool_use_failure,
    "Stop": handle_stop,
    "SessionEnd": handle_session_end,
}


def workspace_is_governed(cwd: Path) -> bool:
    from zence_core.hooks.context import find_workspace_root

    return find_workspace_root(cwd) is not None
