"""Agent-to-agent tools: message peers, broadcast, list, and hand off.

``AgentsCapability(registry, mailbox)`` registers ``send_to``, ``ask_agent``,
``broadcast``, ``list_agents`` (and ``handoff_to`` when enabled) plus a roster in
the instructions, so an agent can talk to its peers from the model loop.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from agentkit.capability import Capability
from agentkit.deps import Deps

__all__ = ["AgentsCapability", "mailbox_tools"]

AGENTS_GUIDE = (
    "You can talk to other agents. Use `list_agents` to see who is available, "
    "`ask_agent` for a request/response, `send_to` for a fire-and-forget message, "
    "and `broadcast` to ask everyone. Use `handoff_to` to transfer the whole "
    "conversation to an agent when it should take over."
)


def mailbox_tools(mailbox: Any, registry: Any = None) -> list[Any]:
    registry = registry or mailbox.registry

    async def send_to(ctx: RunContext[Deps], agent: str, message: str) -> str:
        """Send a fire-and-forget message to another agent.

        Args:
            agent: The recipient agent name.
            message: The message body.
        """
        delivered = await mailbox.send(agent, message, sender=_self_name(ctx))
        return f"sent to {agent}" if delivered else f"could not deliver to {agent!r}"

    async def ask_agent(ctx: RunContext[Deps], agent: str, message: str) -> str:
        """Ask another agent a question and get its reply.

        Args:
            agent: The agent whose help you want.
            message: The request.
        """
        return await mailbox.ask(agent, message, ctx=ctx, sender=_self_name(ctx))

    async def broadcast(ctx: RunContext[Deps], message: str, agents: list[str] | None = None) -> str:
        """Ask several agents at once (default: everyone registered).

        Args:
            message: The request broadcast to peers.
            agents: Optional subset of agent names.
        """
        results = await mailbox.broadcast(message, to=agents, ctx=ctx, sender=_self_name(ctx))
        if not results:
            return "(no agents to broadcast to)"
        return "\n".join(f"{name}: {reply}" for name, reply in results.items())

    async def list_agents(ctx: RunContext[Deps]) -> str:
        """List the agents available to talk to."""
        return registry.roster() or "(no other agents registered)"

    return [send_to, ask_agent, broadcast, list_agents]


def _self_name(ctx: RunContext[Deps]) -> str | None:
    deps = getattr(ctx, "deps", None)
    return getattr(deps, "extras", {}).get("_agent_name") if deps is not None else None


class AgentsCapability(Capability):
    """Registers the peer tools (and roster) on a PydanticAI agent (idempotent)."""

    name = "agents"

    def __init__(
        self,
        registry: Any,
        mailbox: Any,
        *,
        include_handoff: bool = True,
        max_handoffs: int | None = None,
    ) -> None:
        self.registry = registry
        self.mailbox = mailbox
        self.include_handoff = include_handoff
        self.max_handoffs = max_handoffs

    def install(self, agent: Any) -> Any:
        registry = self.registry
        mailbox = self.mailbox
        include_handoff = self.include_handoff
        max_handoffs = self.max_handoffs

        if getattr(agent, "_agentkit_agents_attached", False):
            return agent

        for tool in mailbox_tools(mailbox, registry):
            agent.tool(tool)

        if include_handoff:
            from agentkit.agents.handoff import handoff_tool

            agent.tool(handoff_tool(registry, max_handoffs=max_handoffs))

        @agent.instructions
        def _agents_instructions(ctx: RunContext[Deps]) -> str:
            roster = registry.roster()
            return f"{AGENTS_GUIDE}\n\nAgents you can reach:\n{roster}" if roster else AGENTS_GUIDE

        agent._agentkit_agents_attached = True  # type: ignore[attr-defined]
        return agent
