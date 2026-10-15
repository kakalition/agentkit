"""Tool-result caching and tool registration helpers.

``cached_tool`` wraps a tool function with a small TTL + size-limited cache keyed
on its arguments (the :class:`~pydantic_ai.RunContext` is ignored), so repeated
calls with the same arguments do not re-run the side effect::

    from agentkit.cache import cached_tool

    agent.tool(cached_tool(lookup, ttl=60))

The cache is a ``cachetools.TTLCache`` mutated under an :class:`asyncio.Lock` so
concurrent tasks cannot corrupt it. The wrapper preserves the original signature
(via ``functools.wraps``) so PydanticAI still derives the correct JSON schema.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache

__all__ = ["cached_tool"]

_MISSING = object()


def _is_context(value: Any) -> bool:
    return type(value).__name__ in {"RunContext", "RunContextWrapper"}


def cached_tool(
    function: Callable[..., Any],
    *,
    ttl: float = 300.0,
    maxsize: int = 256,
    key: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Wrap ``function`` with a TTL cache over its (non-context) arguments."""
    store: TTLCache[Any, Any] = TTLCache(maxsize=maxsize, ttl=ttl)
    lock = asyncio.Lock()

    def _key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if key is not None:
            return key(*args, **kwargs)
        parts = [repr(value) for value in args if not _is_context(value)]
        parts += [f"{name}={value!r}" for name, value in sorted(kwargs.items())]
        return (getattr(function, "__name__", "tool"), tuple(parts))

    @functools.wraps(function)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        cache_key = _key(args, kwargs)
        async with lock:
            hit = store.get(cache_key, _MISSING)
        if hit is not _MISSING:
            return hit
        result = function(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        async with lock:
            store[cache_key] = result
        return result

    wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
    return wrapper
