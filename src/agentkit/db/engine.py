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

from agentkit.contracts.database import Dialect
from agentkit.support import register_driver
from agentkit.support.kinds import DatabaseDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "DatabaseManager",
    "Dialect",
    "SQLiteDialect",
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
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
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


class SQLiteDialect:
    """The default dialect: libSQL/SQLite (and passthrough for other URLs)."""

    def async_url(self, url: str) -> str:
        return async_database_url(url)

    def create_engine(
        self, url: str, *, auth_token: str | None = None, echo: bool = False
    ) -> AsyncEngine:
        return create_async_db_engine(url, auth_token=auth_token, echo=echo)


class PostgresDialect(SQLiteDialect):
    """A Postgres-flavoured dialect (``asyncpg`` URL mapping + engine)."""


class DatabaseManager(Manager):
    """Resolves the configured DB dialect (``database_driver``, default ``sqlite``)."""

    kind = DriverKind.DATABASE
    default_driver = DatabaseDriver.SQLITE


@register_driver(DriverKind.DATABASE, DatabaseDriver.SQLITE)
def _sqlite_dialect_driver(app: Any) -> SQLiteDialect:
    return SQLiteDialect()


@register_driver(DriverKind.DATABASE, DatabaseDriver.POSTGRES)
def _postgres_dialect_driver(app: Any) -> PostgresDialect:
    return PostgresDialect()
