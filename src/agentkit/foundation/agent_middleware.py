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

from typing import Any

from agentkit.contracts.middleware import AgentMiddleware
from agentkit.logging import get_logger
from agentkit.support import register_driver
from agentkit.support.kinds import AgentMiddlewareDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "AgentMiddleware",
    "BaseAgentMiddleware",
    "AgentMiddlewareManager",
    "LoggingMiddleware",
    "NoopMiddleware",
]


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
def _noop_middleware_driver(app: Any) -> NoopMiddleware:
    return NoopMiddleware()


@register_driver(DriverKind.AGENT_MIDDLEWARE, AgentMiddlewareDriver.LOGGING)
def _logging_middleware_driver(app: Any) -> LoggingMiddleware:
    return LoggingMiddleware()
