"""The comms contract — a message topology between agents."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Topology"]


@runtime_checkable
class Topology(Protocol):
    """Route messages between named agents."""

    async def send(self, to: str, message: str, *, sender: str | None = None) -> bool: ...

    async def broadcast(
        self, message: str, *, to: list[str] | None = None, sender: str | None = None
    ) -> dict[str, Any]: ...
