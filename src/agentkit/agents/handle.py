"""A uniform handle over a local agent or a remote A2A peer.

One :class:`AgentHandle` type wraps both so callers (orchestrators, the mailbox,
handoff) never branch on local-vs-remote::

    handle = AgentHandle.local(agent, name="researcher", capabilities=["search"])
    reply = await handle.invoke(ctx, "find the docs")
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["AgentHandle"]


@dataclass
class AgentHandle:
    """Identity + invocation for one agent (local agent or remote A2A peer)."""

    name: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    agent: Any = None
    url: str | None = None
    client: Any = None
    is_remote: bool = False

    # -- construction ---------------------------------------------------
    @classmethod
    def local(
        cls,
        agent: Any,
        *,
        name: str | None = None,
        description: str = "",
        capabilities: Sequence[str] = (),
    ) -> AgentHandle:
        resolved_name = name or getattr(agent, "name", None) or "agent"
        resolved_description = description or getattr(agent, "description", None) or ""
        return cls(
            name=resolved_name,
            description=resolved_description or "",
            capabilities=list(capabilities),
            agent=agent,
        )

    @classmethod
    def remote(
        cls,
        name: str,
        url: str,
        *,
        client: Any = None,
        description: str = "",
        capabilities: Sequence[str] = (),
    ) -> AgentHandle:
        return cls(
            name=name,
            description=description,
            capabilities=list(capabilities),
            url=url,
            client=client,
            is_remote=True,
        )

    # -- matching -------------------------------------------------------
    def matches(self, query: str) -> bool:
        """Whether ``query`` names this agent or one of its capabilities/skills."""
        needle = (query or "").strip().lower()
        if not needle:
            return False
        haystack = {self.name.lower(), *[cap.lower() for cap in self.capabilities]}
        if self.description:
            haystack.add(self.description.lower())
        return any(needle == item or needle in item for item in haystack)

    # -- invocation -----------------------------------------------------
    async def invoke(self, ctx: Any = None, task: str = "") -> str:
        """Run the agent on ``task`` and return its text output."""
        if self.is_remote:
            return await self._invoke_remote(task)
        return await self._invoke_local(ctx, task)

    async def _invoke_remote(self, task: str) -> str:
        if self.client is None or not self.url:
            return f"(remote agent {self.name!r} is not configured)"
        return await self.client.call_agent(self.url, task)

    async def _invoke_local(self, ctx: Any, task: str) -> str:
        agent = self.agent
        if agent is None:
            return f"(agent {self.name!r} has no implementation)"
        runnable = agent
        if not hasattr(runnable, "run") and hasattr(runnable, "build"):
            runnable = runnable.build()
        deps = getattr(ctx, "deps", None)
        usage = getattr(ctx, "usage", None)
        model = getattr(deps, "model", None)
        result = await runnable.run(task, deps=deps, usage=usage, model=model)
        output = getattr(result, "output", result)
        return output if isinstance(output, str) else str(output)
