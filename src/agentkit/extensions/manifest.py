"""The extension manifest — what a package/app contributes to agentkit.

An :class:`ExtensionManifest` is a plain, serializable declaration: an extension
returns one of these instead of mutating global registries directly, so discovery
(entry points, ``AGENTKIT_EXTENSIONS``) and programmatic registration
(``app.extensions(...)``) share one code path, and applying it is idempotent and
failure-isolated (see :mod:`agentkit.extensions.registry`).

Contributions map onto the existing substrate rather than a parallel one:

* ``specs``  -> :mod:`agentkit.specs` registry (kind -> pydantic model)
* ``panels`` -> :mod:`agentkit.extensions.panels` (Studio panel SPI)
* ``actions``-> :mod:`agentkit.extensions.actions` (named server-side handlers)
* ``drivers``-> :func:`agentkit.support.register_driver` (``(kind, name)`` factories)
* ``catalogs``-> catalog source factories (:mod:`agentkit.catalog`)
* ``codegen`` -> codegen target registry (:mod:`agentkit.specs.codegen`)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["DriverContribution", "ExtensionManifest", "SpecContribution"]


@dataclass
class SpecContribution:
    """A spec kind the extension registers (its pydantic model + materializer)."""

    kind: str
    model: type
    materializer: Callable[..., Any] | None = None
    runner: Callable[..., Any] | None = None


@dataclass
class DriverContribution:
    """A ``(kind, name)`` driver factory the extension registers globally."""

    kind: str
    name: str
    factory: Callable[[Any], Any]


def _as_spec(value: Any) -> SpecContribution:
    if isinstance(value, SpecContribution):
        return value
    if isinstance(value, tuple):
        return SpecContribution(*value)
    if isinstance(value, Mapping):
        return SpecContribution(**value)
    kind = getattr(value, "kind", None)
    model = getattr(value, "model", None)
    if kind is None or model is None:
        raise TypeError(f"cannot interpret spec contribution {value!r}")
    return SpecContribution(
        kind=kind,
        model=model,
        materializer=getattr(value, "materializer", None),
        runner=getattr(value, "runner", None),
    )


def _as_driver(value: Any) -> DriverContribution:
    if isinstance(value, DriverContribution):
        return value
    if isinstance(value, tuple):
        return DriverContribution(*value)
    if isinstance(value, Mapping):
        return DriverContribution(**value)
    raise TypeError(f"cannot interpret driver contribution {value!r}")


@dataclass
class ExtensionManifest:
    """A declarative contribution bundle returned by an extension package/app."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    specs: list[Any] = field(default_factory=list)
    panels: list[Any] = field(default_factory=list)
    actions: dict[str, Callable[..., Any]] = field(default_factory=dict)
    drivers: list[Any] = field(default_factory=list)
    catalogs: list[Any] = field(default_factory=list)
    codegen: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("extension manifest needs a name")
        self.specs = [_as_spec(spec) for spec in self.specs]
        self.drivers = [_as_driver(driver) for driver in self.drivers]
        self.actions = dict(self.actions)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-friendly description (used by the introspection endpoint)."""
        kinds: Iterable[str] = (spec.kind for spec in self.specs)
        panel_ids = [getattr(panel, "id", None) or str(panel) for panel in self.panels]
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "specs": list(kinds),
            "panels": panel_ids,
            "actions": sorted(self.actions),
            "drivers": [f"{d.kind}:{d.name}" for d in self.drivers],
            "catalogs": [str(catalog) for catalog in self.catalogs],
            "codegen": sorted(self.codegen),
        }
