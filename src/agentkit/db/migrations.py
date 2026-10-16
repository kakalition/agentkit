"""Schema creation and Alembic plumbing (async)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import SQLModel


def _render_default(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"  # valid in both SQLite and Postgres
    if isinstance(value, (int, float)):
        return str(value)
    text_value = str(value)
    if not text_value:
        return "''"
    return "'" + text_value.replace("'", "''") + "'"


def _column_default_sql(column: Any) -> str | None:
    """A literal DEFAULT clause for a column, or ``None`` when unavailable."""
    server_default = getattr(column, "server_default", None)
    if server_default is not None and getattr(server_default, "arg", None) is not None:
        return str(server_default.arg)
    default = getattr(column, "default", None)
    if default is None:
        return None
    arg = getattr(default, "arg", None)
    if arg is None or callable(arg):
        return None
    return _render_default(arg)


def apply_missing_columns(connection: Connection, metadata: Any = None) -> list[str]:
    """Add columns present in the models but missing from existing tables (sync).

    Runs on a sync :class:`~sqlalchemy.Connection` (via ``run_sync`` from the async
    engine). Only *adds* columns (never drops or retypes): nullable columns are
    added bare, while NOT NULL columns are added with their default (skipped when
    they have no scalar/server default). Returns the ``table.column`` names added.
    """
    meta = metadata or SQLModel.metadata
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    added: list[str] = []
    for table in meta.sorted_tables:
        if table.name not in existing:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            default_sql = _column_default_sql(column)
            if not column.nullable and default_sql is None:
                continue
            ddl_type = column.type.compile(connection.dialect)
            clause = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'
            if default_sql is not None:
                clause += f" DEFAULT {default_sql}"
            connection.execute(text(clause))
            added.append(f"{table.name}.{column.name}")
    return added


async def sync_missing_columns(engine: AsyncEngine, metadata: Any = None) -> list[str]:
    """Async wrapper around :func:`apply_missing_columns`."""
    meta = metadata or SQLModel.metadata
    async with engine.begin() as connection:
        return await connection.run_sync(apply_missing_columns, meta)


def _ensure_fts(connection: Connection) -> bool:
    from agentkit.db.fts import ensure_fts

    return ensure_fts(connection)


def copy_team_definitions(connection: Connection) -> int:
    """Copy legacy ``team_definitions`` rows into ``definitions`` (``kind="team"``).

    Idempotent: rows already present for ``(owner_id, 'team', name)`` are skipped,
    and the old table is never modified or dropped. Returns the number copied.
    """
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if "team_definitions" not in tables or "definitions" not in tables:
        return 0
    rows = (
        connection.execute(
            text(
                "SELECT name, owner_id, kind, definition, created_at, updated_at "
                "FROM team_definitions"
            )
        )
        .mappings()
        .all()
    )
    copied = 0
    for row in rows:
        exists = connection.execute(
            text(
                "SELECT 1 FROM definitions "
                "WHERE owner_id = :owner_id AND kind = 'team' AND name = :name"
            ),
            {"owner_id": row["owner_id"], "name": row["name"]},
        ).first()
        if exists is not None:
            continue
        connection.execute(
            text(
                "INSERT INTO definitions "
                "(owner_id, kind, name, version, spec, created_at, updated_at) "
                "VALUES (:owner_id, 'team', :name, 1, :spec, "
                "COALESCE(:created_at, CURRENT_TIMESTAMP), "
                "COALESCE(:updated_at, CURRENT_TIMESTAMP))"
            ),
            {
                "owner_id": row["owner_id"],
                "name": row["name"],
                "spec": row["definition"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
        copied += 1
    return copied


async def init_db(engine: AsyncEngine, metadata: Any = None) -> None:
    """Create all tables (first-run convenience), then reconcile drift + FTS."""
    meta = metadata or SQLModel.metadata
    async with engine.begin() as connection:
        await connection.run_sync(meta.create_all)
        await connection.run_sync(apply_missing_columns, meta)
        await connection.run_sync(copy_team_definitions)
        await connection.run_sync(_ensure_fts)


def make_alembic_config(root: str | Path, *, database_url: str | None = None) -> Any:
    """Build an Alembic ``Config`` for a project whose ``alembic/`` dir is at ``root``."""
    from alembic.config import Config as AlembicConfig

    root = Path(root)
    config = AlembicConfig(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config
