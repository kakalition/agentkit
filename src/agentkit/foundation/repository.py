"""Repositories — a base class so you never hand-write CRUD again.

A repository is the data-access layer for one model. Declare the model and you
inherit the whole surface (create, get, list, update, delete, count, paginate):

    from agentkit import Model, Repository

    class Reminder(Model, table=True):
        ...

    class ReminderRepo(Repository[Reminder]):
        model = Reminder

        def due(self, when):            # add only what is special to reminders
            return self.where(due_at=when).all()

Attach repositories to the app's container declaratively:

    class AppRepositories(Repositories):
        repositories = {"reminders": ReminderRepo}
"""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from sqlmodel import delete as sql_delete
from sqlmodel import func, select

from agentkit.errors import NotFound

ModelT = TypeVar("ModelT")

__all__ = ["Repository", "RepositoryQuery"]


class RepositoryQuery(Generic[ModelT]):
    """An immutable, chainable query bound to a repository's session."""

    def __init__(
        self,
        repository: Repository[ModelT],
        filters: dict[str, Any] | None = None,
        *,
        order_by: Any = None,
        descending: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> None:
        self._repo = repository
        self._filters = dict(filters or {})
        self._order_by = order_by
        self._descending = descending
        self._limit = limit
        self._offset = offset

    # -- chaining -------------------------------------------------------
    def _clone(self, **changes: Any) -> RepositoryQuery[ModelT]:
        state = {
            "order_by": self._order_by,
            "descending": self._descending,
            "limit": self._limit,
            "offset": self._offset,
        }
        state.update(changes)
        return RepositoryQuery(self._repo, self._filters, **state)

    def where(self, **filters: Any) -> RepositoryQuery[ModelT]:
        clone = self._clone()
        clone._filters.update(filters)
        return clone

    def order_by(self, field: Any, *, descending: bool = False) -> RepositoryQuery[ModelT]:
        return self._clone(order_by=field, descending=descending)

    def latest(self, field: Any = "id") -> RepositoryQuery[ModelT]:
        return self._clone(order_by=field, descending=True)

    def limit(self, value: int) -> RepositoryQuery[ModelT]:
        return self._clone(limit=value)

    def offset(self, value: int) -> RepositoryQuery[ModelT]:
        return self._clone(offset=value)

    # -- terminals ------------------------------------------------------
    def _statement(self) -> Any:
        model = self._repo.model
        stmt: Any = select(model)
        stmt = self._repo._scoped(stmt)
        for field, value in self._filters.items():
            stmt = stmt.where(getattr(model, field) == value)
        if self._order_by is not None:
            column = getattr(model, self._order_by) if isinstance(self._order_by, str) else self._order_by
            stmt = stmt.order_by(column.desc() if self._descending else column)
        if self._offset is not None:
            stmt = stmt.offset(self._offset)
        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        return stmt

    def all(self) -> list[ModelT]:
        return list(self._repo.session.exec(self._statement()).all())

    def first(self) -> ModelT | None:
        rows = self.limit(1).all()
        return rows[0] if rows else None

    def count(self) -> int:
        model = self._repo.model
        stmt: Any = select(func.count()).select_from(model)
        stmt = self._repo._scoped(stmt)
        for field, value in self._filters.items():
            stmt = stmt.where(getattr(model, field) == value)
        return int(self._repo.session.exec(stmt).one())

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

    def delete(self) -> int:
        model = self._repo.model
        stmt: Any = sql_delete(model)
        stmt = self._repo._scoped(stmt)
        for field, value in self._filters.items():
            stmt = stmt.where(getattr(model, field) == value)
        result = self._repo.session.exec(stmt)
        self._repo.session.flush()
        return int(getattr(result, "rowcount", 0) or 0)


class Repository(Generic[ModelT]):
    """Base data-access class for one model.

    Subclasses set ``model`` (and optionally ``owner_scoped = False``) and add
    only their domain-specific queries.
    """

    model: ClassVar[Any] = None
    owner_scoped: ClassVar[bool] = True

    def __init__(self, session: Any, owner_id: str) -> None:
        self.session = session
        self.owner_id = owner_id

    # -- helpers --------------------------------------------------------
    def _scoped(self, stmt: Any) -> Any:
        model = self.model
        if self.owner_scoped and hasattr(model, "owner_id"):
            return stmt.where(model.owner_id == self.owner_id)
        return stmt

    def _has_owner(self) -> bool:
        return hasattr(self.model, "owner_id")

    def new(self, **values: Any) -> ModelT:
        """Build an instance (not persisted), filling ``owner_id`` if present."""
        if self._has_owner() and "owner_id" not in values:
            values["owner_id"] = self.owner_id
        return self.model(**values)  # type: ignore[no-any-return]

    # -- writes ---------------------------------------------------------
    def create(self, **values: Any) -> ModelT:
        instance = self.new(**values)
        self.session.add(instance)
        self.session.flush()
        self.session.refresh(instance)
        return instance

    # Laravel-ish alias.
    add = create

    def update(self, ident: Any, **values: Any) -> ModelT | None:
        instance = self.get(ident)
        if instance is None:
            return None
        for field, value in values.items():
            setattr(instance, field, value)
        self.session.add(instance)
        self.session.flush()
        self.session.refresh(instance)
        return instance

    def update_or_create(self, *, defaults: dict[str, Any], **lookup: Any) -> tuple[ModelT, bool]:
        instance = self.first(**lookup)
        if instance is not None:
            for field, value in defaults.items():
                setattr(instance, field, value)
            self.session.add(instance)
            self.session.flush()
            return instance, False
        return self.create(**{**lookup, **defaults}), True

    def delete(self, ident: Any) -> bool:
        instance = self.get(ident)
        if instance is None:
            return False
        self.session.delete(instance)
        self.session.flush()
        return True

    # -- reads ----------------------------------------------------------
    def get(self, ident: Any) -> ModelT | None:
        instance = self.session.get(self.model, ident)
        if instance is None:
            return None
        if self._has_owner() and getattr(instance, "owner_id", None) != self.owner_id:
            return None
        return instance

    def find(self, ident: Any) -> ModelT:
        instance = self.get(ident)
        if instance is None:
            raise NotFound(f"{self.model.__name__} {ident!r} not found")
        return instance

    def exists(self, ident: Any) -> bool:
        return self.get(ident) is not None

    def where(self, **filters: Any) -> RepositoryQuery[ModelT]:
        return RepositoryQuery(self, filters)

    def all(
        self,
        *,
        order_by: Any = None,
        descending: bool = False,
        limit: int | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        query = self.where(**filters)
        if order_by is not None:
            query = query.order_by(order_by, descending=descending)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def first(self, **filters: Any) -> ModelT | None:
        return self.where(**filters).first()

    def count(self, **filters: Any) -> int:
        return self.where(**filters).count()

    def paginate(self, page: int = 1, per_page: int = 15, **filters: Any) -> dict[str, Any]:
        return self.where(**filters).paginate(page, per_page)

    def delete_where(self, **filters: Any) -> int:
        return self.where(**filters).delete()
