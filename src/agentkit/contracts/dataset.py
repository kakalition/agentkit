"""The dataset contract — named eval datasets (inline cases or a file source)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["DatasetStore"]


@runtime_checkable
class DatasetStore(Protocol):
    """Put/get/list/remove named datasets and read back their cases."""

    async def put(
        self, name: str, cases: list[dict[str, Any]], *, source: str = ""
    ) -> Any: ...

    async def get(self, name: str) -> Any | None: ...

    async def remove(self, name: str) -> bool: ...

    async def cases(self, name: str) -> list[dict[str, Any]]: ...

    async def list(self) -> list[Any]: ...
