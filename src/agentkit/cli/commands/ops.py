"""Ops commands: migrate, database backup/restore, and health (class-based)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import typer

from agentkit.foundation import Command


def _runtime():
    from agentkit.runtime import build_runtime

    return build_runtime()


class MigrateCommand(Command):
    signature = "migrate {kind?} {source?} {--target=} {--dry-run}"
    description = "Migrate the DB schema, or import a hub."

    async def handle(
        self,
        kind: str | None = None,
        source: Path | None = None,
        target: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        if kind == "openclaw":
            if source is None:
                self.error("migrate openclaw needs a source directory")
                raise typer.Exit(code=2)
            from agentkit.config import get_settings
            from agentkit.migrate import migrate_openclaw

            resolved = target or get_settings().home
            self.info(migrate_openclaw(source, target=resolved, dry_run=dry_run).render())
            return
        if kind is not None:
            self.error(f"unknown migration source {kind!r}; only 'openclaw' is supported")
            raise typer.Exit(code=2)

        from agentkit.db.migrations import init_db

        runtime = _runtime()
        await init_db(runtime.engine)
        self.info(f"schema up to date: {runtime.settings.db_path}")


class DbBackupCommand(Command):
    signature = "db:backup {--out=}"
    description = "Back up a local SQLite database (WAL-safe via ``VACUUM INTO``)."

    def handle(self, out: Path | None = None) -> None:
        runtime = _runtime()
        db_path = Path(runtime.settings.db_path)
        if not db_path.is_file():
            self.error(f"no database at {db_path}")
            raise typer.Exit(code=1)
        destination = out or db_path.with_suffix(".db.bak")
        connection = sqlite3.connect(str(db_path))
        try:
            connection.execute("VACUUM INTO ?", (str(destination),))
        except sqlite3.OperationalError as exc:
            self.error(f"backup failed: {exc}")
            raise typer.Exit(code=1) from exc
        finally:
            connection.close()
        self.info(f"backed up to {destination}")


class DbRestoreCommand(Command):
    signature = "db:restore {source} {--yes}"
    description = "Restore a SQLite database from a backup file (overwrites the current DB)."

    def handle(self, source: Path, yes: bool = False) -> None:
        runtime = _runtime()
        db_path = Path(runtime.settings.db_path)
        if not source.is_file():
            self.error(f"no backup at {source}")
            raise typer.Exit(code=1)
        if not yes:
            self.info(f"would overwrite {db_path} with {source}; re-run with --yes")
            raise typer.Exit(code=1)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, db_path)
        self.info(f"restored {db_path} from {source}")


class HealthCommand(Command):
    signature = "health"
    description = "Run the dependency readiness checks."

    async def handle(self) -> None:
        from agentkit.health import db_check, run_checks

        runtime = _runtime()
        ok, results = await run_checks([db_check(runtime)])
        for name, passed in results.items():
            self.info(f"{name}: {'ok' if passed else 'FAILING'}")
        if not ok:
            raise typer.Exit(code=1)


class RunsResumeCommand(Command):
    signature = "runs:resume {conversation_id} {--seq=} {--target=}"
    description = "Restore (or branch) a conversation from a stored checkpoint."

    async def handle(
        self, conversation_id: str, seq: int | None = None, target: str | None = None
    ) -> None:
        from agentkit.foundation.application import App

        runtime = _runtime()
        app = App(settings=runtime.settings, discover=False)
        app._runtime = runtime
        try:
            destination = await app.resume_from_checkpoint(
                conversation_id, seq=seq, target=target
            )
        except Exception as exc:
            self.error(str(exc))
            raise typer.Exit(code=1) from exc
        where = f"branch {destination}" if target else destination
        self.info(f"restored {conversation_id} -> {where}")


COMMANDS: list[type] = [
    MigrateCommand,
    DbBackupCommand,
    DbRestoreCommand,
    HealthCommand,
    RunsResumeCommand,
]
