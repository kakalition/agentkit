"""The spec store — persistence for definitions by ``(kind, name)``.

:class:`SpecStore` is the contract; :class:`RepositorySpecStore` is the default
driver over the ``definitions`` table (via
:class:`~agentkit.db.repositories.definitions.DefinitionRepo`). ``team_definitions``
rows are copied into this table at ``init_db`` so the old ``/api/studio/teams``
surface keeps working (see :func:`agentkit.db.migrations.init_db`).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agentkit.specs.registry import SPECS

__all__ = ["RepositorySpecStore", "SpecStore"]


@runtime_checkable
class SpecStore(Protocol):
    """CRUD over serialized definitions keyed by ``(kind, name)``."""

    async def get(self, kind: str, name: str) -> Any | None: ...

    async def upsert(self, kind: str, name: str, spec: Any, *, version: int | None = None) -> Any: ...

    async def list(self, kind: str | None = None) -> list[Any]: ...

    async def remove(self, kind: str, name: str) -> bool: ...


class RepositorySpecStore:
    """A :class:`SpecStore` over an owner-scoped :class:`Repositories` container."""

    def __init__(self, repos: Any) -> None:
        self.repos = repos

    @property
    def _repo(self) -> Any:
        return self.repos.definitions

    async def get(self, kind: str, name: str) -> Any | None:
        return await self._repo.get(kind, name)

    async def upsert(
        self, kind: str, name: str, spec: Any, *, version: int | None = None
    ) -> Any:
        payload = spec if isinstance(spec, str) else _dump(spec)
        resolved_version = version if version is not None else _version(spec)
        return await self._repo.upsert(
            kind, name, spec=payload, version=resolved_version
        )

    async def list(self, kind: str | None = None) -> list[Any]:
        return await self._repo.list(kind)

    async def remove(self, kind: str, name: str) -> bool:
        return await self._repo.remove(kind, name)

    # -- helpers --------------------------------------------------------
    def spec_of(self, kind: str, record: Any) -> Any:
        """Validate a stored record into its spec model."""
        return SPECS.validate(kind, record.spec)

    def view(self, record: Any) -> dict[str, Any]:
        """A plain view of a stored definition (name, kind, version, spec)."""
        return {
            "kind": record.kind,
            "name": record.name,
            "version": record.version,
            "spec": _load(record.spec),
            "created_at": _iso(record.created_at),
            "updated_at": _iso(record.updated_at),
        }


def _dump(spec: Any) -> str:
    if hasattr(spec, "model_dump_json"):
        return spec.model_dump_json()
    import json

    return json.dumps(spec, default=str)


def _load(payload: str) -> Any:
    import json

    try:
        return json.loads(payload or "{}")
    except ValueError:  # pragma: no cover - tolerate corrupt rows
        return {}


def _version(spec: Any) -> int:
    return int(getattr(spec, "version", 1) or 1)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None
