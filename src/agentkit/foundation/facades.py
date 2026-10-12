"""Facade service objects and the class-method facades that resolve them.

Each facade (``Memory``, ``Schedule``, ``DB``, ``Events``, ``Log``) is a thin
class whose attributes resolve, through the current app, to a bound *service*
defined here. The services hold an :class:`~agentkit.foundation.application.App`
and open short-lived repository sessions as needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from agentkit.foundation.db import session_scope
from agentkit.foundation.facade import Facade
from agentkit.logging import get_logger


class MemoryService:
    """Backs the ``Memory`` facade (durable owner-scoped facts)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def remember(self, content: str, *, kind: str = "fact") -> int:
        with self.app.repositories() as repos:
            return int(repos.memories.add(content, kind=kind).id)

    def search(self, query: str, *, limit: int = 5) -> list[Any]:
        with self.app.repositories() as repos:
            return list(repos.memories.search(query, limit=limit))

    def all(self, limit: int | None = None) -> list[Any]:
        with self.app.repositories() as repos:
            return list(repos.memories.list(limit=limit))

    def forget(self, memory_id: int) -> bool:
        with self.app.repositories() as repos:
            return bool(repos.memories.forget(memory_id))

    def digest(self, *, limit: int = 50) -> str | None:
        from agentkit.memory import memory_digest

        with self.app.repositories() as repos:
            return memory_digest(repos, limit=limit)


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

    def cron(
        self,
        name: str,
        expr: str,
        task: str,
        *,
        args: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> None:
        self._scheduler().schedule_cron(name, expr, task, args=args, enabled=enabled)

    def once(self, name: str, when: Any, task: str, *, args: dict[str, Any] | None = None) -> None:
        self._scheduler().schedule_once(name, when, task, args=args)

    def enable(self, name: str) -> bool:
        return bool(self._scheduler().set_enabled(name, True))

    def disable(self, name: str) -> bool:
        return bool(self._scheduler().set_enabled(name, False))

    def remove(self, name: str) -> bool:
        return bool(self._scheduler().remove_job(name))

    def run_due(self, now: Any = None) -> list[str]:
        return list(self._scheduler().run_due_now(now))

    def list(self) -> list[dict[str, Any]]:
        return list(self._scheduler().list_jobs())


class DBService:
    """Backs the ``DB`` facade (sessions, transactions, repositories).

    A ``transaction()``/``session()`` block makes its repositories *ambient*, so
    ``Model.create(...)`` inside it joins the same session.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def repositories(self):
        return self.app.repositories()

    @contextmanager
    def session(self) -> Iterator[Any]:
        with session_scope(self.app) as repos:
            yield repos.session

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with session_scope(self.app) as repos:
            yield repos


class EventsService:
    """Backs the ``Events`` facade (the app's lifecycle dispatcher)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def listen(self, event: str, listener: Any) -> Any:
        return self.app.events.listen(event, listener)

    def on(self, event: str, listener: Any) -> Any:
        return self.app.events.listen(event, listener)

    def dispatch(self, event: str, **payload: Any) -> list[Any]:
        return self.app.events.dispatch(event, **payload)

    async def dispatch_async(self, event: str, **payload: Any) -> list[Any]:
        return await self.app.events.dispatch_async(event, **payload)


class FeedbackService:
    """Backs the ``Feedback`` facade (user ratings on conversations)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def add(
        self,
        rating: int,
        *,
        conversation_id: str = "",
        message_id: int | None = None,
        comment: str = "",
    ) -> Any:
        with session_scope(self.app) as repos:
            return repos.feedback.add(
                rating=rating,
                conversation_id=conversation_id,
                message_id=message_id,
                comment=comment,
            )

    def list(self, *, conversation_id: str | None = None, limit: int = 50) -> list[Any]:
        with session_scope(self.app) as repos:
            return repos.feedback.list(conversation_id=conversation_id, limit=limit)

    def average(self, *, conversation_id: str | None = None) -> float | None:
        with session_scope(self.app) as repos:
            return repos.feedback.average(conversation_id=conversation_id)

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


class Storage(Facade):
    @classmethod
    def binding(cls) -> str:
        return "storage"


__all__ = [
    "Cache",
    "CacheService",
    "DB",
    "DBService",
    "Events",
    "EventsService",
    "Feedback",
    "FeedbackService",
    "Log",
    "LogService",
    "Memory",
    "MemoryService",
    "Schedule",
    "ScheduleService",
    "Storage",
    "StorageService",
]
