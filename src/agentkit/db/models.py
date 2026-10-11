"""Infrastructure tables reused by every agentkit app.

Domain tables (transactions, budgets, …) belong to the application; these are
the generic conversation/history/task tables the framework needs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: str = Field(primary_key=True)
    owner_id: str = Field(index=True)
    channel: str = "cli"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_msg_conv_seq", "conversation_id", "seq"),)

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(index=True, foreign_key="conversations.id")
    seq: int = 0
    payload: str  # JSON-serialized ModelMessagesTypeAdapter payload
    created_at: datetime = Field(default_factory=_utcnow)


class ScheduledJob(SQLModel, table=True):
    """A durable scheduled job: recurring (cron) or one-off (``once``)."""

    __tablename__ = "scheduled_jobs"

    name: str = Field(primary_key=True)
    owner_id: str | None = Field(default=None, index=True)
    kind: str = "cron"  # cron | once
    schedule: str = ""  # cron expression, or an ISO-8601 datetime for "once"
    task: str = ""  # registered task name
    args: str = "{}"  # JSON kwargs
    enabled: bool = True
    last_run: datetime | None = None
    run_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class A2ATaskRecord(SQLModel, table=True):
    """Durable A2A task store (protobuf JSON payloads)."""

    __tablename__ = "a2a_tasks"

    id: str = Field(primary_key=True)
    owner_id: str | None = Field(default=None, index=True)
    context_id: str | None = None
    state: str = "submitted"
    payload: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
