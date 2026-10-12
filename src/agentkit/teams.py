"""Multi-agent: a supervisor over a roster, plus explicit sub-agent spawning.

    from agentkit.teams import Supervisor, spawn_tool

    supervisor = Supervisor({"writer": writer, "researcher": researcher})
    agent = supervisor.build()                  # an Agent that routes to the roster

    # or let any agent run sub-agents as tasks:
    tools = [spawn_tool({"researcher": researcher})]

``Supervisor`` exposes each roster member as a delegation tool (usage and model
are forwarded so token accounting stays correct). ``spawn_tool`` runs a named
sub-agent as an explicit, awaitable task.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps

__all__ = ["Supervisor", "spawn_tool", "team_tools"]

SUPERVISOR_INSTRUCTIONS = (
    "You are a supervisor. Route each request to the most appropriate specialist "
    "by calling its tool, then synthesize a final answer from their output. "
    "Available specialists:\n{roster}"
)


def _tool_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "agent"


class Supervisor:
    """Builds an agent that delegates to a named roster of specialists."""

    def __init__(
        self,
        agents: Mapping[str, Any],
        *,
        name: str = "supervisor",
        instructions: str | None = None,
        output_type: Any = str,
        model: Any = None,
    ) -> None:
        self.agents = dict(agents)
        self.name = name
        self.instructions = instructions
        self.output_type = output_type
        self.model = model

    def build(self) -> Any:
        from agentkit.foundation.agent import Agent as AgentBuilder

        roster = "\n".join(f"- {_tool_name(key)}: {key}" for key in self.agents)
        builder = (
            AgentBuilder.make(self.name, deps_type=Deps)
            .instructions(self.instructions or SUPERVISOR_INSTRUCTIONS.format(roster=roster))
            .orchestrate({_tool_name(key): (agent, f"Delegate to {key}") for key, agent in self.agents.items()})
            .output(self.output_type)
        )
        if self.model is not None:
            builder.model(self.model)
        return builder.build()


def spawn_tool(agents: Mapping[str, Any]) -> Any:
    """A ``spawn(agent, task)`` tool that runs a named sub-agent as a task.

    Usage and model are forwarded from the parent run.
    """
    roster = {_tool_name(key): (key, agent) for key, agent in agents.items()}

    async def spawn(ctx: RunContext[Deps], agent: str, task: str) -> str:
        """Run a sub-agent on a task and return its output.

        Args:
            agent: Which sub-agent to run.
            task: The task to hand it.
        """
        entry = roster.get(agent)
        if entry is None:
            return f"unknown agent {agent!r}; choose one of {', '.join(roster)}"
        _, sub = entry
        result = await sub.run(task, deps=ctx.deps, usage=ctx.usage, model=ctx.deps.model)
        output = getattr(result, "output", result)
        return output if isinstance(output, str) else str(output)

    return spawn


def team_tools(agents: Mapping[str, Any]) -> list[Any]:
    """Convenience: ``[spawn_tool(agents)]`` for use with ``.tools(...)``."""
    return [spawn_tool(agents)]


async def run_all_agents(agents: Mapping[str, Any], task: str, *, deps: Any = None, model: Any = None) -> dict[str, str]:
    """Run every agent in ``agents`` on ``task`` (sequentially) and collect outputs."""
    results: dict[str, str] = {}
    for name, agent in agents.items():
        outcome = agent.run(task, deps=deps, model=model)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        output = getattr(outcome, "output", outcome)
        results[name] = output if isinstance(output, str) else str(output)
    return results
