"""The spec registry — spec kind to pydantic model, schema, and materializer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from agentkit.errors import ConfigurationError, NotFound

__all__ = ["SPECS", "SpecEntry", "SpecRegistry", "register_spec"]


@dataclass
class SpecEntry:
    """One registered spec kind: its model plus how to build/run the live object."""

    kind: str
    model: type[BaseModel]
    materializer: Callable[..., Any] | None = None
    runner: Callable[..., Any] | None = None
    source: str = "core"


class SpecRegistry:
    """A last-wins registry keyed by spec kind."""

    def __init__(self) -> None:
        self._entries: dict[str, SpecEntry] = {}

    def register(
        self,
        kind: str,
        model: type[BaseModel],
        *,
        materializer: Callable[..., Any] | None = None,
        runner: Callable[..., Any] | None = None,
        source: str = "core",
    ) -> SpecEntry:
        entry = SpecEntry(str(kind), model, materializer, runner, source)
        self._entries[entry.kind] = entry
        return entry

    def get(self, kind: str) -> SpecEntry | None:
        return self._entries.get(str(kind))

    def require(self, kind: str) -> SpecEntry:
        entry = self.get(kind)
        if entry is None:
            available = ", ".join(self.kinds()) or "(none)"
            raise NotFound(f"unknown spec kind {kind!r}; choose from {available}")
        return entry

    def kinds(self) -> list[str]:
        return sorted(self._entries)

    def entries(self) -> list[SpecEntry]:
        return [self._entries[kind] for kind in self.kinds()]

    def model_for(self, kind: str) -> type[BaseModel]:
        return self.require(kind).model

    def schema_for(self, kind: str) -> dict[str, Any]:
        return self.model_for(kind).model_json_schema()

    def schemas(self) -> dict[str, dict[str, Any]]:
        return {kind: self.schema_for(kind) for kind in self.kinds()}

    # -- validation -----------------------------------------------------
    def validate(self, kind: str, payload: Any) -> Any:
        """Coerce ``payload`` (a model, dict, or JSON string) into the kind's model."""
        model = self.model_for(kind)
        if isinstance(payload, model):
            return payload
        if isinstance(payload, (str, bytes)):
            return model.model_validate_json(payload)
        return model.model_validate(payload)

    # -- materialize / run ----------------------------------------------
    def materialize(self, kind: str, spec: Any, **options: Any) -> Any:
        entry = self.require(kind)
        if entry.materializer is None:
            raise ConfigurationError(f"spec kind {kind!r} has no materializer")
        resolved = spec if isinstance(spec, entry.model) else self.validate(kind, spec)
        return entry.materializer(resolved, **options)

    async def run(self, kind: str, spec: Any, prompt: str = "", **options: Any) -> Any:
        entry = self.require(kind)
        if entry.runner is None:
            raise ConfigurationError(f"spec kind {kind!r} is not runnable")
        resolved = spec if isinstance(spec, entry.model) else self.validate(kind, spec)
        return await entry.runner(resolved, prompt, **self._supported_options(entry.runner, options))

    @staticmethod
    def _supported_options(runner: Callable[..., Any], options: dict[str, Any]) -> dict[str, Any]:
        """Keep only options a runner accepts (unless it takes ``**kwargs``)."""
        import inspect

        try:
            parameters = inspect.signature(runner).parameters
        except (TypeError, ValueError):  # pragma: no cover - builtins
            return options
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            return options
        return {name: value for name, value in options.items() if name in parameters}

    def clear(self) -> None:
        self._entries.clear()


#: The process-wide spec registry.
SPECS = SpecRegistry()


def register_spec(kind: str, model: type[BaseModel], **options: Any) -> SpecEntry:
    """Register a spec kind on the process-wide registry."""
    return SPECS.register(kind, model, **options)
