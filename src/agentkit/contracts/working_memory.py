"""The working-memory contract — thread-scoped key/value scratch state."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["WorkingMemory"]


@runtime_checkable
class WorkingMemory(Protocol):
    """Namespaced (per conversation) key/value scratch memory."""

    async def set(self, namespace: str, key: str, value: Any) -> Any: ...

    async def get(self, namespace: str, key: str) -> str | None: ...

    async def list(self, namespace: str) -> dict[str, str]: ...

    async def forget(self, namespace: str, key: str) -> bool: ...

    async def clear(self, namespace: str) -> int: ...
