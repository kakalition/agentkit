"""Tool-result caching and tool registration helpers.

``cached_tool`` wraps a tool function with a small TTL + size-limited cache keyed
on its arguments (the :class:`~pydantic_ai.RunContext` is ignored), so repeated
calls with the same arguments do not re-run the side effect::

    from agentkit.cache import cached_tool

    agent.tool(cached_tool(lookup, ttl=60))

The wrapper preserves the original signature (via ``functools.wraps``) so
PydanticAI still derives the correct JSON schema.
"""

from __future__ import annotations

import functools
import inspect
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

__all__ = ["cached_tool"]


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
    store: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def _key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if key is not None:
            return key(*args, **kwargs)
        parts = [repr(value) for value in args if not _is_context(value)]
        parts += [f"{name}={value!r}" for name, value in sorted(kwargs.items())]
        return (getattr(function, "__name__", "tool"), tuple(parts))

    @functools.wraps(function)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        cache_key = _key(args, kwargs)
        now = time.monotonic()
        hit = store.get(cache_key)
        if hit is not None and hit[0] > now:
            store.move_to_end(cache_key)
            return hit[1]
        result = function(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        store[cache_key] = (now + ttl, result)
        store.move_to_end(cache_key)
        while len(store) > maxsize:
            store.popitem(last=False)
        return result

    wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
    return wrapper
