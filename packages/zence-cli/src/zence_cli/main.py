"""The `zence` command line interface.

Commands are organised around the questions someone actually asks:

    zence status              what boundary am I inside?
    zence doctor              is any of this working?
    zence policy validate     will this policy load?
    zence inspect <asset>     what does DataHub say about this?
    zence evaluate ...        what would Zence do if Claude tried this?

`evaluate` is the one worth knowing about. It runs the real engine over a
hypothetical tool call, so a policy can be tested without provoking a violation
in a live session — and its exit code carries the verdict, so CI can assert that
a rule still fires.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from zence_cli.output import (
    ExitCode,
    console,
    emit_json,
    error,
    field_table,
    heading,
    note,
    verdict_banner,
    warn,
)
from zence_core.extract import normalize
from zence_core.hooks.context import (
    NotGovernedError,
    ZenceContext,
    load_context,
)
from zence_core.policy import PolicyError, load_policy_file
from zence_core.policy import evaluate as evaluate_policy
from zence_core.schemas import EvidenceStatus, Verdict

app = typer.Typer(
    name="zence",
    help=(
        "Task-scoped context and policy firewall for Claude Code, powered by DataHub.\n\n"
        "Keeps a session inside the correct client, domain, and environment."
    ),
    no_args_is_help=True,
    add_completion=False,
)
policy_app = typer.Typer(help="Inspect and validate policy files.", no_args_is_help=True)
app.add_typer(policy_app, name="policy")

from zence_cli.demo import demo_app  # noqa: E402

app.add_typer(demo_app, name="demo")

JsonOption = Annotated[
    bool, typer.Option("--json", help="Emit machine-readable JSON instead of a table.")
]
PathOption = Annotated[
    Path | None,
    typer.Option("--path", "-C", help="Workspace directory. Defaults to the current one."),
]


def _load(path: Path | None) -> ZenceContext:
    """Load the workspace context, or exit with a specific code."""
    root = (path or Path.cwd()).resolve()
    try:
        return load_context(root)
    except NotGovernedError:
        error(
            f"no .zence/policy.yaml found at or above {root}\n"
            "        Run `zence init` to create one."
        )
        raise typer.Exit(ExitCode.NOT_GOVERNED) from None
    except PolicyError as exc:
        error(f"policy failed to load:\n        {exc}")
        raise typer.Exit(ExitCode.POLICY_INVALID) from None


# =============================================================================
# status
# =============================================================================


@app.command()
def status(as_json: JsonOption = False, path: PathOption = None) -> None:
    """Show the boundary this workspace is bound to."""
    context = _load(path)
    workspace = context.workspace

    if as_json:
        emit_json(
            {
                "workspace_id": workspace.workspace_id,
                "root": str(context.root),
                "active_client": workspace.active_client,
                "active_domain": workspace.active_domain,
                "allowed_domains": sorted(workspace.allowed_domains),
                "allowed_environments": sorted(workspace.allowed_environments),
                "mode": workspace.mode.value,
                "policy_version": workspace.policy_version,
                "policy_sha256": workspace.policy_sha256,
                "rules": len(context.policy.rules),
                "exceptions": len(context.policy.exceptions),
                "provider": context.provider.kind.value,
            }
        )
        return

    heading(f"{workspace.active_client}")
    field_table(
        [
            ("workspace", workspace.workspace_id),
            ("root", str(context.root)),
            ("domain", workspace.active_domain or "(none)"),
            ("environments", ", ".join(sorted(workspace.allowed_environments)) or "(none)"),
            ("mode", workspace.mode.value),
            ("policy", f"v{workspace.policy_version}"),
            ("rules", str(len(context.policy.rules))),
            ("exceptions", str(len(context.policy.exceptions))),
            ("metadata", context.provider.kind.value),
        ]
    )

    active = context.policy.active_exceptions()
    expired = len(context.policy.exceptions) - len(active)
    if expired:
        warn(f"{expired} exception(s) have expired and no longer apply")


# =============================================================================
# doctor
# =============================================================================


@app.command()
def doctor(as_json: JsonOption = False, path: PathOption = None) -> None:
    """Check that everything Zence needs is present and working.

    Prints no secrets. The DataHub token is reported as present or absent, never
    echoed, because `zence doctor` output is the first thing anyone pastes into
    an issue.
    """
    import os
    import shutil

    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    uv_path = shutil.which("uv")
    record("uv", uv_path is not None, uv_path or "not on PATH — required by the hook shim")

    root = (path or Path.cwd()).resolve()
    context: ZenceContext | None
    try:
        context = load_context(root)
    except NotGovernedError as exc:
        record("workspace", False, str(exc))
        context = None
    except PolicyError as exc:
        record("workspace", False, f"policy invalid: {exc}")
        context = None
    else:
        record(
            "workspace",
            True,
            f"{context.workspace.active_client} (policy v{context.workspace.policy_version})",
        )

    token_present = any(
        os.environ.get(name) for name in ("CLAUDE_PLUGIN_OPTION_DATAHUB_TOKEN", "DATAHUB_GMS_TOKEN")
    )
    record(
        "datahub token",
        token_present,
        "present" if token_present else "not set — see .env.example",
    )

    if context is not None:
        health = context.provider.health()
        record(
            "datahub",
            health.reachable,
            f"{health.detail}" + (f" [{health.endpoint}]" if health.endpoint else ""),
        )
        try:
            sdk_ok = True
            import datahub  # noqa: F401
        except ImportError:
            sdk_ok = False
        record(
            "datahub sdk",
            sdk_ok,
            "installed" if sdk_ok else "not installed — `uv sync --extra datahub`",
        )

    failed = [check for check in checks if not check["ok"]]

    if as_json:
        emit_json({"ok": not failed, "checks": checks})
    else:
        heading("zence doctor")
        field_table(
            [
                (
                    ("[allow]ok[/allow]" if check["ok"] else "[deny]fail[/deny]")
                    + f" {check['check']}",
                    str(check["detail"]),
                )
                for check in checks
            ]
        )
        if failed:
            console.print()
            error(f"{len(failed)} check(s) failed")

    if any(check["check"] == "datahub" and not check["ok"] for check in checks):
        raise typer.Exit(ExitCode.DATAHUB_UNREACHABLE)
    if failed:
        raise typer.Exit(ExitCode.ERROR)


# =============================================================================
# policy validate
# =============================================================================


@policy_app.command("validate")
def policy_validate(
    file: Annotated[
        Path | None, typer.Argument(help="Policy file. Defaults to the workspace's.")
    ] = None,
    as_json: JsonOption = False,
    path: PathOption = None,
) -> None:
    """Check that a policy file loads and every rule is well-formed."""
    target = file or ((path or Path.cwd()).resolve() / ".zence" / "policy.yaml")

    if not target.exists():
        error(f"no policy at {target}")
        raise typer.Exit(ExitCode.NOT_GOVERNED)

    try:
        policy = load_policy_file(target)
    except PolicyError as exc:
        if as_json:
            emit_json({"ok": False, "path": str(target), "error": str(exc)})
        else:
            error(f"{target}\n        {exc}")
        raise typer.Exit(ExitCode.POLICY_INVALID) from None

    by_decision = {
        verdict.value: sum(1 for rule in policy.rules if rule.decision is verdict)
        for verdict in Verdict
    }
    summary = {
        "ok": True,
        "path": str(target),
        "policy_version": policy.policy_version,
        "mode": policy.mode.value,
        "active_client": policy.active_client,
        "rules": len(policy.rules),
        "exceptions": len(policy.exceptions),
        "active_exceptions": len(policy.active_exceptions()),
        "by_decision": by_decision,
    }

    if as_json:
        emit_json(summary)
        return

    console.print(f"[allow]✓[/allow] {target}")
    field_table(
        [
            ("version", policy.policy_version),
            ("client", policy.active_client),
            ("mode", policy.mode.value),
            (
                "rules",
                f"{len(policy.rules)}  "
                f"({by_decision['deny']} deny, "
                f"{by_decision['ask']} ask, "
                f"{by_decision['allow']} allow)",
            ),
            ("exceptions", f"{len(policy.active_exceptions())} active of {len(policy.exceptions)}"),
        ]
    )


# =============================================================================
# inspect
# =============================================================================


@app.command()
def inspect(
    reference: Annotated[str, typer.Argument(help="A dataset name or DataHub URN.")],
    as_json: JsonOption = False,
    path: PathOption = None,
) -> None:
    """Ask DataHub about one asset, exactly as a hook would."""
    from zence_core.extract.base import make_ref

    context = _load(path)
    [evidence] = context.provider.resolve([make_ref(reference, extractor="cli")], context.workspace)

    if as_json:
        emit_json(json.loads(evidence.model_dump_json()))
        if evidence.status is EvidenceStatus.LOOKUP_FAILED:
            raise typer.Exit(ExitCode.DATAHUB_UNREACHABLE)
        return

    if evidence.status is EvidenceStatus.LOOKUP_FAILED:
        error(f"could not reach DataHub: {evidence.failure_reason}")
        raise typer.Exit(ExitCode.DATAHUB_UNREACHABLE)

    if evidence.status is EvidenceStatus.NOT_FOUND:
        console.print(f"[ask]?[/ask] {reference} is not in the catalog")
        raise typer.Exit(ExitCode.OK)

    in_domain = context.workspace.is_in_domain(evidence.domain_urn)
    heading(evidence.name or reference)
    field_table(
        [
            ("urn", f"[urn]{evidence.urn}[/urn]"),
            (
                "domain",
                f"{evidence.domain_name or evidence.domain_urn or '(none)'}  "
                + (
                    "[allow](in boundary)[/allow]"
                    if in_domain
                    else "[deny](outside boundary)[/deny]"
                ),
            ),
            ("environment", evidence.environment or "(unknown)"),
            ("lifecycle", evidence.lifecycle.value),
            ("owners", ", ".join(sorted(evidence.owners)) or "(unowned)"),
            ("tags", ", ".join(sorted(evidence.tags)) or "(none)"),
            ("terms", ", ".join(sorted(evidence.terms)) or "(none)"),
            (
                "sensitive columns",
                ", ".join(evidence.columns_tagged(context.workspace.sensitive_tags)) or "(none)",
            ),
            ("critical downstream", ", ".join(evidence.downstream_critical) or "(none)"),
            ("source", evidence.provider.value),
        ]
    )


# =============================================================================
# evaluate
# =============================================================================


@app.command("evaluate")
def evaluate_action(
    tool: Annotated[
        str, typer.Option("--tool", help="Tool name, e.g. Bash, Write, mcp__datahub__search.")
    ],
    command: Annotated[str | None, typer.Option("--command", help="For Bash.")] = None,
    file: Annotated[
        Path | None, typer.Option("--file", help="For Write/Edit: the target path.")
    ] = None,
    content: Annotated[
        str | None, typer.Option("--content", help="For Write/Edit: the content.")
    ] = None,
    urn: Annotated[str | None, typer.Option("--urn", help="For MCP tools.")] = None,
    as_json: JsonOption = False,
    path: PathOption = None,
) -> None:
    """Run the real engine over a hypothetical tool call.

    The point is to test a policy without provoking a violation in a live
    session. The exit code carries the verdict — 0 allow, 6 deny, 7 ask — so CI
    can assert that a rule still fires after an edit.
    """
    context = _load(path)

    tool_input: dict[str, Any] = {}
    if command:
        tool_input["command"] = command
    if file:
        tool_input["file_path"] = str(file)
    if content:
        tool_input["content"] = content
    elif file and file.exists():
        tool_input["content"] = file.read_text(encoding="utf-8", errors="replace")
    if urn:
        tool_input["urn"] = urn

    if not tool_input:
        error("nothing to evaluate — pass --command, --file, or --urn")
        raise typer.Exit(ExitCode.ERROR)

    normalized = normalize(tool, tool_input, context.root, hook_event="PreToolUse")
    evidences = context.provider.resolve(normalized.refs, context.workspace)
    decision = evaluate_policy(normalized.action, evidences, context.workspace, context.policy)

    if as_json:
        emit_json(
            {
                "decision": json.loads(decision.model_dump_json()),
                "references": [json.loads(ref.model_dump_json()) for ref in normalized.refs],
                "intents": sorted(intent.value for intent in normalized.action.intents),
            }
        )
    else:
        verdict_banner(decision.verdict, decision.rule_id, decision.rule_title)
        console.print()
        console.print(decision.reason)
        if decision.remediation:
            console.print()
            console.print(f"[muted]→ {decision.remediation}[/muted]")
        if decision.evidence_urns:
            console.print()
            field_table(
                [("evidence", "\n".join(f"[urn]{u}[/urn]" for u in decision.evidence_urns))]
            )
        if decision.degraded:
            console.print()
            warn(f"decided with incomplete metadata: {decision.degraded_reason}")
        if not normalized.refs:
            console.print()
            note("no asset references were extracted from this call")

    raise typer.Exit(
        {
            Verdict.ALLOW: ExitCode.OK,
            Verdict.DENY: ExitCode.BLOCKED,
            Verdict.ASK: ExitCode.NEEDS_APPROVAL,
        }[decision.verdict]
    )


# =============================================================================
# init
# =============================================================================


@app.command()
def init(
    client: Annotated[str, typer.Option("--client", help="The client this workspace belongs to.")],
    domain: Annotated[str, typer.Option("--domain", help="Its DataHub domain URN.")],
    path: PathOption = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing policy.")] = False,
) -> None:
    """Create `.zence/policy.yaml` for a workspace."""
    root = (path or Path.cwd()).resolve()
    zence_dir = root / ".zence"
    policy_path = zence_dir / "policy.yaml"

    if policy_path.exists() and not force:
        error(f"{policy_path} already exists. Pass --force to overwrite.")
        raise typer.Exit(ExitCode.ERROR)

    workspace_id = root.name.lower().replace(" ", "-")
    zence_dir.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        f"""# Zence policy for {client}.
# Reference: https://github.com/AmirmLotfy/zence/blob/main/docs/POLICY_ENGINE.md
#
# `mode: audit` records decisions without blocking anything. Start there, watch
# `zence audit` for a few days, then switch to enforce.

policy_version: "1.0.0"
workspace_id: {workspace_id}
mode: audit

active_client: {client}
active_domain: "{domain}"

allowed_domains:
  - "{domain}"

# PROD is deliberately absent. Production work should be a decision, not a default.
allowed_environments:
  - DEV
  - QA

sensitive_tags:
  - "urn:li:tag:PII"
  - "urn:li:tag:Confidential"

protected_terms:
  - "urn:li:glossaryTerm:PersonalData"

# Assets whose breakage would be felt by someone other than you.
critical_downstream: []

# Zence's twelve built-in rules apply automatically. Add rules here only to
# tighten them; see the reference above.
""",
        encoding="utf-8",
    )

    console.print(f"[allow]✓[/allow] created {policy_path.relative_to(root)}")
    note("Starting in audit mode — nothing will be blocked until you switch to enforce.")
    note("Next: `zence doctor` to check the connection, then `zence status`.")


def main() -> None:  # pragma: no cover - console-script shim
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
