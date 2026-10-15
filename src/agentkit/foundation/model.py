"""A thin, expressive ``Model`` / ``Query`` layer over SQLModel (async).

Deliberately small — equality filters, first/get/create/update/delete, counting
and pagination — over the existing async engine/``Repositories``. It is not
Eloquent: no relationships, eager loading, or migrations.

    from agentkit import Model

    class Reminder(Model, table=True):
        name: str
        cron: str

    await Reminder.create(name="digest", cron="0 8 * * 1")
    await Reminder.where(cron="0 8 * * 1").first()
    await Reminder.count()
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import func
from sqlmodel import SQLModel, select

from agentkit.errors import NotFound
from agentkit.foundation.db import active_repos, session_scope


@asynccontextmanager
async def _ambient(repos: Any) -> AsyncIterator[Any]:
    yield repos


def _scope() -> Any:
    existing = active_repos()
    if existing is not None:
        return _ambient(existing)
    from agentkit.foundation.facade import current_app

    return session_scope(current_app())


class Query:
    """A chainable, equality-filtered query over one model."""

    def __init__(
        self,
        model: type,
        filters: dict[str, Any] | None = None,
        *,
        order_by: Any = None,
        descending: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> None:
        self.model = model
        self.filters = dict(filters or {})
        self._order_by = order_by
        self._descending = descending
        self._limit = limit
        self._offset = offset

    def where(self, **filters: Any) -> Query:
        clone = self._clone()
        clone.filters.update(filters)
        return clone

    def order_by(self, field: Any, *, descending: bool = False) -> Query:
        clone = self._clone()
        clone._order_by = field
        clone._descending = descending
        return clone

    def limit(self, value: int) -> Query:
        clone = self._clone()
        clone._limit = value
        return clone

    def offset(self, value: int) -> Query:
        clone = self._clone()
        clone._offset = value
        return clone

    def _clone(self) -> Query:
        return Query(
            self.model,
            self.filters,
            order_by=self._order_by,
            descending=self._descending,
            limit=self._limit,
            offset=self._offset,
        )

    def _statement(self) -> Any:
        stmt: Any = select(self.model)
        for field, value in self.filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        if self._order_by is not None:
            column = getattr(self.model, self._order_by) if isinstance(self._order_by, str) else self._order_by
            stmt = stmt.order_by(column.desc() if self._descending else column)
        if self._offset is not None:
            stmt = stmt.offset(self._offset)
        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        return stmt

    async def all(self) -> list[Any]:
        async with _scope() as repos:
            return list((await repos.session.exec(self._statement())).all())

    async def first(self) -> Any:
        rows = await self.limit(1).all()
        return rows[0] if rows else None

    async def count(self) -> int:
        async with _scope() as repos:
            stmt: Any = select(func.count()).select_from(self.model)
            for field, value in self.filters.items():
                stmt = stmt.where(getattr(self.model, field) == value)
            return int((await repos.session.exec(stmt)).one())

    async def paginate(self, page: int = 1, per_page: int = 15) -> dict[str, Any]:
        page = max(1, page)
        per_page = max(1, per_page)
        total = await self.count()
        items = await self.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }


class Model(SQLModel):
    """Base class for app tables with an active-record-ish surface."""

    @classmethod
    def query(cls, **filters: Any) -> Query:
        return Query(cls, filters)

    @classmethod
    def where(cls, **filters: Any) -> Query:
        return Query(cls, filters)

    @classmethod
    def order_by(cls, field: Any, *, descending: bool = False) -> Query:
        return Query(cls).order_by(field, descending=descending)

    @classmethod
    async def all(cls, **filters: Any) -> list[Any]:
        return await Query(cls, filters).all()

    @classmethod
    async def first(cls, **filters: Any) -> Any:
        rows = await Query(cls, filters).limit(1).all()
        return rows[0] if rows else None

    @classmethod
    async def first_or_fail(cls, **filters: Any) -> Any:
        row = await cls.first(**filters)
        if row is None:
            raise NotFound(f"{cls.__name__} not found for {filters!r}")
        return row

    @classmethod
    async def find_or_fail(cls, ident: Any) -> Any:
        row = await cls.get(ident)
        if row is None:
            raise NotFound(f"{cls.__name__} {ident!r} not found")
        return row

    @classmethod
    async def first_or_create(cls, *, defaults: dict[str, Any] | None = None, **filters: Any) -> Any:
        row = await cls.first(**filters)
        if row is not None:
            return row
        return await cls.create(**{**filters, **(defaults or {})})

    @classmethod
    async def update_or_create(
        cls, *, defaults: dict[str, Any] | None = None, **filters: Any
    ) -> Any:
        row = await cls.first(**filters)
        if row is None:
            return await cls.create(**{**filters, **(defaults or {})})
        for field, value in (defaults or {}).items():
            setattr(row, field, value)
        async with _scope() as repos:
            repos.session.add(row)
            await repos.session.flush()
            await repos.session.refresh(row)
        return row

    @classmethod
    async def get(cls, ident: Any) -> Any:
        async with _scope() as repos:
            return await repos.session.get(cls, ident)

    @classmethod
    async def count(cls, **filters: Any) -> int:
        return await Query(cls, filters).count()

    @classmethod
    async def create(cls, **values: Any) -> Any:
        if "owner_id" not in values and hasattr(cls, "owner_id"):
            from agentkit.foundation.facade import get_current_app

            app = get_current_app()
            values["owner_id"] = getattr(getattr(app, "settings", None), "owner_id", "owner")
        async with _scope() as repos:
            instance = cls(**values)
            repos.session.add(instance)
            await repos.session.flush()
            await repos.session.refresh(instance)
            return instance

    @classmethod
    async def update(cls, ident: Any, **values: Any) -> Any:
        async with _scope() as repos:
            instance = await repos.session.get(cls, ident)
            if instance is None:
                return None
            for field, value in values.items():
                setattr(instance, field, value)
            repos.session.add(instance)
            await repos.session.flush()
            await repos.session.refresh(instance)
            return instance

    @classmethod
    async def delete(cls, ident: Any) -> bool:
        async with _scope() as repos:
            instance = await repos.session.get(cls, ident)
            if instance is None:
                return False
            await repos.session.delete(instance)
            await repos.session.flush()
            return True

    @classmethod
    async def paginate(cls, page: int = 1, per_page: int = 15, **filters: Any) -> dict[str, Any]:
        return await Query(cls, filters).paginate(page, per_page)


__all__ = ["Model", "Query"]
