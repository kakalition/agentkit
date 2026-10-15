"""Subagent context contracts — how a child agent sees its parent's context."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["ContextStrategy"]


@runtime_checkable
class ContextStrategy(Protocol):
    """Build the context a subagent turn is invoked with."""

    def context(self, ctx: Any, task: str) -> Any: ...
