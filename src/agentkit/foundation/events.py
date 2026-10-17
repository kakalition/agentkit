"""Lifecycle event bus.

Listeners are called with an :class:`Event` whose payload keys are exposed as
attributes, so a listener can be written naturally::

    app.listeners([AuditListener()])

Free-form keys are registered on the name; the special ``"*"`` name receives
every event. Both synchronous and asynchronous listeners are supported via
:meth:`Dispatcher.dispatch` and :meth:`Dispatcher.dispatch_async` respectively.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

from agentkit.logging import get_logger

log = get_logger("agentkit.events")

ListenerFunc = Callable[["Event"], Any]


def _normalize_listener(listener: Any) -> Any:
    """Normalize a listener target to a listener-shaped callable (or ``None``)."""
    from agentkit.foundation.callable import normalize

    resolved = normalize(listener, protocol="listener")
    return resolved.invocable


@dataclass
class Event:
    """A dispatched lifecycle event; payload keys are available as attributes."""

    name: str
    app: Any = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, item: str) -> Any:
        if item.startswith("_"):
            raise AttributeError(item)
        payload = object.__getattribute__(self, "payload")
        try:
            return payload[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)

    @classmethod
    def fake(cls, app: Any = None) -> FakeDispatcher:
        """Swap the current app's dispatcher for a recording fake (testing)."""
        return fake_events(app)


class Dispatcher:
    """Register and fire lifecycle listeners."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._listeners: dict[str, list[ListenerFunc]] = {}

    def _key(self, event: Any) -> str:
        if isinstance(event, str):
            return event
        if isinstance(event, type) and issubclass(event, Event):
            name = getattr(event, "name", None)
            return name if isinstance(name, str) else event.__name__
        return str(getattr(event, "name", event))

    def listen(self, event: Any, listener: Any) -> Any:
        """Register ``listener`` for ``event``.

        ``listener`` may be a closure/callable, a :class:`Listener` class or
        instance, or a ``"module:attr"`` string spec; it is normalized through
        the shared layer to a listener-shaped callable.
        """
        normalized = _normalize_listener(listener)
        if normalized is None:
            return listener
        self._listeners.setdefault(self._key(event), []).append(normalized)
        return normalized

    on = listen

    def listeners(self, event: Any) -> list[ListenerFunc]:
        key = self._key(event)
        return [*self._listeners.get(key, []), *self._listeners.get("*", [])]

    def forget(self, event: Any = None) -> None:
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(self._key(event), None)

    def _event(self, event: Any, payload: dict[str, Any]) -> Event:
        if isinstance(event, Event):
            if event.app is None:
                event.app = self.app
            return event
        if isinstance(event, type) and issubclass(event, Event):
            return event(self._key(event), self.app, payload)
        return Event(event, self.app, payload)

    def _queue_listener(self, listener: Any, ev: Event) -> bool:
        """Push a ``ShouldQueue`` listener onto the app queue (if one is bound)."""
        if not isinstance(listener, ShouldQueue):
            return False
        app = ev.app or self.app
        queue = getattr(app, "queue", None) if app is not None else None
        if queue is None:
            return False
        from agentkit.foundation.queue import QueuedListenerJob

        job = QueuedListenerJob(
            listener_path=f"{type(listener).__module__}:{type(listener).__qualname__}",
            name=ev.name,
            payload=dict(ev.payload),
        )
        try:
            from agentkit._sync import run_sync

            run_sync(queue.push(job))
            return True
        except Exception:  # pragma: no cover - fall back to inline
            log.exception("could not queue listener %r", ev.name)
            return False

    def dispatch(self, event: Any, **payload: Any) -> list[Any]:
        ev = self._event(event, payload)
        results: list[Any] = []
        for listener in self.listeners(ev.name):
            if self._queue_listener(listener, ev):
                results.append(None)
                continue
            result = listener(ev)
            if inspect.isawaitable(result):
                close = getattr(result, "close", None)
                if close is not None:
                    close()
                raise RuntimeError(
                    f"async listener for {ev.name!r} used with sync dispatch(); "
                    "use dispatch_async()"
                )
            results.append(result)
        return results

    async def dispatch_async(self, event: Any, **payload: Any) -> list[Any]:
        ev = self._event(event, payload)
        results: list[Any] = []
        for listener in self.listeners(ev.name):
            if self._queue_listener(listener, ev):
                results.append(None)
                continue
            result = listener(ev)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        return results


class ShouldQueue:
    """Marker mixin: run this listener/notification on the durable queue.

    Set ``queue`` / ``connection`` / ``delay`` to steer where and when it runs.
    """

    queue: ClassVar[str | None] = None
    connection: ClassVar[str | None] = None
    delay: ClassVar[float | None] = None
    tries: ClassVar[int] = 1


class ShouldBroadcast:
    """Marker mixin: fan this event/listener out over webhooks + realtime."""

    broadcast_on: ClassVar[str | None] = None
    broadcast_as: ClassVar[str | None] = None


def should_queue(obj: Any) -> bool:
    """Whether ``obj`` (a listener or notification) should be queued."""
    return isinstance(obj, ShouldQueue)


def should_broadcast(obj: Any) -> bool:
    """Whether ``obj`` should be broadcast."""
    return isinstance(obj, ShouldBroadcast)


__all__ = [
    "ApprovalRequested",
    "Booted",
    "ChannelMessageReceived",
    "Dispatcher",
    "Event",
    "FakeDispatcher",
    "GuardrailsFlagged",
    "JobFailed",
    "JobProcessed",
    "Listener",
    "ListenerFunc",
    "MemoryWritten",
    "ScheduleRan",
    "ShouldBroadcast",
    "ShouldQueue",
    "SkillLoaded",
    "ToolEnded",
    "ToolStarted",
    "TurnEnded",
    "TurnStarted",
    "fake_events",
    "should_broadcast",
    "should_queue",
]


# -- named lifecycle events -------------------------------------------------
# Their ``name`` matches the string seam, so a listener may register by class or
# by the legacy string and both fire (dual dispatch).


@dataclass
class Booted(Event):
    name: str = "boot"


@dataclass
class TurnStarted(Event):
    name: str = "turn.start"


@dataclass
class TurnEnded(Event):
    name: str = "turn.end"


@dataclass
class ToolStarted(Event):
    name: str = "tool.start"


@dataclass
class ToolEnded(Event):
    name: str = "tool.end"


@dataclass
class ApprovalRequested(Event):
    name: str = "approval.asked"


@dataclass
class ChannelMessageReceived(Event):
    name: str = "channel.message"


@dataclass
class GuardrailsFlagged(Event):
    name: str = "guardrails.injection"


@dataclass
class JobProcessed(Event):
    name: str = "job.processed"


@dataclass
class JobFailed(Event):
    name: str = "job.failed"


@dataclass
class ScheduleRan(Event):
    name: str = "schedule.ran"


@dataclass
class MemoryWritten(Event):
    name: str = "memory.written"


@dataclass
class SkillLoaded(Event):
    name: str = "skill.loaded"


class Listener:
    """Base class for event listeners.

    Subclass and set ``event`` (a name or names); register with ``app.on`` or the
    provider helper. Instances are callable, so they work anywhere a listener does.
    """

    event: ClassVar[Any] = ()
    queue: ClassVar[str | None] = None

    def handle(self, event: Event) -> Any:
        raise NotImplementedError

    def __call__(self, event: Event) -> Any:
        return self.handle(event)

    @classmethod
    def events(cls) -> list[str]:
        value = cls.event
        if not value:
            return []
        values = value if isinstance(value, (list, tuple)) else [value]
        names: list[str] = []
        for item in values:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, type) and issubclass(item, Event):
                names.append(getattr(item, "name", item.__name__))
        return names


class FakeDispatcher:
    """A recording dispatcher for tests (``fake_events()``)."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self.dispatched: list[Event] = []

    def listen(self, event: Any, listener: Any) -> Any:
        return listener

    on = listen

    def forget(self, event: Any = None) -> None:
        self.dispatched.clear()

    async def dispatch_async(self, event: Any, **payload: Any) -> list[Any]:
        self._record(event, payload)
        return []

    def dispatch(self, event: Any, **payload: Any) -> list[Any]:
        self._record(event, payload)
        return []

    def _record(self, event: Any, payload: dict[str, Any]) -> None:
        if isinstance(event, Event):
            self.dispatched.append(event)
            return
        if isinstance(event, type) and issubclass(event, Event):
            self.dispatched.append(event(self._name(event), self.app, payload))
            return
        self.dispatched.append(Event(str(event), self.app, payload))

    def dispatched_names(self) -> list[str]:
        return [event.name for event in self.dispatched]

    def has_dispatched(self, event: Any) -> bool:
        name = self._name(event)
        return any(item.name == name for item in self.dispatched)

    def assert_dispatched(self, event: Any) -> None:
        if not self.has_dispatched(event):
            raise AssertionError(f"{self._name(event)!r} was not dispatched")

    def assert_not_dispatched(self, event: Any) -> None:
        if self.has_dispatched(event):
            raise AssertionError(f"{self._name(event)!r} was dispatched")

    @staticmethod
    def _name(event: Any) -> str:
        if isinstance(event, str):
            return event
        if isinstance(event, type) and issubclass(event, Event):
            return getattr(event, "name", event.__name__)
        return str(getattr(event, "name", event))


def fake_events(app: Any = None) -> FakeDispatcher:
    """Swap the current app's dispatcher for a recording fake and return it."""
    dispatcher = FakeDispatcher(app)
    if app is None:
        from agentkit.foundation.facade import get_current_app

        app = get_current_app()
    if app is not None:
        dispatcher.app = app
        app.events = dispatcher
    return dispatcher
