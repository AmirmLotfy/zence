"""The Claude Code hook wire format.

Every field here is taken from the published hooks reference, not from memory.
The shapes that matter:

**Input** arrives as JSON on stdin with `hook_event_name`, `session_id`, `cwd`,
`permission_mode`, and for tool events `tool_name`, `tool_input`, `tool_use_id`.

**Output** is JSON on stdout with exit code 0. For `PreToolUse` the decision goes
in `hookSpecificOutput.permissionDecision`, one of `allow` / `deny` / `ask` /
`defer`, with `permissionDecisionReason` required for a deny.

Exit code 2 also blocks, using stderr as the reason. Zence never uses it: the
JSON form carries `additionalContext` as well, which is how Claude learns what
the safe alternative is instead of simply being refused.

The invariant this module exists to guarantee: **stdout is always exactly one
JSON object.** A hook that prints a stray warning, a traceback, or nothing at all
either breaks the session or is silently ignored — and a security control that
gets silently ignored is worse than none, because the user believes it ran.
"""

from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zence_core.schemas import Decision, Verdict

#: Claude Code's permission decisions. `defer` hands the call back to the normal
#: permission flow; Zence uses it for nothing today but the value is accepted so
#: a policy can grow into it.
PERMISSION_ALLOW = "allow"
PERMISSION_DENY = "deny"
PERMISSION_ASK = "ask"

_VERDICT_TO_PERMISSION = {
    Verdict.ALLOW: PERMISSION_ALLOW,
    Verdict.ASK: PERMISSION_ASK,
    Verdict.DENY: PERMISSION_DENY,
}


@dataclass(frozen=True, slots=True)
class HookInput:
    """A parsed hook payload.

    Unknown fields are kept in `raw`. Claude Code adds fields over time, and a
    hook that rejected an unfamiliar payload would break on the next release.
    """

    hook_event_name: str
    session_id: str
    cwd: str
    raw: dict[str, Any] = field(default_factory=dict)

    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_use_id: str | None = None
    permission_mode: str = "default"
    prompt: str = ""
    transcript_path: str | None = None

    @classmethod
    def parse(cls, payload: Any) -> HookInput:
        """Build from an already-decoded payload, tolerating almost anything.

        Malformed input must not raise. The caller is a hook whose only job in
        that situation is to emit a valid fail-safe response.
        """
        data = payload if isinstance(payload, dict) else {}

        tool_input = data.get("tool_input")
        if not isinstance(tool_input, dict):
            tool_input = {}

        return cls(
            hook_event_name=str(data.get("hook_event_name", "") or ""),
            session_id=str(data.get("session_id", "") or ""),
            cwd=str(data.get("cwd", "") or ""),
            raw=data,
            tool_name=str(data.get("tool_name", "") or ""),
            tool_input=tool_input,
            tool_use_id=(str(data["tool_use_id"]) if data.get("tool_use_id") is not None else None),
            permission_mode=str(data.get("permission_mode", "default") or "default"),
            prompt=str(data.get("prompt", "") or ""),
            transcript_path=(str(data["transcript_path"]) if data.get("transcript_path") else None),
        )

    @classmethod
    def read(cls, stream: Any = None) -> HookInput:
        """Read and parse stdin. Never raises."""
        source = stream if stream is not None else sys.stdin
        try:
            text = source.read()
        except Exception:
            return cls.parse(None)

        try:
            return cls.parse(json.loads(text))
        except (json.JSONDecodeError, TypeError, ValueError):
            return cls.parse(None)

    @property
    def workspace_root(self) -> Path:
        """The directory the session is running in.

        Falls back to the process working directory when `cwd` is absent, which
        happens in hand-constructed payloads and some older event shapes.
        """
        return Path(self.cwd) if self.cwd else Path.cwd()


def _base_output(
    *,
    system_message: str | None = None,
    suppress_output: bool = False,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    if system_message:
        output["systemMessage"] = system_message
    if suppress_output:
        output["suppressOutput"] = True
    return output


def pre_tool_use_output(
    decision: Decision,
    *,
    reason: str | None = None,
    additional_context: str | None = None,
) -> dict[str, Any]:
    """The PreToolUse response for a decision.

    `permissionDecisionReason` is what the user sees. `additionalContext` is what
    Claude sees — and carrying the remediation there is what turns a refusal into
    a redirect: the model learns which in-domain asset to use instead, rather
    than simply being told no and trying a variation.
    """
    output = _base_output()
    output["hookSpecificOutput"] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": _VERDICT_TO_PERMISSION[decision.verdict],
        "permissionDecisionReason": reason or decision.reason,
    }

    context = additional_context
    if context:
        output["hookSpecificOutput"]["additionalContext"] = context

    return output


def session_start_output(
    *,
    additional_context: str | None = None,
    session_title: str | None = None,
    watch_paths: list[str] | None = None,
) -> dict[str, Any]:
    output = _base_output()
    specific: dict[str, Any] = {"hookEventName": "SessionStart"}

    if additional_context:
        specific["additionalContext"] = additional_context
    if session_title:
        specific["sessionTitle"] = session_title
    if watch_paths:
        # Claude Code re-runs SessionStart when a watched file changes, so a
        # policy edit made outside the session is picked up on the next turn.
        specific["watchPaths"] = watch_paths

    output["hookSpecificOutput"] = specific
    return output


def user_prompt_submit_output(
    *,
    additional_context: str | None = None,
    block_reason: str | None = None,
) -> dict[str, Any]:
    output = _base_output()
    if block_reason:
        output["decision"] = "block"
        output["reason"] = block_reason

    specific: dict[str, Any] = {"hookEventName": "UserPromptSubmit"}
    if additional_context:
        specific["additionalContext"] = additional_context
    output["hookSpecificOutput"] = specific
    return output


def post_tool_use_output(*, additional_context: str | None = None) -> dict[str, Any]:
    output = _base_output()
    specific: dict[str, Any] = {"hookEventName": "PostToolUse"}
    if additional_context:
        specific["additionalContext"] = additional_context
    output["hookSpecificOutput"] = specific
    return output


def stop_output(*, additional_context: str | None = None) -> dict[str, Any]:
    output = _base_output(suppress_output=True)
    specific: dict[str, Any] = {"hookEventName": "Stop"}
    if additional_context:
        specific["additionalContext"] = additional_context
    output["hookSpecificOutput"] = specific
    return output


def empty_output() -> dict[str, Any]:
    """A valid no-op response.

    Returned when a hook has nothing to say. Deliberately an empty object rather
    than no output at all, so the harness always parses something.
    """
    return {}


def emit(output: dict[str, Any], stream: Any = None) -> None:
    """Write exactly one JSON object to stdout.

    `default=str` because a stray datetime or enum in a response should degrade
    to a readable string, not raise inside the hook and produce no output at all.
    """
    target = stream if stream is not None else sys.stdout
    try:
        target.write(json.dumps(output, default=str))
        target.flush()
    except Exception:
        # Last resort. If even serialization failed, an empty object still keeps
        # the session running. Nothing is logged here on purpose: the only
        # streams available are the ones Claude Code is parsing, and writing a
        # diagnostic into them would corrupt the very output this is rescuing.
        with contextlib.suppress(Exception):
            target.write("{}")
            target.flush()
