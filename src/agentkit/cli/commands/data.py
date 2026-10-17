"""Owner data lifecycle commands: export a bundle and (opt-in) forget data (class-based)."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from agentkit.foundation import Command


@contextlib.asynccontextmanager
async def _data_scope(owner_id: str | None):
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime, owner_id) as repos:
        yield repos


class DataExportCommand(Command):
    signature = "data:export {--owner=} {--out=}"
    description = "Export an owner's data as a JSON bundle."

    async def handle(self, owner: str | None = None, out: Path | None = None) -> None:
        from agentkit.data import export_owner

        async with _data_scope(owner) as repos:
            bundle = await export_owner(repos)
        text = json.dumps(bundle, indent=2, default=str)
        if out is not None:
            out.write_text(text, encoding="utf-8")
            self.info(f"wrote {out}")
        else:
            self.info(text)


class DataForgetCommand(Command):
    signature = "data:forget {--owner=} {--yes}"
    description = "Erase an owner's data (audit entries are kept as tombstones)."

    async def handle(self, owner: str | None = None, yes: bool = False) -> None:
        from agentkit.data import forget_owner

        async with _data_scope(owner) as repos:
            result = await forget_owner(repos, dry_run=not yes)
        key = "would_delete" if result.get("dry_run") else "deleted"
        self.info(f"{'would delete' if result.get('dry_run') else 'deleted'}: {json.dumps(result[key])}")
        if result.get("dry_run"):
            self.info("re-run with --yes to erase")


COMMANDS: list[type] = [
    DataExportCommand,
    DataForgetCommand,
]
