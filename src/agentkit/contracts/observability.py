"""The observability contract — configure span export and instrumentation."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Tracer"]


@runtime_checkable
class Tracer(Protocol):
    """Configure tracing; return whether it was enabled."""

    def setup(self, settings: Any = None) -> bool: ...
