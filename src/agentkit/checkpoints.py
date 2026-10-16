"""Checkpoint stores + the ``CHECKPOINT`` driver kind (run time travel).

Drivers: ``memory`` (tests), ``file`` (JSONL under ``<home>/checkpoints``), and
``repository`` (the ``checkpoints`` table; the default). Retention is bounded per
run so history never grows without bound.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentkit.contracts.checkpoint import CheckpointStore
from agentkit.support import register_driver
from agentkit.support.kinds import CheckpointDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "Checkpoint",
    "CheckpointManager",
    "CheckpointStore",
    "FileCheckpointStore",
    "MemoryCheckpointStore",
    "RepositoryCheckpointStore",
    "checkpointer_for",
]


@dataclass
class Checkpoint:
    """One saved run state."""

    run_id: str
    seq: int
    state: Any
    label: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "state": self.state,
            "label": self.label,
            "created_at": self.created_at,
        }


class MemoryCheckpointStore:
    """An in-process checkpoint store (bounded per run)."""

    def __init__(self, *, retention: int = 50) -> None:
        self.retention = retention
        self._runs: dict[str, list[Checkpoint]] = {}

    async def put(self, run_id: str, seq: int, state: Any, *, label: str = "") -> Checkpoint:
        record = Checkpoint(run_id=run_id, seq=int(seq), state=copy.deepcopy(state), label=label)
        bucket = self._runs.setdefault(run_id, [])
        bucket.append(record)
        if self.retention and len(bucket) > self.retention:
            del bucket[: len(bucket) - self.retention]
        return record

    async def get(self, run_id: str, seq: int) -> Checkpoint | None:
        for record in self._runs.get(run_id, []):
            if record.seq == seq:
                return record
        return None

    async def list(self, run_id: str) -> list[Checkpoint]:
        return sorted(self._runs.get(run_id, []), key=lambda record: record.seq)

    async def latest(self, run_id: str) -> Checkpoint | None:
        rows = self._runs.get(run_id, [])
        return rows[-1] if rows else None

    async def delete(self, run_id: str) -> int:
        return len(self._runs.pop(run_id, []))


class FileCheckpointStore:
    """A JSONL checkpoint store rooted at ``root`` (one file per run)."""

    def __init__(self, root: str | Path = ".checkpoints", *, retention: int = 50) -> None:
        self.root = Path(root)
        self.retention = retention

    def _path(self, run_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in run_id) or "run"
        return self.root / f"{safe}.jsonl"

    def _read(self, run_id: str) -> list[Checkpoint]:
        path = self._path(run_id)
        if not path.is_file():
            return []
        records: list[Checkpoint] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            records.append(
                Checkpoint(
                    run_id=data["run_id"],
                    seq=int(data["seq"]),
                    state=data.get("state"),
                    label=data.get("label", ""),
                    created_at=data.get("created_at", ""),
                )
            )
        return records

    def _write(self, run_id: str, records: list[Checkpoint]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        body = "\n".join(json.dumps(record.to_dict(), default=str) for record in records)
        self._path(run_id).write_text(body + ("\n" if body else ""), encoding="utf-8")

    async def put(self, run_id: str, seq: int, state: Any, *, label: str = "") -> Checkpoint:
        record = Checkpoint(run_id=run_id, seq=int(seq), state=copy.deepcopy(state), label=label)
        records = self._read(run_id)
        records.append(record)
        if self.retention and len(records) > self.retention:
            records = records[-self.retention :]
        self._write(run_id, records)
        return record

    async def get(self, run_id: str, seq: int) -> Checkpoint | None:
        for record in self._read(run_id):
            if record.seq == seq:
                return record
        return None

    async def list(self, run_id: str) -> list[Checkpoint]:
        return sorted(self._read(run_id), key=lambda record: record.seq)

    async def latest(self, run_id: str) -> Checkpoint | None:
        rows = self._read(run_id)
        return rows[-1] if rows else None

    async def delete(self, run_id: str) -> int:
        records = self._read(run_id)
        path = self._path(run_id)
        if path.is_file():
            path.unlink()
        return len(records)


class RepositoryCheckpointStore:
    """A checkpoint store over the ``checkpoints`` table (default driver)."""

    def __init__(self, runtime: Any, *, retention: int = 50) -> None:
        self.runtime = runtime
        self.retention = retention

    async def put(self, run_id: str, seq: int, state: Any, *, label: str = "") -> Any:
        from agentkit.runtime import repositories

        async with repositories(self.runtime) as repos:
            record = await repos.checkpoints.add(run_id, seq, state, label=label)
            if self.retention:
                await repos.checkpoints.prune(run_id, self.retention)
            return record

    async def get(self, run_id: str, seq: int) -> Any | None:
        from agentkit.runtime import repositories

        async with repositories(self.runtime) as repos:
            return await repos.checkpoints.get(run_id, seq)

    async def list(self, run_id: str) -> list[Any]:
        from agentkit.runtime import repositories

        async with repositories(self.runtime) as repos:
            return await repos.checkpoints.list(run_id)

    async def latest(self, run_id: str) -> Any | None:
        from agentkit.runtime import repositories

        async with repositories(self.runtime) as repos:
            return await repos.checkpoints.latest(run_id)

    async def delete(self, run_id: str) -> int:
        from agentkit.runtime import repositories

        async with repositories(self.runtime) as repos:
            return await repos.checkpoints.remove(run_id)


class CheckpointManager(Manager):
    """Resolves the configured checkpoint store (``checkpoint_driver``)."""

    kind = DriverKind.CHECKPOINT
    default_driver = CheckpointDriver.REPOSITORY

    def create_memory_driver(self, app: Any) -> MemoryCheckpointStore:
        return MemoryCheckpointStore(retention=_retention(app))

    def create_file_driver(self, app: Any) -> FileCheckpointStore:
        root = Path(getattr(app.settings, "home", ".")) / "checkpoints"
        return FileCheckpointStore(root, retention=_retention(app))

    def create_repository_driver(self, app: Any) -> RepositoryCheckpointStore:
        return RepositoryCheckpointStore(app.runtime, retention=_retention(app))


def _retention(app: Any) -> int:
    return int(getattr(app.settings, "checkpoint_retention", 50) or 0)


@register_driver(DriverKind.CHECKPOINT, CheckpointDriver.MEMORY)
def _memory_checkpoint_driver(app: Any) -> MemoryCheckpointStore:
    return MemoryCheckpointStore(retention=_retention(app))


@register_driver(DriverKind.CHECKPOINT, CheckpointDriver.FILE)
def _file_checkpoint_driver(app: Any) -> FileCheckpointStore:
    return FileCheckpointStore(
        Path(getattr(app.settings, "home", ".")) / "checkpoints", retention=_retention(app)
    )


def checkpointer_for(repos: Any, *, enabled: bool = False, retention: int = 50) -> Any:
    """A repository-backed checkpoint store over a live ``repos`` container.

    Used by runners that already hold a repository scope (no new sessions).
    """
    if not enabled:
        return None
    store = getattr(repos, "checkpoints", None)
    if store is None:
        return None
    return _ScopeCheckpointStore(store, retention=retention)


class _ScopeCheckpointStore:
    """A :class:`CheckpointStore` over an existing :class:`CheckpointRepo`."""

    def __init__(self, repo: Any, *, retention: int = 50) -> None:
        self.repo = repo
        self.retention = retention

    async def put(self, run_id: str, seq: int, state: Any, *, label: str = "") -> Any:
        record = await self.repo.add(run_id, seq, state, label=label)
        if self.retention:
            await self.repo.prune(run_id, self.retention)
        return record

    async def get(self, run_id: str, seq: int) -> Any | None:
        return await self.repo.get(run_id, seq)

    async def list(self, run_id: str) -> list[Any]:
        return await self.repo.list(run_id)

    async def latest(self, run_id: str) -> Any | None:
        return await self.repo.latest(run_id)

    async def delete(self, run_id: str) -> int:
        return await self.repo.remove(run_id)


#: Convenience alias mirroring the manager/driver naming.
Checkpointer = Callable[..., Any]
