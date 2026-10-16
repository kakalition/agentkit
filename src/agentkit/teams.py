"""Multi-agent: a supervisor over a roster, plus explicit sub-agent spawning.

    from agentkit.teams import Supervisor, spawn_tool

    supervisor = Supervisor({"writer": writer, "researcher": researcher})
    agent = supervisor.build()                  # an Agent that routes to the roster

    # or let any agent run sub-agents as tasks:
    tools = [spawn_tool({"researcher": researcher})]

``Supervisor`` (now an alias of :class:`~agentkit.orchestrator.Orchestrator`) exposes
each roster member as a delegation tool. ``spawn_tool`` runs a named sub-agent as an
explicit, awaitable task. Usage and model are forwarded so token accounting stays
correct.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext

from agentkit.agents.registry import AgentRegistry
from agentkit.agents.speaker import ModeratorSpeaker
from agentkit.deps import Deps
from agentkit.orchestrator import ROUTER_INSTRUCTIONS, Supervisor, run_all_agents

__all__ = [
    "SUPERVISOR_INSTRUCTIONS",
    "Supervisor",
    "TEAMS",
    "TeamSpec",
    "build_team",
    "register_team",
    "resolve_team",
    "run_all_agents",
    "spawn_tool",
    "team_tool",
    "team_tools",
]

SUPERVISOR_INSTRUCTIONS = ROUTER_INSTRUCTIONS

TEAM_KINDS = ("groupchat", "supervisor", "managed")


@dataclass
class TeamSpec:
    """A named team: a roster of agents and the runner kind."""

    name: str
    roster: dict[str, Any] = field(default_factory=dict)
    kind: str = "groupchat"


TEAMS: dict[str, TeamSpec] = {}


def register_team(name: str, roster: Mapping[str, Any], *, kind: str = "groupchat") -> TeamSpec:
    """Register a named team (``groupchat`` | ``supervisor`` | ``managed``)."""
    if kind not in TEAM_KINDS:
        raise ValueError(f"unknown team kind {kind!r}; choose from {', '.join(TEAM_KINDS)}")
    spec = TeamSpec(name=name, roster=dict(roster), kind=kind)
    TEAMS[name] = spec
    return spec


def resolve_team(name: str) -> TeamSpec:
    """The registered team ``name`` (raises :class:`ValueError` when unknown)."""
    try:
        return TEAMS[name]
    except KeyError as exc:
        available = ", ".join(sorted(TEAMS)) or "(none)"
        raise ValueError(f"unknown team {name!r}; choose from {available}") from exc


def build_team(name: str, *, speaker: Any = None, max_turns: int = 12, max_rounds: int = 8) -> Any:
    """Build the runnable for a named team (a runner with ``run(task, ctx=...)``)."""
    spec = resolve_team(name)
    if spec.kind == "managed":
        from agentkit.agents.team import ManagedTeam

        return ManagedTeam(spec.roster, speaker=speaker, max_rounds=max_rounds)
    from agentkit.agents.groupchat import GroupChatRunner

    if spec.kind == "supervisor":
        roster = list(spec.roster)
        speaker = speaker or ModeratorSpeaker(roster[0] if roster else None)
    return GroupChatRunner(spec.roster, speaker=speaker, max_turns=max_turns)


def team_tool(name: str, *, speaker: Any = None, max_turns: int = 12) -> Any:
    """A namespaced ``team_<name>(prompt)`` tool that runs a registered team."""
    spec = resolve_team(name)
    tool_name = "team_" + _tool_name(spec.name)

    async def run_team(ctx: RunContext[Deps], prompt: str) -> str:
        """Run the team on a prompt and return its combined output.

        Args:
            prompt: The task to hand to the team.
        """
        runner = build_team(spec.name, speaker=speaker, max_turns=max_turns)
        result = await runner.run(prompt, ctx=ctx)
        return result.output

    run_team.__name__ = tool_name
    return run_team


def _tool_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "agent"


def spawn_tool(agents: Mapping[str, Any]) -> Any:
    """A ``spawn(agent, task)`` tool that runs a named sub-agent as a task.

    Usage and model are forwarded from the parent run.
    """
    registry = AgentRegistry()
    for key, agent in agents.items():
        registry.register_local(agent, name=key)

    async def spawn(ctx: RunContext[Deps], agent: str, task: str) -> str:
        """Run a sub-agent on a task and return its output.

        Args:
            agent: Which sub-agent to run.
            task: The task to hand it.
        """
        handle = registry.get(agent)
        if handle is None:
            return f"unknown agent {agent!r}; choose one of {', '.join(registry.names())}"
        output = await handle.invoke(ctx, task)
        return output if isinstance(output, str) else str(output)

    return spawn


def team_tools(agents: Mapping[str, Any]) -> list[Any]:
    """Convenience: ``[spawn_tool(agents)]`` for use with ``.tools(...)``."""
    return [spawn_tool(agents)]
