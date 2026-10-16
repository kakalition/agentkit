"""Run tracing: a uniform :class:`RunEvent` for every runner + recorders.

Every runner (``ChatRunner``, ``GroupChatRunner``, ``ManagedTeam``, graph
executors) can accept an optional ``recorder`` and emit the same event shape. With
no recorder there is no behavior change; a :class:`RepositoryRunRecorder` buffers
events and flushes them to the ``run_events`` table at the end of a run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentkit.contracts.run import RunRecorder as RunRecorderProtocol
from agentkit.contracts.run import RunStore

__all__ = [
    "CompositeRecorder",
    "InMemoryRecorder",
    "RepositoryRunRecorder",
    "RunEvent",
    "RunRecorder",
    "RunRecorderProtocol",
    "RunStore",
    "recorder_for",
]

RUN_EVENT_KINDS = (
    "start",
    "turn",
    "tool",
    "compaction",
    "checkpoint",
    "approval",
    "error",
    "final",
)


@dataclass
class RunEvent:
    """One uniform increment of a run (a superset of ``session.StreamEvent``)."""

    kind: str
    run_id: str = ""
    seq: int = 0
    text: str = ""
    tool: str = ""
    node: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "run_id": self.run_id,
            "seq": self.seq,
            "text": self.text,
            "tool": self.tool,
            "node": self.node,
            "data": self.data,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunEvent:
        return cls(
            kind=str(data.get("kind", "")),
            run_id=str(data.get("run_id", "")),
            seq=int(data.get("seq", 0) or 0),
            text=str(data.get("text", "") or ""),
            tool=str(data.get("tool", "") or ""),
            node=str(data.get("node", "") or ""),
            data=dict(data.get("data") or {}),
            created_at=str(data.get("created_at", "") or ""),
        )

    @classmethod
    def from_stream_event(cls, event: Any, *, run_id: str = "") -> RunEvent:
        """Adapt a :class:`~agentkit.session.StreamEvent` into a ``RunEvent``."""
        kind = getattr(event, "kind", "text")
        data: dict[str, Any] = {}
        result = getattr(event, "result", None)
        if kind == "final" and result is not None:
            data["output"] = getattr(result, "output", "")
            data["usage"] = getattr(result, "usage", None)
            data["tool_calls"] = list(getattr(result, "tool_calls", []) or [])
        return cls(kind=kind, run_id=run_id, text=getattr(event, "text", "") or "",
                   tool=getattr(event, "tool", "") or "", data=data)


class RunRecorder:
    """Base recorder: buffers events in memory and assigns sequence numbers."""

    def __init__(self, run_id: str = "") -> None:
        self.run_id = run_id
        self.events: list[RunEvent] = []

    def record(self, event: RunEvent) -> RunEvent:
        if not event.run_id:
            event.run_id = self.run_id
        event.seq = len(self.events)
        self.events.append(event)
        return event

    def emit(self, kind: str, **fields: Any) -> RunEvent:
        return self.record(RunEvent(kind=kind, **fields))

    async def flush(self) -> None:  # pragma: no cover - base is a no-op
        return None


class InMemoryRecorder(RunRecorder):
    """A recorder that only keeps events in memory (tests + ephemeral runs)."""


class CompositeRecorder(RunRecorder):
    """Fan out each event to several recorders."""

    def __init__(self, *recorders: RunRecorder, run_id: str = "") -> None:
        super().__init__(run_id or (recorders[0].run_id if recorders else ""))
        self._recorders = list(recorders)

    def record(self, event: RunEvent) -> RunEvent:
        super().record(event)
        for recorder in self._recorders:
            recorder.record(event)
        return event

    async def flush(self) -> None:
        for recorder in self._recorders:
            await recorder.flush()


class RepositoryRunRecorder(RunRecorder):
    """Buffers events and flushes them to a run-event store (``run_events``)."""

    def __init__(self, store: Any, run_id: str = "", *, retention: int | None = None) -> None:
        super().__init__(run_id)
        self.store = store
        self.retention = retention

    async def flush(self) -> None:
        if self.store is None or not self.events:
            return
        events = self.events
        if self.retention and len(events) > self.retention:
            events = events[-self.retention :]
        await self.store.add_many(self.run_id, [event.to_dict() for event in events])
        self.events.clear()


def recorder_for(repos: Any, run_id: str, *, enabled: bool = True) -> RunRecorder:
    """The recorder for a run: repository-backed when enabled, else in-memory."""
    if enabled:
        store = getattr(repos, "run_events", None)
        if store is not None:
            return RepositoryRunRecorder(store, run_id)
    return InMemoryRecorder(run_id)
