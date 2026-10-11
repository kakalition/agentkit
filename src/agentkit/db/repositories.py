"""Generic repository container: conversations, messages, and A2A tasks.

Application domain repositories subclass or attach to :class:`Repositories`.
All access is owner-scoped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import Session, select

from agentkit.db.models import A2ATaskRecord, Conversation, Message


class ConversationRepo:
    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    def get_or_create(self, conversation_id: str, channel: str = "cli") -> Conversation:
        conversation = self.session.get(Conversation, conversation_id)
        if conversation:
            return conversation
        conversation = Conversation(id=conversation_id, owner_id=self.owner_id, channel=channel)
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def touch(self, conversation_id: str) -> None:
        conversation = self.session.get(Conversation, conversation_id)
        if conversation:
            conversation.updated_at = datetime.now(UTC)
            self.session.add(conversation)
            self.session.flush()


class MessageRepo:
    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    def append(self, conversation_id: str, payloads: list[str]) -> int:
        seq = self.next_seq(conversation_id)
        for payload in payloads:
            self.session.add(Message(conversation_id=conversation_id, seq=seq, payload=payload))
            seq += 1
        self.session.flush()
        return len(payloads)

    def next_seq(self, conversation_id: str) -> int:
        current = self.session.exec(
            select(func.coalesce(func.max(Message.seq), -1)).where(
                Message.conversation_id == conversation_id
            )
        ).one()
        return int(current) + 1

    def list(self, conversation_id: str, limit: int | None = None) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.seq)
        )
        messages = list(self.session.exec(stmt).all())
        if limit is not None and len(messages) > limit:
            messages = messages[-limit:]
        return messages

    def clear(self, conversation_id: str) -> None:
        for message in self.list(conversation_id):
            self.session.delete(message)
        self.session.flush()


class A2ATaskRepo:
    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    def upsert(
        self, task_id: str, owner: str, context_id: str | None, state: str, payload: str
    ) -> A2ATaskRecord:
        existing = self.session.get(A2ATaskRecord, task_id)
        if existing is not None:
            existing.owner_id = owner
            existing.context_id = context_id
            existing.state = state
            existing.payload = payload
            existing.updated_at = datetime.now(UTC)
            self.session.add(existing)
            self.session.flush()
            return existing
        record = A2ATaskRecord(
            id=task_id, owner_id=owner, context_id=context_id, state=state, payload=payload
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, task_id: str) -> A2ATaskRecord | None:
        return self.session.get(A2ATaskRecord, task_id)

    def delete(self, task_id: str) -> None:
        record = self.session.get(A2ATaskRecord, task_id)
        if record is not None:
            self.session.delete(record)
            self.session.flush()

    def list(self) -> list[A2ATaskRecord]:
        return list(
            self.session.exec(
                select(A2ATaskRecord).order_by(A2ATaskRecord.updated_at.desc())
            ).all()
        )


@dataclass
class Repositories:
    """Base container. Domain apps add their own repos (e.g. ``self.transactions``)."""

    session: Session
    owner_id: str

    def __post_init__(self) -> None:
        self.conversations = ConversationRepo(self.session, self.owner_id)
        self.messages = MessageRepo(self.session, self.owner_id)
        self.a2a = A2ATaskRepo(self.session, self.owner_id)
