"""Catalog / gallery — pluggable sources of installable specs, skills, and MCPs.

Sources are drivers (``local``, ``skills``, ``http``, ``git``) selected by
``catalog_driver``; installing an item writes it into a *target* (the definitions
store, the skills directory, or the MCP registry). Installation validates the
payload first and never escapes paths.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentkit.contracts.catalog import Catalog, CatalogItem
from agentkit.logging import get_logger
from agentkit.support import register_driver
from agentkit.support.kinds import CatalogDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "CATALOGS",
    "Catalog",
    "CatalogItem",
    "CatalogManager",
    "DefinitionsTarget",
    "HttpCatalog",
    "LocalCatalog",
    "SkillsCatalog",
    "install_item",
    "register_catalog_source",
]

log = get_logger("agentkit.catalog")


def _read_payload(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(text)
    return json.loads(text)


class LocalCatalog:
    """A catalog backed by a directory of ``*.json``/``*.yaml`` items."""

    name = "local"

    def __init__(self, root: str | Path = "catalog") -> None:
        self.root = Path(root)

    def _entries(self) -> dict[str, Path]:
        if not self.root.is_dir():
            return {}
        found: dict[str, Path] = {}
        for path in sorted(self.root.iterdir()):
            if path.suffix.lower() in {".json", ".yaml", ".yml"}:
                found[path.stem] = path
        return found

    async def search(self, query: str = "") -> list[CatalogItem]:
        needle = (query or "").strip().lower()
        items: list[CatalogItem] = []
        for item_id, path in self._entries().items():
            try:
                payload = _read_payload(path)
            except Exception:  # pragma: no cover - tolerate bad files
                continue
            kind = payload.get("spec_kind") or payload.get("kind") or "spec"
            description = str(payload.get("description", ""))
            if needle and needle not in item_id.lower() and needle not in description.lower():
                continue
            items.append(
                CatalogItem(
                    id=item_id,
                    name=str(payload.get("name", item_id)),
                    kind=str(kind),
                    description=description,
                    source=str(path),
                )
            )
        return items

    async def get(self, item_id: str) -> CatalogItem | None:
        path = self._entries().get(item_id)
        if path is None:
            return None
        payload = _read_payload(path)
        return CatalogItem(
            id=item_id,
            name=str(payload.get("name", item_id)),
            kind=str(payload.get("spec_kind") or payload.get("kind") or "spec"),
            source=str(path),
        )

    def payload(self, item_id: str) -> Any:
        path = self._entries().get(item_id)
        return _read_payload(path) if path is not None else None

    async def install(self, item_id: str, target: Any = None) -> Any:
        payload = self.payload(item_id)
        if payload is None:
            raise KeyError(item_id)
        return await install_item(item_id, payload, target)


class HttpCatalog:
    """A catalog backed by a JSON index over HTTP (``{"items": [...]}``)."""

    name = "http"

    def __init__(self, url: str = "", *, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout
        self._index: list[dict[str, Any]] = []

    async def _load(self) -> list[dict[str, Any]]:
        if self._index:
            return self._index
        if not self.url:
            return []
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            data = response.json()
        self._index = list(data.get("items", data if isinstance(data, list) else []))
        return self._index

    async def search(self, query: str = "") -> list[CatalogItem]:
        needle = (query or "").strip().lower()
        items = []
        for entry in await self._load():
            item = _item_from_entry(entry, self.url)
            if needle and needle not in item.id.lower() and needle not in item.description.lower():
                continue
            items.append(item)
        return items

    async def get(self, item_id: str) -> CatalogItem | None:
        for entry in await self._load():
            item = _item_from_entry(entry, self.url)
            if item.id == item_id:
                return item
        return None

    async def install(self, item_id: str, target: Any = None) -> Any:
        item = await self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        payload = await self._fetch_payload(item)
        return await install_item(item_id, payload, target)

    async def _fetch_payload(self, item: CatalogItem) -> Any:
        entry = next(
            (e for e in await self._load() if str(e.get("id", "")) == item.id), None
        )
        source = (entry or {}).get("url") or item.source
        if not source:
            raise ValueError(f"catalog item {item.id!r} has no payload url")
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(source)
            response.raise_for_status()
            text = response.text
        try:
            return json.loads(text)
        except ValueError:
            import yaml

            return yaml.safe_load(text)


class GitCatalog(HttpCatalog):
    """A catalog backed by a JSON index in a git repo (raw URL for GitHub)."""

    name = "git"

    def __init__(
        self,
        repo: str = "",
        *,
        ref: str = "main",
        path: str = "catalog.json",
        timeout: float = 10.0,
    ) -> None:
        self.repo = repo
        self.ref = ref
        self.path = path
        super().__init__(url=_raw_url(repo, ref, path), timeout=timeout)


class SkillsCatalog:
    """A read-only catalog over a skills directory (each skill is an item)."""

    name = "skills"

    def __init__(self, root: str | Path = "skills") -> None:
        self.root = Path(root)

    async def search(self, query: str = "") -> list[CatalogItem]:
        needle = (query or "").strip().lower()
        items: list[CatalogItem] = []
        if not self.root.is_dir():
            return items
        for skill_dir in sorted(self.root.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                continue
            if needle and needle not in skill_dir.name.lower():
                continue
            items.append(
                CatalogItem(
                    id=skill_dir.name,
                    name=skill_dir.name,
                    kind="skill",
                    source=str(skill_file),
                )
            )
        return items

    async def get(self, item_id: str) -> CatalogItem | None:
        for item in await self.search():
            if item.id == item_id:
                return item
        return None

    async def install(self, item_id: str, target: Any = None) -> Any:
        item = await self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        payload = Path(item.source).read_text(encoding="utf-8")
        return await install_item(item_id, {"kind": "skill", "content": payload}, target)


# ---------------------------------------------------------------------------
# Install targets
# ---------------------------------------------------------------------------


class DefinitionsTarget:
    """Install a spec payload into the ``definitions`` spec store."""

    def __init__(self, store: Any) -> None:
        self.store = store

    async def install(self, item: CatalogItem, payload: Any) -> Any:
        from agentkit.specs import SPECS

        kind = payload.get("spec_kind") or payload.get("kind") or item.kind
        if kind not in SPECS.kinds():
            raise ValueError(f"unknown spec kind {kind!r}")
        spec = SPECS.validate(kind, payload)
        await self.store.upsert(kind, spec.name, spec)
        return {"kind": kind, "name": spec.name, "installed": True}


class SkillsTarget:
    """Install a skill payload into a skills directory."""

    def __init__(self, root: str | Path = "skills") -> None:
        self.root = Path(root)

    async def install(self, item: CatalogItem, payload: Any) -> Any:
        name = _safe_name(item.name or item.id)
        directory = (self.root / name).resolve()
        if self.root.resolve() not in directory.parents:
            raise ValueError("skill install would escape the skills directory")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(str(payload.get("content", "")), encoding="utf-8")
        return {"skill": name, "installed": True, "path": str(directory)}


async def install_item(item_id: str, payload: Any, target: Any) -> Any:
    """Validate + install a payload through a target (or return it when no target)."""
    if target is None:
        return {"id": item_id, "payload": payload, "installed": False}
    item = CatalogItem(id=item_id, name=str(payload.get("name", item_id)))
    return await target.install(item, payload)


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value).strip("_") or "item"


def _item_from_entry(entry: dict[str, Any], base: str) -> CatalogItem:
    return CatalogItem(
        id=str(entry.get("id", "")),
        name=str(entry.get("name", entry.get("id", ""))),
        kind=str(entry.get("kind", "spec")),
        description=str(entry.get("description", "")),
        version=str(entry.get("version", "")),
        source=str(entry.get("url", base)),
    )


def _raw_url(repo: str, ref: str, path: str) -> str:
    if not repo:
        return ""
    if "github.com" in repo and not repo.startswith("http"):
        repo = f"https://github.com/{repo}"
    if repo.endswith(".git"):
        repo = repo[:-4]
    if "github.com" in repo:
        return f"{repo.replace('github.com', 'raw.githubusercontent.com')}/{ref}/{path}"
    return f"{repo.rstrip('/')}/{path}"


# ---------------------------------------------------------------------------
# Registry + drivers
# ---------------------------------------------------------------------------

CATALOGS: dict[str, Callable[[Any], Any]] = {}


def register_catalog_source(name: str, factory: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Register a named catalog source *factory* (an extension contribution)."""
    CATALOGS[str(name)] = factory
    return factory


class CatalogManager(Manager):
    """Resolves the configured catalog driver (``catalog_driver``)."""

    kind = DriverKind.CATALOG
    default_driver = CatalogDriver.LOCAL

    def create_local_driver(self, app: Any) -> LocalCatalog:
        return LocalCatalog(getattr(app.settings, "catalog_dir", None) or "catalog")

    def create_skills_driver(self, app: Any) -> SkillsCatalog:
        return SkillsCatalog(getattr(app.settings, "skills_dir", None) or "skills")

    def create_http_driver(self, app: Any) -> HttpCatalog:
        return HttpCatalog(getattr(app.settings, "catalog_url", "") or "")

    def create_git_driver(self, app: Any) -> GitCatalog:
        return GitCatalog(
            getattr(app.settings, "catalog_repo", "") or "",
            ref=getattr(app.settings, "catalog_ref", "main"),
            path=getattr(app.settings, "catalog_path", "catalog.json"),
        )


def catalog_source(name: str, app: Any = None) -> Any:
    """Resolve a named catalog source factory to an instance."""
    factory = CATALOGS.get(name)
    if factory is None:
        return None
    return factory(app)


@register_driver(DriverKind.CATALOG, CatalogDriver.LOCAL)
def _local_catalog_driver(app: Any) -> LocalCatalog:
    return LocalCatalog(getattr(app.settings, "catalog_dir", None) or "catalog")


@register_driver(DriverKind.CATALOG, CatalogDriver.SKILLS)
def _skills_catalog_driver(app: Any) -> SkillsCatalog:
    return SkillsCatalog(getattr(app.settings, "skills_dir", None) or "skills")


@register_driver(DriverKind.CATALOG, CatalogDriver.HTTP)
def _http_catalog_driver(app: Any) -> HttpCatalog:
    return HttpCatalog(getattr(app.settings, "catalog_url", "") or "")


@register_driver(DriverKind.CATALOG, CatalogDriver.GIT)
def _git_catalog_driver(app: Any) -> GitCatalog:
    return GitCatalog(
        getattr(app.settings, "catalog_repo", "") or "",
        ref=getattr(app.settings, "catalog_ref", "main"),
        path=getattr(app.settings, "catalog_path", "catalog.json"),
    )
