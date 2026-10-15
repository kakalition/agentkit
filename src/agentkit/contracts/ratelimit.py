"""The rate-limiter contract — count hits against a windowed limit."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["RateLimiterContract"]


@runtime_checkable
class RateLimiterContract(Protocol):
    """Fixed-window / token-bucket style limiter."""

    async def hit(
        self, key: str, *, owner_id: str | None = None, limit: int | None = None
    ) -> Any: ...

    async def peek(self, key: str, *, owner_id: str | None = None) -> int: ...

    async def reset(self, key: str, *, owner_id: str | None = None) -> None: ...
