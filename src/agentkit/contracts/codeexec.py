"""The code-execution contract — run untrusted code in a sandbox."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["CodeExecutor"]


@runtime_checkable
class CodeExecutor(Protocol):
    """Execute code and return a result with stdout/stderr/exit code."""

    async def run(
        self, code: str, *, language: str = "python", timeout: float = 10.0, **options: Any
    ) -> Any: ...
