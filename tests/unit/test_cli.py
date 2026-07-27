"""The command line interface.

Two things are worth pinning: the exit codes, because CI and scripts branch on
them, and the absence of secrets in output, because `zence doctor` is the first
thing anyone pastes into a bug report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from zence_cli.main import app
from zence_cli.output import ExitCode

runner = CliRunner()

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
critical_downstream: []
"""

CATALOG: dict[str, Any] = {
    "schema_version": 1,
    "recorded_at": "2026-08-01T12:00:00Z",
    "source_endpoint": "http://localhost:8080",
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
        "bluepeak.patient_contacts": {
            "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)",
            "name": "bluepeak.patient_contacts",
            "domain_urn": "urn:li:domain:bluepeak-health",
            "domain_name": "BluePeak Health",
            "owners": ["urn:li:corpuser:priya"],
            "tags": ["urn:li:tag:PII"],
            "terms": ["urn:li:glossaryTerm:PersonalData"],
            "column_tags": [{"field_path": "email", "tags": ["urn:li:tag:PII"]}],
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
    return tmp_path


def run(*args: str) -> Any:
    return runner.invoke(app, list(args))


# --- status ------------------------------------------------------------------


def test_status_reports_the_boundary(workspace: Path) -> None:
    result = run("status", "-C", str(workspace))
    assert result.exit_code == ExitCode.OK
    assert "Northstar Commerce" in result.stdout


def test_status_json_is_machine_readable(workspace: Path) -> None:
    result = run("status", "-C", str(workspace), "--json")
    payload = json.loads(result.stdout)

    assert payload["active_client"] == "Northstar Commerce"
    assert payload["allowed_domains"] == ["urn:li:domain:northstar-commerce"]
    assert payload["rules"] > 0


def test_status_reports_the_provider_honestly(workspace: Path) -> None:
    """A fixture must never be displayed as a live catalog."""
    payload = json.loads(run("status", "-C", str(workspace), "--json").stdout)
    assert payload["provider"] == "fixture"


def test_ungoverned_workspace_exits_not_governed(tmp_path: Path) -> None:
    result = run("status", "-C", str(tmp_path))
    assert result.exit_code == ExitCode.NOT_GOVERNED


def test_broken_policy_exits_policy_invalid(tmp_path: Path) -> None:
    zence = tmp_path / ".zence"
    zence.mkdir()
    (zence / "policy.yaml").write_text("policy_version: [unclosed\n", encoding="utf-8")

    result = run("status", "-C", str(tmp_path))
    assert result.exit_code == ExitCode.POLICY_INVALID


# --- policy validate ---------------------------------------------------------


def test_policy_validate_accepts_a_good_policy(workspace: Path) -> None:
    result = run("policy", "validate", "-C", str(workspace))
    assert result.exit_code == ExitCode.OK


def test_policy_validate_counts_rules_by_decision(workspace: Path) -> None:
    payload = json.loads(run("policy", "validate", "-C", str(workspace), "--json").stdout)
    assert payload["by_decision"]["deny"] >= 1
    assert payload["by_decision"]["ask"] >= 1
    assert payload["by_decision"]["allow"] >= 1


def test_policy_validate_rejects_a_broken_policy(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "policy_version: '1.0.0'\nworkspace_id: x\nactive_client: X\n"
        "rules:\n  - id: ZR-500\n    title: t\n    decision: ask\n    explanation: e\n"
        "    when: {asset.nonexistent: {equals: 1}}\n",
        encoding="utf-8",
    )
    result = run("policy", "validate", str(bad))
    assert result.exit_code == ExitCode.POLICY_INVALID


# --- inspect -----------------------------------------------------------------


def test_inspect_marks_an_out_of_boundary_asset(workspace: Path) -> None:
    result = run("inspect", "bluepeak.patient_contacts", "-C", str(workspace))
    assert result.exit_code == ExitCode.OK
    assert "outside boundary" in result.stdout


def test_inspect_names_the_sensitive_columns(workspace: Path) -> None:
    result = run("inspect", "bluepeak.patient_contacts", "-C", str(workspace))
    assert "email" in result.stdout


def test_inspect_handles_an_unknown_asset(workspace: Path) -> None:
    result = run("inspect", "nowhere.nothing", "-C", str(workspace))
    assert result.exit_code == ExitCode.OK
    assert "not in the catalog" in result.stdout


# --- evaluate ----------------------------------------------------------------


def test_evaluate_exits_blocked_on_a_denial(workspace: Path) -> None:
    """The exit code is the contract: CI asserts a rule still fires."""
    result = run(
        "evaluate",
        "--tool",
        "Write",
        "--file",
        "models/x.sql",
        "--content",
        "SELECT email FROM bluepeak.patient_contacts",
        "-C",
        str(workspace),
    )
    assert result.exit_code == ExitCode.BLOCKED
    assert "DENY" in result.stdout


def test_evaluate_exits_ok_on_an_allow(workspace: Path) -> None:
    result = run(
        "evaluate",
        "--tool",
        "Write",
        "--file",
        "models/y.sql",
        "--content",
        "SELECT id FROM northstar.marketing_leads",
        "-C",
        str(workspace),
    )
    assert result.exit_code == ExitCode.OK
    assert "ALLOW" in result.stdout


def test_evaluate_json_carries_the_full_decision(workspace: Path) -> None:
    result = run(
        "evaluate",
        "--tool",
        "Write",
        "--file",
        "m.sql",
        "--content",
        "SELECT email FROM bluepeak.patient_contacts",
        "-C",
        str(workspace),
        "--json",
    )
    payload = json.loads(result.stdout)

    assert payload["decision"]["verdict"] == "deny"
    assert payload["decision"]["rule_id"] == "ZR-001"
    assert payload["references"]


def test_evaluate_needs_something_to_evaluate(workspace: Path) -> None:
    result = run("evaluate", "--tool", "Bash", "-C", str(workspace))
    assert result.exit_code == ExitCode.ERROR


def test_a_local_operation_is_not_described_as_in_boundary(workspace: Path) -> None:
    """ "All 0 referenced assets resolve inside the client" is true and useless."""
    result = run("evaluate", "--tool", "Bash", "--command", "rm -rf build/", "-C", str(workspace))

    assert result.exit_code == ExitCode.OK
    assert "references no assets known to DataHub" in result.stdout
    assert "All 0 referenced" not in result.stdout


# --- doctor ------------------------------------------------------------------


def test_doctor_reports_checks(workspace: Path) -> None:
    result = run("doctor", "-C", str(workspace), "--json")
    payload = json.loads(result.stdout)

    names = {check["check"] for check in payload["checks"]}
    assert {"uv", "workspace", "datahub token"} <= names


def test_doctor_never_prints_the_token(workspace: Path, monkeypatch: Any) -> None:
    """This output is the first thing anyone pastes into an issue."""
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "super-secret-token-value")

    result = run("doctor", "-C", str(workspace), "--json")
    assert "super-secret-token-value" not in result.stdout
    assert '"present"' in result.stdout


# --- init --------------------------------------------------------------------


def test_init_creates_a_policy_that_validates(tmp_path: Path) -> None:
    result = run(
        "init",
        "--client",
        "Acme Retail",
        "--domain",
        "urn:li:domain:acme",
        "-C",
        str(tmp_path),
    )
    assert result.exit_code == ExitCode.OK

    created = tmp_path / ".zence" / "policy.yaml"
    assert created.exists()
    assert run("policy", "validate", str(created)).exit_code == ExitCode.OK


def test_init_starts_in_audit_mode(tmp_path: Path) -> None:
    """Blocking a team's work on day one is how a guardrail gets uninstalled."""
    run("init", "--client", "Acme", "--domain", "urn:li:domain:acme", "-C", str(tmp_path))
    assert "mode: audit" in (tmp_path / ".zence" / "policy.yaml").read_text()


def test_init_refuses_to_clobber_without_force(tmp_path: Path) -> None:
    args = ["init", "--client", "Acme", "--domain", "urn:li:domain:acme", "-C", str(tmp_path)]
    assert run(*args).exit_code == ExitCode.OK
    assert run(*args).exit_code == ExitCode.ERROR
    assert run(*args, "--force").exit_code == ExitCode.OK


# --- help --------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [(), ("status", "--help"), ("evaluate", "--help"), ("policy", "--help"), ("doctor", "--help")],
)
def test_help_is_available_everywhere(args: tuple[str, ...]) -> None:
    result = run(*args)
    assert result.exit_code in {0, 2}
    assert result.stdout.strip()
