"""Eloquent-style relationships for :class:`~agentkit.foundation.model.Model`.

Declared as un-annotated class attributes on a model::

    class User(Model, table=True):
        id: int | None = Field(default=None, primary_key=True)
        posts = has_many("Post", foreign_key="user_id")
        profile = has_one("Profile", foreign_key="user_id")

Reading a relationship returns a :class:`Relation` proxy that can be awaited
(lazy load) and caches its value on the instance, so an eager-loaded relationship
reads back as the plain value::

    user.posts          # -> Relation (awaitable)
    posts = await user.posts
    user.posts          # -> Collection (cached)

Eager loading (``Query.with_("posts")``) batches the related rows to avoid N+1.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlmodel import select

from agentkit.foundation.collection import Collection

__all__ = [
    "BelongsTo",
    "BelongsToMany",
    "HasMany",
    "HasManyThrough",
    "HasOne",
    "LazyLoadingViolation",
    "Relation",
    "Relationship",
    "belongs_to",
    "belongs_to_many",
    "has_many",
    "has_many_through",
    "has_one",
]


class LazyLoadingViolation(RuntimeError):
    """Raised when a relationship is lazily loaded while the guard is enabled."""


def _snake(name: str) -> str:
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index and not name[index - 1].isupper():
            out.append("_")
        out.append(char.lower())
    return "".join(out)


def primary_key_name(model: Any) -> str:
    """The primary key column name for a model (falls back to ``"id"``)."""
    table = getattr(model, "__table__", None)
    if table is not None:
        columns = list(table.primary_key.columns)
        if columns:
            return str(columns[0].name)
    fields = getattr(model, "model_fields", {})
    for name, info in fields.items():
        if getattr(info, "primary_key", False):
            return name
    return "id"


def resolve_model(reference: Any, owner: Any = None) -> Any:
    """Resolve a related-model reference (class, string, or lazy ``module:Class``)."""
    if isinstance(reference, type):
        return reference
    if isinstance(reference, str):
        module_name, _, attr = reference.partition(":")
        if module_name and attr:
            import importlib

            return getattr(importlib.import_module(module_name), attr)
        owner_module = getattr(owner, "__module__", None)
        if owner_module:
            import importlib
            import sys

            module = sys.modules.get(owner_module)
            if module is not None and hasattr(module, reference):
                return getattr(module, reference)
        raise LookupError(f"cannot resolve related model {reference!r}")
    return reference


class Relation:
    """An awaitable proxy over a not-yet-loaded relationship."""

    def __init__(self, instance: Any, relationship: Relationship) -> None:
        self._instance = instance
        self._relationship = relationship

    @property
    def name(self) -> str:
        return self._relationship.name

    def __await__(self) -> Any:
        return self._load().__await__()

    async def _load(self) -> Any:
        return await self._relationship.load(self._instance)

    async def all(self) -> Any:
        return await self._load()

    async def first(self) -> Any:
        value = await self._load()
        if isinstance(value, Collection):
            return value.first()
        return value

    async def get(self) -> Any:
        value = await self._load()
        return value

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Relation {self.name} on {type(self._instance).__name__}>"


class Relationship:
    """Base relationship descriptor."""

    kind = "relation"
    singular = False

    def __init__(self, related: Any = None, *, name: str | None = None) -> None:
        self.related = related
        self.name = name or ""
        self.owner: Any = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.owner = owner
        if not self.name:
            self.name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        cache = _cache(instance)
        if self.name in cache:
            return cache[self.name]
        return Relation(instance, self)

    def _related_class(self) -> Any:
        return resolve_model(self.related, self.owner)

    async def load(self, instance: Any) -> Any:
        if getattr(type(instance), "prevent_lazy_loading", False):
            raise LazyLoadingViolation(
                f"lazy loading {self.name!r} on {type(instance).__name__} is disabled; "
                f"eager load it with .with_({self.name!r})"
            )
        from agentkit.foundation.db import session_scope
        from agentkit.foundation.facade import current_app

        async with session_scope(current_app()) as repos:
            value = await self.load_with(instance, repos.session)
        _cache(instance)[self.name] = value
        return value

    async def load_with(self, instance: Any, session: Any) -> Any:
        raise NotImplementedError

    async def eager(self, instances: Sequence[Any], session: Any) -> None:
        raise NotImplementedError


def _cache(instance: Any) -> dict[str, Any]:
    """The per-instance relationship cache (stored in ``__dict__``)."""
    data = getattr(instance, "__dict__", None)
    if data is None:  # pragma: no cover - non-standard instance
        data = {}
        object.__setattr__(instance, "__dict__", data)
    cache = data.get("_relations")
    if cache is None:
        cache = {}
        data["_relations"] = cache
    return cache


def _as_collection(value: Any) -> Any:
    return value if isinstance(value, Collection) else Collection(value)


class HasMany(Relationship):
    kind = "has_many"

    def __init__(
        self,
        related: Any = None,
        *,
        foreign_key: str | None = None,
        local_key: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(related, name=name)
        self.foreign_key = foreign_key
        self.local_key = local_key

    def _fk(self) -> str:
        return self.foreign_key or f"{_snake(self.owner.__name__)}_id"

    def _lk(self) -> str:
        return self.local_key or primary_key_name(self.owner)

    async def load_with(self, instance: Any, session: Any) -> Collection[Any]:
        related = self._related_class()
        owner_value = getattr(instance, self._lk())
        stmt = select(related).where(getattr(related, self._fk()) == owner_value)
        return Collection((await session.exec(stmt)).all())

    async def eager(self, instances: Sequence[Any], session: Any) -> None:
        related = self._related_class()
        keys = {getattr(instance, self._lk()) for instance in instances}
        keys.discard(None)
        if not keys:
            for instance in instances:
                _cache(instance)[self.name] = Collection()
            return
        stmt = select(related).where(getattr(related, self._fk()).in_(list(keys)))
        grouped: dict[Any, list[Any]] = {}
        for row in (await session.exec(stmt)).all():
            grouped.setdefault(getattr(row, self._fk()), []).append(row)
        for instance in instances:
            _cache(instance)[self.name] = Collection(grouped.get(getattr(instance, self._lk()), []))


class HasOne(HasMany):
    kind = "has_one"
    singular = True

    async def load_with(self, instance: Any, session: Any) -> Any:
        collection = await super().load_with(instance, session)
        return collection.first()

    async def eager(self, instances: Sequence[Any], session: Any) -> None:
        related = self._related_class()
        keys = {getattr(instance, self._lk()) for instance in instances}
        keys.discard(None)
        if not keys:
            for instance in instances:
                _cache(instance)[self.name] = None
            return
        stmt = select(related).where(getattr(related, self._fk()).in_(list(keys)))
        firsts: dict[Any, Any] = {}
        for row in (await session.exec(stmt)).all():
            firsts.setdefault(getattr(row, self._fk()), row)
        for instance in instances:
            _cache(instance)[self.name] = firsts.get(getattr(instance, self._lk()))


class BelongsTo(Relationship):
    kind = "belongs_to"
    singular = True

    def __init__(
        self,
        related: Any = None,
        *,
        foreign_key: str | None = None,
        owner_key: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(related, name=name)
        self.foreign_key = foreign_key
        self.owner_key = owner_key

    def _fk(self) -> str:
        return self.foreign_key or f"{_snake(self._related_class().__name__)}_id"

    def _ok(self) -> str:
        return self.owner_key or primary_key_name(self._related_class())

    async def load_with(self, instance: Any, session: Any) -> Any:
        related = self._related_class()
        value = getattr(instance, self._fk())
        if value is None:
            return None
        stmt = select(related).where(getattr(related, self._ok()) == value)
        return (await session.exec(stmt)).first()

    async def eager(self, instances: Sequence[Any], session: Any) -> None:
        related = self._related_class()
        keys = {getattr(instance, self._fk()) for instance in instances}
        keys.discard(None)
        if not keys:
            for instance in instances:
                _cache(instance)[self.name] = None
            return
        stmt = select(related).where(getattr(related, self._ok()).in_(list(keys)))
        found = {getattr(row, self._ok()): row for row in (await session.exec(stmt)).all()}
        for instance in instances:
            _cache(instance)[self.name] = found.get(getattr(instance, self._fk()))


class BelongsToMany(Relationship):
    kind = "belongs_to_many"

    def __init__(
        self,
        related: Any = None,
        *,
        pivot: Any = None,
        foreign_pivot_key: str | None = None,
        related_pivot_key: str | None = None,
        local_key: str | None = None,
        related_key: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(related, name=name)
        self.pivot = pivot
        self.foreign_pivot_key = foreign_pivot_key
        self.related_pivot_key = related_pivot_key
        self.local_key = local_key
        self.related_key = related_key

    def _pivot(self) -> Any:
        if self.pivot is None:
            raise ValueError(f"belongs_to_many {self.name!r} requires a pivot table")
        return self.pivot

    def _fpk(self) -> str:
        return self.foreign_pivot_key or f"{_snake(self.owner.__name__)}_id"

    def _rpk(self) -> str:
        return self.related_pivot_key or f"{_snake(self._related_class().__name__)}_id"

    def _lk(self) -> str:
        return self.local_key or primary_key_name(self.owner)

    def _rk(self) -> str:
        return self.related_key or primary_key_name(self._related_class())

    def _stmt_for_keys(self, keys: Iterable[Any]) -> Any:
        related = self._related_class()
        pivot = self._pivot()
        pivot_table = getattr(pivot, "__table__", pivot)
        related_table = related.__table__
        join = related_table.join(
            pivot_table, getattr(related_table.c, self._rk()) == getattr(pivot_table.c, self._rpk())
        )
        return (
            select(related)
            .select_from(join)
            .where(getattr(pivot_table.c, self._fpk()).in_(list(keys)))
        )

    async def load_with(self, instance: Any, session: Any) -> Collection[Any]:
        value = getattr(instance, self._lk())
        if value is None:
            return Collection()
        return Collection((await session.exec(self._stmt_for_keys([value]))).all())

    async def eager(self, instances: Sequence[Any], session: Any) -> None:
        keys = {getattr(instance, self._lk()) for instance in instances}
        keys.discard(None)
        grouped: dict[Any, list[Any]] = {}
        if keys:
            for row in (await session.exec(self._stmt_for_keys(keys))).all():
                pivot_key = getattr(row, self._rk())
                grouped.setdefault(pivot_key, []).append(row)
        for instance in instances:
            _cache(instance)[self.name] = Collection(grouped.get(getattr(instance, self._lk()), []))


class HasManyThrough(Relationship):
    kind = "has_many_through"

    def __init__(
        self,
        related: Any = None,
        through: Any = None,
        *,
        first_key: str | None = None,
        second_key: str | None = None,
        local_key: str | None = None,
        second_local_key: str | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(related, name=name)
        self.through = through
        self.first_key = first_key
        self.second_key = second_key
        self.local_key = local_key
        self.second_local_key = second_local_key

    def _through(self) -> Any:
        return resolve_model(self.through, self.owner)

    def _first_key(self) -> str:
        return self.first_key or f"{_snake(self.owner.__name__)}_id"

    def _second_local(self) -> str:
        return self.second_local_key or primary_key_name(self._through())

    def _second_key(self) -> str:
        return self.second_key or f"{_snake(self._through().__name__)}_id"

    def _lk(self) -> str:
        return self.local_key or primary_key_name(self.owner)

    async def load_with(self, instance: Any, session: Any) -> Collection[Any]:
        through = self._through()
        related = self._related_class()
        value = getattr(instance, self._lk())
        if value is None:
            return Collection()
        first = select(through).where(getattr(through, self._first_key()) == value)
        rows = list((await session.exec(first)).all())
        keys = [getattr(row, self._second_local()) for row in rows]
        keys = [key for key in keys if key is not None]
        if not keys:
            return Collection()
        second = select(related).where(getattr(related, self._second_key()).in_(keys))
        return Collection((await session.exec(second)).all())

    async def eager(self, instances: Sequence[Any], session: Any) -> None:
        for instance in instances:
            _cache(instance)[self.name] = await self.load_with(instance, session)


def has_many(related: Any = None, **kwargs: Any) -> HasMany:
    return HasMany(related, **kwargs)


def has_one(related: Any = None, **kwargs: Any) -> HasOne:
    return HasOne(related, **kwargs)


def belongs_to(related: Any = None, **kwargs: Any) -> BelongsTo:
    return BelongsTo(related, **kwargs)


def belongs_to_many(related: Any = None, **kwargs: Any) -> BelongsToMany:
    return BelongsToMany(related, **kwargs)


def has_many_through(related: Any = None, through: Any = None, **kwargs: Any) -> HasManyThrough:
    return HasManyThrough(related, through, **kwargs)
