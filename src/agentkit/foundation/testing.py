"""Testing ergonomics: fakes for the queue, notifier, cache, storage, and events.

    from agentkit.testing import fake_queue, boot_test_app

    app = boot_test_app()
    queue = fake_queue(app)
    app.notify(ReminderDue("stretch"))
    queue.assert_pushed(ReminderJob)
    await queue.run_pending()

Each fake records what was sent so tests can assert without real side effects.
``TestCase`` bundles the common setup for pytest-asyncio suites.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, ClassVar

from agentkit.foundation.clock import freeze_time, travel, travel_back
from agentkit.foundation.events import FakeDispatcher, fake_events
from agentkit.foundation.factory import Factory
from agentkit.foundation.jobs import CacheStore
from agentkit.foundation.notifications import Notification, Notifier, SentNotification
from agentkit.foundation.storage import MemoryFilesystem

__all__ = [
    "FakeCache",
    "FakeNotifier",
    "FakeQueue",
    "FakeStorage",
    "TestCase",
    "assert_allows",
    "assert_denies",
    "boot_test_app",
    "create",
    "fake_cache",
    "fake_events",
    "fake_notifications",
    "fake_queue",
    "fake_storage",
    "freeze_time",
    "make",
    "run_pending",
    "travel",
    "travel_back",
]


class FakeQueue:
    """An in-memory queue that records pushed jobs and can run them on demand."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self.jobs: list[Any] = []

    async def push(self, job: Any, **options: Any) -> int:  # noqa: ARG002
        self.jobs.append(job)
        return len(self.jobs)

    async def size(self, queue: str | None = None) -> int:  # noqa: ARG002
        return len(self.jobs)

    async def failed(self, limit: int = 50) -> list[Any]:  # noqa: ARG002
        return []

    async def retry(self, job_id: int) -> bool:  # noqa: ARG002
        return False

    async def flush(self) -> int:
        count = len(self.jobs)
        self.jobs.clear()
        return count

    async def run_once(self, queue: str | None = None) -> bool:  # noqa: ARG002
        if not self.jobs:
            return False
        job = self.jobs.pop(0)
        if self.app is not None and hasattr(job, "dispatch"):
            await job.dispatch(self.app)
        return True

    async def run_pending(self) -> int:
        """Run every queued job; returns how many ran."""
        ran = 0
        while self.jobs:
            await self.run_once()
            ran += 1
        return ran

    # -- assertions -----------------------------------------------------
    def pushed(self, job_type: type | None = None) -> list[Any]:
        if job_type is None:
            return list(self.jobs)
        return [job for job in self.jobs if isinstance(job, job_type)]

    def pushed_types(self) -> list[str]:
        return [type(job).__name__ for job in self.jobs]

    def assert_pushed(self, job_type: type | None = None, *, count: int | None = None) -> None:
        matches = self.pushed(job_type)
        label = job_type.__name__ if job_type is not None else "any job"
        if count is None:
            if not matches:
                raise AssertionError(f"expected {label} to be pushed; pushed={self.pushed_types()}")
        elif len(matches) != count:
            raise AssertionError(f"expected {count}x {label}; got {len(matches)}")

    def assert_not_pushed(self, job_type: type | None = None) -> None:
        if self.pushed(job_type):
            raise AssertionError(f"expected {job_type} not to be pushed")


class FakeNotifier(Notifier):
    """A notifier that records notifications instead of delivering them."""

    def __init__(self, app: Any = None) -> None:
        super().__init__(app)
        self.sent: list[SentNotification] = []

    def send(  # type: ignore[override]
        self,
        notification: Notification,
        *,
        to: Any = None,
        conversation_id: str | None = None,
        _queued: bool = False,
    ) -> list[SentNotification]:
        channels = [to] if isinstance(to, str) else list(to or notification.channels)
        for channel in channels:
            self.sent.append(SentNotification(notification, str(channel), ""))
        return list(self.sent)

    def _enqueue(self, *args: Any, **kwargs: Any) -> bool:  # noqa: ARG002
        return False

    def sent_of(self, notification_type: type) -> list[SentNotification]:
        return [item for item in self.sent if isinstance(item.notification, notification_type)]

    def assert_sent(self, notification_type: type, *, count: int | None = None) -> None:
        matches = self.sent_of(notification_type)
        if count is None:
            if not matches:
                raise AssertionError(f"expected {notification_type.__name__} to be sent")
        elif len(matches) != count:
            raise AssertionError(
                f"expected {count}x {notification_type.__name__}; got {len(matches)}"
            )

    def assert_not_sent(self, notification_type: type) -> None:
        if self.sent_of(notification_type):
            raise AssertionError(f"expected {notification_type.__name__} not to be sent")


class FakeCache(CacheStore):
    """An in-memory cache (the array store) for tests."""

    def assert_has(self, key: str) -> None:
        if not self.has(key):
            raise AssertionError(f"expected cache key {key!r} to be set")

    def assert_missing(self, key: str) -> None:
        if self.has(key):
            raise AssertionError(f"expected cache key {key!r} to be absent")


class FakeStorage(MemoryFilesystem):
    """An in-memory file store for tests."""


def fake_queue(app: Any) -> FakeQueue:
    """Install a :class:`FakeQueue` on ``app`` and return it."""
    fake = FakeQueue(app)
    app.fake("queue", fake)
    return fake


def fake_notifications(app: Any) -> FakeNotifier:
    """Install a :class:`FakeNotifier` on ``app`` and return it."""
    fake = FakeNotifier(app)
    app.fake("notifier", fake)
    return fake


def fake_cache(app: Any) -> FakeCache:
    """Install a :class:`FakeCache` on ``app`` and return it."""
    fake = FakeCache()
    app.fake("cache", fake)
    return fake


def fake_storage(app: Any) -> FakeStorage:
    """Install a :class:`FakeStorage` on ``app`` and return it."""
    fake = FakeStorage()
    app.fake("storage", fake)
    return fake


def make(model: Any, count: int = 1, **overrides: Any) -> Any:
    """Build ``model`` instance(s) from its factory without persisting."""
    resolved = Factory.guess_for(model)
    if resolved is None:
        raise LookupError(f"no factory registered for {model.__name__}")
    instance = resolved() if isinstance(resolved, type) else resolved.clone()
    if count != 1:
        instance = instance.count(count)
    if overrides:
        instance = instance.state(overrides)
    return instance.make()


async def create(model: Any, count: int = 1, **overrides: Any) -> Any:
    """Persist ``model`` instance(s) from its factory."""
    resolved = Factory.guess_for(model)
    if resolved is None:
        raise LookupError(f"no factory registered for {model.__name__}")
    instance = resolved() if isinstance(resolved, type) else resolved.clone()
    if count != 1:
        instance = instance.count(count)
    if overrides:
        instance = instance.state(overrides)
    return await instance.create()


def assert_allows(gate: Any, ability: str, *arguments: Any, actor: Any = None) -> None:
    """Assert the Gate allows ``ability``."""
    if not gate.allows(ability, *arguments, actor=actor):
        raise AssertionError(f"expected gate to allow {ability!r}")


def assert_denies(gate: Any, ability: str, *arguments: Any, actor: Any = None) -> None:
    """Assert the Gate denies ``ability``."""
    if not gate.denies(ability, *arguments, actor=actor):
        raise AssertionError(f"expected gate to deny {ability!r}")


def _boot_app(**kwargs: Any) -> Any:
    from agentkit.foundation.application import App

    kwargs.setdefault("discover", False)
    app = App(**kwargs)
    app.boot()
    return app


def boot_test_app(name: str = "test", home: str | Path | None = None, **kwargs: Any) -> Any:
    """Boot a minimal app for a test (queue/notifier/cache/storage fakes not installed).

    ``home`` is accepted for call-site symmetry with production bootstraps but is
    only applied when the settings object exposes a writable ``home`` field.
    """
    settings = kwargs.pop("settings", None)
    if settings is None:
        from agentkit.config import get_settings

        settings = get_settings()
    return _boot_app(name=name, settings=settings, **kwargs)


class TestCase:
    """A small base for pytest-asyncio suites that need a booted app + fakes.

        class TestReminders(TestCase):
            async def test_notify(self):
                await self.boot()
                queue = self.fake_queue()
                ...
    """

    app_name: ClassVar[str] = "test"
    app: Any = None

    async def boot(self, **kwargs: Any) -> Any:
        self.app = boot_test_app(self.app_name, **kwargs)
        return self.app

    def fake_queue(self) -> FakeQueue:
        assert self.app is not None, "call await self.boot() first"
        return fake_queue(self.app)

    def fake_notifications(self) -> FakeNotifier:
        assert self.app is not None, "call await self.boot() first"
        return fake_notifications(self.app)

    def fake_cache(self) -> FakeCache:
        assert self.app is not None, "call await self.boot() first"
        return fake_cache(self.app)

    def fake_storage(self) -> FakeStorage:
        assert self.app is not None, "call await self.boot() first"
        return fake_storage(self.app)

    def fake_events(self) -> FakeDispatcher:
        assert self.app is not None, "call await self.boot() first"
        return fake_events(self.app)

    def teardown(self) -> None:
        if self.app is not None:
            self.app.restore_fakes()


async def run_pending(app: Any, job: Any | None = None) -> Any:
    """Run ``job`` (or everything on the fake queue) against ``app``."""
    if job is not None:
        result = job.dispatch(app) if hasattr(job, "dispatch") else job(app)
        if inspect.isawaitable(result):
            return await result
        return result
    queue = app.fake("queue")
    if queue is None:
        raise RuntimeError("no fake queue installed")
    return await queue.run_pending()
