"""Job chains and batches (Laravel's ``Bus``/``Batch``).

Chains run jobs in order; each waits for the previous. Batches run a set of jobs
and report progress, with ``then``/``catch`` callbacks::

    await chain(SyncNotes(), Reindex()).then(lambda: log.info("done")).dispatch(app)
    await batch([SyncNotes(), SyncDocs()]).catch(handler).dispatch(app)

Both are async and go through ``app.dispatch`` (so they respect ``queue_enabled``:
inline when disabled, queued when enabled).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

__all__ = ["Batch", "Chain", "batch", "chain", "pending_batches"]


async def _maybe(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class Chain:
    """A sequence of jobs run in order, with optional callbacks."""

    def __init__(self, jobs: Sequence[Any]) -> None:
        self.jobs = list(jobs)
        self._then: list[Callable[[], Any]] = []
        self._catch: list[Callable[[BaseException], Any]] = []

    def then(self, callback: Callable[[], Any]) -> Chain:
        self._then.append(callback)
        return self

    def catch(self, callback: Callable[[BaseException], Any]) -> Chain:
        self._catch.append(callback)
        return self

    async def dispatch(self, app: Any) -> list[Any]:
        results: list[Any] = []
        try:
            for job in self.jobs:
                results.append(await app.dispatch(job))
        except BaseException as exc:  # noqa: BLE001 - user callback handles it
            for catch_cb in self._catch:
                await _maybe(catch_cb(exc))
            return results
        for then_cb in self._then:
            await _maybe(then_cb())
        return results


class Batch:
    """A set of jobs with progress tracking and completion callbacks."""

    def __init__(self, jobs: Sequence[Any]) -> None:
        self.jobs = list(jobs)
        self._then: list[Callable[[Batch], Any]] = []
        self._catch: list[Callable[[Batch, BaseException], Any]] = []
        self.processed = 0
        self.failures: list[tuple[Any, BaseException]] = []

    def then(self, callback: Callable[[Batch], Any]) -> Batch:
        self._then.append(callback)
        return self

    def catch(self, callback: Callable[[Batch, BaseException], Any]) -> Batch:
        self._catch.append(callback)
        return self

    @property
    def total(self) -> int:
        return len(self.jobs)

    @property
    def pending(self) -> int:
        return max(0, self.total - self.processed)

    def progress(self) -> tuple[int, int]:
        return self.processed, self.total

    async def dispatch(self, app: Any) -> Batch:
        _BATCHES.append(self)
        for job in self.jobs:
            try:
                await app.dispatch(job)
            except BaseException as exc:  # noqa: BLE001 - record and keep going
                self.failures.append((job, exc))
                for catch_cb in self._catch:
                    await _maybe(catch_cb(self, exc))
            finally:
                self.processed += 1
        for then_cb in self._then:
            await _maybe(then_cb(self))
        return self


_BATCHES: list[Batch] = []


def pending_batches() -> list[Batch]:
    """Batches dispatched this process (for ``Batch.fake()``-style assertions)."""
    return list(_BATCHES)


def chain(*jobs: Any) -> Chain:
    """Build a :class:`Chain` from ``jobs``."""
    return Chain(jobs)


def batch(jobs: Sequence[Any] | Any) -> Batch:
    """Build a :class:`Batch` from an iterable of jobs."""
    if not isinstance(jobs, Sequence) or isinstance(jobs, (str, bytes)):
        jobs = [jobs]
    return Batch(list(jobs))
