"""The filesystem contract — a root-confined object/file store."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = ["FileSystem"]


@runtime_checkable
class FileSystem(Protocol):
    """Store and retrieve files under a root."""

    def put(self, relative: str | Path, data: str | bytes) -> str: ...

    def get(self, relative: str | Path) -> str: ...

    def get_bytes(self, relative: str | Path) -> bytes: ...

    def exists(self, relative: str | Path) -> bool: ...

    def list(self, prefix: str = "") -> list[str]: ...

    def delete(self, relative: str | Path) -> bool: ...

    def metadata(self, relative: str | Path) -> dict[str, Any]: ...
