"""Typed dependencies shared by every agent run (the ``RunContext`` payload)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentkit.security import Actor


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ApprovalRequest:
    """A pending tool call awaiting user approval."""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any]


ApprovalCallback = Callable[[list[ApprovalRequest]], Awaitable[dict[str, bool]]]


@dataclass(slots=True)
class CommsContext:
    """First-class agent-comms state carried on :class:`Deps`.

    Replaces the ad-hoc ``extras["_mailbox_sender"]`` / ``extras["_handoff_depth"]``
    flags; the legacy ``extras`` keys are still honored for compatibility.
    """

    sender: str | None = None
    handoff_depth: int = 0


@dataclass
class Deps:
    """Everything an agent tool might need. Extend via ``extras``.

    ``repos`` is the domain repository container (a session-bound object with
    whatever repos the app defines). ``mcp``/``a2a`` are optional collaborators.
    """

    settings: Any
    repos: Any = None
    model: Any = None
    mcp: Any = None
    a2a: Any = None
    approve: ApprovalCallback | None = None
    actor: Actor | None = None
    credentials: Any = None
    clock: Any = field(default=_now)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
    comms: CommsContext = field(default_factory=CommsContext)

    def now(self) -> datetime:
        return self.clock()

    def remember_artifact(self, kind: str, path: str, description: str = "") -> None:
        self.artifacts.append({"kind": kind, "path": path, "description": description})

    @property
    def owner_id(self) -> str:
        if self.actor is not None:
            return self.actor.owner_id
        return getattr(self.settings, "owner_id", "owner")

    @property
    def conversation_id(self) -> str:
        """The conversation this turn belongs to (set by ``ChatRunner``)."""
        return self.extras.get("conversation_id", "cli:default")
