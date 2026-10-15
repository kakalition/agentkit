"""The eval-reporter contract — render an evaluation report."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Reporter"]


@runtime_checkable
class Reporter(Protocol):
    """Render an evaluation report to text."""

    def render(self, report: Any) -> str: ...
