"""Local audit trail.

SQLite at `~/.zence/zence.db`. Recording never raises: losing an audit row is
bad, taking down a session because the disk is full is worse, and the decision
has already been delivered by the time anything is written.
"""

from zence_core.audit.db import (
    DB_PATH_ENV,
    SCHEMA_VERSION,
    connect,
    default_db_path,
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

__all__ = [
    "DB_PATH_ENV",
    "SCHEMA_VERSION",
    "connect",
    "default_db_path",
    "get_decision",
    "list_decisions",
    "prune",
    "record_decision",
    "record_outcome",
    "record_writeback",
    "session_decisions",
    "session_row",
    "session_scope",
    "upsert_session",
    "upsert_workspace",
]
