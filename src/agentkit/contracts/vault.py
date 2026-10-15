"""The vault contract — an encrypted secret store."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Vault"]


@runtime_checkable
class Vault(Protocol):
    """Store and retrieve secrets by name."""

    async def set(self, name: str, value: str, **options: Any) -> Any: ...

    async def get(self, name: str, **options: Any) -> str | None: ...

    async def names(self, **options: Any) -> list[str]: ...

    async def delete(self, name: str, **options: Any) -> bool: ...
