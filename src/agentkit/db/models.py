"""Infrastructure tables reused by every agentkit app.

Domain tables (transactions, budgets, …) belong to the application; these are
the generic conversation/history/task tables the framework needs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Column, Index, String, UniqueConstraint
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


class UsageRecord(SQLModel, table=True):
    """Token accounting per run (counts only — no cost)."""

    __tablename__ = "usage_records"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    conversation_id: str | None = None
    kind: str = "turn"  # turn | job
    model: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0  # estimated from pricing (see agentkit.pricing)
    created_at: datetime = Field(default_factory=_utcnow)


class AuditEntry(SQLModel, table=True):
    """Append-only, hash-chained audit log of material actions."""

    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    seq: int = 0
    action: str
    target: str = ""
    detail: str = "{}"
    actor: str = ""
    prev_hash: str = ""
    entry_hash: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


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


class Memory(SQLModel, table=True):
    """A durable fact about the owner the agent should remember across chats.

    Owner-scoped free text (name, preferences, important dates, …). Kept plain
    so it can be shown in the system prompt and searched without extra infra.
    """

    __tablename__ = "memories"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    kind: str = "fact"  # fact | preference | person | date | episodic | procedural
    status: str = "active"  # active | proposed | rejected (default keeps old rows visible)
    content: str
    embedding: str | None = Field(default=None)  # base64 float32 vector for semantic recall
    importance: float = 0.5  # 0..1, used by hybrid recall + consolidation
    last_used_at: datetime | None = None
    access_count: int = 0
    source_conversation_id: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class OwnerProfile(SQLModel, table=True):
    """Single owner-scoped profile row (name, timezone, locale, preferences)."""

    __tablename__ = "owner_profile"

    owner_id: str = Field(primary_key=True)
    name: str = ""
    timezone: str = ""
    locale: str = ""
    preferences: str = "{}"  # JSON object string
    notes: str = ""
    updated_at: datetime = Field(default_factory=_utcnow)


class KnowledgeChunk(SQLModel, table=True):
    """A chunk of indexed source material for retrieval-augmented generation."""

    __tablename__ = "knowledge_chunks"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    source: str = Field(default="", index=True)  # file path / label
    seq: int = 0  # chunk index within the source
    content: str
    embedding: str | None = Field(default=None)  # base64 float32 vector
    created_at: datetime = Field(default_factory=_utcnow)


class LearningRun(SQLModel, table=True):
    """A record of one reflection over a conversation window (idempotency)."""

    __tablename__ = "learning_runs"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    conversation_id: str = Field(default="", index=True)
    signature: str = ""  # hash of the reflected window (re-reflection is cheap)
    lessons: int = 0
    preferences: int = 0
    facts: int = 0
    detail: str = "{}"
    created_at: datetime = Field(default_factory=_utcnow)


class APIKey(SQLModel, table=True):
    """A hashed API key that resolves to an owner + roles (opt-in auth)."""

    __tablename__ = "api_keys"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    name: str = ""
    key_hash: str = Field(default="", index=True)  # sha256 hex of the secret
    prefix: str = ""  # non-secret display prefix
    roles: str = "[]"  # JSON list of role names
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class Credential(SQLModel, table=True):
    """An encrypted, owner-scoped secret (Fernet ciphertext)."""

    __tablename__ = "credentials"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_credential_owner_name"),)

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    name: str = ""
    kind: str = "secret"
    ciphertext: str = ""
    extra: str = Field(default="{}", sa_column=Column("metadata", String, default="{}"))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Webhook(SQLModel, table=True):
    """An outbound webhook subscription (HMAC-signed JSON deliveries)."""

    __tablename__ = "webhooks"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    url: str = ""
    events: str = "[]"  # JSON list of subscribed event names ("*" = all)
    secret: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class WebhookDelivery(SQLModel, table=True):
    """One asynchronous webhook delivery attempt log."""

    __tablename__ = "webhook_deliveries"

    id: int | None = Field(default=None, primary_key=True)
    webhook_id: int | None = Field(default=None, index=True)
    event: str = ""
    payload: str = "{}"
    status: str = "pending"  # pending | ok | failed
    attempts: int = 0
    error: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class EvalCapture(SQLModel, table=True):
    """A captured eval case distilled from a real conversation turn."""

    __tablename__ = "evals_capture"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    conversation_id: str = Field(default="", index=True)
    case: str = "{}"  # JSON-serialized eval case
    created_at: datetime = Field(default_factory=_utcnow)


class RateWindow(SQLModel, table=True):
    """A fixed-window rate-limit counter (one row per owner/key/window)."""

    __tablename__ = "rate_windows"
    __table_args__ = (
        UniqueConstraint("owner_id", "key", "window_start", name="uq_rate_window"),
    )

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    key: str = ""
    window_start: int = 0  # epoch seconds of the window start
    count: int = 0


class Feedback(SQLModel, table=True):
    """User feedback (👍/👎 or a rating) on a conversation/message."""

    __tablename__ = "feedback"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    conversation_id: str = Field(default="", index=True)
    message_id: int | None = Field(default=None)
    rating: int = 0  # -1 / +1, or 1..5
    comment: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
