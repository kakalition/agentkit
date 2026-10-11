"""Generic repository container: conversations, messages, and A2A tasks.

Application domain repositories subclass or attach to :class:`Repositories`.
All access is owner-scoped.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import Session, select

from agentkit.db.models import (
    A2ATaskRecord,
    AuditEntry,
    Conversation,
    Message,
    ScheduledJob,
    UsageRecord,
)


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

    def get(self, conversation_id: str) -> Conversation | None:
        return self.session.get(Conversation, conversation_id)

    def list(self, limit: int | None = None) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.owner_id == self.owner_id)
            .order_by(Conversation.updated_at.desc())
        )
        rows = list(self.session.exec(stmt).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows


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


class ScheduledJobRepo:
    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    def upsert(
        self,
        name: str,
        *,
        kind: str,
        schedule: str,
        task: str,
        args: str = "{}",
        enabled: bool = True,
    ) -> ScheduledJob:
        job = self.session.get(ScheduledJob, name)
        if job is None:
            job = ScheduledJob(name=name, owner_id=self.owner_id)
        job.kind = kind
        job.schedule = schedule
        job.task = task
        job.args = args
        job.enabled = enabled
        job.updated_at = datetime.now(UTC)
        self.session.add(job)
        self.session.flush()
        return job

    def get(self, name: str) -> ScheduledJob | None:
        return self.session.get(ScheduledJob, name)

    def list(self, *, enabled_only: bool = False) -> list[ScheduledJob]:
        stmt = select(ScheduledJob)
        if enabled_only:
            stmt = stmt.where(ScheduledJob.enabled == True)  # noqa: E712
        return list(self.session.exec(stmt.order_by(ScheduledJob.name)).all())

    def remove(self, name: str) -> bool:
        job = self.session.get(ScheduledJob, name)
        if job is None:
            return False
        self.session.delete(job)
        self.session.flush()
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        job = self.session.get(ScheduledJob, name)
        if job is None:
            return False
        job.enabled = enabled
        job.updated_at = datetime.now(UTC)
        self.session.add(job)
        self.session.flush()
        return True

    def record_run(self, name: str) -> None:
        job = self.session.get(ScheduledJob, name)
        if job is None:
            return
        job.last_run = datetime.now(UTC)
        job.run_count += 1
        if job.kind == "once":
            job.enabled = False
        self.session.add(job)
        self.session.flush()


class UsageRepo:
    """Token accounting (counts only)."""

    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    def add(
        self,
        *,
        conversation_id: str | None = None,
        kind: str = "turn",
        model: str = "",
        requests: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ) -> UsageRecord:
        record = UsageRecord(
            owner_id=self.owner_id,
            conversation_id=conversation_id,
            kind=kind,
            model=model,
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def list(self, limit: int | None = None) -> list[UsageRecord]:
        stmt = (
            select(UsageRecord)
            .where(UsageRecord.owner_id == self.owner_id)
            .order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc())
        )
        rows = list(self.session.exec(stmt).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows

    def totals(self, *, since: datetime | None = None) -> dict[str, int]:
        stmt = select(
            func.coalesce(func.sum(UsageRecord.requests), 0),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        ).where(UsageRecord.owner_id == self.owner_id)
        if since is not None:
            stmt = stmt.where(UsageRecord.created_at >= since)
        requests, input_tokens, output_tokens, total_tokens = self.session.exec(stmt).one()
        return {
            "requests": int(requests),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(total_tokens),
        }


class AuditRepo:
    """Append-only, hash-chained audit log (tamper-evident)."""

    def __init__(self, session: Session, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _hash(seq: int, action: str, target: str, detail: dict, actor: str, prev: str) -> str:
        payload = json.dumps(
            {"seq": seq, "action": action, "target": target, "detail": detail, "actor": actor, "prev": prev},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(
        self, action: str, *, target: str = "", detail: dict | None = None, actor: str = ""
    ) -> AuditEntry:
        last = self.session.exec(
            select(AuditEntry)
            .where(AuditEntry.owner_id == self.owner_id)
            .order_by(AuditEntry.seq.desc())
        ).first()
        seq = last.seq + 1 if last else 0
        prev = last.entry_hash if last else ""
        entry_hash = self._hash(seq, action, target, detail or {}, actor, prev)
        entry = AuditEntry(
            owner_id=self.owner_id,
            seq=seq,
            action=action,
            target=target,
            detail=json.dumps(detail or {}, sort_keys=True),
            actor=actor,
            prev_hash=prev,
            entry_hash=entry_hash,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def entries(self, limit: int | None = None) -> list[AuditEntry]:
        stmt = (
            select(AuditEntry)
            .where(AuditEntry.owner_id == self.owner_id)
            .order_by(AuditEntry.seq)
        )
        rows = list(self.session.exec(stmt).all())
        if limit is not None and len(rows) > limit:
            rows = rows[-limit:]
        return rows

    def verify(self) -> bool:
        prev = ""
        for entry in self.entries():
            expected = self._hash(
                entry.seq, entry.action, entry.target, json.loads(entry.detail or "{}"), entry.actor, prev
            )
            if entry.prev_hash != prev or entry.entry_hash != expected:
                return False
            prev = entry.entry_hash
        return True


@dataclass
class Repositories:
    """Base container. Domain apps add their own repos (e.g. ``self.transactions``)."""

    session: Session
    owner_id: str

    def __post_init__(self) -> None:
        self.conversations = ConversationRepo(self.session, self.owner_id)
        self.messages = MessageRepo(self.session, self.owner_id)
        self.a2a = A2ATaskRepo(self.session, self.owner_id)
        self.schedules = ScheduledJobRepo(self.session, self.owner_id)
        self.usage = UsageRepo(self.session, self.owner_id)
        self.audit = AuditRepo(self.session, self.owner_id)
