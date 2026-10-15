"""First-class agent communication: registry, handles, mailbox, handoff."""

from agentkit.agents.handle import AgentHandle
from agentkit.agents.handoff import DEFAULT_MAX_HANDOFFS, handoff, handoff_tool
from agentkit.agents.mailbox import Mailbox
from agentkit.agents.registry import AgentRegistry
from agentkit.agents.tools import attach_agents, mailbox_tools

__all__ = [
    "AgentHandle",
    "AgentRegistry",
    "Mailbox",
    "DEFAULT_MAX_HANDOFFS",
    "attach_agents",
    "handoff",
    "handoff_tool",
    "mailbox_tools",
]
