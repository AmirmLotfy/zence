"""Seeding, verifying, and recording the synthetic demo catalog.

Three commands, in the order you use them:

    zence demo seed     push demo/catalog/catalog.yaml into DataHub
    zence demo verify   assert every entity, tag and lineage edge landed
    zence demo record   capture the live responses into a fixture

`verify` matters more than it looks. Seeding is a batch of upserts that mostly
succeed, and "mostly" is how a demo fails in front of judges — one missing
column tag and Scenario A quietly stops denying. So verify re-reads everything
through the same provider a hook would use, and exits non-zero on the first gap.

`record` is what keeps fixtures honest. Every fixture in this repository is a
capture of a real response from a real instance, never hand-written, and the
recording carries the endpoint and timestamp it came from.
"""

from __future__ import annotations

import json
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from zence_cli.output import ExitCode, console, emit_json, error, heading, note, warn
from zence_core.providers import FIXTURE_SCHEMA_VERSION, LiveProvider

# The SDK emits an ExperimentalWarning per entity constructed, which buried
# the seeding progress output. Silenced module-wide; the warning is about
# API stability, which is recorded in docs/DATAHUB_INTEGRATION.md instead.
warnings.filterwarnings("ignore", message=".*datahub SDK.*")

demo_app = typer.Typer(
    help="Stand up, check, and capture the synthetic two-client demo catalog.",
    no_args_is_help=True,
)

DEFAULT_CATALOG = Path("demo/catalog/catalog.yaml")


def _load_catalog(path: Path) -> dict[str, Any]:
    if not path.exists():
        error(f"no catalog at {path}")
        raise typer.Exit(ExitCode.ERROR)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        error(f"{path} is not a mapping")
        raise typer.Exit(ExitCode.ERROR)
    return data


def _require_sdk() -> Any:
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from datahub import sdk
    except ImportError:
        error(
            "the DataHub SDK is not installed.\n        Install it with `uv sync --extra datahub`."
        )
        raise typer.Exit(ExitCode.ERROR) from None
    return sdk


def _client(sdk: Any, url: str, token: str | None) -> Any:
    import warnings

    from datahub.ingestion.graph.client import DatahubClientConfig

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sdk.DataHubClient(
            config=DatahubClientConfig(server=url, token=token, timeout_sec=30)
        )


def _connection(url: str | None, token: str | None) -> tuple[str, str | None]:
    import os

    resolved_url = (
        url
        or os.environ.get("CLAUDE_PLUGIN_OPTION_DATAHUB_URL")
        or os.environ.get("DATAHUB_GMS_URL")
        or "http://localhost:8080"
    )
    resolved_token = (
        token
        or os.environ.get("CLAUDE_PLUGIN_OPTION_DATAHUB_TOKEN")
        or os.environ.get("DATAHUB_GMS_TOKEN")
    )
    return resolved_url, resolved_token


def dataset_urn(platform: str, name: str, env: str) -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env})"


def dashboard_urn(platform: str, dashboard_id: str) -> str:
    return f"urn:li:dashboard:({platform},{dashboard_id})"


def domain_urn(domain_id: str) -> str:
    return f"urn:li:domain:{domain_id}"


# =============================================================================
# seed
# =============================================================================


def _schema_fields(raw: list[dict[str, Any]]) -> list[Any]:
    """Build schema fields, attaching column-level tags and terms.

    Column-level classification is the realistic case — the dataset is fine, one
    column is not — and it is what lets a denial name the offending field. The
    simple `(name, type)` tuple form cannot carry tags, so tagged columns are
    built as full SchemaFieldClass objects.
    """
    from datahub.metadata.schema_classes import (
        AuditStampClass,
        BooleanTypeClass,
        DateTypeClass,
        GlobalTagsClass,
        GlossaryTermAssociationClass,
        GlossaryTermsClass,
        NumberTypeClass,
        SchemaFieldClass,
        SchemaFieldDataTypeClass,
        StringTypeClass,
        TagAssociationClass,
        TimeTypeClass,
    )

    type_map: dict[str, Any] = {
        "string": StringTypeClass(),
        "number": NumberTypeClass(),
        "boolean": BooleanTypeClass(),
        "date": DateTypeClass(),
        "time": TimeTypeClass(),
    }

    fields: list[Any] = []
    for column in raw:
        name = str(column["name"])
        kind = str(column.get("type", "string"))
        tags = column.get("tags") or []
        terms = column.get("terms") or []

        if not tags and not terms:
            fields.append((name, kind))
            continue

        fields.append(
            SchemaFieldClass(
                fieldPath=name,
                type=SchemaFieldDataTypeClass(type=type_map.get(kind, StringTypeClass())),
                nativeDataType=kind,
                globalTags=GlobalTagsClass(
                    tags=[TagAssociationClass(tag=f"urn:li:tag:{tag}") for tag in tags]
                )
                if tags
                else None,
                glossaryTerms=GlossaryTermsClass(
                    terms=[
                        GlossaryTermAssociationClass(urn=f"urn:li:glossaryTerm:{term}")
                        for term in terms
                    ],
                    auditStamp=AuditStampClass(time=0, actor="urn:li:corpuser:zence"),
                )
                if terms
                else None,
            )
        )
    return fields


def _emit_domain(client: Any, domain_id: str, name: str, description: str) -> None:
    """Domains have no `datahub.sdk` entity yet, so emit the aspect directly."""
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import DomainPropertiesClass

    client._graph.emit_mcp(
        MetadataChangeProposalWrapper(
            entityUrn=domain_urn(domain_id),
            aspect=DomainPropertiesClass(name=name, description=description),
        )
    )


@demo_app.command()
def seed(
    catalog: Annotated[
        Path, typer.Option("--catalog", help="Catalog definition file.")
    ] = DEFAULT_CATALOG,
    url: Annotated[str | None, typer.Option("--url", help="DataHub GMS URL.")] = None,
    token: Annotated[str | None, typer.Option("--token", help="DataHub token.")] = None,
) -> None:
    """Push the synthetic catalog into DataHub. Safe to re-run."""
    from datahub.metadata.urns import CorpUserUrn

    sdk = _require_sdk()
    data = _load_catalog(catalog)
    resolved_url, resolved_token = _connection(url, token)

    try:
        client = _client(sdk, resolved_url, resolved_token)
        client.test_connection()
    except Exception as exc:
        error(f"cannot reach DataHub at {resolved_url}: {exc}")
        raise typer.Exit(ExitCode.DATAHUB_UNREACHABLE) from None

    platform = str(data.get("platform", "snowflake"))
    heading(f"seeding {resolved_url}")

    for domain in data.get("domains", []):
        _emit_domain(client, domain["id"], domain["name"], domain.get("description", ""))
    note(f"{len(data.get('domains', []))} domains")

    for tag in data.get("tags", []):
        client.entities.upsert(sdk.Tag(name=tag["id"], description=tag.get("description", "")))
    note(f"{len(data.get('tags', []))} tags")

    for term in data.get("glossary_terms", []):
        client.entities.upsert(
            sdk.GlossaryTerm(id=term["id"], definition=term.get("description", ""))
        )
    note(f"{len(data.get('glossary_terms', []))} glossary terms")

    for dataset in data.get("datasets", []):
        entity = sdk.Dataset(
            platform=platform,
            name=dataset["name"],
            env=dataset.get("env", "PROD"),
            description=dataset.get("description", ""),
            domain=domain_urn(dataset["domain"]),
            owners=[CorpUserUrn(owner) for owner in dataset.get("owners", [])],
            tags=[f"urn:li:tag:{tag}" for tag in dataset.get("tags", [])],
            terms=[f"urn:li:glossaryTerm:{term}" for term in dataset.get("terms", [])],
            schema=_schema_fields(dataset.get("schema", [])),
        )
        client.entities.upsert(entity)

        if dataset.get("deprecated"):
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import DeprecationClass

            client._graph.emit_mcp(
                MetadataChangeProposalWrapper(
                    entityUrn=dataset_urn(platform, dataset["name"], dataset.get("env", "PROD")),
                    aspect=DeprecationClass(
                        deprecated=True,
                        note=dataset.get("deprecation_note", ""),
                        actor="urn:li:corpuser:zence",
                    ),
                )
            )
    note(f"{len(data.get('datasets', []))} datasets")

    for dashboard in data.get("dashboards", []):
        client.entities.upsert(
            sdk.Dashboard(
                name=dashboard["id"],
                platform=dashboard.get("platform", "looker"),
                display_name=dashboard.get("name"),
                description=dashboard.get("description", ""),
                domain=domain_urn(dashboard["domain"]),
                owners=[CorpUserUrn(owner) for owner in dashboard.get("owners", [])],
            )
        )
    note(f"{len(data.get('dashboards', []))} dashboards")

    edges = data.get("lineage", [])
    for edge in edges:
        client.lineage.add_lineage(
            upstream=_resolve_ref(platform, data, edge["upstream"]),
            downstream=_resolve_ref(platform, data, edge["downstream"]),
        )
    note(f"{len(edges)} lineage edges")

    console.print()
    console.print("[allow]✓[/allow] seeded — now run `zence demo verify`")


def _resolve_ref(platform: str, data: dict[str, Any], ref: str) -> str:
    """Turn a catalog reference into a URN.

    `dashboard:x` names a dashboard; anything else is a dataset, looked up in the
    catalog so its declared environment is used rather than guessed.
    """
    if ref.startswith("dashboard:"):
        dashboard_id = ref.split(":", 1)[1]
        for dashboard in data.get("dashboards", []):
            if dashboard["id"] == dashboard_id:
                return dashboard_urn(dashboard.get("platform", "looker"), dashboard_id)
        return dashboard_urn("looker", dashboard_id)

    for dataset in data.get("datasets", []):
        if dataset["name"] == ref:
            return dataset_urn(platform, ref, dataset.get("env", "PROD"))
    return dataset_urn(platform, ref, "PROD")


# =============================================================================
# verify
# =============================================================================


@demo_app.command()
def verify(
    catalog: Annotated[Path, typer.Option("--catalog")] = DEFAULT_CATALOG,
    url: Annotated[str | None, typer.Option("--url")] = None,
    token: Annotated[str | None, typer.Option("--token")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Assert the seeded catalog is complete. Exits non-zero on the first gap.

    Reads back through the same provider a hook uses, so this checks what Zence
    will actually see rather than what was sent.
    """
    from zence_core.extract.base import make_ref
    from zence_core.schemas import EvidenceStatus, Mode, WorkspaceContext

    data = _load_catalog(catalog)
    platform = str(data.get("platform", "snowflake"))
    resolved_url, resolved_token = _connection(url, token)

    provider = LiveProvider(server=resolved_url, token=resolved_token, timeout_seconds=30)
    health = provider.health()
    if not health.reachable:
        error(f"cannot reach DataHub: {health.detail}")
        raise typer.Exit(ExitCode.DATAHUB_UNREACHABLE)

    # A permissive workspace: this checks the catalog's contents, not a boundary.
    workspace = WorkspaceContext(
        workspace_id="demo-verify",
        root_path=str(Path.cwd()),
        mode=Mode.DEMO,
        active_client="verification",
        allowed_domains=frozenset(domain_urn(d["id"]) for d in data.get("domains", [])),
        critical_downstream=frozenset(
            dashboard_urn(d.get("platform", "looker"), d["id"]) for d in data.get("dashboards", [])
        ),
    )

    problems: list[str] = []
    checked = 0

    for dataset in data.get("datasets", []):
        name = dataset["name"]
        urn = dataset_urn(platform, name, dataset.get("env", "PROD"))
        [evidence] = provider.resolve([make_ref(urn, extractor="verify")], workspace)
        checked += 1

        if evidence.status is not EvidenceStatus.RESOLVED:
            problems.append(f"{name} ({dataset.get('env')}): {evidence.status.value}")
            continue

        expected_domain = domain_urn(dataset["domain"])
        if evidence.domain_urn != expected_domain:
            problems.append(
                f"{name}: domain is {evidence.domain_urn or '(none)'}, expected {expected_domain}"
            )

        for tag in dataset.get("tags", []):
            if f"urn:li:tag:{tag}" not in evidence.tags:
                problems.append(f"{name}: missing dataset tag {tag}")

        # Column-level tags are the ones that silently go missing, and the ones
        # Scenario A depends on.
        for column in dataset.get("schema", []):
            for tag in column.get("tags", []) or []:
                tagged = evidence.columns_tagged(frozenset({f"urn:li:tag:{tag}"}))
                if column["name"] not in tagged:
                    problems.append(f"{name}.{column['name']}: missing column tag {tag}")

        if dataset.get("deprecated") and evidence.lifecycle.value != "deprecated":
            problems.append(f"{name}: expected deprecated, got {evidence.lifecycle.value}")

    # The lineage path ZR-008 depends on.
    critical_edges = [
        edge for edge in data.get("lineage", []) if edge["downstream"].startswith("dashboard:")
    ]
    for edge in critical_edges:
        upstream = _resolve_ref(platform, data, edge["upstream"])
        [evidence] = provider.resolve([make_ref(upstream, extractor="verify")], workspace)
        checked += 1
        if not evidence.downstream_critical:
            problems.append(
                f"{edge['upstream']}: lineage to {edge['downstream']} not visible downstream"
            )

    if as_json:
        emit_json({"ok": not problems, "checked": checked, "problems": problems})
    else:
        heading("zence demo verify")
        note(f"{checked} entities checked against {resolved_url}")
        if problems:
            console.print()
            for problem in problems:
                console.print(f"  [deny]✗[/deny] {problem}")
            console.print()
            error(f"{len(problems)} problem(s) — re-run `zence demo seed`")
        else:
            console.print("[allow]✓[/allow] catalog is complete")

    if problems:
        raise typer.Exit(ExitCode.ERROR)


# =============================================================================
# record
# =============================================================================


@demo_app.command()
def record(
    output: Annotated[Path, typer.Option("--out", help="Where to write the fixture.")] = Path(
        "examples/artifacts/fixtures/demo-catalog.json"
    ),
    catalog: Annotated[Path, typer.Option("--catalog")] = DEFAULT_CATALOG,
    url: Annotated[str | None, typer.Option("--url")] = None,
    token: Annotated[str | None, typer.Option("--token")] = None,
) -> None:
    """Capture live DataHub responses into a fixture.

    This is the only supported way to produce a fixture. A hand-written one
    encodes what its author assumed DataHub returns, which is exactly the thing
    worth testing against reality.
    """
    from zence_core.extract.base import make_ref
    from zence_core.schemas import EvidenceStatus, Mode, WorkspaceContext

    data = _load_catalog(catalog)
    platform = str(data.get("platform", "snowflake"))
    resolved_url, resolved_token = _connection(url, token)

    provider = LiveProvider(server=resolved_url, token=resolved_token, timeout_seconds=30)
    health = provider.health()
    if not health.reachable:
        error(f"cannot reach DataHub: {health.detail}")
        raise typer.Exit(ExitCode.DATAHUB_UNREACHABLE)

    workspace = WorkspaceContext(
        workspace_id="demo-record",
        root_path=str(Path.cwd()),
        mode=Mode.DEMO,
        active_client="recording",
        allowed_domains=frozenset(domain_urn(d["id"]) for d in data.get("domains", [])),
        critical_downstream=frozenset(
            dashboard_urn(d.get("platform", "looker"), d["id"]) for d in data.get("dashboards", [])
        ),
    )

    entities: dict[str, Any] = {}
    missing: list[str] = []

    for dataset in data.get("datasets", []):
        name = dataset["name"]
        urn = dataset_urn(platform, name, dataset.get("env", "PROD"))
        [evidence] = provider.resolve([make_ref(urn, extractor="record")], workspace)

        if evidence.status is not EvidenceStatus.RESOLVED:
            missing.append(name)
            continue

        entities[name] = {
            "urn": evidence.urn,
            "name": evidence.name,
            "domain_urn": evidence.domain_urn,
            "domain_name": next(
                (d["name"] for d in data.get("domains", []) if d["id"] == dataset["domain"]),
                None,
            ),
            "owners": sorted(evidence.owners),
            "tags": sorted(evidence.tags),
            "terms": sorted(evidence.terms),
            "column_tags": [
                {
                    "field_path": column.field_path,
                    "tags": sorted(column.tags),
                    "terms": sorted(column.terms),
                }
                for column in evidence.column_tags
            ],
            "lifecycle": evidence.lifecycle.value,
            "environment": evidence.environment,
            "downstream_critical": list(evidence.downstream_critical),
        }

    if missing:
        warn(f"{len(missing)} dataset(s) not in the catalog and not recorded: {', '.join(missing)}")
        warn("run `zence demo seed` first")

    recording = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "recorded_at": datetime.now(UTC).isoformat(),
        "source_endpoint": resolved_url,
        "datahub_version": None,
        "note": (
            "Captured from a live DataHub instance by `zence demo record`. "
            "Do not edit by hand — re-record instead."
        ),
        "entities": entities,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(recording, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    console.print(f"[allow]✓[/allow] recorded {len(entities)} entities to {output}")
    if missing:
        raise typer.Exit(ExitCode.ERROR)
