"""Workspace commands: list and migrate agent homes (class-based)."""

from __future__ import annotations

from pathlib import Path

import typer

from agentkit.foundation import Command
from agentkit.workspace import default_workspace_root, detect_legacy, migrate, workspace_dir


class WorkspaceListCommand(Command):
    group = 'workspace'
    signature = "workspace:list {--root=}"
    description = "List agent homes under the workspace root (and any legacy data)."

    def handle(self, root: Path | None = None) -> None:
        base = root.expanduser() if root else default_workspace_root()
        self.info(f"workspace root: {base}")
        names: list[str] = []
        if base.is_dir():
            names = sorted(p.name for p in base.iterdir() if p.is_dir())
        if not names:
            self.info("  (no agent homes yet)")
        for name in names:
            home = workspace_dir(name, root=base)
            has_db = any(home.glob("*.db"))
            self.info(f"  {name}: {home}{'' if has_db else ' (no database)'}")
        for name in _legacy_agent_names():
            where = detect_legacy(name)
            if where is not None and not (base / name).exists():
                self.info(
                    f"  {name}: legacy data at {where} (run: agentkit workspace migrate {name})"
                )


class WorkspaceMigrateCommand(Command):
    group = 'workspace'
    signature = "workspace:migrate {name} {--root=} {--copy}"
    description = "Move legacy ``~/.local/share/...`` data under the workspace root."

    def handle(self, name: str, root: Path | None = None, copy: bool = False) -> None:
        from agentkit.errors import Conflict

        try:
            summary = migrate(name, root=root, move=not copy)
        except Conflict as exc:
            self.error(str(exc))
            raise typer.Exit(code=1) from exc
        if not summary["migrated"]:
            self.info(f"nothing to migrate for {name} ({summary['reason']})")
            return
        verb = "copied" if summary["mode"] == "copy" else "moved"
        self.info(f"{verb} {summary['items']} from {summary['source']} -> {summary['target']}")


def _legacy_agent_names() -> list[str]:
    """Agents still stored in the legacy *shared* home (``~/.local/share/agentkit``)."""
    base = Path("~/.local/share/agentkit").expanduser()
    if not base.is_dir():
        return []
    names = {path.stem for path in base.glob("*.db")}
    names.discard("agentkit")
    return sorted(names)


COMMANDS: list[type] = [
    WorkspaceListCommand,
    WorkspaceMigrateCommand,
]
