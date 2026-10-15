"""An in-process (or durable) message bus between agents.

    mailbox = Mailbox(registry, events=app.events)
    await mailbox.send("researcher", "look this up")     # fire-and-forget
    reply = await mailbox.ask("researcher", "what is X?")  # request/response
    await mailbox.broadcast("standup in 5", to=["a", "b"])

In-process delivery is default: a subscribed agent receives messages on its own
queue, and ``ask`` invokes the target handle and returns its reply. ``durable``
mode persists messages through DBOS ``send``/``recv`` so they survive a restart.
Remote handles always go over A2A (via the handle).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from agentkit.agents.registry import AgentRegistry

__all__ = ["Mailbox"]

Handler = Callable[[str], Awaitable[None]]
DEFAULT_MAX_CONCURRENCY = 8


class Mailbox:
    """Name-addressed message bus over an :class:`AgentRegistry`."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        durable: bool = False,
        events: Any = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self.registry = registry
        self.durable = durable
        self.events = events
        self._inboxes: dict[str, asyncio.Queue[str]] = {}
        self._subscribers: dict[str, Handler] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    # -- subscription ---------------------------------------------------
    def subscribe(self, name: str, handler: Handler) -> None:
        self._subscribers[name] = handler

    def unsubscribe(self, name: str) -> None:
        self._subscribers.pop(name, None)

    async def receive(self, name: str) -> str:
        return await self._inbox(name).get()

    def _inbox(self, name: str) -> asyncio.Queue[str]:
        inbox = self._inboxes.get(name)
        if inbox is None:
            inbox = asyncio.Queue()
            self._inboxes[name] = inbox
        return inbox

    # -- send -----------------------------------------------------------
    async def send(
        self, to: str, message: str, *, sender: str | None = None
    ) -> bool:
        """Fire-and-forget delivery to ``to``'s inbox (and subscriber)."""
        if self.registry.get(to) is None and to not in self._subscribers:
            await self._emit_error(to, f"no such agent {to!r}")
            return False
        async with self._lock:
            self._inbox(to).put_nowait(message)
        if self.durable:
            await self._durable_send(to, message, sender)
        handler = self._subscribers.get(to)
        if handler is not None:
            asyncio.ensure_future(handler(message))
        await self._emit("agent.message", to=to, sender=sender, message=message, kind="send")
        return True

    async def ask(
        self,
        to: str,
        message: str,
        *,
        ctx: Any = None,
        sender: str | None = None,
    ) -> str:
        """Request/response: invoke ``to`` and return its reply (never raises)."""
        handle = self.registry.get(to)
        if handle is None:
            await self._emit_error(to, f"no such agent {to!r}")
            return f"no such agent {to!r}; known: {', '.join(self.registry.names()) or '(none)'}"
        try:
            update_ctx = _with_sender(ctx, sender)
            reply = await handle.invoke(update_ctx, message)
        except Exception as exc:  # a peer failure must not break the caller's loop
            await self._emit_error(to, str(exc))
            return f"agent {to!r} failed: {exc}"
        await self._emit("agent.message", to=to, sender=sender, message=message, kind="ask")
        return reply

    async def broadcast(
        self,
        message: str,
        *,
        to: Iterable[str] | None = None,
        ctx: Any = None,
        sender: str | None = None,
    ) -> dict[str, str]:
        """Ask everyone in ``to`` (default: the whole registry) concurrently."""
        targets = list(to) if to is not None else self.registry.names()
        await self._emit("agent.message", to=list(targets), sender=sender, message=message, kind="broadcast")

        async def one(name: str) -> tuple[str, str]:
            async with self._semaphore:
                return name, await self.ask(name, message, ctx=ctx, sender=sender)

        results = await asyncio.gather(*(one(name) for name in targets))
        return dict(results)

    # -- durable mode ---------------------------------------------------
    async def _durable_send(self, to: str, message: str, sender: str | None) -> None:
        try:  # pragma: no cover - depends on DBOS being initialised
            from agentkit import durability

            durability.DBOS.send(to, {"to": to, "sender": sender, "message": message}, topic=to)
        except Exception:
            # DBOS not initialised (or unsupported): stays in-process.
            pass

    # -- events ---------------------------------------------------------
    async def _emit(self, name: str, **payload: Any) -> None:
        if self.events is None:
            return
        dispatch = getattr(self.events, "dispatch_async", None)
        if dispatch is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - observer must not break delivery
            await dispatch(name, **payload)

    async def _emit_error(self, to: str, error: str) -> None:
        await self._emit("agent.error", agent=to, error=error)


def _with_sender(ctx: Any, sender: str | None) -> Any:
    if ctx is None or sender is None:
        return ctx
    deps = getattr(ctx, "deps", None)
    if deps is None:
        return ctx
    comms = getattr(deps, "comms", None)
    if comms is not None:
        comms.sender = sender
    if hasattr(deps, "extras"):
        deps.extras.setdefault("_mailbox_sender", sender)
    return ctx
