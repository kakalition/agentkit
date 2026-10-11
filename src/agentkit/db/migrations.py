"""Schema creation and Alembic plumbing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import SQLModel


def init_db(engine: Engine, metadata: Any = None) -> None:
    """Create all tables (development/first-run convenience)."""
    (metadata or SQLModel.metadata).create_all(engine)


def make_alembic_config(root: str | Path, *, database_url: str | None = None) -> Any:
    """Build an Alembic ``Config`` for a project whose ``alembic/`` dir is at ``root``."""
    from alembic.config import Config as AlembicConfig

    root = Path(root)
    config = AlembicConfig(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config
