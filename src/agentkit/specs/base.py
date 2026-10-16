"""Spec primitives shared by every definition kind.

A spec model subclasses :class:`SpecModel`, sets a :class:`SpecKind` ``spec_kind``,
and gains JSON round-tripping, a JSON Schema for the Studio form renderer, and
codegen via :func:`agentkit.specs.codegen.render_spec`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel

__all__ = ["SpecKind", "SpecModel"]


class SpecKind(StrEnum):
    """The recognized spec kinds (the ``definitions.kind`` values)."""

    AGENT = "agent"
    TEAM = "team"
    WORKFLOW = "workflow"
    EVAL = "eval"


class SpecModel(BaseModel):
    """Base for spec models: serialization + schema + codegen helpers.

    ``spec_kind`` is a :class:`typing.ClassVar` (not a field), so a spec that also
    carries a user-facing ``kind`` field — e.g. :class:`~agentkit.studio.TeamDefinition`'s
    runner kind — can still conform to the :class:`~agentkit.contracts.spec.Spec`
    protocol without a name clash.
    """

    spec_kind: ClassVar[str] = ""

    def render(self, target: str = "python") -> str:
        """Render this spec to a codegen ``target`` (``python`` | ``yaml`` | ``json``)."""
        from agentkit.specs.codegen import render_spec

        return render_spec(self, target)

    @classmethod
    def from_json(cls, data: str) -> SpecModel:
        return cls.model_validate_json(data)

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return cls.model_json_schema()
