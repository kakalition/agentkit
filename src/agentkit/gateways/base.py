"""Shared base for chat gateways (Telegram, Slack, Email, Discord, …).

A :class:`Gateway` owns the concerns every bot shares — the allow-list, the
external-id → conversation-id mapping, running a turn through ``app.answer``,
resolving tool approvals, and a :class:`~agentkit.supervise.Service` factory — so
each concrete channel only implements its transport (``start``, ``send``,
``prompt_approval``).
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import Sequence
from typing import Any, ClassVar

from agentkit.deps import ApprovalRequest

__all__ = ["Gateway", "GatewayError"]

APPROVAL_TIMEOUT = 300.0


class GatewayError(RuntimeError):
    pass


class Gateway(abc.ABC):
    """Base class for chat channels."""

    name: ClassVar[str] = "gateway"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        allowed_channel_ids: Sequence[Any] | None = None,
        timeout: float = APPROVAL_TIMEOUT,
        status_interval_s: float = 2.5,
        typing_interval_s: float = 4.0,
        pairing: Any = None,
    ) -> None:
        self.app = app
        self.settings = settings if settings is not None else getattr(app, "settings", None)
        self.allowed = list(allowed_channel_ids or [])
        self.pairing = pairing
        self.timeout = timeout
        self.status_interval_s = status_interval_s
        self.typing_interval_s = typing_interval_s
        self._conversations: dict[str, str] = {}
        self._pending: dict[str, asyncio.Future[bool]] = {}

    # -- identity -------------------------------------------------------
    def is_allowed(self, external_id: Any) -> bool:
        """Whether ``external_id`` may talk to the bot.

        With an allow-list, only listed ids pass. With no allow-list, everyone
        passes *unless* pairing is enabled, in which case only paired users pass.
        """
        if self.allowed:
            return external_id in self.allowed
        if self.pairing is not None:
            return bool(self.pairing.is_paired(external_id))
        return True

    def pair(self, external_id: Any, *, code: str | None = None) -> str:
        """Issue (and optionally send) a pairing code for ``external_id``."""
        if self.pairing is None:
            from agentkit.gateways.pairing import PairingRegistry

            self.pairing = PairingRegistry()
        return self.pairing.request(external_id, code=code)

    def confirm_pairing(self, external_id: Any, code: str) -> bool:
        """Confirm a pairing code, admitting ``external_id`` on success."""
        return self.pairing is not None and bool(self.pairing.confirm(external_id, code))

    def conversation_id(self, external_id: Any) -> str:
        """Stable conversation id for an external chat/thread (memoized)."""
        key = str(external_id)
        if key not in self._conversations:
            self._conversations[key] = self.make_conversation_id(key)
        return self._conversations[key]

    def make_conversation_id(self, key: str) -> str:
        return f"{self.name}:{key}"

    # -- turns ----------------------------------------------------------
    async def run_turn(self, external_id: Any, text: str, *, approve: Any = None) -> Any:
        """Run one turn for ``external_id`` through ``app.answer`` (``None`` if blocked)."""
        if not self.is_allowed(external_id):
            return None
        if self.app is None:
            raise GatewayError("gateway has no app to run turns against")
        return await self.app.answer(self.conversation_id(external_id), text)

    async def stream_turn(self, external_id: Any, text: str, *, approve: Any = None) -> Any:
        """Yield :class:`~agentkit.session.StreamEvent` increments for one turn."""
        if not self.is_allowed(external_id):
            return
        if self.app is None:
            raise GatewayError("gateway has no app to stream turns against")
        async for event in self.app.stream(
            text, conversation_id=self.conversation_id(external_id), approve=approve
        ):
            yield event

    # -- approvals ------------------------------------------------------
    async def ask_approval(
        self, external_id: Any, requests: list[ApprovalRequest]
    ) -> dict[str, bool]:
        """Ask the user to approve/deny each request; unapproved on timeout."""
        loop = asyncio.get_running_loop()
        futures: dict[str, asyncio.Future[bool]] = {}
        for request in requests:
            future: asyncio.Future[bool] = loop.create_future()
            self._pending[request.tool_call_id] = future
            futures[request.tool_call_id] = future
            await self.prompt_approval(external_id, request)
        decisions: dict[str, bool] = {}
        for call_id, future in futures.items():
            try:
                decisions[call_id] = await asyncio.wait_for(future, timeout=self.timeout)
            except TimeoutError:
                decisions[call_id] = False
        return decisions

    async def prompt_approval(self, external_id: Any, request: ApprovalRequest) -> None:
        """Render an approval prompt (default: send text; channels may add buttons)."""
        await self.send(
            self.conversation_id(external_id),
            f"Approve `{request.tool_name}`?\n{request.args}",
        )

    def resolve_approval(self, tool_call_id: str, value: bool) -> bool:
        future = self._pending.pop(tool_call_id, None)
        if future is not None and not future.done():
            future.set_result(value)
            return True
        return False

    # -- transport ------------------------------------------------------
    @abc.abstractmethod
    async def start(self) -> None:
        """Begin serving (long-poll / listen / poll loop). Blocks until stopped."""

    @abc.abstractmethod
    async def send(self, conversation_id: str, text: str) -> None:
        """Deliver ``text`` to the conversation (markdown-safe)."""

    async def reply(self, external_id: Any, text: str) -> None:
        await self.send(self.conversation_id(external_id), text)

    def service(self) -> Any:
        """A :class:`~agentkit.supervise.Service` that runs :meth:`start`."""
        from agentkit.supervise import Service

        gateway = self

        def run() -> None:
            asyncio.run(gateway.start())

        return Service(name=self.name, run=run)
