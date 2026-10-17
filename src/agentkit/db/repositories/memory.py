"""Typed owner memories and the owner profile."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import Memory, OwnerProfile
from agentkit.embeddings import (
    cosine_similarity,
    embed_documents,
    embed_query,
    get_default_embedder,
    pack_vector,
    similarity_scores,
    unpack_vector,
)

MEMORY_KINDS = ("fact", "preference", "person", "date", "episodic", "procedural")
MEMORY_STATUSES = ("active", "proposed", "rejected")


def _recency(memory: Memory, now: datetime, half_life_days: float) -> float:
    anchor = memory.last_used_at or memory.updated_at or memory.created_at

    if anchor is None:
        return 0.0
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    age_days = max((now - anchor).total_seconds(), 0.0) / 86400.0
    if half_life_days <= 0:
        return 1.0
    return float(2.0 ** (-age_days / half_life_days))


async def _semantic_scores_for(
    query_vector: list[float], candidates: list[Memory], vectors: list[list[float]]
) -> list[float]:
    """Cosine scores for ``candidates``, ranked via the vector store when one is configured.

    With the default ``repository`` driver this is the numpy cosine scan, so the
    scores are identical to the built-in path.
    """
    from agentkit.vector_store import current_vector_store

    store = current_vector_store()
    if store is not None:
        items = [
            (str(memory.id), vector)
            for memory, vector in zip(candidates, vectors, strict=True)
        ]
        hits = await store.rank("__memory__", query_vector, items)
        by_id = {hit.id: hit.score for hit in hits}
        return [by_id.get(str(memory.id), 0.0) for memory in candidates]
    return similarity_scores(query_vector, vectors)


class MemoryRepo:
    """Owner-scoped durable memories with typed, hybrid recall.

    Each row stores a float32 embedding. ``search`` ranks by a weighted blend of
    semantic similarity, recency, and importance (weights from settings), and
    falls back to keyword matching when no embedder is configured. Pass an
    explicit ``embedder`` to override the process default; pass ``None`` to force
    keyword-only search.
    """

    _UNSET = object()

    def __init__(self, session: AsyncSession, owner_id: str, embedder: Any = _UNSET) -> None:
        self.session = session
        self.owner_id = owner_id
        self._embedder = embedder
        self._embedder_resolved = embedder is not MemoryRepo._UNSET
        self._embedder_failed = False

    # -- embeddings -----------------------------------------------------
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
            # Embedding is GIL-bound CPU work: keep it off the event loop.
            vectors = await asyncio.to_thread(embed_documents, embedder, [text])
        except Exception:  # model missing, download failure, … → keyword fallback
            self._embedder_failed = True
            return None
        return vectors[0] if vectors else None

    async def _embed_query(self, text: str) -> list[float] | None:
        embedder = self._get_embedder()
        if embedder is None:
            return None
        try:
            return await asyncio.to_thread(embed_query, embedder, text)
        except Exception:  # model missing, download failure, … → keyword fallback
            self._embedder_failed = True
            return None

    # -- writes ---------------------------------------------------------
    @staticmethod
    def _check_kind(kind: str) -> str:
        if kind not in MEMORY_KINDS:
            raise ValueError(f"unknown memory kind {kind!r}; expected one of {', '.join(MEMORY_KINDS)}")
        return kind

    async def add(
        self,
        content: str,
        *,
        kind: str = "fact",
        importance: float = 0.5,
        source_conversation_id: str | None = None,
        expires_at: datetime | None = None,
        status: str = "active",
    ) -> Memory:
        content = content.strip()
        self._check_kind(kind)
        vector = await self._embed_document(content)
        memory = Memory(
            owner_id=self.owner_id,
            content=content,
            kind=kind,
            status=status,
            importance=float(importance),
            source_conversation_id=source_conversation_id,
            expires_at=expires_at,
            embedding=pack_vector(vector) if vector else None,
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def update(self, memory_id: int, content: str, *, kind: str | None = None) -> bool:
        memory = await self.get(memory_id)
        if memory is None:
            return False
        if kind is not None:
            self._check_kind(kind)
            memory.kind = kind
        content = content.strip()
        vector = await self._embed_document(content)
        memory.content = content
        memory.embedding = pack_vector(vector) if vector else None
        memory.updated_at = datetime.now(UTC)
        self.session.add(memory)
        await self.session.flush()
        return True

    async def forget(self, memory_id: int) -> bool:
        memory = await self.get(memory_id)
        if memory is None:
            return False
        await self.session.delete(memory)
        await self.session.flush()
        return True

    async def clear(self) -> int:
        rows = await self.list()
        for memory in rows:
            await self.session.delete(memory)
        await self.session.flush()
        return len(rows)

    async def record_use(self, memories: Any) -> int:
        """Bump ``access_count`` / ``last_used_at`` for the given rows or ids."""
        if isinstance(memories, (int, Memory)):
            memories = [memories]
        touched = 0
        now = datetime.now(UTC)
        for item in memories:
            memory = await self.get(item) if isinstance(item, int) else item
            if memory is None:
                continue
            memory.access_count = int(memory.access_count or 0) + 1
            memory.last_used_at = now
            self.session.add(memory)
            touched += 1
        await self.session.flush()
        return touched

    # -- reads ----------------------------------------------------------
    async def get(self, memory_id: int) -> Memory | None:
        memory = await self.session.get(Memory, memory_id)
        if memory is not None and memory.owner_id != self.owner_id:
            return None
        return memory

    async def list(
        self, limit: int | None = None, *, kind: str | None = None, status: str | None = "active"
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.owner_id == self.owner_id)
        if kind is not None:
            stmt = stmt.where(Memory.kind == kind)
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        stmt = stmt.order_by(Memory.updated_at.desc(), Memory.id.desc())
        rows = list((await self.session.exec(stmt)).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows

    async def set_status(self, memory_id: int, status: str) -> bool:
        """Change a memory's review status (``active`` | ``proposed`` | ``rejected``)."""
        if status not in MEMORY_STATUSES:
            raise ValueError(f"unknown memory status {status!r}")
        memory = await self.get(memory_id)
        if memory is None:
            return False
        memory.status = status
        memory.updated_at = datetime.now(UTC)
        self.session.add(memory)
        await self.session.flush()
        return True

    async def proposed(self, *, kind: str | None = None) -> list[Memory]:
        """Memories awaiting review (oldest first)."""
        rows = await self.list(kind=kind, status="proposed")
        rows.sort(key=lambda row: (row.id or 0))
        return rows

    def _weights(self) -> tuple[float, float, float, float]:
        defaults = (0.6, 0.2, 0.2, 30.0)
        try:
            from agentkit.config import get_settings

            settings = get_settings()
        except Exception:  # pragma: no cover - defensive
            return defaults
        return (
            float(getattr(settings, "memory_recall_similarity_weight", 0.6)),
            float(getattr(settings, "memory_recall_recency_weight", 0.2)),
            float(getattr(settings, "memory_recall_importance_weight", 0.2)),
            float(getattr(settings, "memory_recall_half_life_days", 30.0)),
        )

    def _recall_strategy(self) -> Any:
        """The configured recall strategy (``memory_recall_driver``), or ``None``.

        Resolved from the current app so the driver selection takes effect; a
        ``None`` result means use the built-in hybrid blend, which reproduces the
        historical default exactly.
        """
        try:
            import agentkit.memory  # noqa: F401 - registers the recall manager
            from agentkit.foundation.facade import get_current_app

            app = get_current_app()
        except Exception:  # pragma: no cover - defensive
            return None
        if app is None:
            return None
        try:
            return app.manager("memory_recall").driver()
        except Exception:  # pragma: no cover - defensive
            return None

    async def search(
        self, query: str, *, kind: str | None = None, limit: int = 5, status: str | None = "active"
    ) -> list[Memory]:
        query = query.strip()
        if not query:
            return []
        rows: dict[int, Memory] = {}
        similarity: dict[int, float] = {}
        for memory, score in await self._semantic_scores(query, kind, status):
            rows[memory.id] = memory
            similarity[memory.id] = score
        for memory in await self._keyword_search(query, limit, kind, status):
            rows.setdefault(memory.id, memory)
            similarity[memory.id] = max(similarity.get(memory.id, 0.0), 1.0)

        now = datetime.now(UTC)
        strategy = self._recall_strategy()
        if strategy is None:
            w_sim, w_rec, w_imp, half_life = self._weights()
            ranked = [
                (
                    w_sim * similarity[memory_id]
                    + w_rec * _recency(memory, now, half_life)
                    + w_imp * float(memory.importance or 0.0),
                    memory,
                )
                for memory_id, memory in rows.items()
            ]
        else:
            ranked = [
                (strategy.score(query, similarity[memory_id], memory, now), memory)
                for memory_id, memory in rows.items()
            ]
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [memory for _, memory in ranked[:limit]]

    async def _keyword_search(
        self, query: str, limit: int, kind: str | None = None, status: str | None = "active"
    ) -> list[Memory]:
        text = f"%{query}%"
        stmt = select(Memory).where(
            Memory.owner_id == self.owner_id,
            or_(Memory.content.ilike(text), Memory.kind.ilike(text)),
        )
        if kind is not None:
            stmt = stmt.where(Memory.kind == kind)
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        stmt = stmt.order_by(Memory.updated_at.desc(), Memory.id.desc()).limit(limit)
        return list((await self.session.exec(stmt)).all())

    async def _semantic_scores(
        self, query: str, kind: str | None = None, status: str | None = "active"
    ) -> list[tuple[Memory, float]]:
        query_vector = await self._embed_query(query)
        if query_vector is None:
            return []
        stmt = select(Memory).where(
            Memory.owner_id == self.owner_id, Memory.embedding.is_not(None)
        )
        if kind is not None:
            stmt = stmt.where(Memory.kind == kind)
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        dimension = len(query_vector)
        candidates: list[Memory] = []
        vectors: list[list[float]] = []
        for memory in (await self.session.exec(stmt)).all():
            try:
                vector = unpack_vector(memory.embedding)  # type: ignore[arg-type]
            except Exception:
                continue
            if len(vector) != dimension:
                continue
            candidates.append(memory)
            vectors.append(vector)
        scores = await _semantic_scores_for(query_vector, candidates, vectors)
        return list(zip(candidates, scores, strict=True))

    # -- consolidation helpers -----------------------------------------
    async def expired(self, *, now: datetime | None = None) -> list[Memory]:
        moment = now or datetime.now(UTC)
        stmt = select(Memory).where(
            Memory.owner_id == self.owner_id,
            Memory.expires_at.is_not(None),
            Memory.expires_at < moment,  # type: ignore[operator]
        )
        return list((await self.session.exec(stmt)).all())

    async def prune_expired(self, *, now: datetime | None = None) -> int:
        rows = await self.expired(now=now)
        for memory in rows:
            await self.session.delete(memory)
        await self.session.flush()
        return len(rows)

    async def near_duplicates(
        self, threshold: float = 0.92, *, kind: str | None = None, status: str | None = "active"
    ) -> list[list[Memory]]:
        """Groups of memories whose embeddings are within ``threshold`` cosine."""
        stmt = select(Memory).where(
            Memory.owner_id == self.owner_id, Memory.embedding.is_not(None)
        )
        if kind is not None:
            stmt = stmt.where(Memory.kind == kind)
        if status is not None:
            stmt = stmt.where(Memory.status == status)
        rows = [row for row in (await self.session.exec(stmt)).all() if row.embedding]
        groups: list[list[Memory]] = []
        assigned: set[int] = set()
        for index, memory in enumerate(rows):
            if memory.id in assigned:
                continue
            base = unpack_vector(memory.embedding)  # type: ignore[arg-type]
            group = [memory]
            for other in rows[index + 1 :]:
                if other.id in assigned:
                    continue
                if other.kind != memory.kind:
                    continue
                try:
                    candidate = unpack_vector(other.embedding)  # type: ignore[arg-type]
                except Exception:
                    continue
                if len(candidate) != len(base):
                    continue
                if cosine_similarity(base, candidate) >= threshold:
                    group.append(other)
            if len(group) > 1:
                assigned.update(m.id for m in group)
                groups.append(group)
        return groups

    async def merge(self, canonical: Memory, others: list[Memory]) -> Memory:
        """Fold ``others`` into ``canonical`` (sum access, max importance), deleting them."""
        for other in others:
            if other.id == canonical.id:
                continue
            canonical.access_count = int(canonical.access_count or 0) + int(other.access_count or 0)
            canonical.importance = max(
                float(canonical.importance or 0.0), float(other.importance or 0.0)
            )
            await self.session.delete(other)
        canonical.updated_at = datetime.now(UTC)
        self.session.add(canonical)
        await self.session.flush()
        return canonical


class OwnerProfileRepo:
    """The single owner-scoped profile row."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def get(self) -> OwnerProfile | None:
        return await self.session.get(OwnerProfile, self.owner_id)

    async def set(self, **fields: Any) -> OwnerProfile:
        """Upsert the profile with the given fields (unset fields left untouched)."""
        profile = await self.get()
        if profile is None:
            profile = OwnerProfile(owner_id=self.owner_id)
        self._apply(profile, fields)
        profile.updated_at = datetime.now(UTC)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def merge(self, **fields: Any) -> OwnerProfile:
        """Alias for :meth:`set` (partial update / upsert)."""
        return await self.set(**fields)

    def _apply(self, profile: OwnerProfile, fields: dict[str, Any]) -> None:
        for key, value in fields.items():
            if key == "owner_id":
                continue
            if key == "preferences" and isinstance(value, dict):
                value = json.dumps(value, sort_keys=True)
            if hasattr(profile, key):
                setattr(profile, key, value)


