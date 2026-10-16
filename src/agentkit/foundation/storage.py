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

from agentkit.contracts.storage import FileSystem
from agentkit.errors import ConfigurationError, InvalidInput
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, StorageDriver
from agentkit.support.manager import Manager

__all__ = [
    "CompositeFileSystem",
    "FileSystem",
    "Filesystem",
    "MemoryFilesystem",
    "S3FileSystem",
    "StorageManager",
]


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

    def disk(self, name: str) -> Filesystem:
        """A named disk (a subdirectory), like Laravel's ``Storage::disk``."""
        return Filesystem(self.root / name)

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

    def glob(self, pattern: str) -> list[str]:
        """Files whose relative path matches an fnmatch ``pattern``."""
        import fnmatch

        return sorted(rel for rel in self.list() if fnmatch.fnmatch(rel, pattern))

    def grep(self, pattern: str, *, prefix: str = "") -> list[tuple[str, int, str]]:
        """``(path, line_number, line)`` for every line matching ``pattern``."""
        import re

        regex = re.compile(pattern)
        hits: list[tuple[str, int, str]] = []
        for relative in self.list(prefix):
            try:
                text = self.get(relative)
            except Exception:  # pragma: no cover - unreadable/binary
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    hits.append((relative, number, line))
        return hits

    def edit_file(self, relative: str | Path, old: str, new: str, *, count: int = 1) -> int:
        """Replace occurrences of ``old`` with ``new``; returns replacements made."""
        text = self.get(relative)
        updated = text.replace(old, new, count)
        if updated == text:
            return 0
        self.put(relative, updated)
        return 1


class MemoryFilesystem:
    """An in-process filesystem driver (useful for tests and ephemeral agents)."""

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix.strip("/")
        self._files: dict[str, bytes] = {}

    def _key(self, relative: str | Path) -> str:
        key = Path(relative).as_posix().lstrip("/")
        if ".." in Path(key).parts:
            raise InvalidInput(f"path {relative!r} escapes storage")
        return f"{self._prefix}/{key}" if self._prefix else key

    def disk(self, name: str) -> MemoryFilesystem:
        return MemoryFilesystem(f"{self._prefix}/{name}" if self._prefix else name)

    def put(self, relative: str | Path, data: str | bytes) -> str:
        key = self._key(relative)
        self._files[key] = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        return key

    def get(self, relative: str | Path) -> str:
        return self.get_bytes(relative).decode("utf-8")

    def get_bytes(self, relative: str | Path) -> bytes:
        key = self._key(relative)
        if key not in self._files:
            raise InvalidInput(f"file not found: {relative}")
        return self._files[key]

    def exists(self, relative: str | Path) -> bool:
        return self._key(relative) in self._files

    def list(self, prefix: str = "") -> list[str]:
        scope = self._key(prefix) if prefix else self._prefix
        scope = f"{scope}/" if scope else ""
        return sorted(key for key in self._files if key.startswith(scope))

    def delete(self, relative: str | Path) -> bool:
        return self._files.pop(self._key(relative), None) is not None

    def metadata(self, relative: str | Path) -> dict[str, Any]:
        key = self._key(relative)
        if key not in self._files:
            raise InvalidInput(f"file not found: {relative}")
        return {"path": key, "size": len(self._files[key]), "modified": 0.0}


class S3FileSystem:
    """A :class:`FileSystem` over an S3 bucket (needs the ``s3`` extra: boto3).

    Same root-confined surface as :class:`Filesystem`; ``disk(name)`` maps to a key
    prefix. Constructing it does not import boto3 — the client is created lazily on
    first use, so the class is import-safe when the extra is absent.
    """

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = "",
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.region = region
        self.endpoint_url = endpoint_url
        self._client = client

    def _boto(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ImportError as exc:
            raise ConfigurationError(
                "this storage driver needs the 's3' extra (pip install agentkit[s3])"
            ) from exc
        self._client = boto3.client("s3", region_name=self.region, endpoint_url=self.endpoint_url)
        return self._client

    def _key(self, relative: str | Path) -> str:
        key = Path(relative).as_posix().lstrip("/")
        if ".." in Path(key).parts:
            raise InvalidInput(f"path {relative!r} escapes storage")
        return f"{self.prefix}/{key}" if self.prefix else key

    def disk(self, name: str) -> S3FileSystem:
        prefix = f"{self.prefix}/{name}".strip("/")
        return S3FileSystem(
            self.bucket,
            prefix=prefix,
            region=self.region,
            endpoint_url=self.endpoint_url,
            client=self._client,
        )

    def put(self, relative: str | Path, data: str | bytes) -> str:
        body = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        key = self._key(relative)
        self._boto().put_object(Bucket=self.bucket, Key=key, Body=body)
        return key

    def get(self, relative: str | Path) -> str:
        return self.get_bytes(relative).decode("utf-8")

    def get_bytes(self, relative: str | Path) -> bytes:
        client = self._boto()  # resolve first so a missing extra is not masked
        try:
            response = client.get_object(Bucket=self.bucket, Key=self._key(relative))
        except Exception as exc:  # noqa: BLE001 - map any S3 error to a domain error
            raise InvalidInput(f"file not found: {relative}") from exc
        return response["Body"].read()

    def exists(self, relative: str | Path) -> bool:
        client = self._boto()
        try:
            client.head_object(Bucket=self.bucket, Key=self._key(relative))
            return True
        except Exception:  # noqa: BLE001
            return False

    def list(self, prefix: str = "") -> list[str]:
        scope = self._key(prefix) if prefix else self.prefix
        scope = f"{scope}/" if scope else ""
        client = self._boto()
        found: list[str] = []
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": scope}
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                key = obj["Key"]
                if self.prefix and key.startswith(f"{self.prefix}/"):
                    key = key[len(self.prefix) + 1 :]
                found.append(key)
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return sorted(found)

    def delete(self, relative: str | Path) -> bool:
        client = self._boto()
        try:
            client.delete_object(Bucket=self.bucket, Key=self._key(relative))
            return True
        except Exception:  # noqa: BLE001
            return False

    def metadata(self, relative: str | Path) -> dict[str, Any]:
        client = self._boto()
        try:
            head = client.head_object(Bucket=self.bucket, Key=self._key(relative))
        except Exception as exc:  # noqa: BLE001
            raise InvalidInput(f"file not found: {relative}") from exc
        return {
            "path": self._key(relative),
            "size": head.get("ContentLength", 0),
            "modified": head.get("LastModified"),
        }

    def glob(self, pattern: str) -> list[str]:
        import fnmatch

        return sorted(rel for rel in self.list() if fnmatch.fnmatch(rel, pattern))


class StorageManager(Manager):
    """Resolves the configured storage driver (``storage_driver``, default ``local``)."""

    kind = DriverKind.STORAGE
    default_driver = StorageDriver.LOCAL


class CompositeFileSystem:
    """Read through a stack of stores; write to the first (overlayfs-style)."""

    def __init__(self, *stores: Any) -> None:
        if not stores:
            raise InvalidInput("CompositeFileSystem needs at least one store")
        self.stores = list(stores)

    def put(self, relative: str | Path, data: str | bytes) -> str:
        return self.stores[0].put(relative, data)

    def _find(self, relative: str | Path) -> Any:
        for store in self.stores:
            if store.exists(relative):
                return store
        return None

    def get(self, relative: str | Path) -> str:
        store = self._find(relative)
        if store is None:
            raise InvalidInput(f"file not found: {relative}")
        return store.get(relative)

    def get_bytes(self, relative: str | Path) -> bytes:
        store = self._find(relative)
        if store is None:
            raise InvalidInput(f"file not found: {relative}")
        return store.get_bytes(relative)

    def exists(self, relative: str | Path) -> bool:
        return self._find(relative) is not None

    def list(self, prefix: str = "") -> list[str]:
        seen: set[str] = set()
        for store in self.stores:
            seen.update(store.list(prefix))
        return sorted(seen)

    def delete(self, relative: str | Path) -> bool:
        store = self._find(relative)
        return bool(store.delete(relative)) if store is not None else False

    def metadata(self, relative: str | Path) -> dict[str, Any]:
        store = self._find(relative)
        if store is None:
            raise InvalidInput(f"file not found: {relative}")
        return store.metadata(relative)

    def glob(self, pattern: str) -> list[str]:
        import fnmatch

        return sorted(rel for rel in self.list() if fnmatch.fnmatch(rel, pattern))


@register_driver(DriverKind.STORAGE, StorageDriver.LOCAL)
def _local_storage_driver(app: Any) -> Filesystem:
    return Filesystem(app.settings.home / "storage")


@register_driver(DriverKind.STORAGE, StorageDriver.MEMORY)
def _memory_storage_driver(app: Any) -> MemoryFilesystem:
    return MemoryFilesystem()


@register_driver(DriverKind.STORAGE, StorageDriver.S3)
def _s3_storage_driver(app: Any) -> S3FileSystem:
    settings = app.settings
    bucket = getattr(settings, "s3_bucket", None)
    if not bucket:
        raise ConfigurationError("storage_driver=s3 requires S3_BUCKET to be set")
    return S3FileSystem(
        bucket,
        prefix=getattr(settings, "s3_prefix", ""),
        region=getattr(settings, "s3_region", None),
        endpoint_url=getattr(settings, "s3_endpoint_url", None),
    )
