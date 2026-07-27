"""The hook entry point, and the guarantee that it always answers.

`run` is what `zence-hook <Event>` executes. Its whole job is to make sure that
whatever happens inside a handler, Claude Code receives exactly one valid JSON
object and a zero exit code.

Three things can go wrong, and each has an explicit answer:

* **The handler raises.** Caught here, converted to a fail-safe decision.
* **The handler hangs.** A watchdog fires before Claude Code's own timeout, so
  the decision is *ours* rather than an absent response. This matters: a hook
  that times out produces no output, and no output means the normal permission
  flow proceeds — a silent allow, arrived at by accident.
* **Serialization fails.** `emit` falls back to `{}`.

The fail-safe verdict depends on what the tool could do. A crash while checking
`Bash` or a catalog mutation returns `ask`; a crash while checking a local file
read returns nothing and lets the normal flow continue. Failing closed on
everything would make a Zence bug indistinguishable from a policy violation and
train users to bypass it.
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from zence_core.hooks.handlers import HANDLERS
from zence_core.hooks.protocol import HookInput, emit, empty_output

#: Fires before Claude Code's own limit so the timeout produces a decision rather
#: than silence. UserPromptSubmit's harness budget is 30s; tool events get 600s
#: but Zence targets a fraction of that — see docs/CLAUDE_CODE_PLUGIN.md.
DEFAULT_DEADLINE_SECONDS = 8.0
PROMPT_DEADLINE_SECONDS = 4.0

#: Tools where a Zence failure must not silently permit the call.
_SENSITIVE_TOOL_MARKERS = ("bash", "write", "edit", "notebook")


class HookTimeout(RuntimeError):
    """The handler exceeded its own deadline."""


@contextmanager
def _deadline(seconds: float) -> Iterator[None]:
    """Raise `HookTimeout` inside the handler after `seconds`.

    SIGALRM is POSIX-only, which matches Zence's stated macOS + Linux support.
    Where it is unavailable the block runs unbounded and Claude Code's own
    timeout remains the backstop.
    """
    if not hasattr(signal, "SIGALRM"):  # pragma: no cover - Windows
        yield
        return

    def _fire(signum: int, frame: Any) -> None:
        raise HookTimeout(f"exceeded {seconds:.0f}s")

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _is_sensitive(payload: HookInput) -> bool:
    """Whether a failure here could let something consequential through."""
    name = payload.tool_name.lower()
    if any(marker in name for marker in _SENSITIVE_TOOL_MARKERS):
        return True
    # Any DataHub MCP call: a mutation tool could reclassify another client's
    # assets, and a read could pull them into context.
    return "datahub" in name


def fail_safe_output(payload: HookInput, reason: str) -> dict[str, Any]:
    """What to return when Zence itself failed."""
    if payload.hook_event_name != "PreToolUse":
        # Only PreToolUse can decide anything. Everywhere else, staying quiet is
        # both correct and safe.
        return empty_output()

    if not _is_sensitive(payload):
        return empty_output()

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"Zence could not complete its check ({reason}), so it cannot "
                "confirm this operation stays inside the active client boundary. "
                "Approve only if you know this asset is in bounds."
            ),
            "additionalContext": (
                "Zence failed to evaluate this call and defaulted to asking. This "
                "is a Zence fault, not a policy violation. Run `zence doctor` to "
                "diagnose."
            ),
        },
        "systemMessage": f"Zence check failed: {reason}",
    }


def dispatch(event: str, payload: HookInput) -> dict[str, Any]:
    handler = HANDLERS.get(event or payload.hook_event_name)
    if handler is None:
        # An event Zence does not handle, or a future one. Silence is correct.
        return empty_output()
    return handler(payload)


def run(argv: list[str] | None = None, stdin: Any = None, stdout: Any = None) -> int:
    """Read one hook payload, answer it, and always exit 0.

    A non-zero exit from a Claude Code hook is either a hard block (2) or a
    reported error. Zence expresses every decision in JSON instead, so the exit
    code stays 0 and the user never sees a stack trace where a policy reason
    belongs.
    """
    args = argv if argv is not None else sys.argv[1:]
    event = args[0] if args else ""

    payload = HookInput.read(stdin)
    seconds = (
        PROMPT_DEADLINE_SECONDS
        if (event or payload.hook_event_name) == "UserPromptSubmit"
        else DEFAULT_DEADLINE_SECONDS
    )
    if override := os.environ.get("ZENCE_HOOK_DEADLINE_SECONDS"):
        # A malformed override keeps the default rather than failing the hook.
        with contextlib.suppress(ValueError):
            seconds = float(override)

    try:
        with _deadline(seconds):
            output = dispatch(event, payload)
    except HookTimeout as exc:
        output = fail_safe_output(payload, f"timed out after {exc}")
    except Exception as exc:
        output = fail_safe_output(payload, type(exc).__name__)

    emit(output, stdout)
    return 0


def main() -> int:  # pragma: no cover - console-script shim
    return run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
