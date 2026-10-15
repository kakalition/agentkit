"""Task contracts — a todo store and a planning strategy."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["PlanningStrategy", "TaskStore"]


@runtime_checkable
class TaskStore(Protocol):
    """Read and mutate an agent's todo list."""

    async def write(self, todos: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    async def read(self) -> list[dict[str, Any]]: ...

    async def add(self, text: str, *, status: str = "pending") -> dict[str, Any]: ...

    async def update(
        self, todo_id: int, *, status: str | None = None, text: str | None = None
    ) -> dict[str, Any] | None: ...

    async def clear(self) -> int: ...


@runtime_checkable
class PlanningStrategy(Protocol):
    """Decompose an objective into an ordered list of steps."""

    async def plan(self, objective: str, **options: Any) -> list[str]: ...
