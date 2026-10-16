"""The Studio panel SPI — server-declared panels with no remote code execution.

A panel is a small descriptor the backend advertises to the SPA
(``GET /api/studio/panels``). The SPA ships one schema-driven renderer plus a
small build-time ``richPanels`` map keyed by panel id (workflow canvas, playground
flow viz, catalog browser); an unknown panel falls back to the generic renderer,
so *adding a spec kind server-side shows a new builder panel with no SPA rebuild*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["PANELS", "PanelRegistry", "PanelSpec", "register_panel"]


@dataclass
class PanelSpec:
    """A declarative panel descriptor (id, title, spec kind, actions, layout)."""

    id: str
    title: str = ""
    spec_kind: str | None = None
    actions: list[str] = field(default_factory=list)
    layout: str = "form"
    order: int = 100
    description: str = ""

    def __post_init__(self) -> None:
        self.id = str(self.id).strip()
        if not self.id:
            raise ValueError("panel needs an id")
        if not self.title:
            self.title = self.id.replace("-", " ").title()
        self.actions = [str(action) for action in self.actions]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "spec_kind": self.spec_kind,
            "actions": list(self.actions),
            "layout": self.layout,
            "order": self.order,
            "description": self.description,
        }

    @classmethod
    def coerce(cls, value: Any) -> PanelSpec:
        if isinstance(value, PanelSpec):
            return value
        if isinstance(value, dict):
            return cls(**value)
        data = {
            name: getattr(value, name)
            for name in ("id", "title", "spec_kind", "actions", "layout", "order", "description")
            if hasattr(value, name)
        }
        return cls(**data)


class PanelRegistry:
    """A last-wins registry of panels keyed by id."""

    def __init__(self) -> None:
        self._panels: dict[str, PanelSpec] = {}

    def register(self, panel: Any) -> PanelSpec:
        spec = PanelSpec.coerce(panel)
        self._panels[spec.id] = spec
        return spec

    def get(self, panel_id: str) -> PanelSpec | None:
        return self._panels.get(panel_id)

    def list(self) -> list[PanelSpec]:
        return sorted(self._panels.values(), key=lambda panel: (panel.order, panel.id))

    def remove(self, panel_id: str) -> bool:
        return self._panels.pop(panel_id, None) is not None

    def clear(self) -> None:
        self._panels.clear()


PANELS = PanelRegistry()


def register_panel(panel: Any) -> PanelSpec:
    """Register (or replace) a panel descriptor."""
    return PANELS.register(panel)
