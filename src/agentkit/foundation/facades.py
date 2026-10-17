"""Facade service objects and the class-method facades that resolve them.

Each facade (``Memory``, ``Schedule``, ``DB``, ``Events``, ``Log``) is a thin
class whose attributes resolve, through the current app, to a bound *service*
defined here. The services hold an :class:`~agentkit.foundation.application.App`
and open short-lived repository sessions as needed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from agentkit.foundation.db import session_scope
from agentkit.foundation.facade import Facade
from agentkit.logging import get_logger


class MemoryService:
    """Backs the ``Memory`` facade (durable owner-scoped facts)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def remember(self, content: str, *, kind: str = "fact") -> int:
        async with self.app.repositories() as repos:
            return int((await repos.memories.add(content, kind=kind)).id)

    async def search(self, query: str, *, limit: int = 5) -> list[Any]:
        async with self.app.repositories() as repos:
            return list(await repos.memories.search(query, limit=limit))

    async def all(self, limit: int | None = None) -> list[Any]:
        async with self.app.repositories() as repos:
            return list(await repos.memories.list(limit=limit))

    async def forget(self, memory_id: int) -> bool:
        async with self.app.repositories() as repos:
            return bool(await repos.memories.forget(memory_id))

    async def digest(self, *, limit: int = 50) -> str | None:
        from agentkit.memory import memory_digest

        async with self.app.repositories() as repos:
            return await memory_digest(repos, limit=limit)


class ScheduleService:
    """Backs the ``Schedule`` facade (durable cron/one-off jobs)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def _scheduler(self) -> Any:
        from agentkit import scheduler

        scheduler.ensure_configured(self.app.settings, repos_factory=self.app.repos_factory)
        return scheduler

    def task(self, name: str):
        """Decorator registering a task callable under ``name``."""
        return self._scheduler().task(name)

    async def cron(
        self,
        name: str,
        expr: str,
        task: str,
        *,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        await self._scheduler().schedule_cron(name, expr, task, args=args, enabled=enabled)

    async def once(
        self, name: str, when: Any, task: str, *, args: dict[str, Any] | None = None
    ) -> None:
        await self._scheduler().schedule_once(name, when, task, args=args)

    async def enable(self, name: str) -> bool:
        return bool(await self._scheduler().set_enabled(name, True))

    async def disable(self, name: str) -> bool:
        return bool(await self._scheduler().set_enabled(name, False))

    async def remove(self, name: str) -> bool:
        return bool(await self._scheduler().remove_job(name))

    async def run_due(self, now: Any = None) -> list[str]:
        return list(await self._scheduler().run_due_now(now))

    async def list(self) -> list[dict[str, Any]]:
        return list(await self._scheduler().list_jobs())


class DBService:
    """Backs the ``DB`` facade (sessions, transactions, repositories).

    A ``transaction()``/``session()`` block makes its repositories *ambient*, so
    ``Model.create(...)`` inside it joins the same session.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def repositories(self):
        return self.app.repositories()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Any]:
        async with session_scope(self.app) as repos:
            yield repos.session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        async with session_scope(self.app) as repos:
            yield repos


class EventsService:
    """Backs the ``Events`` facade (the app's lifecycle dispatcher)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def listen(self, event: str, listener: Any) -> Any:
        return self.app.events.listen(event, listener)

    def dispatch(self, event: str, **payload: Any) -> list[Any]:
        return self.app.events.dispatch(event, **payload)

    async def dispatch_async(self, event: str, **payload: Any) -> list[Any]:
        return await self.app.events.dispatch_async(event, **payload)


class FeedbackService:
    """Backs the ``Feedback`` facade (user ratings on conversations)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def add(
        self,
        rating: int,
        *,
        conversation_id: str = "",
        message_id: int | None = None,
        comment: str = "",
    ) -> Any:
        async with session_scope(self.app) as repos:
            return await repos.feedback.add(
                rating=rating,
                conversation_id=conversation_id,
                message_id=message_id,
                comment=comment,
            )

    async def list(self, *, conversation_id: str | None = None, limit: int = 50) -> list[Any]:
        async with session_scope(self.app) as repos:
            return await repos.feedback.list(conversation_id=conversation_id, limit=limit)

    async def average(self, *, conversation_id: str | None = None) -> float | None:
        async with session_scope(self.app) as repos:
            return await repos.feedback.average(conversation_id=conversation_id)


class QueueService:
    """Backs the ``Queue`` facade."""

    def __init__(self, app: Any) -> None:
        self.app = app

    @property
    def queue(self) -> Any:
        return self.app.queue

    async def push(self, job: Any, **kwargs: Any) -> int:
        return await self.queue.push(job, **kwargs)

    async def run_once(self, queue: str | None = None) -> bool:
        return await self.queue.run_once(queue)

    async def size(self, queue: str | None = None) -> int:
        return await self.queue.size(queue)

    async def failed(self, *, limit: int = 50) -> list[Any]:
        return await self.queue.failed(limit=limit)


class LogService:
    """Backs the ``Log`` facade (structured logging with redaction)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def channel(self, name: str = "agentkit") -> Any:
        return get_logger(name)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        get_logger("agentkit").info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        get_logger("agentkit").warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        get_logger("agentkit").error(message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        get_logger("agentkit").debug(message, *args, **kwargs)


class CacheService:
    """Backs the ``Cache`` facade."""

    def __init__(self, app: Any) -> None:
        self.app = app

    @property
    def store(self) -> Any:
        return self.app.cache

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    def put(self, key: str, value: Any, ttl: float | None = None) -> Any:
        return self.store.put(key, value, ttl)

    def remember(self, key: str, factory: Any, ttl: float | None = None) -> Any:
        return self.store.remember(key, factory, ttl)

    def has(self, key: str) -> bool:
        return self.store.has(key)

    def forget(self, key: str) -> None:
        self.store.forget(key)

    def flush(self) -> None:
        self.store.flush()


class StorageService:
    """Backs the ``Storage`` facade."""

    def __init__(self, app: Any) -> None:
        self.app = app

    @property
    def store(self) -> Any:
        return self.app.storage

    def put(self, relative: Any, data: Any) -> str:
        return self.store.put(relative, data)

    def get(self, relative: Any) -> str:
        return self.store.get(relative)

    def get_bytes(self, relative: Any) -> bytes:
        return self.store.get_bytes(relative)

    def exists(self, relative: Any) -> bool:
        return self.store.exists(relative)

    def list(self, prefix: str = "") -> list[str]:
        return self.store.list(prefix)

    def delete(self, relative: Any) -> bool:
        return self.store.delete(relative)

    def metadata(self, relative: Any) -> dict[str, Any]:
        return self.store.metadata(relative)


class Memory(Facade):
    @classmethod
    def binding(cls) -> str:
        return "memory"

    @classmethod
    def driver_kind(cls) -> str:
        return "memory"


class Schedule(Facade):
    @classmethod
    def binding(cls) -> str:
        return "schedule"


class DB(Facade):
    @classmethod
    def binding(cls) -> str:
        return "db"


class Events(Facade):
    @classmethod
    def binding(cls) -> str:
        return "events"


class Log(Facade):
    @classmethod
    def binding(cls) -> str:
        return "log"


class Feedback(Facade):
    @classmethod
    def binding(cls) -> str:
        return "feedback"


class Cache(Facade):
    @classmethod
    def binding(cls) -> str:
        return "cache"

    @classmethod
    def driver_kind(cls) -> str:
        return "cache"


class Storage(Facade):
    @classmethod
    def binding(cls) -> str:
        return "storage"

    @classmethod
    def driver_kind(cls) -> str:
        return "storage"


class Queue(Facade):
    @classmethod
    def binding(cls) -> str:
        return "queue"


class Gate(Facade):
    """Class-method facade over the app's :class:`~agentkit.foundation.gate.Gate`."""

    @classmethod
    def binding(cls) -> str:
        return "gate"


__all__ = [
    "Cache",
    "CacheService",
    "DB",
    "DBService",
    "Events",
    "EventsService",
    "Feedback",
    "FeedbackService",
    "Gate",
    "Log",
    "LogService",
    "Memory",
    "MemoryService",
    "Queue",
    "QueueService",
    "Schedule",
    "ScheduleService",
    "Storage",
    "StorageService",
]
