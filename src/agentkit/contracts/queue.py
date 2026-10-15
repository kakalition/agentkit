"""The queue contract — durable or inline job dispatch."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["QueueDriver"]


@runtime_checkable
class QueueDriver(Protocol):
    """Persist and/or run jobs."""

    async def push(
        self,
        job: Any,
        *,
        queue: str | None = None,
        delay: float = 0.0,
        max_retries: int | None = None,
    ) -> int: ...

    async def run_once(self, queue: str | None = None) -> bool: ...

    async def size(self, queue: str | None = None) -> int: ...

    async def failed(self, *, limit: int = 50) -> list[Any]: ...
