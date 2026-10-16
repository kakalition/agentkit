"""The checkpoint contract — save/restore run state (time travel)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["CheckpointStore"]


@runtime_checkable
class CheckpointStore(Protocol):
    """Persist and read back run checkpoints (one state per ``(run_id, seq)``)."""

    async def put(
        self, run_id: str, seq: int, state: Any, *, label: str = ""
    ) -> Any: ...

    async def get(self, run_id: str, seq: int) -> Any | None: ...

    async def list(self, run_id: str) -> list[Any]: ...

    async def latest(self, run_id: str) -> Any | None: ...

    async def delete(self, run_id: str) -> int: ...
