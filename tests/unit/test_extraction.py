"""Asset-reference extraction.

Organised so that for every extractor there are three kinds of test: what it
must find, what it must *not* find, and what it does when its parser fails.

The must-not-find cases carry the most weight. An extractor that reports table
aliases, CTE names, SQL keywords, and filenames produces a prompt on every
action, users learn to approve reflexively, and the guardrail becomes a
formality. Precision is a safety property here, not a nicety.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from zence_core.extract import (
    extract_dbt,
    extract_mcp,
    extract_shell,
    extract_sql,
    extract_yaml,
    is_plausible_asset_name,
    normalize,
    redact,
)
from zence_core.schemas import Confidence, Intent


def names(refs: list) -> set[str]:  # type: ignore[type-arg]
    return {ref.raw_text for ref in refs}


# =============================================================================
# SQL
# =============================================================================


def test_sql_finds_both_sides_of_a_cross_client_join() -> None:
    """Scenario A, at the extraction layer."""
    result = extract_sql(
        """
        SELECT l.email, p.phone
        FROM northstar.marketing_leads l
        JOIN bluepeak.patient_contacts p ON p.email = l.email
        """
    )
    assert names(result.refs) == {
        "northstar.marketing_leads",
        "bluepeak.patient_contacts",
    }
    assert Intent.READ in result.intents


def test_sql_attributes_columns_through_aliases() -> None:
    """The denial says *which column*, which requires resolving `p` to its table."""
    result = extract_sql("SELECT p.phone, p.email FROM bluepeak.patient_contacts p")
    ref = next(r for r in result.refs if r.raw_text == "bluepeak.patient_contacts")
    assert ref.columns == ("email", "phone")


def test_sql_does_not_report_aliases_as_assets() -> None:
    result = extract_sql(
        "SELECT l.id FROM northstar.leads l JOIN northstar.orders o ON o.id = l.id"
    )
    assert "l" not in names(result.refs)
    assert "o" not in names(result.refs)


def test_sql_does_not_report_cte_names_as_assets() -> None:
    result = extract_sql(
        """
        WITH recent AS (SELECT * FROM northstar.leads)
        SELECT * FROM recent
        """
    )
    assert names(result.refs) == {"northstar.leads"}


def test_sql_does_not_report_keywords_as_assets() -> None:
    result = extract_sql("SELECT COUNT(*) FROM northstar.leads GROUP BY status")
    assert not {"select", "count", "group", "by", "status"} & {
        n.lower() for n in names(result.refs)
    }


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("DROP TABLE northstar.tmp", Intent.DESTRUCTIVE),
        ("TRUNCATE TABLE northstar.tmp", Intent.DESTRUCTIVE),
        ("DELETE FROM northstar.events", Intent.DESTRUCTIVE),
        ("DELETE FROM northstar.events WHERE id = 1", Intent.WRITE),
        ("INSERT INTO northstar.f SELECT * FROM northstar.s", Intent.WRITE),
        ("UPDATE northstar.dim SET x = 1", Intent.WRITE),
        ("CREATE TABLE northstar.new AS SELECT 1", Intent.WRITE),
        ("SELECT * FROM northstar.leads", Intent.READ),
    ],
)
def test_sql_intent_classification(sql: str, expected: Intent) -> None:
    assert expected in extract_sql(sql).intents


def test_delete_without_where_is_destructive_but_with_where_is_not() -> None:
    """The distinction that separates a targeted fix from emptying a table."""
    assert Intent.DESTRUCTIVE in extract_sql("DELETE FROM northstar.events").intents
    assert (
        Intent.DESTRUCTIVE not in extract_sql("DELETE FROM northstar.events WHERE id = 1").intents
    )


def test_sql_falls_back_when_parsing_fails() -> None:
    """A templated model still must not hide a cross-client reference."""
    result = extract_sql("{% if x %} not really sql {% endif %} bluepeak.patient_contacts")
    assert result.parsed is False
    assert "bluepeak.patient_contacts" in names(result.refs)
    assert all(ref.confidence is Confidence.MEDIUM for ref in result.refs)


def test_sql_fallback_ignores_bare_identifiers() -> None:
    """In unparseable text a bare word is far more likely a variable than a table."""
    result = extract_sql("{% garbage %} customers orders leads")
    assert result.refs == []


def test_empty_sql_is_not_an_error() -> None:
    assert extract_sql("").refs == []
    assert extract_sql("   ").refs == []


def test_sql_picks_up_verbatim_urns_at_exact_confidence() -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,northstar.leads,PROD)"
    result = extract_sql(f"-- see {urn}\nSELECT 1")
    ref = next(r for r in result.refs if r.raw_text == urn)
    assert ref.confidence is Confidence.EXACT
    assert ref.resolved_urn == urn


# =============================================================================
# dbt
# =============================================================================


def test_dbt_extracts_ref_and_source() -> None:
    result = extract_dbt(
        """
        SELECT * FROM {{ ref('dim_customer') }}
        JOIN {{ source('northstar_raw', 'orders') }} USING (id)
        """
    )
    assert names(result.refs) == {"dim_customer", "northstar_raw.orders"}
    assert all(ref.confidence is Confidence.HIGH for ref in result.refs)


def test_dbt_two_argument_ref_uses_the_model_not_the_package() -> None:
    result = extract_dbt("{{ ref('analytics_pkg', 'dim_customer') }}")
    assert names(result.refs) == {"dim_customer"}


def test_dbt_handles_whitespace_and_quote_variants() -> None:
    result = extract_dbt("""{{- ref("dim_customer")  -}} {{ref('fct_orders')}}""")
    assert names(result.refs) == {"dim_customer", "fct_orders"}


def test_dbt_model_path_implies_codegen() -> None:
    result = extract_dbt("{{ ref('x_model') }}", path="models/marts/revenue.sql")
    assert Intent.CODEGEN in result.intents


def test_plain_sql_is_not_dbt() -> None:
    assert extract_dbt("SELECT * FROM northstar.leads").refs == []


# =============================================================================
# Shell
# =============================================================================


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("rm -rf /tmp/build", Intent.DESTRUCTIVE),
        ("rm notes.txt", Intent.WRITE),
        ("bq rm -t northstar.tmp", Intent.DESTRUCTIVE),
        ("gsutil rm gs://bucket/x", Intent.DESTRUCTIVE),
        ("cp a.txt b.txt", Intent.WRITE),
        ("ls -la", Intent.READ),
    ],
)
def test_shell_intent_classification(command: str, expected: Intent) -> None:
    assert expected in extract_shell(command).intents


def test_rm_without_recursive_force_is_not_destructive() -> None:
    """`rm -rf` is the thing ZR-005 exists for; `rm file` is ordinary work."""
    assert Intent.DESTRUCTIVE not in extract_shell("rm one-file.txt").intents
    assert Intent.DESTRUCTIVE in extract_shell("rm -rf build/").intents


def test_shell_extracts_embedded_sql() -> None:
    result = extract_shell(
        "bq query --use_legacy_sql=false 'SELECT email FROM bluepeak.patient_contacts'"
    )
    assert "bluepeak.patient_contacts" in names(result.refs)
    assert result.embedded_sql


def test_shell_extracts_sql_from_psql_command_flag() -> None:
    result = extract_shell("""psql -c "SELECT * FROM northstar.marketing_leads" """)
    assert "northstar.marketing_leads" in names(result.refs)


def test_shell_judges_each_segment_of_a_pipeline() -> None:
    result = extract_shell("echo hello && rm -rf /tmp/x")
    assert Intent.DESTRUCTIVE in result.intents


def test_shell_detects_environment() -> None:
    assert extract_shell("dbt run --target prod").environment == "PROD"
    assert extract_shell("dbt run --target dev").environment == "DEV"


def test_shell_caps_argument_confidence_at_medium() -> None:
    """A bare argument cannot be trusted enough to trigger a deny on its own."""
    result = extract_shell("some-tool northstar.marketing_leads")
    for ref in result.refs:
        if ref.extractor == "shell":
            assert ref.confidence is Confidence.MEDIUM


def test_shell_ignores_paths_and_flags_as_asset_names() -> None:
    result = extract_shell("python3 scripts/seed.py --config config/prod.yaml")
    assert names(result.refs) == set()


def test_unbalanced_quotes_do_not_crash() -> None:
    assert extract_shell("""echo "unbalanced """).intents


def test_empty_command_is_not_an_error() -> None:
    assert extract_shell("").refs == []


# =============================================================================
# MCP arguments
# =============================================================================


def test_mcp_extracts_urn_from_a_datahub_tool() -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)"
    result = extract_mcp("mcp__datahub__get_entities", {"urns": [urn]})

    assert result.is_datahub
    assert names(result.refs) == {urn}
    assert all(ref.confidence is Confidence.EXACT for ref in result.refs)


def test_mcp_matches_the_plugin_bundled_server_name_too() -> None:
    """The matcher must cover both registration styles or interception has a hole."""
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,x.y,PROD)"
    assert extract_mcp("mcp__plugin_zence_datahub__get_entities", {"urn": urn}).is_datahub
    assert extract_mcp("mcp__datahub__get_entities", {"urn": urn}).is_datahub


def test_non_datahub_mcp_tool_is_ignored() -> None:
    result = extract_mcp("mcp__github__search_repositories", {"query": "a.b"})
    assert result.is_datahub is False
    assert result.refs == []


def test_mcp_mutation_tools_carry_mutate_intent() -> None:
    result = extract_mcp(
        "mcp__datahub__add_tags",
        {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,x.y,PROD)", "tags": ["PII"]},
    )
    assert Intent.MUTATE in result.intents


def test_mcp_read_tools_carry_read_or_search_intent() -> None:
    assert Intent.SEARCH in extract_mcp("mcp__datahub__search", {"query": "leads"}).intents
    assert Intent.READ in extract_mcp("mcp__datahub__get_lineage", {"urn": "x"}).intents


def test_mcp_prose_query_yields_no_reference() -> None:
    """Users type sentences into `query`. A phrase must not become an asset claim."""
    result = extract_mcp("mcp__datahub__search", {"query": "where are the marketing leads stored"})
    assert result.refs == []


def test_mcp_query_keeps_a_qualified_identifier_at_medium() -> None:
    result = extract_mcp("mcp__datahub__search", {"query": "bluepeak.patient_contacts"})
    assert names(result.refs) == {"bluepeak.patient_contacts"}
    assert all(ref.confidence is Confidence.MEDIUM for ref in result.refs)


def test_mcp_finds_urns_nested_deep_in_arguments() -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,x.y,PROD)"
    result = extract_mcp(
        "mcp__datahub__save_document",
        {"document": {"related_assets": [{"nested": urn}]}},
    )
    assert names(result.refs) == {urn}


def test_unknown_datahub_tool_is_not_assumed_harmless() -> None:
    result = extract_mcp("mcp__datahub__some_future_tool", {"urn": "x"})
    assert result.is_datahub
    assert result.intents


# =============================================================================
# YAML recipes
# =============================================================================


def test_yaml_recipe_extracts_table_patterns() -> None:
    result = extract_yaml(
        """
        source:
          type: snowflake
          config:
            table_pattern:
              allow:
                - "northstar.marketing_leads"
                - "bluepeak.patient_contacts.*"
        """
    )
    assert names(result.refs) == {"northstar.marketing_leads", "bluepeak.patient_contacts"}
    assert result.is_recipe


def test_yaml_recipe_never_reads_credential_values() -> None:
    """Recipes routinely carry secrets; none may reach an audit record."""
    result = extract_yaml(
        """
        source:
          config:
            password: "hunter2.supersecret"
            token: "abc.def.ghi"
            table_pattern:
              allow: ["northstar.leads"]
        """
    )
    assert names(result.refs) == {"northstar.leads"}
    assert not any("hunter2" in ref.raw_text for ref in result.refs)


def test_malformed_yaml_yields_nothing_rather_than_guesses() -> None:
    result = extract_yaml("key: [unclosed\n  bad: : :")
    assert result.parsed is False
    assert result.refs == []


def test_plain_yaml_is_not_a_recipe() -> None:
    assert extract_yaml("name: myapp\nversion: 1.0").is_recipe is False


# =============================================================================
# Name plausibility
# =============================================================================


@pytest.mark.parametrize(
    "name", ["northstar.marketing_leads", "db.schema.table", "customers", "fct_revenue"]
)
def test_plausible_names_are_accepted(name: str) -> None:
    assert is_plausible_asset_name(name)


@pytest.mark.parametrize(
    "name",
    ["select", "l", "p", "t1", "models.sql", "config.yaml", "script.py", "", "123"],
)
def test_implausible_names_are_rejected(name: str) -> None:
    assert not is_plausible_asset_name(name)


@pytest.mark.parametrize("name", ["db.schema.table", "warehouse.order", "raw.update_log"])
def test_qualified_names_survive_a_sql_keyword_component(name: str) -> None:
    """`table`, `order` and `update` are legitimate identifier parts.

    Stopwords are strict for bare identifiers, where they stop the fallback regex
    reporting `from` as an asset. Applying the same rule to qualified names would
    silently drop real warehouse paths — a false negative in a security tool,
    which is the expensive direction to be wrong in.
    """
    assert is_plausible_asset_name(name)


def test_an_all_stopword_qualified_name_is_still_rejected() -> None:
    assert not is_plausible_asset_name("select.from")


# =============================================================================
# Redaction
# =============================================================================


# These are assembled at runtime rather than written as literals. A file
# containing a credential-shaped constant trips the repository's own secret
# scanner, and the honest fix is to not commit the shape — not to allowlist the
# file, which would create somewhere a real secret could hide.
def _fake_github_token() -> str:
    return "ghp" + "_" + "a1b2c3d4e5" * 3 + "f6g7h8"


def _fake_api_key() -> str:
    return "sk" + "-" + "z9y8x7w6v5u4t3s2r1q0"


def _fake_jwt() -> str:
    return ".".join(["eyJ" + "hbGciOiJIUzI1NiJ9", "eyJ" + "zdWIiOiJ0ZXN0In0", "c2lnbmF0dXJl"])


@pytest.mark.parametrize(
    "make_secret", [_fake_github_token, _fake_api_key, _fake_jwt], ids=["pat", "api-key", "jwt"]
)
def test_secrets_are_redacted(make_secret: object) -> None:
    secret = make_secret()  # type: ignore[operator]
    assert secret not in redact(f"export CREDENTIAL={secret}")


def test_assignment_style_secrets_are_redacted() -> None:
    assert "hunter2" not in redact("DATAHUB_GMS_TOKEN=hunter2")
    assert "swordfish" not in redact('password: "swordfish"')


def test_email_addresses_are_redacted() -> None:
    """Zence's own audit trail must not become a place PII accumulates."""
    assert "dana@northstar.example" not in redact("contact dana@northstar.example")


def test_redaction_runs_before_truncation() -> None:
    """Truncating first could sever a secret's terminator and defeat the pattern."""
    from zence_core.schemas import MAX_EXCERPT_CHARS

    padding = "x" * (MAX_EXCERPT_CHARS - 20)
    assert _fake_github_token() not in redact(f"{_fake_github_token()} {padding}")


def test_redaction_bounds_length() -> None:
    from zence_core.schemas import MAX_EXCERPT_CHARS

    assert len(redact("y" * (MAX_EXCERPT_CHARS * 3))) <= MAX_EXCERPT_CHARS


# =============================================================================
# The router
# =============================================================================


def test_normalize_a_datahub_mcp_call(tmp_path: Path) -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,bluepeak.patient_contacts,PROD)"
    result = normalize("mcp__datahub__get_entities", {"urns": [urn]}, tmp_path)

    assert result.action.tool_kind.value == "mcp_catalog"
    assert names(result.refs) == {urn}


def test_normalize_a_bash_command(tmp_path: Path) -> None:
    result = normalize("Bash", {"command": "rm -rf build/"}, tmp_path)

    assert result.action.tool_kind.value == "shell"
    assert Intent.DESTRUCTIVE in result.action.intents
    assert result.action.is_sensitive


def test_normalize_a_sql_file_write(tmp_path: Path) -> None:
    result = normalize(
        "Write",
        {
            "file_path": "models/revenue.sql",
            "content": "SELECT * FROM northstar.fct_revenue_daily",
        },
        tmp_path,
    )

    assert "northstar.fct_revenue_daily" in names(result.refs)
    assert result.action.target_paths == ("models/revenue.sql",)


def test_normalize_flags_edits_to_zence_config(tmp_path: Path) -> None:
    result = normalize(
        "Edit", {"file_path": ".zence/policy.yaml", "new_string": "mode: audit"}, tmp_path
    )
    assert result.action.targets_zence_config is True


def test_normalize_flags_edits_to_claude_settings(tmp_path: Path) -> None:
    """Disabling the hooks is the same class of action as editing the policy."""
    result = normalize("Write", {"file_path": ".claude/settings.json", "content": "{}"}, tmp_path)
    assert result.action.targets_zence_config is True


def test_normalize_does_not_flag_ordinary_edits(tmp_path: Path) -> None:
    result = normalize(
        "Write", {"file_path": "models/revenue.sql", "content": "SELECT 1"}, tmp_path
    )
    assert result.action.targets_zence_config is False


def test_normalize_redacts_the_stored_excerpt(tmp_path: Path) -> None:
    result = normalize("Bash", {"command": "export DATAHUB_GMS_TOKEN=supersecretvalue"}, tmp_path)
    assert "supersecretvalue" not in result.action.input_excerpt


def test_normalize_handles_an_unknown_tool(tmp_path: Path) -> None:
    result = normalize("SomeFutureTool", {"weird": "input"}, tmp_path)
    assert result.action.intents
    assert result.refs == []
