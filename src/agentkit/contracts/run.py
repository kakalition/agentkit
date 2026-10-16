"""The run-recorder / run-store contracts — a uniform trace for every runner.

``RunEvent`` generalizes :class:`~agentkit.session.StreamEvent` (kept as the session
subtype for back-compat, D6); a :class:`RunRecorder` collects events during a run and
a :class:`RunStore` persists them (Playground v2 + trace grading).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["RunRecorder", "RunStore"]


@runtime_checkable
class RunRecorder(Protocol):
    """Collect :class:`~agentkit.runs.RunEvent` increments during a run."""

    run_id: str

    def record(self, event: Any) -> Any: ...


@runtime_checkable
class RunStore(Protocol):
    """Persist and read back run traces."""

    async def add_many(self, run_id: str, events: list[dict[str, Any]]) -> None: ...

    async def events(self, run_id: str, *, limit: int | None = None) -> list[Any]: ...

    async def list_runs(self, *, limit: int | None = None) -> list[Any]: ...
