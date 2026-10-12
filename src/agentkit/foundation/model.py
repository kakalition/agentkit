"""A thin, expressive ``Model`` / ``Query`` layer over SQLModel.

Deliberately small — equality filters, first/get/create/update/delete, counting
and pagination — over the existing engine/``Repositories``. It is not Eloquent:
no relationships, eager loading, or migrations.

    from agentkit import Model

    class Reminder(Model, table=True):
        name: str
        cron: str

    Reminder.create(name="digest", cron="0 8 * * 1")
    Reminder.where(cron="0 8 * * 1").first()
    Reminder.count()
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from sqlalchemy import func
from sqlmodel import SQLModel, select

from agentkit.foundation.db import active_repos, session_scope


def _scope() -> Any:
    existing = active_repos()
    if existing is not None:
        return nullcontext(existing)
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

    def all(self) -> list[Any]:
        with _scope() as repos:
            return list(repos.session.exec(self._statement()).all())

    def first(self) -> Any:
        rows = self.limit(1).all()
        return rows[0] if rows else None

    def count(self) -> int:
        with _scope() as repos:
            stmt: Any = select(func.count()).select_from(self.model)
            for field, value in self.filters.items():
                stmt = stmt.where(getattr(self.model, field) == value)
            return int(repos.session.exec(stmt).one())

    def paginate(self, page: int = 1, per_page: int = 15) -> dict[str, Any]:
        page = max(1, page)
        per_page = max(1, per_page)
        total = self.count()
        items = self.offset((page - 1) * per_page).limit(per_page).all()
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
    def all(cls, **filters: Any) -> list[Any]:
        return Query(cls, filters).all()

    @classmethod
    def first(cls, **filters: Any) -> Any:
        rows = Query(cls, filters).limit(1).all()
        return rows[0] if rows else None

    @classmethod
    def get(cls, ident: Any) -> Any:
        with _scope() as repos:
            return repos.session.get(cls, ident)

    @classmethod
    def count(cls, **filters: Any) -> int:
        return Query(cls, filters).count()

    @classmethod
    def create(cls, **values: Any) -> Any:
        with _scope() as repos:
            instance = cls(**values)
            repos.session.add(instance)
            repos.session.flush()
            repos.session.refresh(instance)
            return instance

    @classmethod
    def update(cls, ident: Any, **values: Any) -> Any:
        with _scope() as repos:
            instance = repos.session.get(cls, ident)
            if instance is None:
                return None
            for field, value in values.items():
                setattr(instance, field, value)
            repos.session.add(instance)
            repos.session.flush()
            repos.session.refresh(instance)
            return instance

    @classmethod
    def delete(cls, ident: Any) -> bool:
        with _scope() as repos:
            instance = repos.session.get(cls, ident)
            if instance is None:
                return False
            repos.session.delete(instance)
            repos.session.flush()
            return True

    @classmethod
    def paginate(cls, page: int = 1, per_page: int = 15, **filters: Any) -> dict[str, Any]:
        return Query(cls, filters).paginate(page, per_page)


__all__ = ["Model", "Query"]
