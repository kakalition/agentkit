"""Token usage accounting and the hash-chained audit log."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import AuditEntry, UsageRecord


class UsageRepo:
    """Token accounting (counts only)."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add(
        self,
        *,
        conversation_id: str | None = None,
        kind: str = "turn",
        model: str = "",
        requests: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cost_usd: float = 0.0,
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
            cost_usd=cost_usd,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list(self, limit: int | None = None) -> list[UsageRecord]:
        stmt = (
            select(UsageRecord)
            .where(UsageRecord.owner_id == self.owner_id)
            .order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc())
        )
        rows = list((await self.session.exec(stmt)).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows

    async def totals(self, *, since: datetime | None = None) -> dict[str, int | float]:
        columns = (
            func.coalesce(func.sum(UsageRecord.requests), 0),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0),
        )
        stmt: Any = select(*columns).where(UsageRecord.owner_id == self.owner_id)  # type: ignore[call-overload]
        if since is not None:
            stmt = stmt.where(UsageRecord.created_at >= since)
        row: Any = (await self.session.exec(stmt)).one()
        requests, input_tokens, output_tokens, total_tokens, cost_usd = row
        return {
            "requests": int(requests),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(total_tokens),
            "cost_usd": round(float(cost_usd), 6),
        }


class AuditRepo:
    """Append-only, hash-chained audit log (tamper-evident)."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    @staticmethod
    def _hash(seq: int, action: str, target: str, detail: dict, actor: str, prev: str) -> str:
        payload = json.dumps(
            {"seq": seq, "action": action, "target": target, "detail": detail, "actor": actor, "prev": prev},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def append(
        self, action: str, *, target: str = "", detail: dict | None = None, actor: str = ""
    ) -> AuditEntry:
        last = (
            await self.session.exec(
                select(AuditEntry)
                .where(AuditEntry.owner_id == self.owner_id)
                .order_by(AuditEntry.seq.desc())
            )
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
        await self.session.flush()
        return entry

    async def entries(self, limit: int | None = None) -> list[AuditEntry]:
        stmt = (
            select(AuditEntry)
            .where(AuditEntry.owner_id == self.owner_id)
            .order_by(AuditEntry.seq)
        )
        rows = list((await self.session.exec(stmt)).all())
        if limit is not None and len(rows) > limit:
            rows = rows[:limit]
        return rows

    async def verify(self) -> bool:
        prev = ""
        for entry in await self.entries():
            expected = self._hash(
                entry.seq, entry.action, entry.target, json.loads(entry.detail or "{}"), entry.actor, prev
            )
            if entry.prev_hash != prev or entry.entry_hash != expected:
                return False
            prev = entry.entry_hash
        return True


