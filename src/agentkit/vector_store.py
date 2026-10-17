"""Vector stores for semantic recall (contract + drivers).

The default ``repository`` driver ranks with the numpy cosine scan used elsewhere
(:func:`agentkit.embeddings.similarity_scores`), so recall results are
byte-identical to the built-in path. ``sqlite_vec`` (the optional ``vec`` extra)
and ``pgvector`` are real accelerators selected with ``vector_store_driver`` or
registered via ``app.extend("vector", name, factory)``.

Memory recall and RAG retrieval rank through :meth:`VectorStore.rank` (the
caller-supplied vectors already live in the database); the indexed
:meth:`VectorStore.query` is used for stores that hold their own vectors.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agentkit.contracts.vector_store import VectorHit, VectorStore
from agentkit.embeddings import similarity_scores, sqlite_vec_available
from agentkit.errors import ConfigurationError
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, VectorStoreDriver
from agentkit.support.manager import Manager

__all__ = [
    "NumpyVectorStore",
    "PgVectorStore",
    "SqliteVecVectorStore",
    "VectorHit",
    "VectorStore",
    "VectorStoreManager",
    "current_vector_store",
]


def _cosine_rank(
    vector: Sequence[float],
    items: Sequence[tuple[str, Sequence[float]]],
    limit: int | None,
) -> list[VectorHit]:
    """Rank ``items`` by cosine similarity to ``vector`` (stable on ties)."""
    if not items:
        return []
    scores = similarity_scores(vector, [list(item_vector) for _, item_vector in items])
    hits = [VectorHit(id=key, score=score) for (key, _), score in zip(items, scores, strict=True)]
    # sort is stable, so equal scores keep their original (candidate) order.
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits if limit is None else hits[:limit]


class NumpyVectorStore:
    """The ``repository`` driver: an in-process store ranked with the numpy cosine scan."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, tuple[list[float], dict[str, Any]]]] = {}

    async def upsert(
        self,
        collection: str,
        id: str,
        vector: list[float],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._rows.setdefault(collection, {})[id] = (list(vector), dict(metadata or {}))

    async def query(
        self, collection: str, vector: list[float], *, limit: int = 5
    ) -> list[VectorHit]:
        rows = self._rows.get(collection, {})
        if not rows:
            return []
        ranked = _cosine_rank(vector, [(key, rows[key][0]) for key in rows], limit)
        for hit in ranked:
            hit.metadata = dict(rows[hit.id][1])
        return ranked

    async def rank(
        self,
        collection: str,
        vector: Sequence[float],
        items: Sequence[tuple[str, Sequence[float]]],
        *,
        limit: int | None = None,
    ) -> list[VectorHit]:
        return _cosine_rank(vector, items, limit)

    async def delete(self, collection: str, id: str) -> bool:
        return self._rows.get(collection, {}).pop(id, None) is not None

    async def count(self, collection: str) -> int:
        return len(self._rows.get(collection, {}))


class SqliteVecVectorStore:
    """A ``sqlite-vec`` backed store (requires the optional ``vec`` extra).

    Vectors persist in a dedicated SQLite file; ``query`` ranks with
    ``vec_distance_cosine`` inside SQLite. Caller-supplied ranking
    (:meth:`rank`) uses the shared numpy cosine scan.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        if not sqlite_vec_available():
            raise ConfigurationError(
                "the sqlite_vec vector driver requires the 'vec' extra: "
                "pip install 'agentkit[vec]'"
            )
        try:
            import sqlite_vec
        except Exception as exc:  # pragma: no cover - optional extra
            raise ConfigurationError(
                "the sqlite_vec vector driver requires the 'vec' extra: "
                "pip install 'agentkit[vec]'"
            ) from exc
        self._sqlite_vec = sqlite_vec
        self.path = str(path)
        self._connection: Any = None
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.enable_load_extension(True)
            self._sqlite_vec.load(connection)
            connection.enable_load_extension(False)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vectors ("
                "collection TEXT, id TEXT, embedding BLOB, metadata TEXT, "
                "PRIMARY KEY (collection, id))"
            )
            connection.commit()
            self._connection = connection
        return self._connection

    def _upsert(
        self, collection: str, id: str, vector: list[float], metadata: dict[str, Any] | None
    ) -> None:
        with self._lock:
            connection = self._connect()
            connection.execute(
                "INSERT OR REPLACE INTO vectors (collection, id, embedding, metadata) "
                "VALUES (?, ?, ?, ?)",
                (
                    collection,
                    str(id),
                    self._sqlite_vec.serialize_float32(list(vector)),
                    json.dumps(metadata or {}, default=str),
                ),
            )
            connection.commit()

    def _query(self, collection: str, vector: list[float], limit: int) -> list[VectorHit]:
        with self._lock:
            connection = self._connect()
            rows = connection.execute(
                "SELECT id, metadata, vec_distance_cosine(embedding, ?) AS d "
                "FROM vectors WHERE collection = ? ORDER BY d LIMIT ?",
                (self._sqlite_vec.serialize_float32(list(vector)), collection, int(limit)),
            ).fetchall()
        return [
            VectorHit(id=row[0], score=1.0 - float(row[2]), metadata=json.loads(row[1] or "{}"))
            for row in rows
        ]

    async def upsert(
        self,
        collection: str,
        id: str,
        vector: list[float],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(self._upsert, collection, id, vector, metadata)

    async def query(
        self, collection: str, vector: list[float], *, limit: int = 5
    ) -> list[VectorHit]:
        return await asyncio.to_thread(self._query, collection, vector, limit)

    async def rank(
        self,
        collection: str,
        vector: Sequence[float],
        items: Sequence[tuple[str, Sequence[float]]],
        *,
        limit: int | None = None,
    ) -> list[VectorHit]:
        return _cosine_rank(vector, items, limit)

    async def delete(self, collection: str, id: str) -> bool:
        def _delete() -> bool:
            with self._lock:
                connection = self._connect()
                cursor = connection.execute(
                    "DELETE FROM vectors WHERE collection = ? AND id = ?", (collection, str(id))
                )
                connection.commit()
                return cursor.rowcount > 0

        return await asyncio.to_thread(_delete)

    async def count(self, collection: str) -> int:
        def _count() -> int:
            with self._lock:
                connection = self._connect()
                row = connection.execute(
                    "SELECT COUNT(*) FROM vectors WHERE collection = ?", (collection,)
                ).fetchone()
                return int(row[0]) if row else 0

        return await asyncio.to_thread(_count)


class PgVectorStore:
    """A ``pgvector`` backed store over a Postgres ``vector`` column.

    Requires a Postgres ``database_url`` and the ``vector`` extension (installed
    automatically). Distances are computed with the ``<=>`` cosine operator.
    """

    def __init__(self, database_url: str = "") -> None:
        self.database_url = database_url
        self._engine: Any = None
        self._ready = False

    def _validate(self) -> None:
        url = self.database_url or ""
        if not url.startswith(("postgres", "postgresql")):
            raise ConfigurationError(
                "the pgvector vector driver requires a Postgres database_url"
            )

    async def _ensure(self) -> Any:
        self._validate()
        if self._engine is None:
            from agentkit.db.engine import create_async_db_engine

            self._engine = create_async_db_engine(self.database_url)
        if not self._ready:
            from sqlalchemy import text

            async with self._engine.begin() as connection:
                await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await connection.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS vector_store ("
                        "collection TEXT, id TEXT, embedding vector, metadata TEXT, "
                        "PRIMARY KEY (collection, id))"
                    )
                )
            self._ready = True
        return self._engine

    @staticmethod
    def _literal(vector: Sequence[float]) -> str:
        return "[" + ",".join(f"{float(value):.8g}" for value in vector) + "]"

    async def upsert(
        self,
        collection: str,
        id: str,
        vector: list[float],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from sqlalchemy import text

        engine = await self._ensure()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO vector_store (collection, id, embedding, metadata) "
                    "VALUES (:c, :i, (:e)::vector, :m) "
                    "ON CONFLICT (collection, id) DO UPDATE "
                    "SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata"
                ),
                {
                    "c": collection,
                    "i": str(id),
                    "e": self._literal(vector),
                    "m": json.dumps(metadata or {}, default=str),
                },
            )

    async def query(
        self, collection: str, vector: list[float], *, limit: int = 5
    ) -> list[VectorHit]:
        from sqlalchemy import text

        engine = await self._ensure()
        async with engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT id, metadata, 1 - (embedding <=> (:e)::vector) AS score "
                        "FROM vector_store WHERE collection = :c "
                        "ORDER BY embedding <=> (:e)::vector LIMIT :l"
                    ),
                    {"c": collection, "e": self._literal(vector), "l": int(limit)},
                )
            ).fetchall()
        return [
            VectorHit(id=row[0], score=float(row[2]), metadata=json.loads(row[1] or "{}"))
            for row in rows
        ]

    async def rank(
        self,
        collection: str,
        vector: Sequence[float],
        items: Sequence[tuple[str, Sequence[float]]],
        *,
        limit: int | None = None,
    ) -> list[VectorHit]:
        return _cosine_rank(vector, items, limit)

    async def delete(self, collection: str, id: str) -> bool:
        from sqlalchemy import text

        engine = await self._ensure()
        async with engine.begin() as connection:
            result = await connection.execute(
                text("DELETE FROM vector_store WHERE collection = :c AND id = :i"),
                {"c": collection, "i": str(id)},
            )
            return bool(result.rowcount)

    async def count(self, collection: str) -> int:
        from sqlalchemy import text

        engine = await self._ensure()
        async with engine.begin() as connection:
            row = (
                await connection.execute(
                    text("SELECT COUNT(*) FROM vector_store WHERE collection = :c"),
                    {"c": collection},
                )
            ).fetchone()
        return int(row[0]) if row else 0


class VectorStoreManager(Manager):
    """Resolves the configured vector store (``vector_store_driver``)."""

    kind = DriverKind.VECTOR
    default_driver = VectorStoreDriver.REPOSITORY

    @property
    def setting_name(self) -> str:
        # The kind is ``vector`` but the plan-facing setting is ``vector_store_driver``.
        return "vector_store_driver"

    def create_repository_driver(self, app: Any) -> NumpyVectorStore:
        return NumpyVectorStore()

    def create_sqlite_vec_driver(self, app: Any) -> SqliteVecVectorStore:
        return SqliteVecVectorStore(_vectors_path(app))

    def create_pgvector_driver(self, app: Any) -> PgVectorStore:
        return PgVectorStore(str(getattr(app.settings, "resolved_database_url", "")))


def _vectors_path(app: Any) -> Path:
    home = Path(str(getattr(app.settings, "home", ".")))
    return home / "vectors.db"


def current_vector_store() -> Any:
    """The configured vector store from the current app, or ``None``.

    Used by memory recall and RAG retrieval to rank through the configured
    ``vector_store_driver``; returns ``None`` outside an app context so callers
    fall back to the numpy cosine scan.
    """
    try:
        from agentkit.foundation.facade import get_current_app

        app = get_current_app()
    except Exception:  # pragma: no cover - defensive
        return None
    if app is None:
        return None
    try:
        return app.manager("vector").driver()
    except Exception:  # pragma: no cover - defensive
        return None


@register_driver(DriverKind.VECTOR, VectorStoreDriver.REPOSITORY)
class RepositoryVectorDriver(Driver):
    def build(self) -> NumpyVectorStore:
        return NumpyVectorStore()


@register_driver(DriverKind.VECTOR, VectorStoreDriver.SQLITE_VEC)
class SqliteVecVectorDriver(Driver):
    def build(self) -> SqliteVecVectorStore:
        app = self.app
        return SqliteVecVectorStore(_vectors_path(app))


@register_driver(DriverKind.VECTOR, VectorStoreDriver.PGVECTOR)
class PgVectorVectorDriver(Driver):
    def build(self) -> PgVectorStore:
        app = self.app
        return PgVectorStore(str(getattr(app.settings, "resolved_database_url", "")))
