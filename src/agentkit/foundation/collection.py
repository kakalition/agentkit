"""A small, immutable :class:`Collection` over a list (Laravel's ``Collection``).

The collection is the return type of Eloquent-ish reads (``Model.where().all()``,
relationships, paginators) and carries the familiar chainable surface —
``map``/``filter``/``pluck``/``groupBy``/``each``/``reduce`` — without pulling in
a dependency. Methods that transform return a new collection; nothing mutates the
original.

``CursorCollection`` is the lazy sibling: it wraps an iterable and materializes
only when asked, so a large read can be streamed with ``each``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import Any, Generic, TypeVar, overload

T = TypeVar("T")
U = TypeVar("U")
K = TypeVar("K")

_MISSING: Any = object()

__all__ = ["Collection", "CursorCollection", "collect"]


def _item_key(item: Any, key: Any) -> Any:
    if callable(key):
        return key(item)
    if isinstance(item, dict):
        return item.get(key)
    if isinstance(item, str) and hasattr(item, "get"):
        return item.get(key)
    return getattr(item, key, None)


class Collection(Sequence[T], Generic[T]):
    """An immutable, chainable list wrapper."""

    def __init__(self, items: Iterable[T] | None = None) -> None:
        self._items: list[T] = list(items) if items is not None else []

    # -- sequence protocol ---------------------------------------------
    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Collection[T]: ...

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            return Collection(self._items[index])
        return self._items[index]

    def __repr__(self) -> str:
        return f"Collection({self._items!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Collection):
            return self._items == other._items
        if isinstance(other, list):
            return self._items == other
        return NotImplemented

    def __hash__(self) -> int:  # pragma: no cover - lists are mutable in spirit
        return object.__hash__(self)

    # -- access ---------------------------------------------------------
    def all(self) -> list[T]:
        return list(self._items)

    #: Laravel alias.
    to_list = all

    def first(self, default: Any = None) -> Any:
        return self._items[0] if self._items else default

    def last(self, default: Any = None) -> Any:
        return self._items[-1] if self._items else default

    def get(self, index: int, default: Any = None) -> Any:
        try:
            return self._items[index]
        except IndexError:
            return default

    def count(self, predicate: Callable[[T], bool] | None = None) -> int:
        if predicate is None:
            return len(self._items)
        return sum(1 for item in self._items if predicate(item))

    def isEmpty(self) -> bool:  # noqa: N802 - Laravel spelling
        return not self._items

    def isNotEmpty(self) -> bool:  # noqa: N802 - Laravel spelling
        return bool(self._items)

    def contains(self, value: Any) -> bool:
        if callable(value):
            return any(value(item) for item in self._items)
        return value in self._items

    # -- transforms -----------------------------------------------------
    def map(self, callback: Callable[[T], U]) -> Collection[U]:
        return Collection(callback(item) for item in self._items)

    def each(self, callback: Callable[[T], Any]) -> Collection[T]:
        for item in self._items:
            callback(item)
        return self

    def filter(self, callback: Callable[[T], bool] | None = None) -> Collection[T]:
        if callback is None:
            return Collection(item for item in self._items if item)
        return Collection(item for item in self._items if callback(item))

    #: Laravel's ``where`` is an equality filter; here ``where`` is the predicate filter.
    where = filter

    def reject(self, callback: Callable[[T], bool]) -> Collection[T]:
        return Collection(item for item in self._items if not callback(item))

    def pluck(self, key: Any, value: Any = None) -> Collection[Any]:
        if value is None:
            return Collection(_item_key(item, key) for item in self._items)
        return Collection(
            {_item_key(item, key): _item_key(item, value)} for item in self._items
        )

    def keyBy(self, key: Any) -> dict[Any, T]:  # noqa: N802 - Laravel spelling
        return {_item_key(item, key): item for item in self._items}

    def groupBy(self, key: Any) -> dict[Any, Collection[T]]:  # noqa: N802
        grouped: dict[Any, list[T]] = {}
        for item in self._items:
            grouped.setdefault(_item_key(item, key), []).append(item)
        return {group: Collection(items) for group, items in grouped.items()}

    def unique(self, key: Any = None) -> Collection[T]:
        seen: set[Any] = set()
        out: list[T] = []
        for item in self._items:
            marker = _item_key(item, key) if key is not None else item
            if marker in seen:
                continue
            seen.add(marker)
            out.append(item)
        return Collection(out)

    def sortBy(self, key: Any = None, *, descending: bool = False) -> Collection[T]:  # noqa: N802
        def sort_key(item: T) -> Any:
            return _item_key(item, key) if key is not None else item

        return Collection(sorted(self._items, key=sort_key, reverse=descending))

    def sortByDesc(self, key: Any = None) -> Collection[T]:  # noqa: N802
        return self.sortBy(key, descending=True)

    def reverse(self) -> Collection[T]:
        return Collection(reversed(self._items))

    def take(self, count: int) -> Collection[T]:
        return Collection(self._items[:count])

    def skip(self, count: int) -> Collection[T]:
        return Collection(self._items[count:])

    def slice(self, start: int, length: int | None = None) -> Collection[T]:
        return Collection(self._items[start : None if length is None else start + length])

    def chunk(self, size: int) -> Collection[Collection[T]]:
        return Collection(Collection(self._items[i : i + size]) for i in range(0, len(self._items), size))

    def merge(self, other: Iterable[T]) -> Collection[T]:
        return Collection([*self._items, *list(other)])

    def push(self, *values: T) -> Collection[T]:
        return Collection([*self._items, *values])

    def values(self) -> Collection[T]:
        return Collection(self._items)

    def keys(self) -> Collection[int]:
        return Collection(range(len(self._items)))

    # -- aggregation ----------------------------------------------------
    def reduce(self, callback: Callable[[U, T], U], initial: U = None) -> U:  # type: ignore[assignment]
        result = initial
        for item in self._items:
            result = callback(result, item)
        return result

    def sum(self, key: Any = None) -> Any:
        values: list[Any] = [_item_key(item, key) if key is not None else item for item in self._items]
        return sum(values)

    def avg(self, key: Any = None) -> float | None:
        if not self._items:
            return None
        return self.sum(key) / len(self._items)

    def min(self, key: Any = None) -> Any:
        values: list[Any] = [_item_key(item, key) if key is not None else item for item in self._items]
        return min(values) if values else None

    def max(self, key: Any = None) -> Any:
        values: list[Any] = [_item_key(item, key) if key is not None else item for item in self._items]
        return max(values) if values else None

    def implode(self, glue: str = "", key: Any = _MISSING) -> str:
        if key is _MISSING:
            return glue.join(str(item) for item in self._items)
        return glue.join(str(_item_key(item, key)) for item in self._items)

    def to_dict(self) -> list[Any]:
        out: list[Any] = []
        for item in self._items:
            if hasattr(item, "to_dict"):
                out.append(item.to_dict())
            elif isinstance(item, dict):
                out.append(dict(item))
            else:
                out.append(item)
        return out


class CursorCollection(Generic[T]):
    """A lazily-consumed iterable with a small chainable surface."""

    def __init__(self, items: Iterable[T]) -> None:
        self._source: Iterable[T] = items

    def __iter__(self) -> Iterator[T]:
        return iter(self._source)

    def map(self, callback: Callable[[T], U]) -> CursorCollection[U]:
        return CursorCollection(callback(item) for item in self)

    def filter(self, callback: Callable[[T], bool]) -> CursorCollection[T]:
        return CursorCollection(item for item in self if callback(item))

    def take(self, count: int) -> CursorCollection[T]:
        return CursorCollection(self._head(count))

    def _head(self, count: int) -> Iterator[T]:
        for index, item in enumerate(self):
            if index >= count:
                break
            yield item

    def each(self, callback: Callable[[T], Any]) -> CursorCollection[T]:
        for item in self:
            callback(item)
        return self

    def to_list(self) -> list[T]:
        return list(self)


def collect(items: Iterable[T] | None = None) -> Collection[T]:
    """Build a :class:`Collection` (the ``collect()`` helper)."""
    if isinstance(items, Collection):
        return items
    return Collection(items)
