"""WS9 — testing ergonomics: queue/notifier/cache/storage fakes and TestCase."""

from __future__ import annotations

from typing import Any

import pytest
from sqlmodel import Field

from agentkit import Factory, Job, Model, Notification
from agentkit.runtime import Runtime
from agentkit.testing import (
    FakeQueue,
    TestCase,
    boot_test_app,
    fake_cache,
    fake_notifications,
    fake_queue,
    fake_storage,
    run_pending,
)


class Ping(Job):
    def handle(self, app: Any) -> str:  # noqa: ARG002
        return "pong"


class Hello(Notification):
    channels = ("log",)

    def __init__(self, text: str = "") -> None:
        self.text = text

    def to_log(self) -> str:
        return self.text


async def test_fake_queue_records_and_runs(runtime: Runtime) -> None:
    app = boot_test_app("t", settings=runtime.settings)
    app._runtime = runtime
    queue = fake_queue(app)
    assert isinstance(queue, FakeQueue)
    await queue.push(Ping())
    queue.assert_pushed(Ping)
    assert queue.pushed_types() == ["Ping"]
    assert await queue.run_pending() == 1
    queue.assert_not_pushed(Ping)


def test_fake_notifier_records() -> None:
    app = boot_test_app("t")
    notifier = fake_notifications(app)
    app.notify(Hello("hi"))
    notifier.assert_sent(Hello)
    assert notifier.sent[0].notification.text == "hi"
    assert app.notifier is notifier


def test_fake_cache_and_storage() -> None:
    app = boot_test_app("t")
    cache = fake_cache(app)
    app.cache.put("k", 1)
    cache.assert_has("k")
    assert app.cache.get("k") == 1
    cache.assert_missing("nope")

    storage = fake_storage(app)
    app.storage.put("a.txt", "hello")
    assert app.storage.get("a.txt") == "hello"
    assert storage.exists("a.txt")


def test_app_fake_and_restore() -> None:
    app = boot_test_app("t")
    fake_queue(app)
    assert app.fake("queue") is not None
    app.restore_fakes()
    assert app.fake("queue") is None


async def test_test_case_base() -> None:
    case = TestCase()
    await case.boot()
    queue = case.fake_queue()
    await queue.push(Ping())
    queue.assert_pushed(Ping)
    case.teardown()


async def test_run_pending_helper(runtime: Runtime) -> None:
    app = boot_test_app("t", settings=runtime.settings)
    app._runtime = runtime
    queue = fake_queue(app)
    await queue.push(Ping())
    assert await run_pending(app) == 1


def test_fake_queue_assertions_fail_cleanly() -> None:
    queue = FakeQueue()
    with pytest.raises(AssertionError):
        queue.assert_pushed(Ping)
    queue.assert_not_pushed(Ping)


def test_freeze_time_and_travel() -> None:
    from datetime import UTC, datetime, timedelta

    from agentkit.foundation.clock import now
    from agentkit.testing import freeze_time, travel, travel_back

    when = datetime(2030, 1, 1, tzinfo=UTC)
    with freeze_time(when):
        assert now() == when
        with travel(days=1):
            assert now() == when + timedelta(days=1)
        assert now() == when
    travel_back()


class _Widget(Model, table=True):
    __tablename__ = "ws9_widgets"

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""


class _WidgetFactory(Factory):
    model = _Widget

    def definition(self) -> dict[str, Any]:
        return {"name": "w"}


def test_make_and_create_helpers(runtime: Runtime) -> None:
    from agentkit.foundation.factory import Factory as _Factory
    from agentkit.testing import make

    app = boot_test_app("t", settings=runtime.settings)
    app._runtime = runtime
    _Factory.for_model(_Widget, _WidgetFactory)

    built = make(_Widget, name="built")
    assert isinstance(built, _Widget) and built.name == "built"


async def test_create_helper_persists(runtime: Runtime) -> None:
    from agentkit.foundation.factory import Factory as _Factory
    from agentkit.testing import create

    app = boot_test_app("t", settings=runtime.settings)
    app._runtime = runtime
    _Factory.for_model(_Widget, _WidgetFactory)
    made = await create(_Widget, name="made")
    assert made.id is not None


def test_gate_assertions() -> None:
    from agentkit import GateManager
    from agentkit.testing import assert_allows, assert_denies

    gate = GateManager()
    gate.define("view", lambda actor, subject: True)
    gate.define("edit", lambda actor, subject: False)
    assert_allows(gate, "view", object())
    assert_denies(gate, "edit", object())
    with pytest.raises(AssertionError):
        assert_allows(gate, "edit", object())
