"""Lifecycle event bus.

Listeners are called with an :class:`Event` whose payload keys are exposed as
attributes, so a listener can be written naturally::

    app.on("turn.end", lambda ctx: audit.append(ctx.conversation_id))

Free-form keys are registered on the name; the special ``"*"`` name receives
every event. Both synchronous and asynchronous listeners are supported via
:meth:`Dispatcher.dispatch` and :meth:`Dispatcher.dispatch_async` respectively.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Listener = Callable[["Event"], Any]


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


class Dispatcher:
    """Register and fire lifecycle listeners."""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self._listeners: dict[str, list[Listener]] = {}

    def listen(self, event: str, listener: Listener) -> Listener:
        self._listeners.setdefault(event, []).append(listener)
        return listener

    def on(self, event: str, listener: Listener) -> Listener:
        return self.listen(event, listener)

    def listeners(self, event: str) -> list[Listener]:
        return [*self._listeners.get(event, []), *self._listeners.get("*", [])]

    def forget(self, event: str | None = None) -> None:
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(event, None)

    def _event(self, event: str | Event, payload: dict[str, Any]) -> Event:
        if isinstance(event, Event):
            if event.app is None:
                event.app = self.app
            return event
        return Event(event, self.app, payload)

    def dispatch(self, event: str | Event, **payload: Any) -> list[Any]:
        ev = self._event(event, payload)
        results: list[Any] = []
        for listener in self.listeners(ev.name):
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

    async def dispatch_async(self, event: str | Event, **payload: Any) -> list[Any]:
        ev = self._event(event, payload)
        results: list[Any] = []
        for listener in self.listeners(ev.name):
            result = listener(ev)
            if inspect.isawaitable(result):
                result = await result
            results.append(result)
        return results


__all__ = ["Dispatcher", "Event", "Listener"]
