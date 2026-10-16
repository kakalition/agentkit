"""The catalog contract — discover and install specs / skills / MCP servers.

A :class:`Catalog` is a pluggable source (a local directory, the skills registry,
a git repo, or an HTTP index) exposing a searchable list of :class:`CatalogItem`\\ s.
Installing an item writes it into the right target (the definitions store, the
skills dir, or the MCP registry), validating it first and never escaping paths.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Catalog", "CatalogItem"]


class CatalogItem:
    """One catalog entry: id, kind, name, and where it installs from."""

    __slots__ = ("description", "id", "kind", "name", "source", "version")

    def __init__(
        self,
        id: str,
        *,
        name: str = "",
        kind: str = "spec",
        description: str = "",
        version: str = "",
        source: str = "",
    ) -> None:
        self.id = id
        self.name = name or id
        self.kind = kind
        self.description = description
        self.version = version
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "version": self.version,
            "source": self.source,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CatalogItem({self.id!r}, kind={self.kind!r})"


@runtime_checkable
class Catalog(Protocol):
    """A source of installable items."""

    name: str

    async def search(self, query: str = "") -> list[CatalogItem]: ...

    async def get(self, item_id: str) -> CatalogItem | None: ...

    async def install(self, item_id: str, target: Any = None) -> Any: ...
