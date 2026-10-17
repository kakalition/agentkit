"""Subagents: delegate a task to a child agent under a chosen context strategy.

    from agentkit.agents.subagent import subagent_tool

    tool = subagent_tool(registry)          # a ``task(subagent, prompt)`` tool
    agent.tool(tool)

The :class:`ContextStrategy` decides what the child sees:

* ``isolated`` (default) — the child runs with no inherited deps/history; pass a
  self-contained brief.
* ``shared`` — the child reuses the parent's context (deps, conversation, model).
* ``summarized`` — like isolated, but the tool labels the prompt as a summary.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from agentkit.contracts.subagent import ContextStrategy
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import ContextDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "ContextManager",
    "ContextStrategy",
    "IsolatedContext",
    "SharedContext",
    "SummarizedContext",
    "subagent_tool",
]


class IsolatedContext:
    """The default: the child inherits nothing and must be given a full brief."""

    def context(self, ctx: Any, task: str) -> Any:
        return None


class SharedContext:
    """The child reuses the parent's context (deps + conversation)."""

    def context(self, ctx: Any, task: str) -> Any:
        return ctx


class SummarizedContext:
    """The child is isolated; the tool frames the prompt as a focused summary."""

    def context(self, ctx: Any, task: str) -> Any:
        return None

    def prompt(self, task: str) -> str:
        return f"Summary of prior context:\n{task}"


class ContextManager(Manager):
    """Resolves the configured subagent context strategy (``context_driver``, default ``isolated``)."""

    kind = DriverKind.CONTEXT
    default_driver = ContextDriver.ISOLATED


@register_driver(DriverKind.CONTEXT, ContextDriver.ISOLATED)
class IsolatedContextDriver(Driver):
    def build(self) -> IsolatedContext:
        return IsolatedContext()
@register_driver(DriverKind.CONTEXT, ContextDriver.SHARED)
class SharedContextDriver(Driver):
    def build(self) -> SharedContext:
        return SharedContext()
@register_driver(DriverKind.CONTEXT, ContextDriver.SUMMARIZED)
class SummarizedContextDriver(Driver):
    def build(self) -> SummarizedContext:
        return SummarizedContext()
def subagent_tool(registry: Any, *, strategy: Any = None) -> Any:
    """A ``task(subagent, prompt)`` tool backed by ``registry`` and a context strategy."""
    strategy = strategy or IsolatedContext()

    async def task(ctx: RunContext[Any], subagent: str, prompt: str) -> str:
        """Delegate a self-contained task to another agent and return its reply.

        Args:
            subagent: The name of the agent to delegate to.
            prompt: The task brief (self-contained when the child is isolated).
        """
        handle = registry.get(subagent)
        if handle is None:
            return f"no such agent {subagent!r}; known: {', '.join(registry.names()) or '(none)'}"
        child_ctx = strategy.context(ctx, prompt)
        text = strategy.prompt(prompt) if hasattr(strategy, "prompt") else prompt
        try:
            return await handle.invoke(child_ctx, text)
        except Exception as exc:  # a child failure must not break the caller
            return f"agent {subagent!r} failed: {exc}"

    return task
