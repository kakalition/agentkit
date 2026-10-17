"""Model factories (Laravel's ``Factory``) and the ``HasFactory`` trait.

    class UserFactory(Factory):
        model = User
        def definition(self):
            return {"name": "Ada"}

    await UserFactory().create(name="Grace")
    await UserFactory().count(3).make()

A factory can be bound to a model with :meth:`Factory.for_model` (or the
``factory_class`` attribute on a ``HasFactory`` model); ``Model.factory()`` then
resolves it by convention.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, ClassVar

from agentkit.foundation.collection import Collection

__all__ = ["Factory", "HasFactory", "factory"]

_FACTORIES: dict[type, Any] = {}


class Factory:
    """Produces model instances from a ``definition`` plus states/overrides."""

    model: ClassVar[Any] = None

    def __init__(self) -> None:
        self._states: list[dict[str, Any]] = []
        self._after: list[Callable[[Any], Any]] = []
        self._count: int = 1
        self._overrides: dict[str, Any] = {}

    # -- configuration --------------------------------------------------
    def clone(self) -> Factory:
        clone = type(self)()
        clone._states = list(self._states)
        clone._after = list(self._after)
        clone._count = self._count
        clone._overrides = dict(self._overrides)
        return clone

    def state(self, values: dict[str, Any] | None = None, **kwargs: Any) -> Factory:
        clone = self.clone()
        clone._states.append({**(values or {}), **kwargs})
        return clone

    def count(self, number: int) -> Factory:
        clone = self.clone()
        clone._count = max(0, number)
        return clone

    def after_creating(self, callback: Callable[[Any], Any]) -> Factory:
        clone = self.clone()
        clone._after.append(callback)
        return clone

    #: Laravel spelling.
    afterCreating = after_creating  # noqa: N815

    @staticmethod
    def sequence(values: list[Any]) -> Callable[[int], Any]:
        """A cycling value generator for a definition entry."""
        items = list(values)

        def picker(index: int) -> Any:
            return items[index % len(items)] if items else None

        picker.__factory_sequence__ = True  # type: ignore[attr-defined]
        return picker

    # -- definition -----------------------------------------------------
    def definition(self) -> dict[str, Any]:
        return {}

    def _resolve(self, index: int) -> dict[str, Any]:
        definition = self.definition()
        values = {
            key: (value(index) if callable(value) and getattr(value, "__factory_sequence__", False) else value)
            for key, value in definition.items()
        }
        for state in self._states:
            values.update(state)
        values.update(self._overrides)
        return values

    # -- building -------------------------------------------------------
    def new(self, **overrides: Any) -> Any:
        model = self._model()
        return model(**{**self._resolve(0), **overrides})

    def make(self, **overrides: Any) -> Any | Collection[Any]:
        """Build instance(s) without persisting."""
        if self._count == 1 and not overrides:
            return self.new()
        if self._count == 1:
            return self.new(**overrides)
        return Collection(self.new(**overrides) for _ in range(self._count))

    async def create(self, **overrides: Any) -> Any | Collection[Any]:
        """Persist instance(s) and run ``after_creating`` callbacks."""
        if self._count == 1:
            instance = await self._model().create(**{**self._resolve(0), **overrides})
            await self._run_after(instance)
            return instance
        created: Collection[Any] = Collection()
        for index in range(self._count):
            instance = await self._model().create(**{**self._resolve(index), **overrides})
            await self._run_after(instance)
            created = created.push(instance)
        return created

    def make_many(self, number: int, **overrides: Any) -> Collection[Any]:
        return Collection(self.new(**overrides) for _ in range(max(0, number)))

    async def create_many(self, number: int, **overrides: Any) -> Collection[Any]:
        created: Collection[Any] = Collection()
        for _ in range(max(0, number)):
            created = created.push(await self.create(**overrides))
        return created

    def __iter__(self) -> Iterator[Any]:  # pragma: no cover - convenience
        return iter([self.new() for _ in range(self._count)])

    async def _run_after(self, instance: Any) -> None:
        import inspect

        for callback in self._after:
            result = callback(instance)
            if inspect.isawaitable(result):
                await result

    # -- binding --------------------------------------------------------
    def _model(self) -> Any:
        if self.model is None:
            raise TypeError(f"{type(self).__name__} declares no model")
        return self.model

    @classmethod
    def for_model(cls, model: Any, factory: Any = None) -> Any:
        """Bind ``factory`` to ``model`` (or look one up)."""
        if factory is not None:
            _FACTORIES[model] = factory
            return factory
        return _FACTORIES.get(model)

    @classmethod
    def guess_for(cls, model: Any) -> Any:
        """Look up a factory for ``model``: a registered one, else ``<Name>Factory``."""
        registered = _FACTORIES.get(model)
        if registered is not None:
            return registered
        name = f"{model.__name__}Factory"
        import sys

        module = sys.modules.get(getattr(model, "__module__", ""))
        if module is not None and hasattr(module, name):
            return getattr(module, name)
        return None


def factory(model: Any, count: int = 1, **overrides: Any) -> Factory:
    """Resolve the factory for ``model`` and configure it (``count``/overrides)."""
    resolved = Factory.guess_for(model)
    if resolved is None:
        raise LookupError(f"no factory registered for {model.__name__}")
    instance = resolved() if isinstance(resolved, type) else resolved.clone()
    if count != 1:
        instance = instance.count(count)
    if overrides:
        instance = instance.state(overrides)
    return instance


class HasFactory:
    """Mixin giving a model ``Model.factory()`` (Laravel's ``HasFactory``)."""

    factory_class: ClassVar[Any] = None

    @classmethod
    def factory(cls, count: int = 1, **overrides: Any) -> Factory:
        resolved = cls.factory_class or Factory.guess_for(cls)
        if resolved is None:
            raise LookupError(f"no factory registered for {cls.__name__}")
        instance = resolved() if isinstance(resolved, type) else resolved.clone()
        if count != 1:
            instance = instance.count(count)
        if overrides:
            instance = instance.state(overrides)
        return instance
