"""The graph-executor contract — how a state graph is executed."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["GraphExecutor"]


@runtime_checkable
class GraphExecutor(Protocol):
    """Run a state graph to completion."""

    async def run(self, graph: Any, state: Any, **options: Any) -> Any: ...
