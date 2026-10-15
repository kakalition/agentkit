"""Owner data lifecycle: export a JSON bundle and erase an owner's data.

Erasure is destructive and opt-in. Audit entries are **never** deleted — a
``data.forget`` tombstone is appended so the hash chain stays verifiable and the
erasure itself is recorded.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import delete

from agentkit.db.models import (
    Conversation,
    Feedback,
    KnowledgeChunk,
    LearningRun,
    Memory,
    Message,
    OwnerProfile,
    UsageRecord,
)

FORGET_TABLES = (
    "conversations",
    "messages",
    "memories",
    "owner_profile",
    "knowledge",
    "learning_runs",
    "feedback",
    "usage",
)


def _row_data(row: Any) -> dict[str, Any]:
    try:
        return row.model_dump(mode="json")
    except Exception:  # pragma: no cover - defensive
        return {key: getattr(row, key, None) for key in ("id",)}


async def export_owner(repos: Any) -> dict[str, Any]:
    """A JSON-serializable bundle of everything owned by ``repos.owner_id``."""
    conversations = await repos.conversations.list(limit=100_000)
    messages: list[dict[str, Any]] = []
    for conversation in conversations:
        for row in await repos.messages.list(conversation.id, limit=100_000):
            messages.append(_row_data(row))
    profile = await repos.profile.get()
    return {
        "owner_id": repos.owner_id,
        "conversations": [_row_data(row) for row in conversations],
        "messages": messages,
        "memories": [_row_data(row) for row in await repos.memories.list(limit=100_000, status=None)],
        "owner_profile": _row_data(profile) if profile is not None else None,
        "knowledge": [_row_data(row) for row in await repos.knowledge.list(limit=100_000)],
        "learning_runs": [
            _row_data(row) for row in await repos.learning_runs.list(limit=100_000)
        ],
        "feedback": [_row_data(row) for row in await repos.feedback.list(limit=100_000)],
        "usage": [_row_data(row) for row in await repos.usage.list(limit=100_000)],
    }


async def _counts(repos: Any) -> dict[str, int]:
    conversations = await repos.conversations.list(limit=100_000)
    messages = 0
    for conversation in conversations:
        messages += len(await repos.messages.list(conversation.id, limit=100_000))
    return {
        "conversations": len(conversations),
        "messages": messages,
        "memories": len(await repos.memories.list(limit=100_000, status=None)),
        "owner_profile": 1 if await repos.profile.get() is not None else 0,
        "knowledge": len(await repos.knowledge.list(limit=100_000)),
        "learning_runs": len(await repos.learning_runs.list(limit=100_000)),
        "feedback": len(await repos.feedback.list(limit=100_000)),
        "usage": len(await repos.usage.list(limit=100_000)),
    }


async def forget_owner(repos: Any, *, dry_run: bool = True) -> dict[str, Any]:
    """Erase owner data (conversations/messages/memories/profile/knowledge/…).

    ``dry_run=True`` reports what *would* be erased and changes nothing. Audit
    entries are preserved; a ``data.forget`` tombstone is appended on real erasure.
    """
    counts = await _counts(repos)
    if dry_run:
        return {"owner_id": repos.owner_id, "dry_run": True, "would_delete": counts}

    session = repos.session
    conversation_ids = [row.id for row in await repos.conversations.list(limit=100_000)]
    if conversation_ids:
        await session.exec(delete(Message).where(Message.conversation_id.in_(conversation_ids)))  # type: ignore[attr-defined]
    await session.exec(delete(Conversation).where(Conversation.owner_id == repos.owner_id))
    await session.exec(delete(Memory).where(Memory.owner_id == repos.owner_id))
    await session.exec(delete(OwnerProfile).where(OwnerProfile.owner_id == repos.owner_id))
    await session.exec(delete(KnowledgeChunk).where(KnowledgeChunk.owner_id == repos.owner_id))
    await session.exec(delete(LearningRun).where(LearningRun.owner_id == repos.owner_id))
    await session.exec(delete(Feedback).where(Feedback.owner_id == repos.owner_id))
    await session.exec(delete(UsageRecord).where(UsageRecord.owner_id == repos.owner_id))
    await session.flush()

    audit = getattr(repos, "audit", None)
    if audit is not None:
        await audit.append("data.forget", detail={"deleted": counts}, actor=repos.owner_id)
    return {"owner_id": repos.owner_id, "dry_run": False, "deleted": counts}


__all__ = ["FORGET_TABLES", "export_owner", "forget_owner"]
