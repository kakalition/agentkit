from __future__ import annotations

from pydantic_ai import FunctionToolset, RunContext

from agentkit import cached_tool
from agentkit.deps import Deps
from agentkit.foundation.agent import Agent


async def test_cached_tool_caches_by_arguments():
    calls: list[int] = []

    async def slow(ctx: RunContext[Deps], value: int) -> int:
        """Compute."""
        calls.append(value)
        return value * 2

    cached = cached_tool(slow, ttl=60)
    assert await cached(None, 2) == 4
    assert await cached(None, 2) == 4
    assert calls == [2]
    assert await cached(None, 3) == 6
    assert calls == [2, 3]
    cached.cache_clear()


def test_builder_tool_options_and_toolset_build():
    async def tool(ctx: RunContext[Deps], value: str) -> str:
        """Do a thing."""
        return value

    def extra(ctx: RunContext[Deps], q: str) -> str:
        """Extra."""
        return q

    toolset = FunctionToolset(tools=[extra])
    agent = (
        Agent.make("tools")
        .instructions("x")
        .tool(tool, timeout=5.0, sequential=True, defer_loading=True, retries=2)
        .toolset(toolset)
        .output(str)
        .build()
    )
    assert "tool" in set(agent._function_toolset.tools.keys())


async def test_builder_cache_ttl_wraps_tool():
    calls: list[str] = []

    async def lookup(ctx: RunContext[Deps], query: str) -> str:
        """Look up."""
        calls.append(query)
        return "hit"

    agent = Agent.make("c").instructions("x").tool(lookup, cache_ttl=60).output(str).build()
    assert "lookup" in set(agent._function_toolset.tools.keys())
