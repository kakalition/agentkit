"""First-class extension substrate.

Build on the existing contract + driver + manager layers instead of forking them:
an :class:`~agentkit.extensions.manifest.ExtensionManifest` declares what a package
contributes (specs, panels, actions, drivers, catalogs, codegen targets), the
:data:`~agentkit.extensions.registry.EXTENSIONS` registry applies it idempotently at
``App.boot()``, and failures are logged rather than fatal::

    from agentkit import ExtensionManifest, PanelSpec

    manifest = ExtensionManifest(
        name="my-extension",
        specs=[("greeting", GreetingSpec)],
        panels=[PanelSpec(id="greetings", spec_kind="greeting")],
    )
    app.extensions(manifest)

Discovery accepts entry points (the ``agentkit.extensions`` group) and the
``AGENTKIT_EXTENSIONS=module:callable`` env var.
"""

from agentkit.extensions.actions import (
    ACTIONS,
    ActionRegistry,
    register_action,
    run_action,
)
from agentkit.extensions.discovery import (
    ENTRY_POINT_GROUP,
    EXTENSIONS_ENV,
    discover_from_entry_points,
    discover_from_env,
    discover_manifests,
    resolve_manifest,
)
from agentkit.extensions.manifest import (
    DriverContribution,
    ExtensionManifest,
    SpecContribution,
)
from agentkit.extensions.panels import PANELS, PanelRegistry, PanelSpec, register_panel
from agentkit.extensions.registry import (
    EXTENSIONS,
    Extensions,
    apply_manifest,
    register_manifest,
)

__all__ = [
    "ACTIONS",
    "ActionRegistry",
    "ENTRY_POINT_GROUP",
    "EXTENSIONS",
    "EXTENSIONS_ENV",
    "DriverContribution",
    "ExtensionManifest",
    "Extensions",
    "PANELS",
    "PanelRegistry",
    "PanelSpec",
    "SpecContribution",
    "apply_manifest",
    "discover_from_entry_points",
    "discover_from_env",
    "discover_manifests",
    "register_action",
    "register_manifest",
    "register_panel",
    "resolve_manifest",
    "run_action",
]
