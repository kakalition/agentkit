"""Conversations, messages, and durable A2A task records."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import A2ATaskRecord, Conversation, Message


class ConversationRepo:
    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def get_or_create(self, conversation_id: str, channel: str = "cli") -> Conversation:
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation:
            return conversation
        conversation = Conversation(id=conversation_id, owner_id=self.owner_id, channel=channel)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def touch(self, conversation_id: str) -> None:
        conversation = await self.session.get(Conversation, conversation_id)
        if conversation:
            conversation.updated_at = datetime.now(UTC)
            self.session.add(conversation)
            await self.session.flush()

    async def get(self, conversation_id: str) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def list(self, limit: int | None = None) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.owner_id == self.owner_id)
            .order_by(Conversation.updated_at.desc())
        )
        rows = list((await self.session.exec(stmt)).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows

    async def fork(self, source: str, target: str, *, upto: int | None = None) -> int:
        """Copy ``source``'s messages into a new conversation ``target``.

        ``upto`` limits how many messages are copied (a branch point). Returns the
        number of messages copied.
        """
        src = await self.get_or_create(source)
        await self.get_or_create(target, channel=src.channel)
        stmt = (
            select(Message)
            .where(Message.conversation_id == source)
            .order_by(Message.seq, Message.id)
        )
        rows = list((await self.session.exec(stmt)).all())
        if upto is not None:
            rows = rows[:upto]
        await self.session.exec(delete(Message).where(Message.conversation_id == target))
        for seq, row in enumerate(rows):
            self.session.add(Message(conversation_id=target, seq=seq, payload=row.payload))
        await self.session.flush()
        return len(rows)


class MessageRepo:
    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def append(self, conversation_id: str, payloads: list[str]) -> int:
        seq = await self.next_seq(conversation_id)
        for payload in payloads:
            self.session.add(Message(conversation_id=conversation_id, seq=seq, payload=payload))
            seq += 1
        await self.session.flush()
        return len(payloads)

    async def next_seq(self, conversation_id: str) -> int:
        current = (
            await self.session.exec(
                select(func.coalesce(func.max(Message.seq), -1)).where(
                    Message.conversation_id == conversation_id
                )
            )
        ).one()
        return int(current) + 1

    async def list(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq)
        )
        messages = list((await self.session.exec(stmt)).all())
        if limit is not None and len(messages) > limit:
            messages = messages[-limit:]
        return messages

    async def clear(self, conversation_id: str) -> None:
        for message in await self.list(conversation_id):
            await self.session.delete(message)
        await self.session.flush()


class A2ATaskRepo:
    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def upsert(
        self, task_id: str, owner: str, context_id: str | None, state: str, payload: str
    ) -> A2ATaskRecord:
        existing = await self.session.get(A2ATaskRecord, task_id)
        if existing is not None:
            existing.owner_id = owner
            existing.context_id = context_id
            existing.state = state
            existing.payload = payload
            existing.updated_at = datetime.now(UTC)
            self.session.add(existing)
            await self.session.flush()
            return existing
        record = A2ATaskRecord(
            id=task_id, owner_id=owner, context_id=context_id, state=state, payload=payload
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, task_id: str) -> A2ATaskRecord | None:
        return await self.session.get(A2ATaskRecord, task_id)

    async def delete(self, task_id: str) -> None:
        record = await self.session.get(A2ATaskRecord, task_id)
        if record is not None:
            await self.session.delete(record)
            await self.session.flush()

    async def list(self) -> list[A2ATaskRecord]:
        return list(
            (
                await self.session.exec(
                    select(A2ATaskRecord).order_by(A2ATaskRecord.updated_at.desc())
                )
            ).all()
        )


