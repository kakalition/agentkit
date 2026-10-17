"""Thread-scoped working memory: scratch key/value state an agent keeps per thread.

Unlike :mod:`agentkit.memory` (durable facts about the owner), working memory is
scoped to a *thread* (conversation): the agent can stash intermediate notes,
plans, or fetched values and read them back on later turns::

    agent = Agent.make("planner").working_memory().build()

Tools: ``memory_set`` / ``memory_get`` / ``memory_list`` / ``memory_forget``.
The default driver is in-process (``memory``); ``repository`` persists to the
``working_memory`` table.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from agentkit.capability import Capability
from agentkit.contracts.working_memory import WorkingMemory
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, WorkingMemoryDriver
from agentkit.support.manager import Manager

__all__ = [
    "InMemoryWorkingMemory",
    "RepositoryWorkingMemory",
    "WorkingMemory",
    "WorkingMemoryCapability",
    "WorkingMemoryManager",
]

WORKING_MEMORY_GUIDE = (
    "You have thread-scoped working memory: use `memory_set`/`memory_get` to stash "
    "and recall intermediate notes, plans, or values for this conversation, and "
    "`memory_list`/`memory_forget` to review or clear them. It is per-conversation "
    "scratch space, not durable facts about the user."
)


class InMemoryWorkingMemory:
    """An in-process working-memory store (the default driver)."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, str]] = {}

    async def set(self, namespace: str, key: str, value: Any) -> str:
        self._rows.setdefault(namespace, {})[key] = str(value)
        return str(value)

    async def get(self, namespace: str, key: str) -> str | None:
        return self._rows.get(namespace, {}).get(key)

    async def list(self, namespace: str) -> dict[str, str]:
        return dict(self._rows.get(namespace, {}))

    async def forget(self, namespace: str, key: str) -> bool:
        bucket = self._rows.get(namespace)
        if not bucket or key not in bucket:
            return False
        del bucket[key]
        return True

    async def clear(self, namespace: str) -> int:
        return len(self._rows.pop(namespace, {}))


class RepositoryWorkingMemory:
    """A repository-backed working-memory store (one session per call)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def set(self, namespace: str, key: str, value: Any) -> Any:
        async with self.app.repositories() as repos:
            return await repos.working_memory.set(namespace, key, value)

    async def get(self, namespace: str, key: str) -> str | None:
        async with self.app.repositories() as repos:
            return await repos.working_memory.get(namespace, key)

    async def list(self, namespace: str) -> dict[str, str]:
        async with self.app.repositories() as repos:
            return await repos.working_memory.list(namespace)

    async def forget(self, namespace: str, key: str) -> bool:
        async with self.app.repositories() as repos:
            return await repos.working_memory.forget(namespace, key)

    async def clear(self, namespace: str) -> int:
        async with self.app.repositories() as repos:
            return await repos.working_memory.clear(namespace)


def _namespace(deps: Any) -> str:
    extras = getattr(deps, "extras", None) or {}
    return str(extras.get("conversation_id") or getattr(deps, "conversation_id", None) or "default")


def _current_app() -> Any:
    try:
        from agentkit.foundation.facade import get_current_app

        return get_current_app()
    except Exception:  # pragma: no cover - defensive
        return None


def _store(deps: Any) -> Any:
    """The active working-memory store: the repository (live session) or the driver."""
    app = _current_app()
    settings = getattr(app, "settings", None) or getattr(deps, "settings", None)
    driver = str(getattr(settings, "working_memory_driver", "memory") or "memory")
    repo_store = getattr(getattr(deps, "repos", None), "working_memory", None)
    if driver == "repository" and repo_store is not None:
        return repo_store
    if app is not None:
        try:
            return app.manager("working_memory").driver()
        except Exception:  # pragma: no cover - defensive
            pass
    return repo_store


class WorkingMemoryCapability(Capability):
    """Registers the working-memory tools on a PydanticAI agent (idempotent)."""

    name = "working_memory"

    def install(self, agent: Agent[Any, Any]) -> Agent[Any, Any]:
        if getattr(agent, "_agentkit_working_memory_attached", False):
            return agent

        @agent.tool
        async def memory_set(ctx: RunContext[Any], key: str, value: str) -> str:
            """Store a value in this conversation's working memory.

            Args:
                key: The name to store under.
                value: The value to store.
            """
            store = _store(ctx.deps)
            if store is None:
                return "working memory is unavailable"
            await store.set(_namespace(ctx.deps), key, value)
            return f"stored {key}"

        @agent.tool
        async def memory_get(ctx: RunContext[Any], key: str) -> str:
            """Read a value from this conversation's working memory."""
            store = _store(ctx.deps)
            if store is None:
                return "working memory is unavailable"
            value = await store.get(_namespace(ctx.deps), key)
            return value if value is not None else f"(no value for {key})"

        @agent.tool
        async def memory_list(ctx: RunContext[Any]) -> str:
            """List everything in this conversation's working memory."""
            store = _store(ctx.deps)
            if store is None:
                return "working memory is unavailable"
            rows = await store.list(_namespace(ctx.deps))
            if not rows:
                return "(working memory is empty)"
            return "\n".join(f"{key}: {value}" for key, value in sorted(rows.items()))

        @agent.tool
        async def memory_forget(ctx: RunContext[Any], key: str) -> str:
            """Delete a key from this conversation's working memory."""
            store = _store(ctx.deps)
            if store is None:
                return "working memory is unavailable"
            forgotten = await store.forget(_namespace(ctx.deps), key)
            return "forgotten" if forgotten else f"(no value for {key})"

        @agent.instructions
        async def _working_memory_instructions(ctx: RunContext[Any]) -> str:
            return WORKING_MEMORY_GUIDE

        agent._agentkit_working_memory_attached = True  # type: ignore[attr-defined]
        return agent


class WorkingMemoryManager(Manager):
    """Resolves the configured working-memory store (``working_memory_driver``)."""

    kind = DriverKind.WORKING_MEMORY
    default_driver = WorkingMemoryDriver.MEMORY

    def create_memory_driver(self, app: Any) -> InMemoryWorkingMemory:
        return InMemoryWorkingMemory()

    def create_repository_driver(self, app: Any) -> RepositoryWorkingMemory:
        return RepositoryWorkingMemory(app)


@register_driver(DriverKind.WORKING_MEMORY, WorkingMemoryDriver.MEMORY)
class MemoryWorkingMemoryDriver(Driver):
    def build(self) -> InMemoryWorkingMemory:
        return InMemoryWorkingMemory()


@register_driver(DriverKind.WORKING_MEMORY, WorkingMemoryDriver.REPOSITORY)
class RepositoryWorkingMemoryDriver(Driver):
    def build(self) -> RepositoryWorkingMemory:
        app = self.app
        return RepositoryWorkingMemory(app)
