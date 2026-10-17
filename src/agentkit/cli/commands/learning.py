"""Self-learning commands: reflect, list lessons, forget a lesson (class-based)."""

from __future__ import annotations

import contextlib
import json

import typer

from agentkit.foundation import Command


@contextlib.asynccontextmanager
async def _learning_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


class LearningReflectCommand(Command):
    signature = "learning:reflect {--conversation=} {--window=20} {--dry-run}"
    description = "Distil lessons/preferences/facts from a conversation (the durable task)."

    async def handle(
        self, conversation: str | None = None, window: int = 20, dry_run: bool = False
    ) -> None:
        from agentkit.learning import reflect

        async with _learning_scope() as repos:
            summary = await reflect(
                repos, conversation_id=conversation, window=window, dry_run=dry_run
            )
        if summary.get("skipped"):
            self.info("nothing new to reflect on (already processed)")
            return
        prefix = "would learn " if dry_run else "learned "
        self.info(
            f"{prefix}{summary['lessons']} lesson(s), {summary['preferences']} preference(s), "
            f"{summary['facts']} fact(s); merged {summary['merged']}"
        )
        if summary.get("skill_candidates"):
            self.info(f"skill candidates: {json.dumps(summary['skill_candidates'], default=str)}")


class LearningLessonsCommand(Command):
    signature = "learning:lessons {--limit=50} {--status=active}"
    description = "List the lessons the agent has learned."

    async def handle(self, limit: int = 50, status: str = "active") -> None:
        wanted = None if status == "all" else status
        async with _learning_scope() as repos:
            rows = await repos.memories.list(limit=limit, kind="procedural", status=wanted)
            rows.sort(key=lambda row: float(row.importance or 0.0), reverse=True)
            lines = [f"#{row.id} [{row.status}] {row.content}" for row in rows]
        if not lines:
            self.info("(no lessons)")
            return
        for line in lines:
            self.info(line)


class LearningReviewCommand(Command):
    signature = "learning:review {action} {lesson_id}"
    description = "Approve or reject a proposed lesson."

    async def handle(self, action: str, lesson_id: int) -> None:
        from agentkit.learning import approve_lesson, reject_lesson

        normalised = action.strip().lower()
        if normalised not in {"approve", "reject"}:
            self.error("action must be 'approve' or 'reject'")
            raise typer.Exit(code=2)

        async with _learning_scope() as repos:
            if normalised == "approve":
                ok = await approve_lesson(repos, lesson_id)
            else:
                ok = await reject_lesson(repos, lesson_id)
        if ok:
            self.info(f"{normalised}d #{lesson_id}")
        else:
            self.error(f"no lesson #{lesson_id}")
            raise typer.Exit(code=1)


class LearningForgetCommand(Command):
    signature = "learning:forget {lesson_id}"
    description = "Delete a learned lesson by id."

    async def handle(self, lesson_id: int) -> None:
        async with _learning_scope() as repos:
            deleted = await repos.memories.forget(lesson_id)
        if deleted:
            self.info(f"forgotten #{lesson_id}")
        else:
            self.error(f"no lesson #{lesson_id}")
            raise typer.Exit(code=1)


COMMANDS: list[type] = [
    LearningReflectCommand,
    LearningLessonsCommand,
    LearningReviewCommand,
    LearningForgetCommand,
]
