"""The code-execution contract — run untrusted code in a sandbox."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["CodeExecutor", "HibernatingExecutor"]


@runtime_checkable
class CodeExecutor(Protocol):
    """Execute code and return a result with stdout/stderr/exit code."""

    async def run(
        self, code: str, *, language: str = "python", timeout: float = 10.0, **options: Any
    ) -> Any: ...


@runtime_checkable
class HibernatingExecutor(Protocol):
    """An optional capability for serverless backends: pause/resume a sandbox.

    Kept separate from :class:`CodeExecutor` so adding it never breaks the base
    conformance check (``isinstance(driver, CodeExecutor)``); backends that can
    hibernate implement both.
    """

    async def hibernate(self) -> Any: ...

    async def wake(self) -> Any: ...
