"""An in-process (or durable) message bus between agents.

    mailbox = Mailbox(registry, events=app.events)
    await mailbox.send("researcher", "look this up")     # fire-and-forget
    reply = await mailbox.ask("researcher", "what is X?")  # request/response
    await mailbox.broadcast("standup in 5", to=["a", "b"])

In-process delivery is default: a subscribed agent receives messages on its own
queue, and ``ask`` invokes the target handle and returns its reply. ``durable``
mode spools messages for at-least-once delivery: the default spool is in-process
(:class:`MemorySpool`), and ``spool=RepositoryMailboxSpool(app)`` persists them to
the database so they survive a restart and are visible across processes. Remote
handles always go over A2A (via the handle).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from agentkit.agents.registry import AgentRegistry

__all__ = ["Mailbox", "MemorySpool", "RepositoryMailboxSpool", "default_spool"]

Handler = Callable[[str], Awaitable[None]]
DEFAULT_MAX_CONCURRENCY = 8


class MemorySpool:
    """An in-process durable spool for at-least-once delivery.

    Share one spool between ``Mailbox`` instances to survive a restart: a message
    sent by one is drained by ``receive`` on another. For cross-process durability
    use :class:`RepositoryMailboxSpool`, which spools to the database.
    """

    def __init__(self) -> None:
        self._rows: dict[str, list[dict[str, Any]]] = {}

    async def append(self, to: str, message: str, *, sender: str | None = None) -> None:
        self._rows.setdefault(to, []).append({"to": to, "message": message, "sender": sender})

    async def drain(self, to: str) -> list[dict[str, Any]]:
        return self._rows.pop(to, [])

    async def peek(self, to: str) -> list[dict[str, Any]]:
        return list(self._rows.get(to, []))


class RepositoryMailboxSpool:
    """A repository-backed spool: at-least-once delivery across processes.

    Opens a fresh repositories session per operation (mirroring
    ``RepositoryWorkingMemory``), so a message appended by one process is drained
    by ``receive`` on another.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def append(self, to: str, message: str, *, sender: str | None = None) -> None:
        async with self.app.repositories() as repos:
            await repos.mailbox.append(to, message, sender)

    async def drain(self, to: str) -> list[dict[str, Any]]:
        async with self.app.repositories() as repos:
            messages = await repos.mailbox.drain(to)
        return [{"to": to, "message": message} for message in messages]

    async def peek(self, to: str) -> list[dict[str, Any]]:
        async with self.app.repositories() as repos:
            messages = await repos.mailbox.peek(to)
        return [{"to": to, "message": message} for message in messages]


_DEFAULT_SPOOL: MemorySpool | None = None


def default_spool() -> MemorySpool:
    """A process-wide spool used when a durable mailbox has no explicit one."""
    global _DEFAULT_SPOOL
    if _DEFAULT_SPOOL is None:
        _DEFAULT_SPOOL = MemorySpool()
    return _DEFAULT_SPOOL


class Mailbox:
    """Name-addressed message bus over an :class:`AgentRegistry`."""

    def __init__(
        self,
        registry: AgentRegistry,
        *,
        durable: bool = False,
        events: Any = None,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        spool: MemorySpool | RepositoryMailboxSpool | None = None,
    ) -> None:
        self.registry = registry
        self.durable = durable
        self.events = events
        self.spool = spool if spool is not None else (default_spool() if durable else None)
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
        """The next message for ``name``: in-process inbox first, then the spool."""
        inbox = self._inboxes.get(name)
        if inbox is not None and not inbox.empty():
            return await inbox.get()
        if self.durable and self.spool is not None:
            rows = await self.spool.drain(name)
            if rows:
                return str(rows[0]["message"])
        return await self._inbox(name).get()

    async def replay(self, name: str) -> list[str]:
        """Spooled (undrained) messages for ``name`` (at-least-once inspection)."""
        if not self.durable or self.spool is None:
            return []
        return [str(row["message"]) for row in await self.spool.peek(name)]

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
        if self.spool is not None:
            with contextlib.suppress(Exception):
                await self.spool.append(to, message, sender=sender)
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
