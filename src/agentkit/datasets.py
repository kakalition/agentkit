"""Eval datasets: named case collections stored inline or imported from disk.

The default ``repository`` driver persists to the ``eval_datasets`` table;
``memory`` keeps them in-process (tests). ``load_dataset_file`` parses CSV, JSON,
or JSONL into a list of case dicts for import.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agentkit.contracts.dataset import DatasetStore
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DatasetDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "DatasetManager",
    "DatasetStore",
    "MemoryDatasetStore",
    "RepositoryDatasetStore",
    "load_dataset_file",
]


def load_dataset_file(path: str | Path) -> list[dict[str, Any]]:
    """Parse ``path`` (``.csv``/``.json``/``.jsonl``) into a list of case dicts."""
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".csv":
        with file.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix in {".jsonl", ".ndjson"}:
        cases: list[dict[str, Any]] = []
        for line in file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                cases.append(json.loads(line))
        return cases
    data = json.loads(file.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [case if isinstance(case, dict) else {"input": case} for case in data]
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return list(data["cases"])
    return [data]  # a single case object


class MemoryDatasetStore:
    """An in-process dataset store (the default for tests)."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    async def put(self, name: str, cases: list[dict[str, Any]], *, source: str = "") -> Any:
        self._rows[name] = {"name": name, "cases": list(cases), "source": source}
        return self._rows[name]

    async def get(self, name: str) -> Any | None:
        return self._rows.get(name)

    async def remove(self, name: str) -> bool:
        return self._rows.pop(name, None) is not None

    async def cases(self, name: str) -> list[dict[str, Any]]:
        row = self._rows.get(name)
        return list(row["cases"]) if row else []

    async def list(self) -> list[Any]:
        return [self._rows[key] for key in sorted(self._rows)]


class RepositoryDatasetStore:
    """A dataset store over the ``eval_datasets`` table (the default driver)."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def put(self, name: str, cases: list[dict[str, Any]], *, source: str = "") -> Any:
        async with self.app.repositories() as repos:
            return await repos.eval_datasets.upsert(name, cases=cases, source=source)

    async def get(self, name: str) -> Any | None:
        async with self.app.repositories() as repos:
            return await repos.eval_datasets.get(name)

    async def remove(self, name: str) -> bool:
        async with self.app.repositories() as repos:
            return await repos.eval_datasets.remove(name)

    async def cases(self, name: str) -> list[dict[str, Any]]:
        record = await self.get(name)
        if record is None:
            return []
        try:
            parsed = json.loads(record.cases or "[]")
        except ValueError:  # pragma: no cover - tolerate corrupt rows
            return []
        return list(parsed) if isinstance(parsed, list) else []

    async def list(self) -> list[Any]:
        async with self.app.repositories() as repos:
            return await repos.eval_datasets.list()


class DatasetManager(Manager):
    """Resolves the configured dataset store (``dataset_driver``)."""

    kind = DriverKind.DATASET
    default_driver = DatasetDriver.REPOSITORY

    def create_memory_driver(self, app: Any) -> MemoryDatasetStore:
        return MemoryDatasetStore()

    def create_repository_driver(self, app: Any) -> RepositoryDatasetStore:
        return RepositoryDatasetStore(app)


@register_driver(DriverKind.DATASET, DatasetDriver.MEMORY)
class MemoryDatasetDriver(Driver):
    def build(self) -> MemoryDatasetStore:
        return MemoryDatasetStore()


@register_driver(DriverKind.DATASET, DatasetDriver.REPOSITORY)
class RepositoryDatasetDriver(Driver):
    def build(self) -> RepositoryDatasetStore:
        app = self.app
        return RepositoryDatasetStore(app)
