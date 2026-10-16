"""The extension registry: register manifests, then apply them to an app.

Application is idempotent and **failure-isolated** — every manifest is wrapped in
``try/except`` with ``log.exception`` so a broken extension degrades gracefully and
never breaks boot (the same idiom as :mod:`agentkit.foundation.fullstack`).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from typing import Any

from agentkit.extensions.actions import ACTIONS
from agentkit.extensions.manifest import ExtensionManifest
from agentkit.extensions.panels import PANELS
from agentkit.logging import get_logger

__all__ = ["EXTENSIONS", "Extensions", "apply_manifest", "register_manifest"]

log = get_logger("agentkit.extensions")


def _register_specs(manifest: ExtensionManifest) -> list[str]:
    if not manifest.specs:
        return []
    from agentkit.specs.registry import SPECS

    registered: list[str] = []
    for spec in manifest.specs:
        SPECS.register(
            spec.kind,
            spec.model,
            materializer=spec.materializer,
            runner=spec.runner,
            source=manifest.name,
        )
        registered.append(spec.kind)
    return registered


def _register_panels(manifest: ExtensionManifest) -> list[str]:
    return [PANELS.register(panel).id for panel in manifest.panels]


def _register_actions(manifest: ExtensionManifest) -> list[str]:
    for action_id, handler in manifest.actions.items():
        ACTIONS.register(action_id, handler)
    return sorted(manifest.actions)


def _register_drivers(manifest: ExtensionManifest, app: Any) -> list[str]:
    register_driver = _driver_registrar()

    registered: list[str] = []
    for driver in manifest.drivers:
        register_driver(driver.kind, driver.name)(driver.factory)
        # Drop a cached instance so the new factory is used on next resolution.
        with contextlib.suppress(Exception):
            app.manager(driver.kind).forget(driver.name)
        registered.append(f"{driver.kind}:{driver.name}")
    return registered


def _driver_registrar() -> Any:
    from agentkit.support import register_driver

    return register_driver


def _register_catalogs(manifest: ExtensionManifest) -> list[str]:
    if not manifest.catalogs:
        return []
    from agentkit.catalog import register_catalog_source

    names: list[str] = []
    for entry in manifest.catalogs:
        name, factory = (entry if isinstance(entry, tuple) else (None, entry))
        if name is None:
            name = getattr(factory, "__name__", str(factory))
        register_catalog_source(str(name), factory)
        names.append(str(name))
    return names


def _register_codegen(manifest: ExtensionManifest) -> list[str]:
    if not manifest.codegen:
        return []
    from agentkit.specs.codegen import register_codegen

    for target, renderer in manifest.codegen.items():
        register_codegen(target, renderer)
    return sorted(manifest.codegen)


def apply_manifest(app: Any, manifest: ExtensionManifest) -> dict[str, Any]:
    """Apply one manifest to ``app`` (idempotent; every contribution is optional)."""
    summary: dict[str, Any] = {"name": manifest.name, "version": manifest.version}
    summary["specs"] = _register_specs(manifest)
    summary["panels"] = _register_panels(manifest)
    summary["actions"] = _register_actions(manifest)
    summary["drivers"] = _register_drivers(manifest, app)
    summary["catalogs"] = _register_catalogs(manifest)
    summary["codegen"] = _register_codegen(manifest)
    return summary


class Extensions:
    """A last-wins registry of extension manifests."""

    def __init__(self) -> None:
        self._manifests: dict[str, ExtensionManifest] = {}

    def register_manifest(self, manifest: ExtensionManifest) -> ExtensionManifest:
        if not isinstance(manifest, ExtensionManifest):
            raise TypeError(f"expected an ExtensionManifest, got {type(manifest)!r}")
        existing = self._manifests.get(manifest.name)
        if existing is not None and existing is not manifest:
            log.warning(
                "extension %r registered twice; last definition wins (%s -> %s)",
                manifest.name,
                existing.version,
                manifest.version,
            )
        self._manifests[manifest.name] = manifest
        return manifest

    def register_manifests(self, manifests: Iterable[ExtensionManifest]) -> None:
        for manifest in manifests:
            self.register_manifest(manifest)

    def manifests(self) -> list[ExtensionManifest]:
        return list(self._manifests.values())

    def describe(self) -> list[dict[str, Any]]:
        return [manifest.to_dict() for manifest in self._manifests.values()]

    def clear(self) -> None:
        self._manifests.clear()

    def apply(self, app: Any) -> list[dict[str, Any]]:
        """Apply every registered manifest to ``app``; failures are logged, not fatal."""
        applied: list[dict[str, Any]] = []
        for manifest in self._manifests.values():
            try:
                applied.append(apply_manifest(app, manifest))
            except Exception:  # pragma: no cover - never fatal
                log.exception("extension %r failed to apply", manifest.name)
        return applied


#: The process-wide extension registry.
EXTENSIONS = Extensions()


def register_manifest(manifest: ExtensionManifest) -> ExtensionManifest:
    """Register a manifest on the process-wide registry."""
    return EXTENSIONS.register_manifest(manifest)
