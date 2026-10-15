"""The durability contract — durable workflow infrastructure."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Durability"]


@runtime_checkable
class Durability(Protocol):
    """Configure durable execution and enqueue/schedule work."""

    def init(
        self,
        settings: Any = None,
        *,
        launch: bool = True,
        queues: Any = None,
    ) -> Any: ...

    def register_queue(self, name: str, **options: Any) -> Any: ...

    def enqueue(self, queue: str, func: Any, *args: Any, **kwargs: Any) -> str: ...

    def apply_schedules(self, schedules: list[dict[str, Any]]) -> None: ...
