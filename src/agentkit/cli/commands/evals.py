"""Run evaluation suites (class-based)."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import typer

from agentkit.foundation import Command
from agentkit.foundation.commands import load_bootstrap


@contextlib.asynccontextmanager
async def _eval_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


class EvalCommand(Command):
    signature = "eval {path} {--bootstrap=}"
    description = "Run an evaluation suite against the booted app."

    async def handle(self, path: Path, bootstrap: str | None = None) -> None:
        from agentkit import EvalSuite

        suite = EvalSuite.from_file(path)
        booted = load_bootstrap(bootstrap)
        booted.boot()
        report = await suite.run(booted)
        self.info(report.summary())
        if not report.passed:
            raise typer.Exit(code=1)


class EvalCaptureCommand(Command):
    signature = "eval:capture {--conversation=} {--limit=50}"
    description = "Capture eval cases from a conversation's real turns (input → reply)."

    async def handle(self, conversation: str | None = None, limit: int = 50) -> None:
        from agentkit.evals import capture_turns

        async with _eval_scope() as repos:
            captured = await capture_turns(repos, conversation_id=conversation, limit=limit)
        if not captured:
            self.info("nothing to capture")
            return
        self.info(f"captured {len(captured)} case(s)")


class EvalGateCommand(Command):
    signature = "eval:gate {--conversation=} {--bootstrap=}"
    description = "Run captured cases against the booted app; non-zero exit on failure."

    async def handle(self, conversation: str | None = None, bootstrap: str | None = None) -> None:
        from agentkit.evals import load_captured

        async with _eval_scope() as repos:
            suite = await load_captured(repos, conversation_id=conversation, name="captured")
        if not suite.cases:
            self.info("no captured cases")
            return
        booted = load_bootstrap(bootstrap)
        booted.boot()
        report = await suite.run(booted)
        self.info(report.summary())
        if not report.passed:
            raise typer.Exit(code=1)


class EvalDatasetCommand(Command):
    signature = "eval:dataset {name} {--conversation=} {--file=} {--limit=50}"
    description = "Create or update an eval dataset from a conversation or a file."

    async def handle(
        self,
        name: str,
        conversation: str | None = None,
        file: Path | None = None,
        limit: int = 50,
    ) -> None:
        from agentkit.evals import capture_turns

        async with _eval_scope() as repos:
            cases: list[dict] = []
            if file is not None:
                from dataclasses import asdict

                from agentkit.evals import EvalSuite

                suite = EvalSuite.from_file(file)
                for case in suite.cases:
                    payload = asdict(case)
                    payload.pop("check", None)
                    cases.append(payload)
            elif conversation is not None:
                cases = await capture_turns(repos, conversation_id=conversation, limit=limit)
            await repos.eval_datasets.upsert(name, cases=cases)
        self.info(f"dataset {name!r}: {len(cases)} case(s)")


class EvalGradeCommand(Command):
    signature = "eval:grade {name} {--grader=exact} {--run=}"
    description = "Grade a dataset (or a stored run trace) with a reference grader."

    async def handle(
        self, name: str, grader: str = "exact", run_id: str | None = None
    ) -> None:
        from agentkit.evals import Case
        from agentkit.graders import grader_by_name, run_grader

        active = grader_by_name(grader)
        if active is None:
            self.error(f"unknown grader {grader!r}")
            raise typer.Exit(code=2)

        try:
            async with _eval_scope() as repos:
                if run_id is not None:
                    events = await repos.run_events.events(run_id)
                    payload = [json.loads(row.data) for row in events]
                    result = await run_grader(active, Case(name=run_id, input=""), payload)
                    graded = [{"case": run_id, **result.to_dict()}]
                else:
                    record = await repos.eval_datasets.get(name)
                    if record is None:
                        raise ValueError(f"no dataset {name!r}")
                    cases = json.loads(record.cases or "[]")
                    graded = []
                    for index, raw in enumerate(cases):
                        case = Case.from_dict(raw) if isinstance(raw, dict) else raw
                        output = getattr(case, "expect", None) or ""
                        result = await run_grader(active, case, output)
                        graded.append(
                            {"case": getattr(case, "name", str(index)), **result.to_dict()}
                        )
                    await repos.eval_runs.add(
                        name, passed=all(item["passed"] for item in graded), report=graded
                    )
        except ValueError as exc:
            self.error(str(exc))
            raise typer.Exit(code=1) from exc

        for item in graded:
            mark = "✓" if item["passed"] else "✗"
            self.info(f"{mark} {item['case']}: {item.get('reason', '')}")
        if not all(item["passed"] for item in graded):
            raise typer.Exit(code=1)


COMMANDS: list[type] = [
    EvalCommand,
    EvalCaptureCommand,
    EvalGateCommand,
    EvalDatasetCommand,
    EvalGradeCommand,
]
