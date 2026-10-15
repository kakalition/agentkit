"""Task planning: an in-loop todo store plus planning strategies.

    from agentkit import Agent
    from agentkit.tasks import attach_tasks

    agent = Agent.make("planner").instructions("…").build()
    attach_tasks(agent)          # write_todos / read_todos / add_todo / update_todo / clear_todos

Todos are held by a :class:`TaskStore` driver (default ``memory``; select with
``tasks_driver`` or register your own). Planning strategies (``planning_driver``)
decompose an objective into steps; the default ``single`` returns the objective
unchanged, and ``batched`` splits it on newlines/semicolons.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from agentkit.contracts.tasks import PlanningStrategy, TaskStore
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, PlanningDriver, TaskDriver
from agentkit.support.manager import Manager

__all__ = [
    "BatchedPlanning",
    "InMemoryTaskStore",
    "PlanningManager",
    "PlanningStrategy",
    "SingleStepPlanning",
    "TaskManager",
    "TaskStore",
    "attach_tasks",
]

_TODO_STATUSES = ("pending", "in_progress", "completed")


class InMemoryTaskStore:
    """A per-process todo store (the default task driver)."""

    def __init__(self) -> None:
        self._todos: list[dict[str, Any]] = []
        self._next = 1

    async def write(self, todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._todos = []
        self._next = 1
        for item in todos:
            text = item.get("text") if isinstance(item, dict) else str(item)
            status = item.get("status", "pending") if isinstance(item, dict) else "pending"
            if text:
                await self.add(str(text), status=status)
        return await self.read()

    async def read(self) -> list[dict[str, Any]]:
        return [dict(todo) for todo in self._todos]

    async def add(self, text: str, *, status: str = "pending") -> dict[str, Any]:
        todo = {"id": self._next, "text": text.strip(), "status": status}
        self._next += 1
        self._todos.append(todo)
        return dict(todo)

    async def update(
        self, todo_id: int, *, status: str | None = None, text: str | None = None
    ) -> dict[str, Any] | None:
        for todo in self._todos:
            if todo["id"] == todo_id:
                if status is not None:
                    todo["status"] = status
                if text is not None:
                    todo["text"] = text.strip()
                return dict(todo)
        return None

    async def clear(self) -> int:
        count = len(self._todos)
        self._todos = []
        self._next = 1
        return count


class SingleStepPlanning:
    """The default planning strategy: one step, the objective itself."""

    async def plan(self, objective: str, **options: Any) -> list[str]:
        text = (objective or "").strip()
        return [text] if text else []


class BatchedPlanning:
    """Split an objective on newlines/semicolons into steps."""

    async def plan(self, objective: str, **options: Any) -> list[str]:
        import re

        parts = re.split(r"[\n;]+", objective or "")
        return [part.strip() for part in parts if part.strip()]


class TaskManager(Manager):
    """Resolves the configured task store (``tasks_driver``, default ``memory``)."""

    kind = DriverKind.TASKS
    default_driver = TaskDriver.MEMORY


class PlanningManager(Manager):
    """Resolves the configured planning strategy (``planning_driver``, default ``single``)."""

    kind = DriverKind.PLANNING
    default_driver = PlanningDriver.SINGLE


@register_driver(DriverKind.TASKS, TaskDriver.MEMORY)
def _memory_task_store_driver(app: Any) -> InMemoryTaskStore:
    return InMemoryTaskStore()


@register_driver(DriverKind.PLANNING, PlanningDriver.SINGLE)
def _single_planning_driver(app: Any) -> SingleStepPlanning:
    return SingleStepPlanning()


@register_driver(DriverKind.PLANNING, PlanningDriver.BATCHED)
def _batched_planning_driver(app: Any) -> BatchedPlanning:
    return BatchedPlanning()


def _store(ctx: RunContext[Any]) -> Any:
    deps = getattr(ctx, "deps", None)
    extras = getattr(deps, "extras", None)
    return extras.get("task_store") if isinstance(extras, dict) else None


def _format(todos: list[dict[str, Any]]) -> str:
    if not todos:
        return "(no todos)"
    return "\n".join(f"#{todo['id']} [{todo['status']}] {todo['text']}" for todo in todos)


def attach_tasks(agent: Any, *, store: Any = None) -> Any:
    """Register the todo tools on a built agent (idempotent)."""
    if getattr(agent, "_agentkit_tasks_attached", False):
        return agent
    fallback = store if store is not None else InMemoryTaskStore()

    def resolve(ctx: RunContext[Any]) -> Any:
        return _store(ctx) or fallback

    @agent.tool
    async def write_todos(ctx: RunContext[Any], todos: list[str]) -> str:
        """Replace the todo list with a fresh set of steps.

        Args:
            todos: The ordered list of steps to work through.
        """
        store_ = resolve(ctx)
        written = await store_.write([{"text": text} for text in todos])
        return _format(written)

    @agent.tool
    async def read_todos(ctx: RunContext[Any]) -> str:
        """Show the current todo list."""
        return _format(await resolve(ctx).read())

    @agent.tool
    async def add_todo(ctx: RunContext[Any], text: str) -> str:
        """Append a step to the todo list.

        Args:
            text: The step to add.
        """
        todo = await resolve(ctx).add(text)
        return f"added #{todo['id']}"

    @agent.tool
    async def update_todo(ctx: RunContext[Any], id: int, status: str = "completed") -> str:
        """Change a todo's status (pending | in_progress | completed).

        Args:
            id: The todo id.
            status: The new status.
        """
        if status not in _TODO_STATUSES:
            return f"unknown status {status!r}; expected {', '.join(_TODO_STATUSES)}"
        todo = await resolve(ctx).update(id, status=status)
        return f"updated #{todo['id']} -> {todo['status']}" if todo else "no such todo"

    @agent.tool
    async def clear_todos(ctx: RunContext[Any]) -> str:
        """Remove every todo."""
        count = await resolve(ctx).clear()
        return f"cleared {count} todo(s)"

    agent._agentkit_tasks_attached = True  # type: ignore[attr-defined]
    return agent
