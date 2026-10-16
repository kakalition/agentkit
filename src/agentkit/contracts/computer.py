"""The computer-use contract — drive a browser/desktop surface.

A computer is the primitive behind browser tools: navigate, snapshot the page,
click, type, screenshot, and evaluate a script. Implementations may be a real
headless browser (``PlaywrightComputer``, optional extra) or an in-process stub
(``LoopbackComputer``) for tests.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Computer"]


@runtime_checkable
class Computer(Protocol):
    """A controllable browser/desktop surface."""

    async def goto(self, url: str) -> str: ...

    async def snapshot(self) -> str: ...

    async def click(self, selector: str) -> str: ...

    async def type(self, selector: str, text: str) -> str: ...

    async def screenshot(self) -> Any: ...

    async def evaluate(self, expression: str) -> Any: ...

    async def close(self) -> None: ...
