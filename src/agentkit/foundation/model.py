"""Eloquent-style models over SQLModel (async).

``Model`` keeps the original thin surface (``where``/``first``/``create``/
``update``/``delete``/``count``/``paginate``) and adds the Eloquent features on
top of the existing async session: relationships, eager loading, casts,
accessors/mutators, scopes, global scopes, soft deletes, observers/model events,
mass assignment, and :class:`~agentkit.foundation.collection.Collection` /
:class:`~agentkit.foundation.pagination.LengthAwarePaginator` returns.

    from agentkit import Model, SoftDeletes

    class User(Model, table=True):
        id: int | None = Field(default=None, primary_key=True)
        name: str
        casts = {"meta": "json"}
        posts = has_many("Post", foreign_key="user_id")

    user = await User.create(name="Ada")
    await User.where(name="Ada").first()
    await User.with_("posts").all()
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import func
from sqlmodel import Field, SQLModel, select
from sqlmodel.main import SQLModelConfig, SQLModelMetaclass

from agentkit.errors import NotFound
from agentkit.foundation.casts import Cast, resolve_cast
from agentkit.foundation.clock import now
from agentkit.foundation.collection import Collection, CursorCollection
from agentkit.foundation.db import active_repos, session_scope
from agentkit.foundation.pagination import LengthAwarePaginator
from agentkit.foundation.relations import LazyLoadingViolation, Relationship

__all__ = [
    "Attribute",
    "GlobalScope",
    "LazyLoadingViolation",
    "Model",
    "ModelEvent",
    "Observer",
    "Query",
    "SoftDeletes",
]


# -- helpers ---------------------------------------------------------------


@asynccontextmanager
async def _scope() -> AsyncIterator[Any]:
    existing = active_repos()
    if existing is not None:
        yield existing
        return
    from agentkit.foundation.facade import current_app

    async with session_scope(current_app()) as repos:
        yield repos


def _has_soft_deletes(model: Any) -> bool:
    return bool(getattr(model, "__soft_deletes__", False))


class Attribute:
    """A computed/appended attribute (Laravel's ``Attribute`` accessor).

        full_name = Attribute(get=lambda self: f"{self.first} {self.last}")
    """

    def __init__(
        self,
        get: Callable[[Any], Any] | None = None,
        set: Callable[[Any, Any], Any] | None = None,
    ) -> None:
        self._get = get
        self._set = set

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        if self._get is None:
            raise AttributeError(self.name)
        return self._get(instance)

    def __set__(self, instance: Any, value: Any) -> None:
        if self._set is None:
            raise AttributeError(f"{self.name} is read-only")
        self._set(instance, value)

    def __delete__(self, instance: Any) -> None:  # pragma: no cover - defensive
        raise AttributeError(self.name)


class GlobalScope:
    """A query filter applied to every read of a model."""

    name: ClassVar[str] = "global"

    def apply(self, query: Query) -> Query:  # pragma: no cover - overridden
        return query


_CONFIG_KEYS = {
    "casts",
    "appends",
    "hidden",
    "visible",
    "fillable",
    "guarded",
    "global_scopes",
    "observers",
    "prevent_lazy_loading",
}


class ModelMeta(SQLModelMetaclass):
    """Pull Laravel config keys out of the namespace and precompute class tables."""

    def __new__(mcls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any):
        config: dict[str, Any] = {}
        for key in list(namespace):
            if key in _CONFIG_KEYS:
                config[key] = namespace.pop(key)
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        # Inherit from bases, then override with this class's config.
        casts: dict[str, Cast] = {}
        appends: list[str] = []
        hidden: set[str] = set()
        fillable: tuple[str, ...] | None = None
        guarded: tuple[str, ...] = ()
        global_scopes: list[Any] = []
        observers: list[Any] = []
        for base in reversed(bases):
            casts.update(getattr(base, "__casts__", {}) or {})
            appends = list(getattr(base, "__appends__", ()) or [])
            hidden |= set(getattr(base, "__hidden__", ()) or ())
            if getattr(base, "__fillable__", None) is not None:
                fillable = getattr(base, "__fillable__")  # noqa: B009
            guarded = tuple(getattr(base, "__guarded__", ()) or ())
            global_scopes = list(getattr(base, "__global_scopes__", ()) or [])
            observers = list(getattr(base, "__observers__", ()) or [])
        if "casts" in config:
            casts.update({key: resolve_cast(value) for key, value in config["casts"].items()})
        if "appends" in config:
            appends = list(config["appends"])
        if "hidden" in config:
            hidden |= set(config["hidden"])
        if "fillable" in config:
            fillable = tuple(config["fillable"])
        if "guarded" in config:
            guarded = tuple(config["guarded"])
        if "global_scopes" in config:
            global_scopes = list(config["global_scopes"])
        if "observers" in config:
            observers = list(config["observers"])

        accessors: dict[str, Callable[[Any], Any]] = {}
        mutators: dict[str, Callable[[Any, Any], Any]] = {}
        for attr_name, value in vars(cls).items():
            if attr_name.startswith("get_") and attr_name.endswith("_attribute"):
                accessors[attr_name[4:-10]] = _unbound(value)
            elif attr_name.startswith("set_") and attr_name.endswith("_attribute"):
                mutators[attr_name[4:-10]] = _unbound(value)

        cls.__casts__ = casts
        cls.__appends__ = appends
        cls.__hidden__ = hidden
        cls.__fillable__ = fillable
        cls.__guarded__ = guarded
        cls.__global_scopes__ = global_scopes
        cls.__observers__ = observers
        cls.__accessors__ = accessors
        cls.__mutators__ = mutators
        if "prevent_lazy_loading" in config:
            cls.prevent_lazy_loading = bool(config["prevent_lazy_loading"])
        return cls

    def __getattr__(cls, name: str) -> Any:
        # Local scopes: ``Model.active()`` -> ``scope_active(query)``.
        candidates = [f"scope_{name}"]
        if name.endswith("_"):
            candidates.append(f"scope_{name.rstrip('_')}")
        scope = None
        for candidate in candidates:
            for base in cls.__mro__:
                if candidate in base.__dict__:
                    scope = base.__dict__[candidate]
                    break
            if scope is not None:
                break
        if scope is not None:
            scope = scope.__get__(cls, cls) if hasattr(scope, "__get__") else scope

            def scoped(*args: Any, **kwargs: Any) -> Any:
                return scope(cls.query(), *args, **kwargs)

            scoped.__name__ = name
            return scoped
        raise AttributeError(name)


def _unbound(value: Any) -> Any:
    """Return the plain function behind a method defined in a class body."""
    if isinstance(value, (staticmethod, classmethod)):
        return value.__func__
    return value


# -- query -----------------------------------------------------------------


class Query:
    """A chainable query over one model (conditions, ordering, eager loading)."""

    def __init__(
        self,
        model: type,
        conditions: list[Any] | None = None,
        *,
        order_by: Any = None,
        descending: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        eager: Sequence[str] | None = None,
        without_global: Sequence[str] | None = None,
        with_trashed: bool = False,
        only_trashed: bool = False,
    ) -> None:
        self.model = model
        self._conditions = list(conditions or [])
        self._order_by = order_by
        self._descending = descending
        self._limit = limit
        self._offset = offset
        self._eager = list(eager or [])
        self._without_global = list(without_global or [])
        self._with_trashed = with_trashed
        self._only_trashed = only_trashed

    # -- cloning --------------------------------------------------------
    def _clone(self) -> Query:
        return Query(
            self.model,
            self._conditions,
            order_by=self._order_by,
            descending=self._descending,
            limit=self._limit,
            offset=self._offset,
            eager=self._eager,
            without_global=self._without_global,
            with_trashed=self._with_trashed,
            only_trashed=self._only_trashed,
        )

    # -- local scopes ---------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        candidates = [name, name.rstrip("_")] if name.endswith("_") else [name]
        method = None
        for candidate in candidates:
            method = getattr(self.model, f"scope_{candidate}", None)
            if method is not None:
                break
        if method is None:
            raise AttributeError(name)

        def scoped(*args: Any, **kwargs: Any) -> Query:
            return method(self, *args, **kwargs)

        return scoped

    # -- filters --------------------------------------------------------
    def where(self, *expressions: Any, **filters: Any) -> Query:
        clone = self._clone()
        for expression in expressions:
            clone._conditions.append(expression)
        for field, value in filters.items():
            clone._conditions.append(getattr(self.model, field) == value)
        return clone

    def or_where(self, **filters: Any) -> Query:
        from sqlalchemy import or_

        clone = self._clone()
        clone._conditions.append(
            or_(*[getattr(self.model, field) == value for field, value in filters.items()])
        )
        return clone

    def where_in(self, field: str, values: Sequence[Any]) -> Query:
        clone = self._clone()
        clone._conditions.append(getattr(self.model, field).in_(list(values)))
        return clone

    whereIn = where_in  # noqa: N815 - Laravel spelling

    def where_not_in(self, field: str, values: Sequence[Any]) -> Query:
        clone = self._clone()
        clone._conditions.append(getattr(self.model, field).not_in(list(values)))
        return clone

    whereNotIn = where_not_in  # noqa: N815

    def where_null(self, field: str) -> Query:
        clone = self._clone()
        clone._conditions.append(getattr(self.model, field).is_(None))
        return clone

    whereNull = where_null  # noqa: N815

    def where_not_null(self, field: str) -> Query:
        clone = self._clone()
        clone._conditions.append(getattr(self.model, field).is_not(None))
        return clone

    whereNotNull = where_not_null  # noqa: N815

    def where_between(self, field: str, low: Any, high: Any) -> Query:
        clone = self._clone()
        clone._conditions.append(getattr(self.model, field).between(low, high))
        return clone

    whereBetween = where_between  # noqa: N815

    def when(self, condition: Any, callback: Callable[[Query], Query]) -> Query:
        return callback(self) if condition else self

    def with_(self, *names: str) -> Query:
        clone = self._clone()
        for name in names:
            if name not in clone._eager:
                clone._eager.append(name)
        return clone

    def without_global_scope(self, *names: str) -> Query:
        clone = self._clone()
        clone._without_global.extend(names)
        return clone

    def with_trashed(self) -> Query:
        clone = self._clone()
        clone._with_trashed = True
        clone._only_trashed = False
        return clone

    def only_trashed(self) -> Query:
        clone = self._clone()
        clone._only_trashed = True
        clone._with_trashed = False
        return clone

    # -- ordering / paging ---------------------------------------------
    def order_by(self, field: Any, *, descending: bool = False) -> Query:
        clone = self._clone()
        clone._order_by = field
        clone._descending = descending
        return clone

    def latest(self, field: Any = "id") -> Query:
        return self.order_by(field, descending=True)

    def oldest(self, field: Any = "id") -> Query:
        return self.order_by(field)

    def limit(self, value: int) -> Query:
        clone = self._clone()
        clone._limit = value
        return clone

    def take(self, value: int) -> Query:
        return self.limit(value)

    def skip(self, value: int) -> Query:
        return self.offset(value)

    def offset(self, value: int) -> Query:
        clone = self._clone()
        clone._offset = value
        return clone

    # -- statement ------------------------------------------------------
    def _effective_conditions(self) -> list[Any]:
        conditions = list(self._conditions)
        if _has_soft_deletes(self.model) and not self._with_trashed:
            column = getattr(self.model, "deleted_at")  # noqa: B009
            conditions.append(column.is_not(None) if self._only_trashed else column.is_(None))
        return conditions

    def _compiled(self) -> Query:
        """Apply global scopes (each may add conditions), returning a new query."""
        query = self
        for scope in getattr(self.model, "__global_scopes__", ()) or ():
            if getattr(scope, "name", None) in self._without_global:
                continue
            apply = getattr(scope, "apply", None)
            if callable(apply):
                query = apply(query)
        return query

    def _statement(self) -> Any:
        stmt: Any = select(self.model)
        for condition in self._effective_conditions():
            stmt = stmt.where(condition)
        if self._order_by is not None:
            column = (
                getattr(self.model, self._order_by)
                if isinstance(self._order_by, str)
                else self._order_by
            )
            stmt = stmt.order_by(column.desc() if self._descending else column)
        if self._offset is not None:
            stmt = stmt.offset(self._offset)
        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        return stmt

    # -- terminals ------------------------------------------------------
    async def all(self) -> Collection[Any]:
        compiled = self._compiled()
        async with _scope() as repos:
            rows = list((await repos.session.exec(compiled._statement())).all())
            await compiled._eager_load(rows, repos.session)
            return Collection(rows)

    async def get(self) -> Collection[Any]:
        return await self.all()

    async def first(self) -> Any:
        rows = await self.limit(1).all()
        return rows.first()

    async def first_or_fail(self) -> Any:
        row = await self.first()
        if row is None:
            raise NotFound(f"{self.model.__name__} not found")
        return row

    async def find(self, ident: Any) -> Any:
        return await Query(self.model, [getattr(self.model, _pk_name(self.model)) == ident]).first()

    async def count(self) -> int:
        compiled = self._compiled()
        async with _scope() as repos:
            stmt: Any = select(func.count()).select_from(self.model)
            for condition in compiled._effective_conditions():
                stmt = stmt.where(condition)
            return int((await repos.session.exec(stmt)).one())

    async def exists(self) -> bool:
        return (await self.first()) is not None

    async def doesnt_exist(self) -> bool:
        return not await self.exists()

    async def pluck(self, field: str) -> Collection[Any]:
        return (await self.all()).pluck(field)

    async def value(self, field: str, default: Any = None) -> Any:
        row = await self.first()
        return getattr(row, field, default) if row is not None else default

    async def paginate(self, page: int = 1, per_page: int = 15) -> LengthAwarePaginator[Any]:
        page = max(1, page)
        per_page = max(1, per_page)
        total = await self.count()
        items = await self.offset((page - 1) * per_page).limit(per_page).all()
        return LengthAwarePaginator(
            items=items, total=total, per_page=per_page, current_page=page
        )

    async def chunk(self, size: int, callback: Callable[[Collection[Any]], Any]) -> None:
        page = 1
        while True:
            batch = await self.offset((page - 1) * size).limit(size).all()
            if not batch:
                return
            result = callback(batch)
            if inspect.isawaitable(result):
                await result
            if len(batch) < size:
                return
            page += 1

    async def cursor(self) -> CursorCollection[Any]:
        return CursorCollection(await self.all())

    async def update(self, **values: Any) -> int:
        async with _scope() as repos:
            rows = list((await repos.session.exec(self._compiled()._statement())).all())
            for row in rows:
                for field, value in values.items():
                    setattr(row, field, value)
                repos.session.add(row)
            await repos.session.flush()
            for row in rows:
                await row._dispatch_event("updated")
            return len(rows)

    async def delete(self) -> int:
        async with _scope() as repos:
            rows = list((await repos.session.exec(self._compiled()._statement())).all())
            if _has_soft_deletes(self.model):
                for row in rows:
                    setattr(row, "deleted_at", now())  # noqa: B010
                    repos.session.add(row)
            else:
                for row in rows:
                    await repos.session.delete(row)
            await repos.session.flush()
            return len(rows)

    async def _eager_load(self, rows: Sequence[Any], session: Any) -> None:
        if not rows:
            return
        for name in self._eager:
            relationship = getattr(self.model, name, None)
            if isinstance(relationship, Relationship):
                await relationship.eager(rows, session)


def _pk_name(model: Any) -> str:
    from agentkit.foundation.relations import primary_key_name

    return primary_key_name(model)


class _HybridMethod:
    """A method usable as ``Model.delete(1)`` and ``instance.delete()``."""

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func
        self.__name__ = getattr(func, "__name__", "hybrid")
        self.__doc__ = func.__doc__

    def __get__(self, instance: Any, owner: type | None = None) -> Callable[..., Any]:
        if instance is None:

            async def as_class(ident: Any) -> Any:
                return await self.func(owner, None, ident)

            return as_class

        async def as_instance() -> Any:
            return await self.func(type(instance), instance, None)

        return as_instance


# -- model -----------------------------------------------------------------


class Model(SQLModel, metaclass=ModelMeta):
    """Base class for app tables with an Eloquent-ish surface."""

    model_config = SQLModelConfig(ignored_types=(Relationship, Attribute, GlobalScope, _HybridMethod))

    __casts__: ClassVar[dict[str, Cast]] = {}
    __appends__: ClassVar[list[str]] = []
    __hidden__: ClassVar[set[str]] = set()
    __visible__: ClassVar[set[str] | None] = None
    __fillable__: ClassVar[tuple[str, ...] | None] = None
    __guarded__: ClassVar[tuple[str, ...]] = ()
    __global_scopes__: ClassVar[list[Any]] = []
    __observers__: ClassVar[list[Any]] = []
    __accessors__: ClassVar[dict[str, Callable[[Any], Any]]] = {}
    __mutators__: ClassVar[dict[str, Callable[[Any, Any], Any]]] = {}
    __soft_deletes__: ClassVar[bool] = False
    prevent_lazy_loading: ClassVar[bool] = False

    # -- attribute access (casts + accessors) ---------------------------
    def __getattribute__(self, name: str) -> Any:
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        cls = object.__getattribute__(self, "__class__")
        accessors = cls.__accessors__
        if name in accessors:
            return accessors[name](self)
        casts = cls.__casts__
        if name in casts:
            raw = object.__getattribute__(self, name)
            return casts[name].get(self, name, raw)
        return object.__getattribute__(self, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        cls = type(self)
        mutators = cls.__mutators__
        if name in mutators:
            value = mutators[name](self, value)
        casts = cls.__casts__
        if name in casts:
            value = casts[name].set(self, name, value)
        object.__setattr__(self, name, value)

    # -- mass assignment ------------------------------------------------
    @classmethod
    def _mass_assignable(cls, values: dict[str, Any]) -> dict[str, Any]:
        fillable = cls.__fillable__
        guarded = cls.__guarded__
        if fillable is not None:
            return {key: value for key, value in values.items() if key in fillable}
        if guarded:
            return {key: value for key, value in values.items() if key not in guarded}
        return dict(values)

    @classmethod
    def fill_values(cls, values: dict[str, Any]) -> dict[str, Any]:
        """The values that survive mass-assignment (``fillable``/``guarded``)."""
        return cls._mass_assignable(values)

    # -- query builders -------------------------------------------------
    @classmethod
    def query(cls, **filters: Any) -> Query:
        return Query(cls, [getattr(cls, field) == value for field, value in filters.items()])

    @classmethod
    def where(cls, *expressions: Any, **filters: Any) -> Query:
        return Query(cls).where(*expressions, **filters)

    @classmethod
    def where_in(cls, field: str, values: Sequence[Any]) -> Query:
        return Query(cls).where_in(field, values)

    @classmethod
    def where_null(cls, field: str) -> Query:
        return Query(cls).where_null(field)

    @classmethod
    def where_not_null(cls, field: str) -> Query:
        return Query(cls).where_not_null(field)

    @classmethod
    def where_between(cls, field: str, low: Any, high: Any) -> Query:
        return Query(cls).where_between(field, low, high)

    @classmethod
    def with_(cls, *names: str) -> Query:
        return Query(cls).with_(*names)

    @classmethod
    def with_trashed(cls) -> Query:
        return Query(cls).with_trashed()

    @classmethod
    def only_trashed(cls) -> Query:
        return Query(cls).only_trashed()

    @classmethod
    def without_global_scope(cls, *names: str) -> Query:
        return Query(cls).without_global_scope(*names)

    @classmethod
    def when(cls, condition: Any, callback: Callable[[Query], Query]) -> Query:
        return Query(cls).when(condition, callback)

    @classmethod
    def order_by(cls, field: Any, *, descending: bool = False) -> Query:
        return Query(cls).order_by(field, descending=descending)

    @classmethod
    def latest(cls, field: Any = "id") -> Query:
        return Query(cls).latest(field)

    @classmethod
    def oldest(cls, field: Any = "id") -> Query:
        return Query(cls).oldest(field)

    # -- reads ----------------------------------------------------------
    @classmethod
    async def all(cls, **filters: Any) -> Collection[Any]:
        return await cls.query(**filters).all()

    @classmethod
    async def first(cls, **filters: Any) -> Any:
        return await cls.query(**filters).first()

    @classmethod
    async def first_or_fail(cls, **filters: Any) -> Any:
        row = await cls.first(**filters)
        if row is None:
            raise NotFound(f"{cls.__name__} not found for {filters!r}")
        return row

    @classmethod
    async def find(cls, ident: Any) -> Any:
        return await Query(cls, [getattr(cls, _pk_name(cls)) == ident]).first()

    @classmethod
    async def find_or_fail(cls, ident: Any) -> Any:
        row = await cls.find(ident)
        if row is None:
            raise NotFound(f"{cls.__name__} {ident!r} not found")
        return row

    @classmethod
    async def get(cls, ident: Any) -> Any:
        return await cls.find(ident)

    @classmethod
    async def count(cls, **filters: Any) -> int:
        return await cls.query(**filters).count()

    @classmethod
    async def exists(cls, **filters: Any) -> bool:
        return await cls.query(**filters).exists()

    @classmethod
    async def paginate(
        cls, page: int = 1, per_page: int = 15, **filters: Any
    ) -> LengthAwarePaginator[Any]:
        return await cls.query(**filters).paginate(page, per_page)

    @classmethod
    async def first_or_create(
        cls, *, defaults: dict[str, Any] | None = None, **filters: Any
    ) -> Any:
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
        await row.save()
        return row

    # -- writes ---------------------------------------------------------
    @classmethod
    async def create(cls, **values: Any) -> Any:
        values = cls._mass_assignable(values)
        if "owner_id" not in values and hasattr(cls, "owner_id"):
            from agentkit.foundation.facade import get_current_app

            app = get_current_app()
            values["owner_id"] = getattr(getattr(app, "settings", None), "owner_id", "owner")
        instance = cls(**values)
        await instance.save()
        return instance

    @classmethod
    async def update(cls, ident: Any, **values: Any) -> Any:
        instance = await cls.find(ident)
        if instance is None:
            return None
        for field, value in cls._mass_assignable(values).items():
            setattr(instance, field, value)
        await instance.save()
        return instance

    @_HybridMethod
    async def delete(cls, instance: Any, ident: Any = None) -> bool:
        if instance is None:
            instance = await cls.find(ident)
            if instance is None:
                return False
        await instance._dispatch_event("deleting")
        async with _scope() as repos:
            if _has_soft_deletes(cls):
                setattr(instance, "deleted_at", now())  # noqa: B010
                repos.session.add(instance)
            else:
                await repos.session.delete(instance)
            await repos.session.flush()
        await instance._dispatch_event("deleted")
        return True

    @classmethod
    async def upsert(cls, rows: Sequence[dict[str, Any]]) -> int:
        count = 0
        for row in rows:
            pk = _pk_name(cls)
            ident = row.get(pk)
            if ident is not None and await cls.find(ident) is not None:
                await cls.update(ident, **{k: v for k, v in row.items() if k != pk})
            else:
                await cls.create(**row)
            count += 1
        return count

    # -- instance lifecycle ---------------------------------------------
    async def save(self) -> Any:
        is_new = getattr(self, _pk_name(type(self)), None) is None
        await self._dispatch_event("saving")
        if is_new:
            await self._dispatch_event("creating")
        else:
            await self._dispatch_event("updating")
        async with _scope() as repos:
            repos.session.add(self)
            await repos.session.flush()
            await repos.session.refresh(self)
        await self._dispatch_event("created" if is_new else "updated")
        await self._dispatch_event("saved")
        return self

    async def refresh(self) -> Any:
        pk = _pk_name(type(self))
        fresh = await type(self).find(getattr(self, pk))
        if fresh is not None:
            for field in type(self).model_fields:
                object.__setattr__(self, field, getattr(fresh, field))
        return self

    async def force_delete(self) -> bool:
        await self._dispatch_event("deleting")
        async with _scope() as repos:
            await repos.session.delete(self)
            await repos.session.flush()
        await self._dispatch_event("deleted")
        return True

    async def restore(self) -> bool:
        if not _has_soft_deletes(type(self)):
            return False
        setattr(self, "deleted_at", None)  # noqa: B010
        await self._dispatch_event("restoring")
        await self.save()
        await self._dispatch_event("restored")
        return True

    def trashed(self) -> bool:
        return bool(getattr(self, "deleted_at", None))

    async def load(self, *names: str) -> Any:
        async with _scope() as repos:
            for name in names:
                relationship = getattr(type(self), name, None)
                if isinstance(relationship, Relationship):
                    await relationship.load_with(self, repos.session)
        return self

    async def load_missing(self, *names: str) -> Any:
        missing = [name for name in names if name not in self.__dict__.get("_relations", {})]
        if missing:
            await self.load(*missing)
        return self

    def replicate(self, **values: Any) -> Any:
        pk = _pk_name(type(self))
        data = {field: getattr(self, field) for field in type(self).model_fields}
        data.update(values)
        data.pop(pk, None)
        return type(self)(**data)

    def to_dict(self, *, include_hidden: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in type(self).model_fields:
            data[field] = getattr(self, field)
        for name in type(self).__appends__:
            data[name] = getattr(self, name, None)
        if not include_hidden:
            for name in type(self).__hidden__:
                data.pop(name, None)
        return {key: _plain(value) for key, value in data.items()}

    # -- observers / events ---------------------------------------------
    @classmethod
    def observe(cls, *observers: Any) -> type:
        for observer in observers:
            instance = observer() if isinstance(observer, type) else observer
            cls.__observers__.append(instance)
        return cls

    async def _dispatch_event(self, event: str) -> None:
        for observer in type(self).__observers__:
            handler = getattr(observer, event, None)
            if handler is not None:
                result = handler(self)
                if inspect.isawaitable(result):
                    await result
        try:
            from agentkit.foundation.facade import emit

            await emit(f"model.{event}", model=self, name=type(self).__name__)
        except Exception:  # pragma: no cover - listeners never break a write
            pass


def _plain(value: Any) -> Any:
    if isinstance(value, Collection):
        return value.to_dict()
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


class ModelEvent:
    """The payload of a model lifecycle event (``model.updated`` etc.)."""

    def __init__(self, model: Any, name: str, event: str) -> None:
        self.model = model
        self.name = name
        self.event = event


class SoftDeletes(Model):
    """Mixin adding a ``deleted_at`` column and soft-delete behaviour.

        class Note(SoftDeletes, table=True):
            ...
    """

    __soft_deletes__: ClassVar[bool] = True

    deleted_at: datetime | None = Field(default=None, index=True)


class Observer:
    """Base class for model observers (implement any lifecycle hook)."""

    def retrieved(self, model: Any) -> None: ...  # noqa: D401
    def creating(self, model: Any) -> None: ...
    def created(self, model: Any) -> None: ...
    def updating(self, model: Any) -> None: ...
    def updated(self, model: Any) -> None: ...
    def saving(self, model: Any) -> None: ...
    def saved(self, model: Any) -> None: ...
    def deleting(self, model: Any) -> None: ...
    def deleted(self, model: Any) -> None: ...
    def restoring(self, model: Any) -> None: ...
    def restored(self, model: Any) -> None: ...
