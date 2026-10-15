"""The agent-middleware contract — hooks across the model/tool lifecycle."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["AgentMiddleware"]


@runtime_checkable
class AgentMiddleware(Protocol):
    """Lifecycle hooks a middleware may implement (all optional)."""

    async def before_model(self, ctx: Any) -> None: ...

    async def after_model(self, ctx: Any, response: Any) -> Any: ...

    async def before_tool(self, ctx: Any, name: str, args: Any) -> Any: ...

    async def after_tool(self, ctx: Any, name: str, result: Any) -> Any: ...

    async def wrap_model_call(self, ctx: Any, call_next: Any) -> Any: ...

    async def wrap_tool_call(self, ctx: Any, name: str, call_next: Any) -> Any: ...
