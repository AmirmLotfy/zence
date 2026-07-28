"""Audit persistence and write-back.

Two things carry the weight here:

* **Recording never breaks a session.** The decision has already been made and
  delivered by the time anything is written, so a full disk or a locked database
  costs an audit row, not a developer's afternoon.
* **Duplicate write-back is prevented structurally.** The DataHub document id is
  derived from workspace and session, so finalizing twice updates one record.
  There is no existence check to lose a race against.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import (
    bluepeak_pii_evidence,
    make_action,
    make_evidence,
    make_policy,
    make_ref,
    make_workspace,
)
from zence_core.audit import (
    connect,
    get_decision,
    list_decisions,
    prune,
    record_decision,
    record_outcome,
    record_writeback,
    session_decisions,
    session_row,
    session_scope,
    upsert_session,
    upsert_workspace,
)
from zence_core.policy import evaluate
from zence_core.schemas import Intent, Verdict
from zence_core.writeback import idempotency_key, write_session_document


@pytest.fixture
def db(tmp_path: Path, monkeypatch: Any) -> Iterator[sqlite3.Connection]:
    monkeypatch.setenv("ZENCE_DB_PATH", str(tmp_path / "zence.db"))
    connection = connect(tmp_path / "zence.db")
    yield connection
    connection.close()


def seed_decision(
    connection: sqlite3.Connection,
    *,
    session_id: str = "sess-1",
    intents: set[Intent] | None = None,
    evidence: Any = None,
) -> str:
    workspace = make_workspace()
    action = make_action(
        tool_name="Write", intents=intents or {Intent.READ}, input_excerpt="SELECT 1"
    )
    evidences = [evidence if evidence is not None else bluepeak_pii_evidence()]
    decision = evaluate(action, evidences, workspace, make_policy())

    workspace_pk = upsert_workspace(connection, workspace)
    session_pk = upsert_session(connection, workspace_pk, session_id, "enforce")
    return record_decision(
        connection,
        session_pk=session_pk,
        action=action,
        refs=[make_ref()],
        evidences=evidences,
        decision=decision,
    )


# =============================================================================
# Schema
# =============================================================================


def test_database_is_created_and_migrated(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "zence.db"
    connection = connect(path)

    assert path.exists()
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"workspace", "session", "action", "decision", "writeback"} <= tables
    connection.close()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "zence.db"
    connect(path).close()
    connect(path).close()

    connection = connect(path)
    versions = connection.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()
    assert versions["n"] == 1
    connection.close()


# =============================================================================
# Recording
# =============================================================================


def test_a_decision_is_recorded_with_its_evidence(db: sqlite3.Connection) -> None:
    decision_id = seed_decision(db)
    record = get_decision(db, decision_id)

    assert record is not None
    assert record["verdict"] == "deny"
    assert record["rule_id"] == "ZR-001"
    assert record["references"]
    assert record["evidence"]
    assert record["active_client"] == "Northstar Commerce"


def test_a_decision_can_be_fetched_by_id_prefix(db: sqlite3.Connection) -> None:
    """Nobody types a 32-character hex id."""
    decision_id = seed_decision(db)
    assert get_decision(db, decision_id[:8]) is not None


def test_workspace_is_upserted_not_duplicated(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="a")
    seed_decision(db, session_id="b")

    count = db.execute("SELECT COUNT(*) AS n FROM workspace").fetchone()["n"]
    assert count == 1


def test_sessions_are_distinct(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="a")
    seed_decision(db, session_id="b")

    count = db.execute("SELECT COUNT(*) AS n FROM session").fetchone()["n"]
    assert count == 2


def test_decisions_list_newest_first(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="a")
    seed_decision(db, session_id="b")

    rows = list_decisions(db, limit=10)
    assert len(rows) == 2
    assert rows[0]["created_at"] >= rows[1]["created_at"]


def test_decisions_can_be_filtered_by_verdict(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="denied")
    seed_decision(
        db,
        session_id="allowed",
        evidence=make_evidence(environment="DEV"),
    )

    assert len(list_decisions(db, verdict="deny")) == 1
    assert len(list_decisions(db, verdict="allow")) == 1


# =============================================================================
# Redaction
# =============================================================================


def test_no_secret_reaches_the_database(db: sqlite3.Connection) -> None:
    """Redaction happens at extraction, before anything is stored. There is no
    redact-on-read path, because that would mean the raw value was on disk."""
    from zence_core.extract import normalize

    secret = "ghp" + "_" + "s3cr3tv4lue" * 3
    workspace = make_workspace()
    normalized = normalize(
        "Bash", {"command": f"export TOKEN={secret}"}, Path("/tmp"), hook_event="PreToolUse"
    )
    decision = evaluate(normalized.action, [], workspace, make_policy())

    workspace_pk = upsert_workspace(db, workspace)
    session_pk = upsert_session(db, workspace_pk, "s", "enforce")
    record_decision(
        db,
        session_pk=session_pk,
        action=normalized.action,
        refs=[],
        evidences=[],
        decision=decision,
    )

    dumped = "\n".join(db.iterdump())
    assert secret not in dumped


# =============================================================================
# Outcomes
# =============================================================================


def test_an_outcome_attaches_to_its_decision(db: sqlite3.Connection) -> None:
    workspace = make_workspace()
    action = make_action(tool_name="Write", intents={Intent.READ})
    evidences = [make_evidence(environment="DEV")]
    decision = evaluate(action, evidences, workspace, make_policy())

    workspace_pk = upsert_workspace(db, workspace)
    session_pk = upsert_session(db, workspace_pk, "s", "enforce")
    decision_id = record_decision(
        db,
        session_pk=session_pk,
        action=action.model_copy(update={"tool_use_id": "toolu_42"}),
        refs=[],
        evidences=evidences,
        decision=decision,
    )

    assert record_outcome(db, tool_use_id="toolu_42", executed=True, success=True)

    record = get_decision(db, decision_id)
    assert record is not None
    assert record["outcome"][0]["success"] == 1


def test_a_failure_is_recorded_distinctly_from_a_denial(db: sqlite3.Connection) -> None:
    """A denied call never executes, so it has no outcome. A permitted call that
    then failed is a different fact."""
    workspace = make_workspace()
    action = make_action(tool_name="Bash", intents={Intent.READ})
    decision = evaluate(action, [], workspace, make_policy())

    workspace_pk = upsert_workspace(db, workspace)
    session_pk = upsert_session(db, workspace_pk, "s", "enforce")
    record_decision(
        db,
        session_pk=session_pk,
        action=action.model_copy(update={"tool_use_id": "toolu_99"}),
        refs=[],
        evidences=[],
        decision=decision,
    )

    record_outcome(db, tool_use_id="toolu_99", executed=True, success=False)

    row = db.execute("SELECT executed, success FROM outcome").fetchone()
    assert row["executed"] == 1
    assert row["success"] == 0


def test_an_outcome_for_an_unknown_tool_use_is_ignored(db: sqlite3.Connection) -> None:
    assert not record_outcome(db, tool_use_id="never-seen", executed=True, success=True)


# =============================================================================
# Write-back bookkeeping
# =============================================================================


def test_a_blocking_decision_marks_the_session_dirty(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="s")
    row = session_row(db, "s")
    assert row is not None
    assert row["writeback_dirty"] == 1


def test_an_uneventful_allow_does_not_mark_the_session_dirty(
    db: sqlite3.Connection,
) -> None:
    """Otherwise every session would produce a document saying nothing happened."""
    seed_decision(db, session_id="s", evidence=make_evidence(environment="DEV"))
    row = session_row(db, "s")
    assert row is not None
    assert row["writeback_dirty"] == 0


def test_write_back_is_recorded_once_per_key(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="s")
    row = session_row(db, "s")
    assert row is not None
    session_pk = row["session_pk"]

    first = record_writeback(
        db,
        session_pk=session_pk,
        idempotency_key="zence-session-abc",
        kind="session_document",
        target_urn=None,
        datahub_urn="urn:li:document:abc",
        status="confirmed",
    )
    second = record_writeback(
        db,
        session_pk=session_pk,
        idempotency_key="zence-session-abc",
        kind="session_document",
        target_urn=None,
        datahub_urn="urn:li:document:abc",
        status="confirmed",
    )

    assert first is True
    assert second is False, "the second attempt must be recognised as a repeat"

    count = db.execute("SELECT COUNT(*) AS n FROM writeback").fetchone()["n"]
    assert count == 1


def test_a_successful_write_back_clears_the_dirty_flag(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="s")
    row = session_row(db, "s")
    assert row is not None
    session_pk = row["session_pk"]

    record_writeback(
        db,
        session_pk=session_pk,
        idempotency_key="k",
        kind="session_document",
        target_urn=None,
        datahub_urn="urn:li:document:k",
        status="confirmed",
    )
    row = session_row(db, "s")
    assert row is not None
    assert row["writeback_dirty"] == 0


def test_session_decisions_are_ordered_for_the_document(db: sqlite3.Connection) -> None:
    seed_decision(db, session_id="s")
    seed_decision(db, session_id="s")

    decisions = session_decisions(db, "s")
    assert len(decisions) == 2
    assert decisions[0]["created_at"] <= decisions[1]["created_at"]


# =============================================================================
# Idempotency
# =============================================================================


def test_the_document_id_is_deterministic() -> None:
    assert idempotency_key("ws", "sess") == idempotency_key("ws", "sess")


def test_the_document_id_distinguishes_sessions_and_workspaces() -> None:
    assert idempotency_key("ws", "a") != idempotency_key("ws", "b")
    assert idempotency_key("a", "sess") != idempotency_key("b", "sess")


def test_the_document_id_is_readable_in_a_catalog() -> None:
    key = idempotency_key("northstar-analytics", "sess-1")
    assert key.startswith("zence-session-")
    assert len(key) < 40


def test_write_back_with_nothing_to_say_does_not_call_datahub() -> None:
    result = write_session_document(
        server="http://127.0.0.1:1",
        token=None,
        client_name="Northstar Commerce",
        workspace_id="ws",
        session_id="s",
        repository="repo",
        policy_version="1.0.0",
        decisions=[],
    )
    assert result.ok is False
    assert "nothing to record" in result.detail


def test_write_back_to_an_unreachable_catalog_fails_without_raising() -> None:
    result = write_session_document(
        server="http://127.0.0.1:1",
        token=None,
        client_name="Northstar Commerce",
        workspace_id="ws",
        session_id="s",
        repository="repo",
        policy_version="1.0.0",
        decisions=[
            {
                "verdict": "deny",
                "rule_id": "ZR-001",
                "rule_title": "Cross-client PII access",
                "reason": "…",
                "remediation": None,
                "evidence_urns": "[]",
                "degraded": 0,
                "would_have_been": None,
            }
        ],
    )
    assert result.ok is False
    assert result.idempotency_key.startswith("zence-session-")


def test_the_document_body_leads_with_what_was_blocked() -> None:
    from zence_core.writeback.document import _render

    body = _render(
        client_name="Northstar Commerce",
        workspace_id="northstar-analytics",
        session_id="sess-1",
        repository="northstar-analytics",
        policy_version="1.0.0",
        decisions=[
            {
                "verdict": "deny",
                "rule_id": "ZR-001",
                "rule_title": "Cross-client PII access",
                "reason": "bluepeak.patient_contacts belongs to BluePeak Health.",
                "remediation": "Use an asset inside Northstar Commerce.",
                "evidence_urns": '["urn:li:dataset:(x,bluepeak.patient_contacts,PROD)"]',
                "degraded": 0,
                "would_have_been": None,
            },
            {
                "verdict": "allow",
                "rule_id": "ZR-009",
                "rule_title": "In-boundary development read",
                "reason": "fine",
                "remediation": None,
                "evidence_urns": "[]",
                "degraded": 0,
                "would_have_been": None,
            },
        ],
    )

    assert "**1 blocked**" in body
    assert "## Blocked" in body
    assert body.index("## Blocked") < body.index("## Allowed")
    assert "bluepeak.patient_contacts" in body
    assert "Generated by Zence" in body


# =============================================================================
# Resilience
# =============================================================================


def test_an_unopenable_database_yields_none_rather_than_raising(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A hook calls this. Losing an audit row is acceptable; taking down the
    session because the disk is full is not."""
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("this is a file, so it cannot contain a database")
    monkeypatch.setenv("ZENCE_DB_PATH", str(blocked / "zence.db"))

    with session_scope() as connection:
        assert connection is None


def test_prune_removes_old_actions(db: sqlite3.Connection) -> None:
    seed_decision(db)
    assert prune(db, older_than_days=90) == 0
    assert prune(db, older_than_days=-1) == 1
    assert list_decisions(db) == []


# =============================================================================
# End to end
# =============================================================================


def test_a_denial_survives_the_full_round_trip(db: sqlite3.Connection) -> None:
    """Evaluate, record, read back — the evidence that justified the block is
    still there, which is what makes the audit trail worth keeping."""
    decision_id = seed_decision(db)
    record = get_decision(db, decision_id)

    assert record is not None
    assert record["verdict"] == Verdict.DENY.value
    assert "BluePeak Health" in record["reason"]
    assert any("bluepeak" in (e["urn"] or "") for e in record["evidence"])
    assert any("PII" in (e["tags"] or "") for e in record["evidence"])


def test_write_back_does_not_stall_when_the_catalog_is_unreachable() -> None:
    """The SDK retries with backoff by default, which made this take 28 seconds
    against a dead endpoint — inside the Stop hook, so every session would have
    appeared to hang at the end. Retries are disabled; the hook is the retry.
    """
    import time

    started = time.monotonic()
    write_session_document(
        server="http://127.0.0.1:1",
        token=None,
        client_name="Northstar Commerce",
        workspace_id="ws",
        session_id="s",
        repository="repo",
        policy_version="1.0.0",
        decisions=[
            {
                "verdict": "deny",
                "rule_id": "ZR-001",
                "rule_title": "t",
                "reason": "x",
                "remediation": None,
                "evidence_urns": "[]",
                "degraded": 0,
                "would_have_been": None,
            }
        ],
    )
    elapsed = time.monotonic() - started

    assert elapsed < 5.0, f"write-back took {elapsed:.1f}s; retries are not disabled"
