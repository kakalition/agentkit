"""Owner-scoped eval datasets, graders, and run records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.models import EvalDatasetRecord, EvalGraderRecord, EvalRunRecord


class EvalDatasetRepo:
    """CRUD over named eval datasets."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def upsert(
        self,
        name: str,
        *,
        cases: list[dict[str, Any]] | None = None,
        source: str = "",
        cases_json: str | None = None,
    ) -> EvalDatasetRecord:
        record = await self.get(name)
        if record is None:
            record = EvalDatasetRecord(owner_id=self.owner_id, name=name)
        record.source = source
        record.cases = cases_json if cases_json is not None else json.dumps(cases or [], default=str)
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, name: str) -> EvalDatasetRecord | None:
        stmt = select(EvalDatasetRecord).where(
            EvalDatasetRecord.owner_id == self.owner_id, EvalDatasetRecord.name == name
        )
        return (await self.session.exec(stmt)).first()

    async def list(self) -> list[EvalDatasetRecord]:
        stmt = (
            select(EvalDatasetRecord)
            .where(EvalDatasetRecord.owner_id == self.owner_id)
            .order_by(EvalDatasetRecord.name)  # type: ignore[attr-defined]
        )
        return list((await self.session.exec(stmt)).all())

    async def remove(self, name: str) -> bool:
        record = await self.get(name)
        if record is None:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True


class EvalGraderRepo:
    """CRUD over named grader configurations."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def upsert(
        self, name: str, *, driver: str = "exact", options: dict[str, Any] | None = None
    ) -> EvalGraderRecord:
        return await self._upsert(name, driver, json.dumps(options or {}, default=str))

    async def _upsert(self, name: str, driver: str, options_json: str) -> EvalGraderRecord:
        record = await self.get(name)
        if record is None:
            record = EvalGraderRecord(owner_id=self.owner_id, name=name)
        record.driver = driver
        record.options = options_json
        record.updated_at = datetime.now(UTC)
        self.session.add(record)
        await self.session.flush()
        return record

    async def get(self, name: str) -> EvalGraderRecord | None:
        stmt = select(EvalGraderRecord).where(
            EvalGraderRecord.owner_id == self.owner_id, EvalGraderRecord.name == name
        )
        return (await self.session.exec(stmt)).first()

    async def list(self) -> list[EvalGraderRecord]:
        stmt = (
            select(EvalGraderRecord)
            .where(EvalGraderRecord.owner_id == self.owner_id)
            .order_by(EvalGraderRecord.name)  # type: ignore[attr-defined]
        )
        return list((await self.session.exec(stmt)).all())

    async def remove(self, name: str) -> bool:
        record = await self.get(name)
        if record is None:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True


class EvalRunRepo:
    """Append + read recorded eval runs."""

    def __init__(self, session: AsyncSession, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    async def add(
        self,
        dataset: str,
        *,
        passed: bool = False,
        report: Any = None,
        run_id: str = "",
    ) -> EvalRunRecord:
        payload = report if isinstance(report, str) else json.dumps(report or {}, default=str)
        record = EvalRunRecord(
            owner_id=self.owner_id,
            dataset=dataset,
            run_id=run_id,
            passed=bool(passed),
            report=payload,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list(self, *, limit: int = 100) -> list[EvalRunRecord]:
        stmt = (
            select(EvalRunRecord)
            .where(EvalRunRecord.owner_id == self.owner_id)
            .order_by(EvalRunRecord.id.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        return list((await self.session.exec(stmt)).all())
