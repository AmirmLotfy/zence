"""Claude Code hook handlers.

`main.run` is the entry point invoked by `zence-hook <Event>`. It guarantees that
Claude Code always receives exactly one valid JSON object and a zero exit code,
whatever happens inside a handler.
"""

from zence_core.hooks.context import (
    NotGovernedError,
    ProjectSettings,
    ZenceContext,
    find_workspace_root,
    load_context,
)
from zence_core.hooks.handlers import HANDLERS, boundary_context
from zence_core.hooks.main import HookTimeout, dispatch, fail_safe_output, run
from zence_core.hooks.protocol import (
    HookInput,
    emit,
    empty_output,
    pre_tool_use_output,
    session_start_output,
)

__all__ = [
    "HANDLERS",
    "HookInput",
    "HookTimeout",
    "NotGovernedError",
    "ProjectSettings",
    "ZenceContext",
    "boundary_context",
    "dispatch",
    "emit",
    "empty_output",
    "fail_safe_output",
    "find_workspace_root",
    "load_context",
    "pre_tool_use_output",
    "run",
    "session_start_output",
]
