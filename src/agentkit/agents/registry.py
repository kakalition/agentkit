"""A discoverable registry of agents (local handles + remote A2A peers).

    registry = AgentRegistry()
    registry.register(AgentHandle.local(agent, capabilities=["search"]))
    registry.resolve("search").name  # -> the first capable agent

Populated at boot from local agents (specialists, supervisor rosters, an app's
primary agent) and from configured A2A peers, so "which agents exist and what
can they do" is first-class.
"""

from __future__ import annotations

import builtins
import threading
from collections.abc import Iterable
from typing import Any

from agentkit.agents.handle import AgentHandle

__all__ = ["AgentRegistry"]


class AgentRegistry:
    """Name → :class:`AgentHandle`, with capability-based resolution."""

    def __init__(self, handles: Iterable[AgentHandle] | None = None) -> None:
        self._handles: dict[str, AgentHandle] = {}
        self._lock = threading.RLock()
        for handle in handles or []:
            self.register(handle)

    # -- mutation -------------------------------------------------------
    def register(self, handle: AgentHandle) -> AgentHandle:
        with self._lock:
            self._handles[handle.name] = handle
        return handle

    def register_local(self, agent: Any, **options: Any) -> AgentHandle:
        return self.register(AgentHandle.local(agent, **options))

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._handles.pop(name, None) is not None

    # -- reads ----------------------------------------------------------
    def get(self, name: str) -> AgentHandle | None:
        return self._handles.get(name)

    def list(self) -> builtins.list[AgentHandle]:
        return [self._handles[key] for key in sorted(self._handles)]

    def names(self) -> builtins.list[str]:
        return sorted(self._handles)

    def resolve(self, query: str) -> AgentHandle | None:
        """The first handle matching ``query`` by name or capability."""
        direct = self._handles.get(query)
        if direct is not None:
            return direct
        for name in sorted(self._handles):
            handle = self._handles[name]
            if handle.matches(query):
                return handle
        return None

    def capable(self, capability: str) -> builtins.list[AgentHandle]:
        return [handle for handle in self.list() if handle.matches(capability)]

    def roster(self) -> str:
        """A compact ``- name: description`` listing for instructions."""
        lines = [f"- {h.name}: {h.description}".rstrip(": ") for h in self.list()]
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._handles)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._handles
