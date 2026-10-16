"""Postures — one runtime, three opinionated default profiles.

A *posture* is a thin defaults layer over the layers
:meth:`agentkit.Agent.full` already exposes, the settings flags, and the tool
policy. It never forks a code path: selecting a posture only changes defaults,
and an explicit builder argument or a settings flag always wins.

* ``specialized`` — a tightly-scoped, egress-free, approval-gated specialist.
* ``hybrid`` — today's ``.full()`` behavior (the default; no breaking change).
* ``free`` — an autonomous generalist (durable memory, code, egress, peers).

Precedence (see :func:`agentkit.foundation.agent.Agent.full`)::

    explicit arg  >  builder method  >  posture  >  settings flag

Settings flags remain a hard gate: a layer whose settings flag is disabled stays
disabled even when a posture would otherwise enable it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agentkit.policy import (
    ToolPolicy,
    default_policy,
    free_policy,
    specialized_policy,
)

__all__ = [
    "POSTURES",
    "Posture",
    "PostureProfile",
    "apply_settings_overrides",
    "register_posture",
    "resolve_posture",
]

#: The layers a profile may toggle, in the order ``.full()`` applies them. Only
#: the layers ``.full()`` understands are meaningful here; ``workspace`` and
#: ``subagents`` are enabled only when a root/registry is available.
LAYER_KEYS = (
    "persona",
    "memory",
    "skills",
    "hitl",
    "safety",
    "native",
    "learning",
    "todos",
    "code",
    "workspace",
    "subagents",
)


class Posture(StrEnum):
    """The three built-in postures."""

    SPECIALIZED = "specialized"
    HYBRID = "hybrid"
    FREE = "free"


SPECIALIZED_PREAMBLE = (
    "You are a focused specialist. Stay strictly within your assigned scope: do "
    "not attempt web access, code execution, or any action outside the tools you "
    "were given. Prefer a concise, correct answer over exploring."
)

FREE_PREAMBLE = (
    "You are an autonomous generalist. Take initiative, plan multi-step work, "
    "use your workspace, tools, memory and peers, and keep the user informed of "
    "what you did and why."
)


@dataclass(frozen=True)
class PostureProfile:
    """The defaults a posture applies to one ``.full()`` build.

    ``layers`` feeds the ``.full()`` layer toggles, ``settings_overrides`` are
    merged into the builder settings view (never mutating the settings object),
    ``policy_factory`` supplies the safety policy, and ``preamble`` is prepended
    to the instructions.
    """

    name: Posture
    preamble: str = ""
    layers: dict[str, bool] = field(default_factory=dict)
    settings_overrides: dict[str, Any] = field(default_factory=dict)
    policy_factory: Callable[[], ToolPolicy] = default_policy
    budget: Any = None
    egress: bool = False

    def layer(self, key: str, default: bool) -> bool:
        """The profile's value for a layer, or ``default`` when unspecified."""
        return bool(self.layers.get(key, default))


def _specialized() -> PostureProfile:
    return PostureProfile(
        name=Posture.SPECIALIZED,
        preamble=SPECIALIZED_PREAMBLE,
        layers={
            "persona": True,
            "memory": False,
            "skills": True,
            "hitl": True,
            "safety": True,
            "native": False,
            "learning": False,
            "todos": False,
            "code": False,
            "workspace": False,
            "subagents": False,
        },
        policy_factory=specialized_policy,
        egress=False,
    )


def _hybrid() -> PostureProfile:
    return PostureProfile(
        name=Posture.HYBRID,
        preamble="",
        layers={
            "persona": True,
            "memory": True,
            "skills": True,
            "hitl": True,
            "safety": True,
            "native": True,
            "learning": True,
            "todos": True,
            "code": False,
            "workspace": False,
            "subagents": False,
        },
        policy_factory=default_policy,
        egress=False,
    )


def _free() -> PostureProfile:
    return PostureProfile(
        name=Posture.FREE,
        preamble=FREE_PREAMBLE,
        layers={
            "persona": True,
            "memory": True,
            "skills": True,
            "hitl": True,
            "safety": True,
            "native": True,
            "learning": True,
            "todos": True,
            "code": True,
            "workspace": True,
            "subagents": True,
        },
        settings_overrides={
            "tool_output_offload_threshold": 4000,
            "memory_nudge_every": 10,
        },
        policy_factory=free_policy,
        egress=True,
    )


#: The built-in posture profiles. Extend with :func:`register_posture`.
POSTURES: dict[str, PostureProfile] = {
    Posture.SPECIALIZED.value: _specialized(),
    Posture.HYBRID.value: _hybrid(),
    Posture.FREE.value: _free(),
}


def register_posture(name: str | Posture, profile: PostureProfile) -> PostureProfile:
    """Register (or replace) a named posture profile."""
    POSTURES[str(name)] = profile
    return profile


def resolve_posture(name: str | Posture | None) -> PostureProfile | None:
    """The profile for ``name`` (``None`` when no posture is selected).

    A ``str``/``Posture`` resolves against :data:`POSTURES`; an unknown name
    raises :class:`ValueError` listing the known postures.
    """
    if name is None:
        return None
    if isinstance(name, PostureProfile):
        return name
    key = str(name).strip().lower()
    if not key:
        return None
    try:
        return POSTURES[key]
    except KeyError as exc:
        available = ", ".join(sorted(POSTURES))
        raise ValueError(f"unknown posture {name!r}; choose from {available}") from exc


def apply_settings_overrides(settings: Any, profile: PostureProfile | None) -> Any:
    """Return ``settings`` with a posture's overrides applied (or unchanged).

    An override only applies while the setting is still at its field default, so
    an operator-set (non-default) value always wins. Returns ``settings`` itself
    when ``profile`` is ``None``, declares no overrides, or every override key is
    already non-default — callers can compare with ``is`` to detect a change.
    """
    if settings is None or profile is None or not profile.settings_overrides:
        return settings
    from pydantic_core import PydanticUndefined

    fields = getattr(type(settings), "model_fields", {})
    applicable: dict[str, Any] = {}
    for key, value in profile.settings_overrides.items():
        field = fields.get(key)
        if field is None or not hasattr(settings, key):
            continue
        default = field.get_default(call_default_factory=True)
        if default is PydanticUndefined:
            continue
        if getattr(settings, key) == default:
            applicable[key] = value
    if not applicable:
        return settings
    return settings.model_copy(update=applicable)
