"""WS3 — class-based events and listeners."""

from __future__ import annotations

import sys
from pathlib import Path

from agentkit import (
    App,
    Event,
    Listener,
    Notification,
    ShouldQueue,
    TurnEnded,
    fake_events,
)
from agentkit.foundation import discovery
from agentkit.runtime import Runtime

_SEEN: list[str] = []


class QueuedNotice(ShouldQueue, Notification):
    channels = ("log",)

    def __init__(self, text: str = "") -> None:
        self.text = text

    def to_log(self) -> str:
        _SEEN.append(self.text)
        return self.text


def _app(runtime: Runtime) -> App:
    app = App(name="events", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


class RecordTurnEnded(Listener):
    event = TurnEnded

    def handle(self, event: Event) -> None:
        _SEEN.append(event.get("conversation_id"))


class QueuedTurnEnded(Listener, ShouldQueue):
    event = "turn.end"

    def handle(self, event: Event) -> None:
        _SEEN.append("queued")


def test_listener_by_event_class() -> None:
    app = App(name="events", discover=False)
    app.listeners([RecordTurnEnded])
    _SEEN.clear()
    app.events.dispatch("turn.end", conversation_id="cli:1")
    assert _SEEN == ["cli:1"]


def test_dispatch_event_class_instance() -> None:
    app = App(name="events", discover=False)
    app.listeners([RecordTurnEnded])
    _SEEN.clear()
    app.events.dispatch(TurnEnded(app=app, payload={"conversation_id": "x"}))
    assert _SEEN == ["x"]


def test_legacy_string_listener_still_fires() -> None:
    app = App(name="events", discover=False)
    _SEEN.clear()
    class _Legacy(Listener):
        event = "turn.end"

        def handle(self, event) -> None:
            _SEEN.append("legacy")

    app.listeners([_Legacy()])
    app.events.dispatch(TurnEnded(app=app, payload={"conversation_id": "1"}))
    assert _SEEN == ["legacy"]


def test_fake_events_records_and_asserts(runtime: Runtime) -> None:
    app = _app(runtime)
    fake = fake_events(app)
    app.events.dispatch_async  # noqa: B018 - attribute exists
    fake.dispatch("turn.end", conversation_id="c")
    fake.assert_dispatched(TurnEnded)
    assert fake.has_dispatched("turn.end")
    assert fake.dispatched_names() == ["turn.end"]
    fake.assert_not_dispatched("tool.start")


async def test_should_queue_listener_enqueues(runtime: Runtime) -> None:
    runtime.settings.queue_enabled = True
    try:
        app = _app(runtime)
        app.listeners([QueuedTurnEnded])
        _SEEN.clear()
        await app.events.dispatch_async("turn.end", conversation_id="q")
        assert _SEEN == []  # queued, not inline
        assert await app.queue.size() >= 1
        assert await app.queue.run_once() is True
        assert _SEEN == ["queued"]
    finally:
        runtime.settings.queue_enabled = False


async def test_should_queue_notification_enqueues(runtime: Runtime) -> None:
    runtime.settings.queue_enabled = True
    try:
        app = _app(runtime)
        _SEEN.clear()
        app.notify(QueuedNotice("hi"))
        assert _SEEN == []  # queued, not delivered inline
        assert await app.queue.size() >= 1
        assert await app.queue.run_once() is True
        assert _SEEN == ["hi"]
    finally:
        runtime.settings.queue_enabled = False


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_listeners(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _write(root / "app" / "__init__.py", "")
    _write(root / "app" / "Listeners" / "__init__.py", "")
    _write(
        root / "app" / "Listeners" / "AuditListener.py",
        "from agentkit import Listener\n\n\n"
        "class AuditListener(Listener):\n    event = 'turn.end'\n\n"
        "    def handle(self, event):\n        return None\n",
    )
    resolved = str(root.resolve())
    try:
        found = discovery.discover_listeners(root)
        assert [listener.__name__ for listener in found] == ["AuditListener"]
    finally:
        sys.path[:] = [entry for entry in sys.path if entry != resolved]
        for name, module in list(sys.modules.items()):
            source = getattr(module, "__file__", None)
            if source and resolved in source:
                sys.modules.pop(name, None)
