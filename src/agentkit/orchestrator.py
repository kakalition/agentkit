"""Orchestrator + specialist delegation.

PydanticAI v2 removed ``Agent.as_tool``; the supported core pattern is a tool
that calls ``specialist.run(...)`` and forwards ``deps``/``usage``/``model``.
:class:`Orchestrator` builds those delegation tools for you.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from agentkit.deps import Deps


async def delegate(
    ctx: RunContext[Deps], specialist: Agent[Any, str], request: str
) -> str:
    """Run a specialist agent and return its reply."""
    result = await specialist.run(
        request, deps=ctx.deps, usage=ctx.usage, model=ctx.deps.model
    )
    return result.output


def make_delegate(specialist: Agent[Any, str], *, tool_name: str, description: str):
    """Create a delegation tool function for ``specialist``.

    The returned function carries the right ``RunContext[Deps]`` annotation so
    PydanticAI treats it as a typed tool.
    """

    async def tool(ctx: RunContext[Deps], request: str) -> str:
        return await delegate(ctx, specialist, request)

    tool.__name__ = tool_name
    tool.__doc__ = description
    return tool


class Orchestrator:
    """An agent that routes requests to registered specialists."""

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        deps_type: type = Deps,
        output_type: Any = str,
        model: Any = None,
        capabilities: list[Any] | None = None,
    ) -> None:
        self.agent: Agent[Any, str] = Agent(
            name=name,
            deps_type=deps_type,
            output_type=output_type,
            instructions=instructions,
            model=model,
            capabilities=capabilities or [],
        )

    def add_specialist(
        self, specialist: Agent[Any, str], *, tool_name: str, description: str
    ) -> Orchestrator:
        """Register a specialist as a delegation tool on the orchestrator."""
        self.agent.tool(make_delegate(specialist, tool_name=tool_name, description=description))
        return self

    def tool(self, function: Any) -> Orchestrator:
        """Register a plain tool on the orchestrator."""
        self.agent.tool(function)
        return self
