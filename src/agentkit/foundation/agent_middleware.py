"""Model/tool-level agent middleware (beyond turn middleware).

Turn middleware (:mod:`agentkit.foundation.pipeline`) wraps a whole turn. This
module wraps the model and tool calls inside a turn: ``before_model``/
``after_model``, ``before_tool``/``after_tool``, and the ``wrap_*_call`` hooks
that may short-circuit by not calling ``call_next``.

    class Cache(Middleware):
        async def wrap_tool_call(self, ctx, name, call_next):
            ...
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.capabilities import Hooks

from agentkit.contracts.middleware import AgentMiddleware
from agentkit.logging import get_logger
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import AgentMiddlewareDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "AgentCallContext",
    "AgentMiddleware",
    "AgentMiddlewareCapability",
    "AgentMiddlewareManager",
    "BaseAgentMiddleware",
    "LoggingMiddleware",
    "NoopMiddleware",
    "agent_middleware_hooks",
]


@dataclass
class AgentCallContext:
    """The context handed to agent-middleware hooks.

    Wraps the PydanticAI ``RunContext`` (as ``run``) plus, for model hooks, the
    request context, and for tool hooks the tool definition. ``state`` is a scratch
    dict shared across a single model/tool call, so a ``wrap_*`` hook can enrich
    what a later ``after_*`` hook observes.
    """

    run: Any = None
    request: Any = None
    tool: Any = None
    name: str | None = None
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def deps(self) -> Any:
        """The run's deps (``RunContext.deps``), if available."""
        return getattr(self.run, "deps", None)


async def _maybe(value: Any) -> Any:
    """Await ``value`` when it is awaitable, else return it unchanged."""
    if inspect.isawaitable(value):
        return await value
    return value


def _get(middleware: Any, hook: str) -> Any:
    function = getattr(middleware, hook, None)
    return function if callable(function) else None


class AgentMiddlewareCapability:
    """Adapts :class:`AgentMiddleware` objects onto PydanticAI model/tool hooks.

    Composition order is the list order: ``before_*`` hooks run forwards,
    ``after_*`` hooks run in reverse, and ``wrap_*_call`` hooks nest so the first
    middleware is outermost. A ``wrap_*`` hook short-circuits by not calling
    ``call_next``; a ``before_tool`` hook denies by raising.
    """

    def __init__(self, middleware: Sequence[Any] = ()) -> None:
        self.middleware: list[Any] = [item for item in middleware if item is not None]

    def hooks(self) -> Hooks:
        """A PydanticAI :class:`~pydantic_ai.capabilities.Hooks` capability."""
        hooks = Hooks()
        entries = self.middleware

        @hooks.on.model_request
        async def _wrap_model(ctx: Any, *, request_context: Any, handler: Any) -> Any:
            call = AgentCallContext(run=ctx, request=request_context)
            for middleware in entries:
                before = _get(middleware, "before_model")
                if before is not None:
                    await _maybe(before(call))
            request_context = call.request

            async def core() -> Any:
                return await handler(call.request)

            chain = core
            for middleware in reversed(entries):
                wrap = _get(middleware, "wrap_model_call")
                if wrap is not None:
                    chain = _model_link(wrap, call, chain)
            response = await chain()
            for middleware in reversed(entries):
                after = _get(middleware, "after_model")
                if after is not None:
                    replaced = await _maybe(after(call, response))
                    if replaced is not None:
                        response = replaced
            return response

        @hooks.on.tool_execute
        async def _wrap_tool(
            ctx: Any, *, call: Any, tool_def: Any, args: Any, handler: Any
        ) -> Any:
            name = getattr(tool_def, "name", None) or getattr(call, "tool_name", "") or ""
            call_ctx = AgentCallContext(run=ctx, tool=tool_def, name=name)
            for middleware in entries:
                before = _get(middleware, "before_tool")
                if before is not None:
                    replaced = await _maybe(before(call_ctx, name, args))
                    if replaced is not None:
                        args = replaced

            async def core() -> Any:
                return await handler(args)

            chain = core
            for middleware in reversed(entries):
                wrap = _get(middleware, "wrap_tool_call")
                if wrap is not None:
                    chain = _tool_link(wrap, call_ctx, name, chain)
            result = await chain()
            for middleware in reversed(entries):
                after = _get(middleware, "after_tool")
                if after is not None:
                    replaced = await _maybe(after(call_ctx, name, result))
                    if replaced is not None:
                        result = replaced
            return result

        return hooks


def _model_link(wrap: Any, ctx: AgentCallContext, next_call: Any) -> Any:
    async def link() -> Any:
        return await wrap(ctx, next_call)

    return link


def _tool_link(wrap: Any, ctx: AgentCallContext, name: str, next_call: Any) -> Any:
    async def link() -> Any:
        return await wrap(ctx, name, next_call)

    return link


def agent_middleware_hooks(middleware: Sequence[Any] = ()) -> Hooks:
    """Convenience: a PydanticAI ``Hooks`` capability for the given middleware."""
    return AgentMiddlewareCapability(middleware).hooks()


class BaseAgentMiddleware:
    """A no-op base implementing every optional hook; subclass and override."""

    async def before_model(self, ctx: Any) -> None:
        return None

    async def after_model(self, ctx: Any, response: Any) -> Any:
        return response

    async def before_tool(self, ctx: Any, name: str, args: Any) -> Any:
        return args

    async def after_tool(self, ctx: Any, name: str, result: Any) -> Any:
        return result

    async def wrap_model_call(self, ctx: Any, call_next: Any) -> Any:
        return await call_next()

    async def wrap_tool_call(self, ctx: Any, name: str, call_next: Any) -> Any:
        return await call_next()


class NoopMiddleware(BaseAgentMiddleware):
    """The default middleware: every hook is a pass-through."""


class LoggingMiddleware(BaseAgentMiddleware):
    """Log model and tool calls at debug level."""

    def __init__(self, name: str = "agentkit.middleware") -> None:
        self.log = get_logger(name)

    async def before_model(self, ctx: Any) -> None:
        self.log.debug("model call starting")

    async def before_tool(self, ctx: Any, name: str, args: Any) -> Any:
        self.log.debug("tool call: %s", name)
        return args

    async def after_tool(self, ctx: Any, name: str, result: Any) -> Any:
        self.log.debug("tool result: %s", name)
        return result


class AgentMiddlewareManager(Manager):
    """Resolves the configured agent middleware (``agent_middleware_driver``, default ``noop``)."""

    kind = DriverKind.AGENT_MIDDLEWARE
    default_driver = AgentMiddlewareDriver.NOOP


@register_driver(DriverKind.AGENT_MIDDLEWARE, AgentMiddlewareDriver.NOOP)
class NoopMiddlewareDriver(Driver):
    def build(self) -> NoopMiddleware:
        return NoopMiddleware()
@register_driver(DriverKind.AGENT_MIDDLEWARE, AgentMiddlewareDriver.LOGGING)
class LoggingMiddlewareDriver(Driver):
    def build(self) -> LoggingMiddleware:
        return LoggingMiddleware()
