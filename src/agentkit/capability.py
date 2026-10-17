"""The :class:`Capability` base — a class-based agent capability.

A *capability* is a framework feature that registers tools and/or instructions on
a built PydanticAI agent (memory, tasks, learning, artifacts, …). It is a leaf
module (no framework imports) so top-level modules can subclass it without
import cycles.
"""

from __future__ import annotations

from typing import Any, ClassVar

__all__ = ["Capability"]


class Capability:
    """Base class for a class-based agent capability (``install(agent)``)."""

    name: ClassVar[str] = ""

    def install(self, agent: Any) -> Any:
        raise NotImplementedError

    def __call__(self, agent: Any) -> Any:
        return self.install(agent)
