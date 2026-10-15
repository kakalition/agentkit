"""Async libSQL / SQLite engine wiring.

Sensible local defaults: WAL + a busy timeout so concurrent writers wait rather
than fail with "database is locked". The local default URL (``sqlite+libsql``)
is translated to the async ``sqlite+aiosqlite`` driver so the whole data layer is
async by default.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

__all__ = [
    "async_database_url",
    "create_async_db_engine",
    "make_async_session_factory",
    "session_scope",
]


def async_database_url(url: str) -> str:
    """Map a sync libSQL/SQLite URL to its async driver.

    Local files use ``sqlite+aiosqlite``; other URLs (e.g. a remote driver) are
    passed through unchanged.
    """
    if url.startswith("sqlite+libsql:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite+libsql:///") :]
    if url.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + url[len("sqlite://") :]
    return url


def create_async_db_engine(
    database_url: str, *, auth_token: str | None = None, echo: bool = False
) -> AsyncEngine:
    """Create an async SQLAlchemy engine for a libSQL/SQLite (or other) URL."""
    connect_args: dict[str, Any] = {}
    url = async_database_url(database_url)
    if auth_token and not url.startswith("sqlite"):
        connect_args["auth_token"] = auth_token
    kwargs: dict[str, Any] = {"connect_args": connect_args, "echo": echo, "future": True}
    if url.startswith("sqlite"):
        # A local SQLite file: no pooling benefit, and NullPool avoids reusing a
        # connection across event loops (e.g. the sync seam's private loop).
        kwargs["poolclass"] = NullPool
    engine = create_async_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
            except Exception:  # pragma: no cover - best effort  # nosec B110
                pass

    return engine


def make_async_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=SQLModelAsyncSession)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Transactional scope: commits on success, rolls back on error."""
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
