"""Memory commands: list, forget, profile, consolidate (class-based)."""

from __future__ import annotations

import contextlib
import json

import typer

from agentkit.foundation import Command


@contextlib.asynccontextmanager
async def _memory_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


class MemoryListCommand(Command):
    signature = "memory:list {--kind=} {--limit=50}"
    description = "List remembered facts (and the owner profile)."

    async def handle(self, kind: str | None = None, limit: int = 50) -> None:
        async with _memory_scope() as repos:
            profile = await repos.profile.get()
            if profile is not None:
                self.info(
                    f"profile: name={profile.name!r} timezone={profile.timezone!r} "
                    f"locale={profile.locale!r} notes={profile.notes!r}"
                )
            rows = await repos.memories.list(limit=limit, kind=kind)
            if not rows:
                self.info("(no memories)")
                return
            for row in rows:
                self.info(
                    f"  #{row.id} [{row.kind}] {row.content} "
                    f"(importance {row.importance:.2f}, used {row.access_count}x)"
                )


class MemoryForgetCommand(Command):
    signature = "memory:forget {memory_id}"
    description = "Delete a remembered fact by id."

    async def handle(self, memory_id: int) -> None:
        async with _memory_scope() as repos:
            deleted = await repos.memories.forget(memory_id)
        if deleted:
            self.info(f"forgotten #{memory_id}")
        else:
            self.error(f"no memory #{memory_id}")
            raise typer.Exit(code=1)


class MemoryProfileCommand(Command):
    signature = "memory:profile"
    description = "Show the owner's stored profile."

    async def handle(self) -> None:
        async with _memory_scope() as repos:
            profile = await repos.profile.get()
            if profile is None:
                self.info("(no profile yet)")
                return
            self.info(
                json.dumps(
                    {
                        "name": profile.name,
                        "timezone": profile.timezone,
                        "locale": profile.locale,
                        "preferences": profile.preferences,
                        "notes": profile.notes,
                    },
                    indent=2,
                )
            )


class MemoryConsolidateCommand(Command):
    signature = "memory:consolidate {--dry-run}"
    description = "Dedupe, summarize, and prune memories (the daily durable task)."

    async def handle(self, dry_run: bool = False) -> None:
        from agentkit.consolidation import consolidate_memories

        async with _memory_scope() as repos:
            summary = await consolidate_memories(repos, dry_run=dry_run)
        prefix = "would " if dry_run else ""
        self.info(
            f"{prefix}merge {summary['merged']}, {prefix}summarize {summary['summarized']}, "
            f"{prefix}prune {summary['pruned']}"
        )


COMMANDS: list[type] = [
    MemoryListCommand,
    MemoryForgetCommand,
    MemoryProfileCommand,
    MemoryConsolidateCommand,
]
