"""The local audit database.

SQLite, stdlib only, at `~/.zence/zence.db`. No ORM: the schema is nine tables
and the queries are simple, so an ORM would add a dependency and a layer without
removing any work.

Two properties matter more than anything else here:

**Nothing sensitive is stored.** Redaction happens at the extraction boundary,
before a value ever reaches this module. There is no "redact on read" path,
because that would mean the raw value was on disk the whole time.

**Writing must never break a session.** Every function in this module swallows
its own storage errors. A full disk or a locked database is a reason to lose an
audit row, not a reason for Claude Code to stop working — the decision has
already been made and delivered by then.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zence_core.schemas import (
    Action,
    AssetRef,
    Decision,
    Evidence,
    WorkspaceContext,
)

SCHEMA_VERSION = 1

#: Overridable so tests and `--db` never touch a developer's real history.
DB_PATH_ENV = "ZENCE_DB_PATH"

#: Ordered. Each migration runs once; `schema_version` records how far we got.
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE workspace (
        id            TEXT PRIMARY KEY,
        root_path     TEXT NOT NULL UNIQUE,
        workspace_id  TEXT NOT NULL,
        active_client TEXT NOT NULL,
        active_domain TEXT,
        mode          TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        policy_sha256 TEXT,
        first_seen_at TEXT NOT NULL
    );

    CREATE TABLE session (
        id                TEXT PRIMARY KEY,
        workspace_pk      TEXT NOT NULL REFERENCES workspace(id),
        claude_session_id TEXT NOT NULL,
        mode              TEXT NOT NULL,
        started_at        TEXT NOT NULL,
        ended_at          TEXT,
        writeback_dirty   INTEGER NOT NULL DEFAULT 0
    );
    CREATE UNIQUE INDEX idx_session_claude ON session(claude_session_id);

    CREATE TABLE action (
        id             TEXT PRIMARY KEY,
        session_pk     TEXT NOT NULL REFERENCES session(id),
        tool_use_id    TEXT,
        tool_name      TEXT NOT NULL,
        tool_kind      TEXT NOT NULL,
        hook_event     TEXT NOT NULL,
        intents        TEXT NOT NULL,
        input_excerpt  TEXT NOT NULL,
        target_paths   TEXT NOT NULL,
        created_at     TEXT NOT NULL
    );
    CREATE INDEX idx_action_session ON action(session_pk, created_at);
    CREATE INDEX idx_action_tool_use ON action(tool_use_id);

    CREATE TABLE asset_ref (
        id           TEXT PRIMARY KEY,
        action_pk    TEXT NOT NULL REFERENCES action(id),
        raw_text     TEXT NOT NULL,
        kind         TEXT NOT NULL,
        confidence   TEXT NOT NULL,
        extractor    TEXT NOT NULL,
        resolved_urn TEXT
    );
    CREATE INDEX idx_asset_ref_urn ON asset_ref(resolved_urn);

    CREATE TABLE evidence (
        id                  TEXT PRIMARY KEY,
        action_pk           TEXT NOT NULL REFERENCES action(id),
        urn                 TEXT,
        name                TEXT,
        status              TEXT NOT NULL,
        provider            TEXT NOT NULL,
        domain_urn          TEXT,
        domain_name         TEXT,
        owners              TEXT NOT NULL,
        tags                TEXT NOT NULL,
        terms               TEXT NOT NULL,
        column_tags         TEXT NOT NULL,
        lifecycle           TEXT NOT NULL,
        environment         TEXT,
        downstream_critical TEXT NOT NULL,
        failure_reason      TEXT,
        fetched_at          TEXT NOT NULL
    );
    CREATE INDEX idx_evidence_action ON evidence(action_pk);

    CREATE TABLE decision (
        id                  TEXT PRIMARY KEY,
        action_pk           TEXT NOT NULL REFERENCES action(id),
        verdict             TEXT NOT NULL,
        source              TEXT NOT NULL,
        risk                TEXT NOT NULL,
        rule_id             TEXT NOT NULL,
        rule_title          TEXT NOT NULL,
        policy_version      TEXT NOT NULL,
        mode                TEXT NOT NULL,
        reason              TEXT NOT NULL,
        remediation         TEXT,
        evidence_urns       TEXT NOT NULL,
        matched_tags        TEXT NOT NULL,
        matched_columns     TEXT NOT NULL,
        downstream_critical TEXT NOT NULL,
        provider            TEXT,
        degraded            INTEGER NOT NULL,
        degraded_reason     TEXT,
        exception_applied   TEXT,
        would_have_been     TEXT,
        created_at          TEXT NOT NULL
    );
    CREATE INDEX idx_decision_action ON decision(action_pk);
    CREATE INDEX idx_decision_created ON decision(created_at);

    CREATE TABLE outcome (
        id          TEXT PRIMARY KEY,
        decision_pk TEXT NOT NULL REFERENCES decision(id),
        executed    INTEGER NOT NULL,
        success     INTEGER NOT NULL,
        summary     TEXT,
        created_at  TEXT NOT NULL
    );
    CREATE INDEX idx_outcome_decision ON outcome(decision_pk);

    CREATE TABLE writeback (
        id              TEXT PRIMARY KEY,
        session_pk      TEXT NOT NULL REFERENCES session(id),
        idempotency_key TEXT NOT NULL UNIQUE,
        kind            TEXT NOT NULL,
        target_urn      TEXT,
        datahub_urn     TEXT,
        status          TEXT NOT NULL,
        detail          TEXT,
        attempted_at    TEXT NOT NULL,
        confirmed_at    TEXT
    );

    CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
    """,
)


def default_db_path() -> Path:
    override = os.environ.get(DB_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".zence" / "zence.db"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _dump(value: Any) -> str:
    """Sets and tuples are stored as sorted JSON so rows compare stably."""
    if isinstance(value, frozenset | set):
        return json.dumps(sorted(str(item) for item in value))
    if isinstance(value, list | tuple):
        return json.dumps([str(item) for item in value])
    return json.dumps(value, default=str)


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database, creating and migrating it if needed."""
    target = path or default_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(target, timeout=5.0)
    connection.row_factory = sqlite3.Row
    # WAL so a long-running read (`zence audit list`) never blocks a hook trying
    # to record a decision.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _migrate(connection)
    return connection


def _migrate(connection: sqlite3.Connection) -> None:
    current = 0
    try:
        row = connection.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = int(row["v"] or 0)
    except sqlite3.OperationalError:
        current = 0

    for index, statements in enumerate(MIGRATIONS, start=1):
        if index <= current:
            continue
        connection.executescript(statements)
        connection.execute("INSERT INTO schema_version (version) VALUES (?)", (index,))
        connection.commit()


@contextmanager
def session_scope(path: Path | None = None) -> Iterator[sqlite3.Connection | None]:
    """Yield a connection, or None if the database cannot be opened.

    Callers treat None as "skip recording". Losing an audit row is bad; taking
    down a developer's session because the disk is full is worse, and the
    decision has already been delivered by the time we get here.
    """
    connection: sqlite3.Connection | None = None
    try:
        connection = connect(path)
        yield connection
        connection.commit()
    except (sqlite3.Error, OSError):
        if connection is not None:
            with contextlib.suppress(sqlite3.Error):
                connection.rollback()
        yield None
    finally:
        if connection is not None:
            with contextlib.suppress(sqlite3.Error):
                connection.close()


# --- Writers -----------------------------------------------------------------


def upsert_workspace(connection: sqlite3.Connection, workspace: WorkspaceContext) -> str:
    row = connection.execute(
        "SELECT id FROM workspace WHERE root_path = ?", (workspace.root_path,)
    ).fetchone()

    if row is not None:
        connection.execute(
            """UPDATE workspace SET active_client=?, active_domain=?, mode=?,
                   policy_version=?, policy_sha256=? WHERE id=?""",
            (
                workspace.active_client,
                workspace.active_domain,
                workspace.mode.value,
                workspace.policy_version,
                workspace.policy_sha256,
                row["id"],
            ),
        )
        return str(row["id"])

    workspace_pk = _new_id()
    connection.execute(
        """INSERT INTO workspace
           (id, root_path, workspace_id, active_client, active_domain, mode,
            policy_version, policy_sha256, first_seen_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            workspace_pk,
            workspace.root_path,
            workspace.workspace_id,
            workspace.active_client,
            workspace.active_domain,
            workspace.mode.value,
            workspace.policy_version,
            workspace.policy_sha256,
            _now(),
        ),
    )
    return workspace_pk


def upsert_session(
    connection: sqlite3.Connection,
    workspace_pk: str,
    claude_session_id: str,
    mode: str,
) -> str:
    row = connection.execute(
        "SELECT id FROM session WHERE claude_session_id = ?", (claude_session_id,)
    ).fetchone()
    if row is not None:
        return str(row["id"])

    session_pk = _new_id()
    connection.execute(
        """INSERT INTO session
           (id, workspace_pk, claude_session_id, mode, started_at)
           VALUES (?,?,?,?,?)""",
        (session_pk, workspace_pk, claude_session_id, mode, _now()),
    )
    return session_pk


def record_decision(
    connection: sqlite3.Connection,
    *,
    session_pk: str,
    action: Action,
    refs: Sequence[AssetRef],
    evidences: Sequence[Evidence],
    decision: Decision,
) -> str:
    """Store one evaluation. Returns the decision id."""
    action_pk = _new_id()
    connection.execute(
        """INSERT INTO action
           (id, session_pk, tool_use_id, tool_name, tool_kind, hook_event,
            intents, input_excerpt, target_paths, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            action_pk,
            session_pk,
            action.tool_use_id,
            action.tool_name,
            action.tool_kind.value,
            action.hook_event,
            _dump(sorted(intent.value for intent in action.intents)),
            action.input_excerpt,
            _dump(action.target_paths),
            _now(),
        ),
    )

    for ref in refs:
        connection.execute(
            """INSERT INTO asset_ref
               (id, action_pk, raw_text, kind, confidence, extractor, resolved_urn)
               VALUES (?,?,?,?,?,?,?)""",
            (
                _new_id(),
                action_pk,
                ref.raw_text,
                ref.kind.value,
                ref.confidence.value,
                ref.extractor,
                ref.resolved_urn,
            ),
        )

    for evidence in evidences:
        connection.execute(
            """INSERT INTO evidence
               (id, action_pk, urn, name, status, provider, domain_urn, domain_name,
                owners, tags, terms, column_tags, lifecycle, environment,
                downstream_critical, failure_reason, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _new_id(),
                action_pk,
                evidence.urn,
                evidence.name,
                evidence.status.value,
                evidence.provider.value,
                evidence.domain_urn,
                evidence.domain_name,
                _dump(evidence.owners),
                _dump(evidence.tags),
                _dump(evidence.terms),
                _dump(
                    [
                        {"field_path": c.field_path, "tags": sorted(c.tags)}
                        for c in evidence.column_tags
                    ]
                ),
                evidence.lifecycle.value,
                evidence.environment,
                _dump(evidence.downstream_critical),
                evidence.failure_reason,
                evidence.fetched_at.isoformat(),
            ),
        )

    decision_pk = _new_id()
    connection.execute(
        """INSERT INTO decision
           (id, action_pk, verdict, source, risk, rule_id, rule_title,
            policy_version, mode, reason, remediation, evidence_urns,
            matched_tags, matched_columns, downstream_critical, provider,
            degraded, degraded_reason, exception_applied, would_have_been, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            decision_pk,
            action_pk,
            decision.verdict.value,
            decision.source.value,
            decision.risk.value,
            decision.rule_id,
            decision.rule_title,
            decision.policy_version,
            decision.mode.value,
            decision.reason,
            decision.remediation,
            _dump(decision.evidence_urns),
            _dump(decision.matched_tags),
            _dump(decision.matched_columns),
            _dump(decision.downstream_critical),
            decision.provider.value if decision.provider else None,
            1 if decision.degraded else 0,
            decision.degraded_reason,
            decision.exception_applied,
            decision.would_have_been.value if decision.would_have_been else None,
            _now(),
        ),
    )

    # Only a decision that concluded something is worth writing back. An
    # uneventful allow would make every session produce a document saying
    # nothing happened.
    if decision.verdict.value != "allow" or decision.would_have_been:
        connection.execute("UPDATE session SET writeback_dirty = 1 WHERE id = ?", (session_pk,))

    return decision_pk


def record_outcome(
    connection: sqlite3.Connection,
    *,
    tool_use_id: str,
    executed: bool,
    success: bool,
    summary: str | None = None,
) -> bool:
    """Attach an execution result to the decision that permitted it."""
    row = connection.execute(
        """SELECT d.id AS decision_pk FROM decision d
           JOIN action a ON a.id = d.action_pk
           WHERE a.tool_use_id = ? ORDER BY d.created_at DESC LIMIT 1""",
        (tool_use_id,),
    ).fetchone()
    if row is None:
        return False

    connection.execute(
        """INSERT INTO outcome (id, decision_pk, executed, success, summary, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            _new_id(),
            row["decision_pk"],
            1 if executed else 0,
            1 if success else 0,
            summary,
            _now(),
        ),
    )
    return True


def record_writeback(
    connection: sqlite3.Connection,
    *,
    session_pk: str,
    idempotency_key: str,
    kind: str,
    target_urn: str | None,
    datahub_urn: str | None,
    status: str,
    detail: str | None = None,
) -> bool:
    """Record a write-back attempt.

    The UNIQUE constraint on `idempotency_key` is the local half of duplicate
    prevention; the deterministic DataHub document id is the half that actually
    matters. Returns False when this key has already been written.
    """
    try:
        connection.execute(
            """INSERT INTO writeback
               (id, session_pk, idempotency_key, kind, target_urn, datahub_urn,
                status, detail, attempted_at, confirmed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                _new_id(),
                session_pk,
                idempotency_key,
                kind,
                target_urn,
                datahub_urn,
                status,
                detail,
                _now(),
                _now() if status == "confirmed" else None,
            ),
        )
    except sqlite3.IntegrityError:
        connection.execute(
            """UPDATE writeback SET status=?, datahub_urn=?, detail=?, confirmed_at=?
               WHERE idempotency_key=?""",
            (
                status,
                datahub_urn,
                detail,
                _now() if status == "confirmed" else None,
                idempotency_key,
            ),
        )
        return False

    connection.execute("UPDATE session SET writeback_dirty = 0 WHERE id = ?", (session_pk,))
    return True


# --- Readers -----------------------------------------------------------------


def list_decisions(
    connection: sqlite3.Connection,
    *,
    limit: int = 50,
    workspace_root: str | None = None,
    verdict: str | None = None,
) -> list[dict[str, Any]]:
    query = """
        SELECT d.id, d.verdict, d.rule_id, d.rule_title, d.reason, d.risk,
               d.degraded, d.created_at, d.exception_applied, d.would_have_been,
               a.tool_name, a.hook_event,
               w.active_client, w.root_path,
               o.executed, o.success
        FROM decision d
        JOIN action a    ON a.id = d.action_pk
        JOIN session s   ON s.id = a.session_pk
        JOIN workspace w ON w.id = s.workspace_pk
        LEFT JOIN outcome o ON o.decision_pk = d.id
    """
    clauses: list[str] = []
    params: list[Any] = []
    if workspace_root:
        clauses.append("w.root_path = ?")
        params.append(workspace_root)
    if verdict:
        clauses.append("d.verdict = ?")
        params.append(verdict)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY d.created_at DESC LIMIT ?"
    params.append(limit)

    return [dict(row) for row in connection.execute(query, params).fetchall()]


def get_decision(connection: sqlite3.Connection, decision_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT d.*, a.tool_name, a.tool_kind, a.hook_event, a.input_excerpt,
                  a.target_paths, a.intents, a.id AS action_pk,
                  w.active_client, w.root_path, w.active_domain
           FROM decision d
           JOIN action a    ON a.id = d.action_pk
           JOIN session s   ON s.id = a.session_pk
           JOIN workspace w ON w.id = s.workspace_pk
           WHERE d.id = ? OR d.id LIKE ?""",
        (decision_id, f"{decision_id}%"),
    ).fetchone()
    if row is None:
        return None

    record = dict(row)
    record["references"] = [
        dict(r)
        for r in connection.execute(
            "SELECT raw_text, kind, confidence, extractor, resolved_urn "
            "FROM asset_ref WHERE action_pk = ?",
            (record["action_pk"],),
        ).fetchall()
    ]
    record["evidence"] = [
        dict(r)
        for r in connection.execute(
            "SELECT urn, name, status, provider, domain_urn, domain_name, tags, "
            "terms, column_tags, lifecycle, environment, downstream_critical, "
            "failure_reason FROM evidence WHERE action_pk = ?",
            (record["action_pk"],),
        ).fetchall()
    ]
    record["outcome"] = [
        dict(r)
        for r in connection.execute(
            "SELECT executed, success, summary, created_at FROM outcome WHERE decision_pk = ?",
            (record["id"],),
        ).fetchall()
    ]
    return record


def session_decisions(
    connection: sqlite3.Connection, claude_session_id: str
) -> list[dict[str, Any]]:
    """Everything decided in one session, oldest first — the write-back input."""
    return [
        dict(row)
        for row in connection.execute(
            """SELECT d.id, d.verdict, d.rule_id, d.rule_title, d.reason,
                      d.remediation, d.risk, d.evidence_urns, d.matched_tags,
                      d.matched_columns, d.downstream_critical, d.degraded,
                      d.exception_applied, d.would_have_been, d.policy_version,
                      d.created_at, a.tool_name
               FROM decision d
               JOIN action a  ON a.id = d.action_pk
               JOIN session s ON s.id = a.session_pk
               WHERE s.claude_session_id = ?
               ORDER BY d.created_at ASC""",
            (claude_session_id,),
        ).fetchall()
    ]


def session_row(connection: sqlite3.Connection, claude_session_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT s.id AS session_pk, s.writeback_dirty, s.mode,
                  w.active_client, w.root_path, w.workspace_id, w.active_domain,
                  w.policy_version
           FROM session s JOIN workspace w ON w.id = s.workspace_pk
           WHERE s.claude_session_id = ?""",
        (claude_session_id,),
    ).fetchone()
    return dict(row) if row else None


def prune(connection: sqlite3.Connection, *, older_than_days: int = 90) -> int:
    """Delete decisions older than the retention window."""
    cutoff = datetime.now(UTC).timestamp() - older_than_days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=UTC).isoformat()

    actions = [
        row["id"]
        for row in connection.execute(
            "SELECT id FROM action WHERE created_at < ?", (cutoff_iso,)
        ).fetchall()
    ]
    if not actions:
        return 0

    placeholders = ",".join("?" * len(actions))
    connection.execute(
        f"DELETE FROM outcome WHERE decision_pk IN "  # noqa: S608 - placeholders are generated, not interpolated data
        f"(SELECT id FROM decision WHERE action_pk IN ({placeholders}))",
        actions,
    )
    for table in ("decision", "evidence", "asset_ref"):
        connection.execute(
            f"DELETE FROM {table} WHERE action_pk IN ({placeholders})",  # noqa: S608
            actions,
        )
    connection.execute(
        f"DELETE FROM action WHERE id IN ({placeholders})",  # noqa: S608
        actions,
    )
    return len(actions)
