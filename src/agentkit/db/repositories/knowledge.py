"""Indexed source chunks with semantic recall (RAG)."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import KnowledgeChunk
from agentkit.embeddings import (
    embed_documents,
    embed_query,
    get_default_embedder,
    pack_vector,
    similarity_scores,
    unpack_vector,
)
from agentkit.vector_store import current_vector_store


class KnowledgeRepo:
    """Owner-scoped indexed source chunks with semantic recall (RAG).

    Each chunk stores a float32 embedding; ``search`` ranks by cosine similarity
    and falls back to keyword matching when no embedder is configured.
    """

    _UNSET = object()

    def __init__(self, session: AsyncSession, owner_id: str, embedder: Any = _UNSET) -> None:
        self.session = session
        self.owner_id = owner_id
        self._embedder = embedder
        self._embedder_resolved = embedder is not KnowledgeRepo._UNSET
        self._embedder_failed = False

    def _get_embedder(self) -> Any:
        if not self._embedder_resolved:
            self._embedder = get_default_embedder()
            self._embedder_resolved = True
        if self._embedder_failed:
            return None
        return self._embedder

    async def _embed_document(self, text: str) -> list[float] | None:
        embedder = self._get_embedder()
        if embedder is None:
            return None
        try:
            vectors = await asyncio.to_thread(embed_documents, embedder, [text])
        except Exception:
            self._embedder_failed = True
            return None
        return vectors[0] if vectors else None

    async def _embed_query(self, text: str) -> list[float] | None:
        embedder = self._get_embedder()
        if embedder is None:
            return None
        try:
            return await asyncio.to_thread(embed_query, embedder, text)
        except Exception:
            self._embedder_failed = True
            return None

    async def add(self, source: str, contents: list[str]) -> int:
        added = 0
        for seq, content in enumerate(contents):
            text = content.strip()
            if not text:
                continue
            vector = await self._embed_document(text)
            self.session.add(
                KnowledgeChunk(
                    owner_id=self.owner_id,
                    source=source,
                    seq=seq,
                    content=text,
                    embedding=pack_vector(vector) if vector else None,
                )
            )
            added += 1
        await self.session.flush()
        return added

    async def replace(self, source: str, contents: list[str]) -> int:
        await self.clear(source)
        return await self.add(source, contents)

    async def clear(self, source: str | None = None) -> int:
        rows = await self.list(source) if source is not None else await self.list()
        for row in rows:
            await self.session.delete(row)
        await self.session.flush()
        return len(rows)

    async def get(self, chunk_id: int) -> KnowledgeChunk | None:
        chunk = await self.session.get(KnowledgeChunk, chunk_id)
        if chunk is not None and chunk.owner_id != self.owner_id:
            return None
        return chunk

    async def list(self, source: str | None = None, limit: int | None = None) -> list[KnowledgeChunk]:
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.owner_id == self.owner_id)
        if source is not None:
            stmt = stmt.where(KnowledgeChunk.source == source)
        stmt = stmt.order_by(KnowledgeChunk.source, KnowledgeChunk.seq)
        rows = list((await self.session.exec(stmt)).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows

    async def sources(self) -> list[str]:
        stmt = (
            select(KnowledgeChunk.source)
            .where(KnowledgeChunk.owner_id == self.owner_id)
            .distinct()
            .order_by(KnowledgeChunk.source)
        )
        return [source for source in (await self.session.exec(stmt)).all() if source]

    async def count(self, source: str | None = None) -> int:
        stmt = select(func.count()).select_from(KnowledgeChunk).where(
            KnowledgeChunk.owner_id == self.owner_id
        )
        if source is not None:
            stmt = stmt.where(KnowledgeChunk.source == source)
        return int((await self.session.exec(stmt)).one())

    async def search(self, query: str, *, limit: int = 5, source: str | None = None) -> list[KnowledgeChunk]:
        query = (query or "").strip()
        if not query:
            return []
        semantic = await self._semantic_search(query, limit, source)
        ordered = list(semantic)
        seen = {row.id for row in semantic}
        for row in await self._keyword_search(query, limit, source):
            if row.id not in seen:
                ordered.append(row)
                seen.add(row.id)
        return ordered[:limit]

    async def _keyword_search(
        self, query: str, limit: int, source: str | None
    ) -> list[KnowledgeChunk]:
        stmt = select(KnowledgeChunk).where(
            KnowledgeChunk.owner_id == self.owner_id, KnowledgeChunk.content.ilike(f"%{query}%")
        )
        if source is not None:
            stmt = stmt.where(KnowledgeChunk.source == source)
        return list((await self.session.exec(stmt.limit(limit))).all())

    async def _semantic_search(
        self, query: str, limit: int, source: str | None
    ) -> list[KnowledgeChunk]:
        query_vector = await self._embed_query(query)
        if query_vector is None:
            return []
        stmt = select(KnowledgeChunk).where(
            KnowledgeChunk.owner_id == self.owner_id, KnowledgeChunk.embedding.is_not(None)
        )
        if source is not None:
            stmt = stmt.where(KnowledgeChunk.source == source)
        dimension = len(query_vector)
        candidates: list[KnowledgeChunk] = []
        vectors: list[list[float]] = []
        for chunk in (await self.session.exec(stmt)).all():
            try:
                vector = unpack_vector(chunk.embedding)  # type: ignore[arg-type]
            except Exception:
                continue
            if len(vector) != dimension:
                continue
            candidates.append(chunk)
            vectors.append(vector)
        store = current_vector_store()
        if store is not None:
            hits = await store.rank(
                "__knowledge__",
                query_vector,
                [(str(index), vector) for index, vector in enumerate(vectors)],
                limit=limit,
            )
            return [candidates[int(hit.id)] for hit in hits]
        scores = similarity_scores(query_vector, vectors)
        order = sorted(range(len(candidates)), key=lambda index: scores[index], reverse=True)
        return [candidates[index] for index in order[:limit]]


