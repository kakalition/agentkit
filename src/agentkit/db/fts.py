"""Full-text search over messages (SQLite FTS5), with a graceful fallback.

The ``messages_fts`` table is an *external-content* FTS5 index over the
``messages.payload`` column, kept in sync by triggers. If FTS5 is unavailable
(some libSQL builds) :func:`ensure_fts` returns ``False`` and callers fall back
to ``LIKE`` (see :meth:`agentkit.db.repositories.conversations.MessageRepo.search_text`).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

__all__ = ["ensure_fts", "fts_available"]

_FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts "
    "USING fts5(payload, content='messages', content_rowid='rowid')",
    "CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN "
    "INSERT INTO messages_fts(rowid, payload) VALUES (new.rowid, new.payload); END",
    "CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN "
    "INSERT INTO messages_fts(messages_fts, rowid, payload) "
    "VALUES ('delete', old.rowid, old.payload); END",
    "CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN "
    "INSERT INTO messages_fts(messages_fts, rowid, payload) "
    "VALUES ('delete', old.rowid, old.payload); "
    "INSERT INTO messages_fts(rowid, payload) VALUES (new.rowid, new.payload); END",
    "INSERT INTO messages_fts(rowid, payload) "
    "SELECT rowid, payload FROM messages "
    "WHERE rowid NOT IN (SELECT rowid FROM messages_fts)",
)


def ensure_fts(connection: Any) -> bool:
    """Create the FTS5 index + triggers (sync ; run via ``run_sync``). Idempotent.

    Returns ``True`` when the index is available, ``False`` when FTS5 is not
    compiled in (the caller then relies on the ``LIKE`` fallback).
    """
    try:
        for statement in _FTS_DDL:
            connection.execute(text(statement))
        return True
    except Exception:  # pragma: no cover - depends on the SQLite build
        return False


def fts_available(connection: Any) -> bool:
    """Whether the FTS5 module is compiled into this SQLite build."""
    try:
        connection.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)"))
        connection.execute(text("DROP TABLE IF EXISTS _fts_probe"))
        return True
    except Exception:  # pragma: no cover - depends on the SQLite build
        return False
