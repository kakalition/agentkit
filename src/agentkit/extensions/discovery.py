"""Discovery of extension manifests.

Order of precedence (last wins): **programmatic** ``app.extensions(...)`` >
``AGENTKIT_EXTENSIONS`` env var > ``agentkit.extensions`` entry points (D9).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

from agentkit.extensions.manifest import ExtensionManifest
from agentkit.logging import get_logger

__all__ = [
    "ENTRY_POINT_GROUP",
    "EXTENSIONS_ENV",
    "discover_from_entry_points",
    "discover_from_env",
    "discover_manifests",
    "resolve_manifest",
]

log = get_logger("agentkit.extensions.discovery")

ENTRY_POINT_GROUP = "agentkit.extensions"
EXTENSIONS_ENV = "AGENTKIT_EXTENSIONS"


def resolve_manifest(value: Any) -> ExtensionManifest:
    """Coerce a manifest, a ``"module:callable"`` string, or a factory to a manifest."""
    if isinstance(value, ExtensionManifest):
        return value
    if isinstance(value, str):
        value = _load_reference(value)
    if callable(value):
        value = value()
    if isinstance(value, ExtensionManifest):
        return value
    raise TypeError(f"cannot resolve an extension manifest from {value!r}")


def _load_reference(reference: str) -> Any:
    module_name, separator, attribute = reference.strip().partition(":")
    if not separator:
        raise ValueError(f"extension reference {reference!r} must be 'module:callable'")
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def discover_from_entry_points(group: str = ENTRY_POINT_GROUP) -> list[ExtensionManifest]:
    """Load installed extensions from the ``agentkit.extensions`` entry-point group."""
    discovered: list[ExtensionManifest] = []
    for entry_point in entry_points(group=group):
        try:
            discovered.append(resolve_manifest(entry_point.load()))
        except Exception:  # pragma: no cover - one bad package cannot stop discovery
            log.exception("failed to load extension entry point %r", entry_point.name)
    return discovered


def discover_from_env(var: str = EXTENSIONS_ENV) -> list[ExtensionManifest]:
    """Load extensions named by ``AGENTKIT_EXTENSIONS`` (``module:callable,…``)."""
    raw = os.environ.get(var, "").strip()
    if not raw:
        return []
    discovered: list[ExtensionManifest] = []
    for reference in raw.split(","):
        reference = reference.strip()
        if not reference:
            continue
        try:
            discovered.append(resolve_manifest(reference))
        except Exception:  # pragma: no cover - one bad reference cannot stop discovery
            log.exception("failed to load extension %r from %s", reference, var)
    return discovered


def discover_manifests(
    *, env: str = EXTENSIONS_ENV, loader: Callable[[str], list[ExtensionManifest]] | None = None
) -> list[ExtensionManifest]:
    """Every discovered manifest: entry points first, then env (env wins on conflict)."""
    entry_loader = loader or discover_from_entry_points
    return [*entry_loader(ENTRY_POINT_GROUP), *discover_from_env(env)]
