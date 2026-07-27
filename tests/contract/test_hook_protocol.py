"""Hook wire-format contract.

The highest-value suite in the repository. Every other test proves Zence reached
the right conclusion; these prove the conclusion actually reaches Claude Code in
a form it acts on.

A hook that returns a subtly wrong shape does not error. It is ignored — and an
ignored security control is worse than an absent one, because the user believes
it ran. So these assert the exact field names from the published hooks reference,
not merely that "something was returned".

Everything here runs through `run()`, the real entry point, with real JSON on a
real stream.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from zence_core.hooks import run

# --- Harness -----------------------------------------------------------------


def invoke(event: str, payload: dict[str, Any] | str) -> dict[str, Any]:
    """Run a hook exactly as Claude Code would, and parse its stdout."""
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    stdout = io.StringIO()

    exit_code = run([event], stdin=stdin, stdout=stdout)

    # Exit 0 always: Zence expresses decisions in JSON, never through the exit
    # code, so the user never sees a stack trace where a policy reason belongs.
    assert exit_code == 0, f"hook exited {exit_code}"

    raw = stdout.getvalue()
    assert raw, "hook produced no output; Claude Code reads silence as 'no opinion'"

    parsed = json.loads(raw)  # must be exactly one JSON object
    assert isinstance(parsed, dict)
    return parsed


POLICY = """\
policy_version: "1.0.0"
workspace_id: northstar-analytics
mode: enforce
active_client: Northstar Commerce
active_domain: "urn:li:domain:northstar-commerce"
allowed_domains: ["urn:li:domain:northstar-commerce"]
allowed_environments: ["DEV", "QA"]
sensitive_tags: ["urn:li:tag:PII"]
protected_terms: ["urn:li:glossaryTerm:PersonalData"]
critical_downstream: ["urn:li:dashboard:(looker,northstar_revenue)"]
"""

CATALOG: dict[str, Any] = {
    "schema_version": 1,
    "recorded_at": "2026-08-01T12:00:00Z",
    "source_endpoint": "http://localhost:8080",
    "datahub_version": "1.6.0",
    "entities": {
        "northstar.marketing_leads": {
            "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.marketing_leads,DEV)",
            "name": "northstar.marketing_leads",
            "domain_urn": "urn:li:domain:northstar-commerce",
            "domain_name": "Northstar Commerce",
            "owners": ["urn:li:corpuser:dana"],
            "tags": [],
            "terms": [],
            "column_tags": [],
            "lifecycle": "active",
            "environment": "DEV",
            "downstream_critical": [],
        },
        "northstar.fct_revenue_daily": {
            "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.fct_revenue_daily,DEV)",
            "name": "northstar.fct_revenue_daily",
            "domain_urn": "urn:li:domain:northstar-commerce",
            "domain_name": "Northstar Commerce",
            "owners": ["urn:li:corpuser:dana"],
            "tags": [],
            "terms": [],
            "column_tags": [],
            "lifecycle": "active",
            "environment": "DEV",
            "downstream_critical": ["urn:li:dashboard:(looker,northstar_revenue)"],
        },
        "bluepeak.patient_contacts": {
            "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)",
            "name": "bluepeak.patient_contacts",
            "domain_urn": "urn:li:domain:bluepeak-health",
            "domain_name": "BluePeak Health",
            "owners": ["urn:li:corpuser:priya"],
            "tags": ["urn:li:tag:PII"],
            "terms": ["urn:li:glossaryTerm:PersonalData"],
            "column_tags": [
                {"field_path": "email", "tags": ["urn:li:tag:PII"]},
                {"field_path": "phone", "tags": ["urn:li:tag:PII"]},
            ],
            "lifecycle": "active",
            "environment": "PROD",
            "downstream_critical": [],
        },
    },
}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    zence = tmp_path / ".zence"
    zence.mkdir()
    (zence / "policy.yaml").write_text(POLICY, encoding="utf-8")
    (zence / "project.yaml").write_text("fixture: .zence/catalog.json\n", encoding="utf-8")
    (zence / "catalog.json").write_text(json.dumps(CATALOG), encoding="utf-8")
    (tmp_path / "models").mkdir()
    return tmp_path


def pre_tool(workspace: Path, tool: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "sess-1",
        "cwd": str(workspace),
        "permission_mode": "default",
        "tool_name": tool,
        "tool_input": tool_input,
        "tool_use_id": "toolu_01",
    }


def decision_of(output: dict[str, Any]) -> str:
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    return str(specific["permissionDecision"])


# =============================================================================
# SessionStart
# =============================================================================


def test_session_start_injects_the_boundary(workspace: Path) -> None:
    output = invoke(
        "SessionStart",
        {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(workspace)},
    )
    specific = output["hookSpecificOutput"]

    assert specific["hookEventName"] == "SessionStart"
    assert "Northstar Commerce" in specific["additionalContext"]
    assert "urn:li:domain:northstar-commerce" in specific["additionalContext"]


def test_session_start_sets_a_title_naming_the_client(workspace: Path) -> None:
    output = invoke(
        "SessionStart",
        {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(workspace)},
    )
    assert "Northstar Commerce" in output["hookSpecificOutput"]["sessionTitle"]


def test_session_start_watches_the_policy_files(workspace: Path) -> None:
    """So a policy edited outside the session is picked up on the next turn."""
    output = invoke(
        "SessionStart",
        {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(workspace)},
    )
    assert ".zence/policy.yaml" in output["hookSpecificOutput"]["watchPaths"]


def test_session_start_is_silent_in_an_ungoverned_workspace(tmp_path: Path) -> None:
    """Not every repository is governed. Saying nothing is correct."""
    output = invoke(
        "SessionStart",
        {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(tmp_path)},
    )
    assert output == {}


def test_session_start_says_so_when_the_policy_is_broken(tmp_path: Path) -> None:
    """A workspace with an unparseable policy is not protected, and silence
    would let the user believe otherwise."""
    zence = tmp_path / ".zence"
    zence.mkdir()
    (zence / "policy.yaml").write_text("policy_version: [unclosed\n", encoding="utf-8")

    output = invoke(
        "SessionStart",
        {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(tmp_path)},
    )
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "failed to load" in context
    assert "no data boundary is being enforced" in context


# =============================================================================
# PreToolUse — the decisions
# =============================================================================


def test_cross_client_pii_is_denied(workspace: Path) -> None:
    output = invoke(
        "PreToolUse",
        pre_tool(
            workspace,
            "Write",
            {
                "file_path": "models/blend.sql",
                "content": (
                    "SELECT l.email, p.phone FROM northstar.marketing_leads l "
                    "JOIN bluepeak.patient_contacts p ON p.email = l.email"
                ),
            },
        ),
    )

    assert decision_of(output) == "deny"

    specific = output["hookSpecificOutput"]
    reason = specific["permissionDecisionReason"]
    assert reason, "a deny must carry a reason; Claude Code requires it"
    assert "BluePeak Health" in reason
    assert "Northstar Commerce" in reason
    assert "email" in reason and "phone" in reason


def test_a_denial_tells_claude_what_to_do_instead(workspace: Path) -> None:
    """A bare refusal invites a retry with a variation. Remediation redirects."""
    output = invoke(
        "PreToolUse",
        pre_tool(
            workspace,
            "Write",
            {
                "file_path": "models/blend.sql",
                "content": "SELECT email FROM bluepeak.patient_contacts",
            },
        ),
    )
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "Suggested next step" in context
    assert "Do not retry this call in a modified form" in context
    assert "urn:li:dataset" in context


def test_denial_prose_is_grammatical(workspace: Path) -> None:
    """`verdict + "ed"` produced "denyed" in text shown on every refusal."""
    output = invoke(
        "PreToolUse",
        pre_tool(
            workspace,
            "Write",
            {"file_path": "m.sql", "content": "SELECT email FROM bluepeak.patient_contacts"},
        ),
    )
    context = output["hookSpecificOutput"]["additionalContext"]

    assert "denied this operation" in context
    assert "denyed" not in context


def test_critical_downstream_impact_asks(workspace: Path) -> None:
    output = invoke(
        "PreToolUse",
        pre_tool(
            workspace,
            "Edit",
            {
                "file_path": "models/revenue.sql",
                "new_string": "INSERT INTO northstar.fct_revenue_daily SELECT 1",
            },
        ),
    )

    assert decision_of(output) == "ask"
    assert "northstar_revenue" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_in_boundary_work_produces_no_interference(workspace: Path) -> None:
    """An allow should be invisible: no prompt, no transcript noise."""
    output = invoke(
        "PreToolUse",
        pre_tool(
            workspace,
            "Write",
            {
                "file_path": "models/leads.sql",
                "content": "SELECT id FROM northstar.marketing_leads",
            },
        ),
    )
    assert output == {}


def test_editing_zence_config_is_denied(workspace: Path) -> None:
    output = invoke(
        "PreToolUse",
        pre_tool(
            workspace, "Edit", {"file_path": ".zence/policy.yaml", "new_string": "mode: audit"}
        ),
    )

    assert decision_of(output) == "deny"
    assert "policy" in output["hookSpecificOutput"]["permissionDecisionReason"].lower()


def test_datahub_mcp_calls_are_intercepted(workspace: Path) -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)"
    output = invoke(
        "PreToolUse", pre_tool(workspace, "mcp__datahub__get_entities", {"urns": [urn]})
    )
    assert decision_of(output) == "deny"


def test_the_plugin_bundled_mcp_server_name_is_also_intercepted(workspace: Path) -> None:
    """Interception must not depend on how the server happened to be registered."""
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)"
    output = invoke(
        "PreToolUse",
        pre_tool(workspace, "mcp__plugin_zence_datahub__get_entities", {"urns": [urn]}),
    )
    assert decision_of(output) == "deny"


def test_ungoverned_workspace_is_never_blocked(tmp_path: Path) -> None:
    output = invoke("PreToolUse", pre_tool(tmp_path, "Bash", {"command": "rm -rf /"}))
    assert output == {}


# =============================================================================
# Degraded and malformed input
# =============================================================================


def test_unreachable_datahub_asks_rather_than_allowing(tmp_path: Path) -> None:
    """No fixture configured and no catalog reachable: Zence must not wave it through."""
    zence = tmp_path / ".zence"
    zence.mkdir()
    (zence / "policy.yaml").write_text(POLICY, encoding="utf-8")
    (zence / "project.yaml").write_text("datahub:\n  url: http://127.0.0.1:1\n", encoding="utf-8")

    output = invoke(
        "PreToolUse",
        pre_tool(
            tmp_path,
            "Write",
            {"file_path": "m.sql", "content": "SELECT * FROM bluepeak.patient_contacts"},
        ),
    )

    assert decision_of(output) in {"ask", "deny"}
    assert "DataHub" in output["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    "payload",
    ["", "not json", "[]", "null", '{"tool_input": "a string, not an object"}', "{"],
)
def test_malformed_input_still_produces_valid_json(payload: str) -> None:
    """Garbage in must not mean silence out."""
    stdin = io.StringIO(payload)
    stdout = io.StringIO()

    assert run(["PreToolUse"], stdin=stdin, stdout=stdout) == 0
    assert json.loads(stdout.getvalue()) is not None


def test_unknown_event_is_handled_quietly() -> None:
    output = invoke("SomeFutureEvent", {"hook_event_name": "SomeFutureEvent"})
    assert output == {}


def test_missing_cwd_does_not_crash() -> None:
    output = invoke("PreToolUse", {"hook_event_name": "PreToolUse", "tool_name": "Bash"})
    assert isinstance(output, dict)


# =============================================================================
# The fail-safe path
# =============================================================================


def test_an_internal_failure_asks_for_sensitive_tools(monkeypatch: Any) -> None:
    """A Zence bug must not become a silent allow on a tool that touches data."""
    import zence_core.hooks.main as main_module

    def explode(event: str, payload: Any) -> dict[str, Any]:
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(main_module, "dispatch", explode)

    stdin = io.StringIO(
        json.dumps(
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "x"}}
        )
    )
    stdout = io.StringIO()
    assert main_module.run(["PreToolUse"], stdin=stdin, stdout=stdout) == 0

    output = json.loads(stdout.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert (
        "could not complete its check" in (output["hookSpecificOutput"]["permissionDecisionReason"])
    )
    # And it says whose fault it is, so the user does not read a Zence bug as a
    # policy violation and learn to bypass the tool.
    assert "not a policy violation" in output["hookSpecificOutput"]["additionalContext"]


def test_an_internal_failure_does_not_ask_for_harmless_tools(monkeypatch: Any) -> None:
    """Failing closed on everything would train users to click through prompts."""
    import zence_core.hooks.main as main_module

    def explode(event: str, payload: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "dispatch", explode)

    stdin = io.StringIO(
        json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}})
    )
    stdout = io.StringIO()
    main_module.run(["PreToolUse"], stdin=stdin, stdout=stdout)

    assert json.loads(stdout.getvalue()) == {}


def test_a_timeout_produces_a_decision_rather_than_silence(monkeypatch: Any) -> None:
    """A hook that times out emits nothing, and nothing means the normal
    permission flow proceeds — a silent allow arrived at by accident."""
    import zence_core.hooks.main as main_module

    def hang(event: str, payload: Any) -> dict[str, Any]:
        import time

        time.sleep(5)
        return {}

    monkeypatch.setattr(main_module, "dispatch", hang)
    monkeypatch.setenv("ZENCE_HOOK_DEADLINE_SECONDS", "0.2")

    stdin = io.StringIO(
        json.dumps(
            {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "x"}}
        )
    )
    stdout = io.StringIO()
    main_module.run(["PreToolUse"], stdin=stdin, stdout=stdout)

    output = json.loads(stdout.getvalue())
    assert output["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "timed out" in output["hookSpecificOutput"]["permissionDecisionReason"]


# =============================================================================
# Secrets
# =============================================================================


def test_no_secret_reaches_the_hook_output(workspace: Path) -> None:
    """Zence's own output must not become the place a credential leaks."""
    secret = "ghp" + "_" + "s3cr3tv4lue" * 3

    output = invoke(
        "PreToolUse",
        pre_tool(workspace, "Bash", {"command": f"export TOKEN={secret} && psql -c 'SELECT 1'"}),
    )
    assert secret not in json.dumps(output)


def test_no_secret_reaches_the_session_context(workspace: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "super-secret-token-value")

    output = invoke(
        "SessionStart",
        {"hook_event_name": "SessionStart", "session_id": "s", "cwd": str(workspace)},
    )
    assert "super-secret-token-value" not in json.dumps(output)
