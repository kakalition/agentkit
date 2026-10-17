"""Inspect registered extensions (``agentkit extensions list``) — class-based."""

from __future__ import annotations

from agentkit.foundation import Command


class ExtensionsListCommand(Command):
    group = 'extensions'
    signature = "extensions:list {--bootstrap=}"
    description = "List discovered extensions and what they contribute."

    def handle(self, bootstrap: str | None = None) -> None:  # noqa: ARG002 - accepted for parity
        from agentkit.extensions import EXTENSIONS
        from agentkit.extensions.discovery import discover_manifests

        for manifest in discover_manifests():
            EXTENSIONS.register_manifest(manifest)
        manifests = EXTENSIONS.manifests()
        if not manifests:
            self.info("no extensions found")
            return
        for manifest in manifests:
            info = manifest.to_dict()
            self.info(f"{info['name']} {info['version']}")
            for key in ("specs", "panels", "actions", "drivers", "catalogs", "codegen"):
                values = info[key]
                if values:
                    self.info(f"  {key}: {', '.join(map(str, values))}")


COMMANDS: list[type] = [
    ExtensionsListCommand,
]
