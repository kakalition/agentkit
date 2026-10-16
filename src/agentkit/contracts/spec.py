"""The spec contract — a serializable, materializable definition.

A *spec* is the declarative half of a subsystem object (an agent, team, workflow,
or eval). It round-trips through JSON, exposes a JSON Schema for the Studio form
renderer, and can render itself to a codegen target (``python``/``yaml``/``json``).
The live object (agent/runner/graph/suite) is produced by a *materializer*
registered alongside the model in :mod:`agentkit.specs.registry`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Spec"]


@runtime_checkable
class Spec(Protocol):
    """A declarative definition that can be stored, described, and rendered."""

    #: The spec kind (``agent`` | ``team`` | ``workflow`` | ``eval``) — not the
    #: runner kind. Named ``spec_kind`` so models that already carry a ``kind``
    #: field (e.g. :class:`~agentkit.studio.TeamDefinition`) can still conform.
    spec_kind: str

    #: The unique name of the definition within its kind.
    name: str

    def model_dump_json(self) -> str: ...

    @classmethod
    def from_json(cls, data: str) -> Spec: ...

    @classmethod
    def json_schema(cls) -> dict[str, Any]: ...

    def render(self, target: str = "python") -> str: ...
