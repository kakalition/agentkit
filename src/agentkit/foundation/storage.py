"""Storage — Laravel's filesystem facade for agent artifacts.

A thin, root-confined filesystem under ``<agent_home>/storage``::

    from agentkit import Storage

    Storage.put("reports/q4.md", "...")
    Storage.get("reports/q4.md")
    Storage.list("reports")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.errors import InvalidInput

__all__ = ["Filesystem"]


class Filesystem:
    """A root-confined file store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str | Path = ".") -> Path:
        target = (self.root / relative).resolve()
        if target != self.root and self.root not in target.parents:
            raise InvalidInput(f"path {relative!r} escapes storage")
        return target

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:  # pragma: no cover - resolve() prevents this
            return path.as_posix()

    def put(self, relative: str | Path, data: str | bytes) -> str:
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            target.write_bytes(data)
        else:
            target.write_text(data, encoding="utf-8")
        return self._rel(target)

    def get(self, relative: str | Path) -> str:
        return self.resolve(relative).read_text(encoding="utf-8")

    def get_bytes(self, relative: str | Path) -> bytes:
        return self.resolve(relative).read_bytes()

    def exists(self, relative: str | Path) -> bool:
        return self.resolve(relative).exists()

    def list(self, prefix: str = "") -> list[str]:
        target = self.resolve(prefix) if prefix else self.root
        if not target.exists():
            return []
        if target.is_file():
            return [self._rel(target)]
        return sorted(self._rel(child) for child in target.rglob("*") if child.is_file())

    def delete(self, relative: str | Path) -> bool:
        target = self.resolve(relative)
        if target.is_file():
            target.unlink()
            return True
        return False

    def metadata(self, relative: str | Path) -> dict[str, Any]:
        target = self.resolve(relative)
        stat = target.stat()
        return {"path": self._rel(target), "size": stat.st_size, "modified": stat.st_mtime}
