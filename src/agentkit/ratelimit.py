"""Database-backed fixed-window rate limiting (works on SQLite and Postgres).

Counters live in the ``rate_windows`` table keyed ``(owner_id, key, window_start)``
so limits hold across processes. A small in-process cache short-circuits once a
key is already over its limit, avoiding further round-trips.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from agentkit.contracts.ratelimit import RateLimiterContract
from agentkit.errors import RateLimited
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, RateLimitDriver
from agentkit.support.manager import Manager

WINDOW_SECONDS = 60


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    count: int


class RateLimiter:
    """Fixed-window limiter over the ``rate_windows`` table."""

    def __init__(
        self,
        runtime: Any,
        *,
        per_minute: int = 60,
        tool_per_minute: int = 0,
        burst: int = 0,
    ) -> None:
        self.runtime = runtime
        self.per_minute = int(per_minute)
        self.tool_per_minute = int(tool_per_minute)
        self.burst = int(burst)
        self._cache: dict[tuple[str, str], tuple[int, int]] = {}

    @staticmethod
    def window_start(now: float | None = None) -> int:
        return int((now if now is not None else time.time()) // WINDOW_SECONDS * WINDOW_SECONDS)

    def _effective_limit(self, limit: int | None) -> int:
        if limit is not None:
            return int(limit)
        return self.per_minute + self.burst

    async def hit(self, key: str, *, owner_id: str | None = None, limit: int | None = None) -> RateDecision:
        effective = self._effective_limit(limit)
        owner = str(owner_id or getattr(self.runtime.settings, "owner_id", "owner") or "owner")
        window = self.window_start()
        cache_key = (owner, key)
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] == window and cached[1] >= effective:
            return RateDecision(
                allowed=False,
                limit=effective,
                remaining=0,
                retry_after=window + WINDOW_SECONDS - int(time.time()),
                count=cached[1],
            )
        from agentkit.runtime import repositories

        async with repositories(self.runtime, owner_id) as repos:
            count = await repos.rate_windows.increment(key, window, owner_id=owner_id)
        self._cache[cache_key] = (window, count)
        allowed = count <= effective
        return RateDecision(
            allowed=allowed,
            limit=effective,
            remaining=max(0, effective - count),
            retry_after=0 if allowed else window + WINDOW_SECONDS - int(time.time()),
            count=count,
        )

    async def peek(self, key: str, *, owner_id: str | None = None) -> int:
        from agentkit.runtime import repositories

        async with repositories(self.runtime, owner_id) as repos:
            return await repos.rate_windows.count(key, self.window_start(), owner_id=owner_id)

    async def reset(self, key: str, *, owner_id: str | None = None) -> None:
        owner = str(owner_id or getattr(self.runtime.settings, "owner_id", "owner") or "owner")
        self._cache.pop((owner, key), None)

    def enforce(self, decision: RateDecision) -> RateDecision:
        if not decision.allowed:
            raise RateLimited(
                "rate limit exceeded",
                detail={"retry_after": decision.retry_after, "limit": decision.limit},
            )
        return decision


def build_limiter(settings: Any, runtime: Any) -> RateLimiter | None:
    """Build a limiter from settings, or ``None`` when rate limiting is disabled."""
    if not getattr(settings, "rate_limit_enabled", False):
        return None
    return RateLimiter(
        runtime,
        per_minute=getattr(settings, "rate_limit_per_minute", 60),
        tool_per_minute=getattr(settings, "rate_limit_tool_per_minute", 0),
        burst=getattr(settings, "rate_limit_burst", 0),
    )


class InMemoryRateLimiter:
    """A fixed-window limiter held in process memory (no database)."""

    def __init__(
        self,
        *,
        per_minute: int = 60,
        tool_per_minute: int = 0,
        burst: int = 0,
        owner_id: str = "owner",
    ) -> None:
        self.per_minute = int(per_minute)
        self.tool_per_minute = int(tool_per_minute)
        self.burst = int(burst)
        self.owner_id = owner_id
        self._windows: dict[tuple[str, str, int], int] = {}

    def _effective_limit(self, limit: int | None) -> int:
        return int(limit) if limit is not None else self.per_minute + self.burst

    async def hit(
        self, key: str, *, owner_id: str | None = None, limit: int | None = None
    ) -> RateDecision:
        effective = self._effective_limit(limit)
        owner = str(owner_id or self.owner_id)
        window = RateLimiter.window_start()
        bucket = (owner, key, window)
        count = self._windows.get(bucket, 0) + 1
        self._windows[bucket] = count
        allowed = count <= effective
        return RateDecision(
            allowed=allowed,
            limit=effective,
            remaining=max(0, effective - count),
            retry_after=0 if allowed else window + WINDOW_SECONDS - int(time.time()),
            count=count,
        )

    async def peek(self, key: str, *, owner_id: str | None = None) -> int:
        return self._windows.get((str(owner_id or self.owner_id), key, RateLimiter.window_start()), 0)

    async def reset(self, key: str, *, owner_id: str | None = None) -> None:
        owner = str(owner_id or self.owner_id)
        window = RateLimiter.window_start()
        self._windows.pop((owner, key, window), None)

    def enforce(self, decision: RateDecision) -> RateDecision:
        if not decision.allowed:
            raise RateLimited(
                "rate limit exceeded",
                detail={"retry_after": decision.retry_after, "limit": decision.limit},
            )
        return decision


class RateLimitManager(Manager):
    """Resolves the configured rate-limit driver (``rate_limit_driver``, default ``database``)."""

    kind = DriverKind.RATELIMIT
    default_driver = RateLimitDriver.DATABASE


def _limiter_options(app: Any) -> dict[str, Any]:
    settings = getattr(app, "settings", None)
    return {
        "per_minute": int(getattr(settings, "rate_limit_per_minute", 60) or 60),
        "tool_per_minute": int(getattr(settings, "rate_limit_tool_per_minute", 0) or 0),
        "burst": int(getattr(settings, "rate_limit_burst", 0) or 0),
    }


@register_driver(DriverKind.RATELIMIT, RateLimitDriver.DATABASE)
def _database_limiter_driver(app: Any) -> RateLimiter:
    return RateLimiter(app.runtime, **_limiter_options(app))


@register_driver(DriverKind.RATELIMIT, RateLimitDriver.MEMORY)
def _memory_limiter_driver(app: Any) -> InMemoryRateLimiter:
    settings = getattr(app, "settings", None)
    return InMemoryRateLimiter(
        owner_id=str(getattr(settings, "owner_id", "owner") or "owner"),
        **_limiter_options(app),
    )


__all__ = [
    "WINDOW_SECONDS",
    "InMemoryRateLimiter",
    "RateDecision",
    "RateLimitManager",
    "RateLimiter",
    "RateLimiterContract",
    "build_limiter",
]
