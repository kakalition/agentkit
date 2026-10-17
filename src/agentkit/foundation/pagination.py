"""Paginators over a page of items (Laravel's ``LengthAwarePaginator``).

The model/repository query layer keeps returning a plain ``dict`` for back-compat;
these classes are the richer, object-oriented form used by the Eloquent surface.
``LengthAwarePaginator`` also indexes like the legacy dict, so callers can move
between the two without a rewrite.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Generic, TypeVar

from agentkit.foundation.collection import Collection

T = TypeVar("T")

__all__ = ["LengthAwarePaginator", "Paginator", "paginate"]


class Paginator(Generic[T]):
    """A page of items with a known page size (no total)."""

    def __init__(
        self,
        items: Sequence[T] | Collection[T] | None = None,
        per_page: int = 15,
        current_page: int = 1,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.items: Collection[T] = items if isinstance(items, Collection) else Collection(items)
        self.per_page = max(1, per_page)
        self.current_page = max(1, current_page)
        self.options = dict(options or {})

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def page(self) -> int:
        return self.current_page

    def has_more_pages(self) -> bool:
        return len(self.items) >= self.per_page

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items.to_dict(),
            "per_page": self.per_page,
            "current_page": self.current_page,
        }


class LengthAwarePaginator(Paginator[T]):
    """A page of items plus the total count (the common case)."""

    def __init__(
        self,
        items: Sequence[T] | Collection[T] | None = None,
        total: int = 0,
        per_page: int = 15,
        current_page: int = 1,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(items=items, per_page=per_page, current_page=current_page, options=options)
        self.total = int(total)

    @property
    def pages(self) -> int:
        return (self.total + self.per_page - 1) // self.per_page if self.total else 0

    @property
    def last_page(self) -> int:
        return max(1, self.pages)

    @property
    def has_pages(self) -> bool:
        return self.pages > 1

    @property
    def from_(self) -> int:
        return 0 if not self.items else (self.current_page - 1) * self.per_page + 1

    @property
    def to(self) -> int:
        return 0 if not self.items else self.from_ + len(self.items) - 1

    def has_more_pages(self) -> bool:
        return self.current_page < self.last_page

    def on_first_page(self) -> bool:
        return self.current_page <= 1

    def on_last_page(self) -> bool:
        return self.current_page >= self.last_page

    def links(self) -> dict[str, str | None]:
        """Named page links (prev/next/first/last plus the numeric pages as keys)."""
        previous = self.current_page - 1 if self.current_page > 1 else None
        following = self.current_page + 1 if self.current_page < self.last_page else None
        result: dict[str, str | None] = {
            "prev": None if previous is None else str(previous),
            "next": None if following is None else str(following),
            "first": "1",
            "last": str(self.last_page),
        }
        for page in range(1, self.pages + 1):
            result[str(page)] = str(page)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items.to_dict(),
            "total": self.total,
            "per_page": self.per_page,
            "page": self.current_page,
            "pages": self.pages,
            "from": self.from_,
            "to": self.to,
        }

    def __getitem__(self, key: str) -> Any:
        """Legacy dict-style access (``page["page"]``, ``page["items"]`` …)."""
        data = self.to_dict()
        if key not in data:
            raise KeyError(key)
        return data[key]


def paginate(
    items: Sequence[T], total: int, per_page: int = 15, page: int = 1
) -> LengthAwarePaginator[T]:
    """Build a :class:`LengthAwarePaginator` from a page of ``items`` and a total."""
    return LengthAwarePaginator(items=items, total=total, per_page=per_page, current_page=page)
