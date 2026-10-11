"""Workspace layout helpers: ``~/.agentkit/<agent_name>`` + legacy migration.

agentkit keeps every agent under one workspace root (default ``~/.agentkit``);
an agent's home is ``<workspace_root>/<agent_name>``. The old
``~/.local/share/...`` locations are detected so existing data can be migrated
in place.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agentkit.config import DEFAULT_WORKSPACE_ROOT
from agentkit.errors import Conflict

# Legacy layout: agents used agentkit's old shared home, or their own dir.
LEGACY_ROOTS = ("~/.local/share/agentkit", "~/.local/share/{name}")
_SHARED_ROOT_NAME = "agentkit"
_MOVABLE_FILES = ("dbos.sqlite", "SOUL.md")
_MOVABLE_DIRS = ("artifacts", "logs")


def default_workspace_root() -> Path:
    return Path(DEFAULT_WORKSPACE_ROOT).expanduser()


def workspace_dir(name: str, *, root: Path | str | None = None) -> Path:
    """The agent home under ``root`` (default: the workspace root)."""
    base = Path(root).expanduser() if root is not None else default_workspace_root()
    return base / name


def _payload_names(path: Path) -> list[str]:
    """Agent artifacts present directly under ``path`` (db files + known items)."""
    if not path.is_dir():
        return []
    found = sorted(db.name for db in path.glob("*.db"))
    for item in (*_MOVABLE_FILES, *_MOVABLE_DIRS):
        if (path / item).exists():
            found.append(item)
    return found


def _legacy_candidates(name: str) -> list[Path]:
    out: list[Path] = []
    for template in LEGACY_ROOTS:
        candidate = Path(template.format(name=name)).expanduser()
        if candidate not in out:
            out.append(candidate)
    return out


def _has_name_data(path: Path, name: str) -> bool:
    """Name-aware check, so a shared/unrelated dir is not claimed by the wrong agent.

    A legacy agent home must hold *this* agent's database (``<name>.db`` or the
    generic ``agent.db``); a name-specific root may also hold only ``dbos.sqlite``.
    Mere ``artifacts``/``logs``/``SOUL.md`` presences are not enough — unrelated
    app dirs under ``~/.local/share`` also have those.
    """
    if not path.is_dir():
        return False
    if (path / f"{name}.db").exists() or (path / "agent.db").exists():
        return True
    if path.name == _SHARED_ROOT_NAME:
        return False
    return (path / "dbos.sqlite").exists()


def detect_legacy(name: str) -> Path | None:
    """Return the legacy home holding data for ``name`` (or ``None``)."""
    for candidate in _legacy_candidates(name):
        if _has_name_data(candidate, name):
            return candidate
    return None


def is_populated(path: Path | str) -> bool:
    return bool(_payload_names(Path(path)))


def migrate(name: str, *, root: Path | str | None = None, move: bool = True) -> dict:
    """Move (or copy) legacy data for ``name`` under the workspace root.

    Raises :class:`~agentkit.errors.Conflict` when the target already holds data
    (never overwrites) and is a safe no-op when there is nothing to migrate.
    """
    target = workspace_dir(name, root=root)
    legacy = detect_legacy(name)
    if legacy is None:
        return {
            "migrated": False,
            "reason": "no legacy data found",
            "name": name,
            "source": None,
            "target": str(target),
            "items": [],
            "mode": None,
        }
    if is_populated(target):
        raise Conflict(
            f"{target} already contains agent data; refusing to overwrite",
            detail={"target": str(target)},
        )
    target.mkdir(parents=True, exist_ok=True)
    items: list[str] = []
    for name_ in _payload_names(legacy):
        src = legacy / name_
        dest = target / name_
        if dest.exists():
            continue
        if move:
            shutil.move(str(src), str(dest))
        elif src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        items.append(name_)
    return {
        "migrated": bool(items),
        "reason": None if items else "nothing to migrate",
        "name": name,
        "source": str(legacy),
        "target": str(target),
        "items": items,
        "mode": "move" if move else "copy",
    }
