"""Schema creation and Alembic plumbing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, inspect, text
from sqlmodel import SQLModel


def sync_missing_columns(engine: Engine, metadata: Any = None) -> list[str]:
    """Add columns that exist in the models but not in an existing table.

    ``create_all`` never alters existing tables, so a table created by an older
    release can drift from the model. This only *adds* missing nullable columns
    (never drops, retypes, or adds NOT NULL) so local upgrades keep working.
    Returns the ``table.column`` names that were added.
    """
    meta = metadata or SQLModel.metadata
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    added: list[str] = []
    with engine.begin() as conn:
        for table in meta.sorted_tables:
            if table.name not in existing:
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or not column.nullable:
                    continue
                ddl_type = column.type.compile(engine.dialect)
                conn.execute(
                    text(
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {ddl_type}'
                    )
                )
                added.append(f"{table.name}.{column.name}")
    return added


def init_db(engine: Engine, metadata: Any = None) -> None:
    """Create all tables (development/first-run convenience), then reconcile drift."""
    meta = metadata or SQLModel.metadata
    meta.create_all(engine)
    sync_missing_columns(engine, meta)


def make_alembic_config(root: str | Path, *, database_url: str | None = None) -> Any:
    """Build an Alembic ``Config`` for a project whose ``alembic/`` dir is at ``root``."""
    from alembic.config import Config as AlembicConfig

    root = Path(root)
    config = AlembicConfig(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config
