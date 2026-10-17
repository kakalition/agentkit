"""A durable, database-backed queue — Laravel's queues for agents.

Jobs are persisted and processed by a worker, so long work survives restarts and
is retried::

    from agentkit import Job, Queue

    class SyncNotes(Job):
        max_retries = 3
        def handle(self, app) -> None: ...

    Queue.push(SyncNotes())          # store it
    await Queue.run_once()           # or run the worker: `agentkit queue:work`

When ``queue_enabled`` is false (the default) ``await app.dispatch(job)`` runs the
job inline; when true it is pushed and a worker processes it.
"""

from __future__ import annotations

import importlib
import inspect
import json
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Field, select

from agentkit.contracts.queue import QueueDriver
from agentkit.foundation.clock import now
from agentkit.foundation.model import Model
from agentkit.foundation.repository import Repository
from agentkit.logging import get_logger
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, QueueDriverKind
from agentkit.support.manager import Manager

log = get_logger("agentkit.queue")

__all__ = [
    "DeserializationError",
    "Job",
    "Queue",
    "QueueDriver",
    "QueueManager",
    "QueueRepo",
    "QueuedJob",
    "QueuedListenerJob",
    "SyncQueue",
    "deserialize_job",
    "serialize_job",
]


class DeserializationError(RuntimeError):
    """Raised when a queued job's payload cannot be rebuilt."""


class Job:
    """Base class for dispatchable work.

    Constructor arguments are captured (from attributes of the same name) when the
    job is queued, so jobs should store them on ``self``.
    """

    queue: str = "default"
    max_retries: int = 3

    def handle(self, app: Any) -> Any:
        raise NotImplementedError

    def middleware(self) -> list[Any]:
        """Job middleware: ``async def mw(job, app, call_next)`` wrappers."""
        return []

    def failed(self, app: Any, error: BaseException) -> None:
        """Called when the job raises (default: re-raise)."""
        raise error

    async def dispatch(self, app: Any) -> Any:
        async def run() -> Any:
            result = self.handle(app)
            if inspect.isawaitable(result):
                return await result
            return result

        chain = run
        for middleware in reversed(self.middleware()):
            chain = _wrap_job_middleware(middleware, self, app, chain)
        try:
            return await chain()
        except BaseException as exc:  # noqa: BLE001 - routed through failed()
            self.failed(app, exc)
            raise

    def to_payload(self) -> dict[str, Any]:
        return serialize_job(self)


def _wrap_job_middleware(
    middleware: Any, job: Job, app: Any, nxt: Any
) -> Any:
    async def handler() -> Any:
        async def call_next() -> Any:
            return await nxt()

        result = middleware(job, app, call_next)
        if inspect.isawaitable(result):
            result = await result
        return result

    return handler


def serialize_job(job: Job) -> dict[str, Any]:
    """Represent a job as ``{"job": "module:QualName", "kwargs": {...}}``."""
    signature = inspect.signature(type(job).__init__)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if hasattr(job, name):
            kwargs[name] = getattr(job, name)
    return {"job": f"{type(job).__module__}:{type(job).__qualname__}", "kwargs": kwargs}


def deserialize_job(payload: dict[str, Any]) -> Job:
    """Rebuild a job from :func:`serialize_job` output."""
    reference = payload.get("job")
    if not reference:
        raise DeserializationError("payload has no 'job' reference")
    module_name, _, qualname = reference.partition(":")
    try:
        target: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            target = getattr(target, part)
        return target(**payload.get("kwargs", {}))
    except Exception as exc:  # pragma: no cover - defensive
        raise DeserializationError(f"cannot rebuild job {reference!r}: {exc}") from exc


class QueuedListenerJob(Job):
    """A ``ShouldQueue`` event listener dispatched onto the durable queue.

    The listener is referenced by ``module:ClassName`` (it must be
    default-constructible) and the event is replayed with its payload.
    """

    def __init__(self, listener_path: str = "", name: str = "", payload: dict[str, Any] | None = None) -> None:
        self.listener_path = listener_path
        self.name = name
        self.payload = dict(payload or {})

    def handle(self, app: Any) -> Any:
        from agentkit.foundation.events import Event

        module_name, _, qualname = self.listener_path.partition(":")
        target: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            target = getattr(target, part)
        listener = target() if isinstance(target, type) else target
        result = listener(Event(self.name, app, dict(self.payload)))
        if inspect.isawaitable(result):
            from agentkit._sync import run_sync

            return run_sync(result)  # type: ignore[arg-type]
        return result


class QueuedJob(Model, table=True):
    """A stored job awaiting processing."""

    __tablename__ = "queued_jobs"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: str = Field(index=True)
    queue: str = Field(default="default", index=True)
    job: str = ""
    payload: str = "{}"
    attempts: int = 0
    max_retries: int = 3
    available_at: datetime = Field(default_factory=lambda: now(), index=True)
    reserved_at: datetime | None = Field(default=None)
    failed: bool = False
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: now())
    updated_at: datetime = Field(default_factory=lambda: now())


class QueueRepo(Repository[QueuedJob]):
    model = QueuedJob

    async def ready(self, queue: str, now: datetime, *, limit: int = 1) -> list[QueuedJob]:
        stmt = (
            select(QueuedJob)
            .where(QueuedJob.owner_id == self.owner_id, QueuedJob.queue == queue)
            .where(QueuedJob.failed == False, QueuedJob.reserved_at == None)  # noqa: E711, E712
            .where(QueuedJob.available_at <= now)
            .order_by(QueuedJob.available_at, QueuedJob.id)  # type: ignore[arg-type]
            .limit(limit)
        )
        return list((await self.session.exec(stmt)).all())

    async def failed_jobs(self, *, limit: int = 50) -> list[QueuedJob]:
        return await self.where(failed=True).order_by("id", descending=True).limit(limit).all()

    async def size(self, queue: str | None = None) -> int:
        filters: dict[str, Any] = {"failed": False}
        if queue is not None:
            filters["queue"] = queue
        return await self.count(**filters)


class Queue:
    """A database-backed job queue bound to an app."""

    def __init__(self, app: Any) -> None:
        self.app = app

    @property
    def default(self) -> str:
        return getattr(self.app.settings, "queue_default", "default") or "default"

    # -- producer -------------------------------------------------------
    async def push(
        self,
        job: Any,
        *,
        queue: str | None = None,
        delay: float = 0.0,
        max_retries: int | None = None,
    ) -> int:
        """Persist a job; returns its id."""
        payload = job.to_payload() if hasattr(job, "to_payload") else serialize_job(job)
        current = now()
        async with self.app.repositories() as repos:
            record = await repos.queue.create(
                queue=queue or getattr(job, "queue", self.default),
                job=payload["job"],
                payload=json.dumps(payload),
                max_retries=max_retries if max_retries is not None else getattr(job, "max_retries", 3),
                available_at=current + timedelta(seconds=delay),
            )
            return int(record.id)

    async def size(self, queue: str | None = None) -> int:
        async with self.app.repositories() as repos:
            size = await repos.queue.size(queue)
        from agentkit import metrics

        metrics.record_queue_depth(queue or self.default, size)
        return size

    async def failed(self, *, limit: int = 50) -> list[QueuedJob]:
        async with self.app.repositories() as repos:
            return await repos.queue.failed_jobs(limit=limit)

    async def retry(self, job_id: int) -> bool:
        """Requeue a failed job."""
        async with self.app.repositories() as repos:
            record = await repos.queue.get(job_id)
            if record is None or not record.failed:
                return False
            record.failed = False
            record.attempts = 0
            record.error = ""
            record.reserved_at = None
            record.available_at = now()
            record.updated_at = now()
            repos.session.add(record)
            await repos.session.flush()
            return True

    async def flush(self) -> int:
        """Delete all failed jobs; returns how many were removed."""
        async with self.app.repositories() as repos:
            rows = await repos.queue.failed_jobs(limit=10_000)
            for record in rows:
                await repos.session.delete(record)
            await repos.session.flush()
            return len(rows)

    # -- worker ---------------------------------------------------------
    async def run_once(self, queue: str | None = None) -> bool:
        """Reserve and run one job; returns False when the queue is empty."""
        record = await self._reserve(queue or self.default)
        if record is None:
            return False
        assert record.id is not None
        try:
            job = deserialize_job(json.loads(record.payload))
        except DeserializationError as exc:
            await self._fail(record.id, str(exc))
            return True
        try:
            await job.dispatch(self.app)
        except Exception as exc:  # pragma: no cover - depends on job
            log.exception("queued job %s failed", record.id)
            await self._fail(record.id, repr(exc))
            return True
        await self._complete(record.id)
        return True

    async def _reserve(self, queue: str) -> QueuedJob | None:
        current = now()
        async with self.app.repositories() as repos:
            candidates = await repos.queue.ready(queue, current, limit=1)
            if not candidates:
                return None
            record = candidates[0]
            record.reserved_at = current
            record.attempts += 1
            record.updated_at = current
            repos.session.add(record)
            await repos.session.flush()
            await repos.session.refresh(record)
            return record

    async def _complete(self, job_id: int) -> None:
        async with self.app.repositories() as repos:
            record = await repos.queue.get(job_id)
            if record is not None:
                await repos.session.delete(record)

    async def _fail(self, job_id: int, error: str) -> None:
        async with self.app.repositories() as repos:
            record = await repos.queue.get(job_id)
            if record is None:
                return
            record.error = error
            record.reserved_at = None
            record.updated_at = now()
            if record.attempts >= record.max_retries:
                record.failed = True
            else:
                record.available_at = now()
            repos.session.add(record)
            await repos.session.flush()


class SyncQueue:
    """A synchronous driver: jobs run inline, nothing is persisted."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def push(
        self,
        job: Any,
        *,
        queue: str | None = None,
        delay: float = 0.0,
        max_retries: int | None = None,
    ) -> int:
        if hasattr(job, "dispatch"):
            await job.dispatch(self.app)
        else:  # pragma: no cover - defensive
            raise TypeError("queue.push() expects a Job instance")
        return 0

    async def run_once(self, queue: str | None = None) -> bool:
        return False

    async def size(self, queue: str | None = None) -> int:
        return 0

    async def failed(self, *, limit: int = 50) -> list[Any]:
        return []


class QueueManager(Manager):
    """Resolves the configured queue driver (``queue_driver``, default ``database``)."""

    kind = DriverKind.QUEUE
    default_driver = QueueDriverKind.DATABASE


@register_driver(DriverKind.QUEUE, QueueDriverKind.DATABASE)
class DatabaseQueueDriver(Driver):
    def build(self) -> Queue:
        app = self.app
        return Queue(app)
@register_driver(DriverKind.QUEUE, QueueDriverKind.SYNC)
class SyncQueueDriver(Driver):
    def build(self) -> SyncQueue:
        app = self.app
        return SyncQueue(app)
