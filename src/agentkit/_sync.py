"""Bridge helpers to run async code from synchronous seams.

Used for build-time indexing and DBOS workflow/step bodies: the async work runs to
completion on a private event loop (never on the caller's loop, if there is one).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

__all__ = ["run_sync"]


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # A loop is already running (so nested asyncio.run is illegal): offload to a
    # worker thread with its own loop.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def run_sync_call(function: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any) -> T:
    """Convenience: build the coroutine and run it via :func:`run_sync`."""
    return run_sync(function(*args, **kwargs))
