"""Run evaluation suites."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import typer

from agentkit.cli._app import app
from agentkit.foundation.commands import load_bootstrap


@contextlib.asynccontextmanager
async def _eval_scope():
    from agentkit.runtime import build_runtime, repositories

    runtime = build_runtime()
    async with repositories(runtime) as repos:
        yield repos


@app.command("eval")
def eval_command(
    path: Path = typer.Argument(..., help="Eval suite file (.json/.yaml)."),
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="module:attr of the app."),
) -> None:
    """Run an evaluation suite against the booted app."""

    from agentkit import EvalSuite

    suite = EvalSuite.from_file(path)
    booted = load_bootstrap(bootstrap)
    booted.boot()
    report = asyncio.run(suite.run(booted))
    typer.echo(report.summary())
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("eval:capture")
def eval_capture(
    conversation: str | None = typer.Option(None, "--conversation", help="Conversation id."),
    limit: int = typer.Option(50, "--limit", help="Maximum pairs to capture."),
) -> None:
    """Capture eval cases from a conversation's real turns (input → reply)."""
    from agentkit.evals import capture_turns

    async def _run() -> list[dict]:
        async with _eval_scope() as repos:
            return await capture_turns(repos, conversation_id=conversation, limit=limit)

    captured = asyncio.run(_run())
    if not captured:
        typer.echo("nothing to capture")
        return
    typer.echo(f"captured {len(captured)} case(s)")


@app.command("eval:gate")
def eval_gate(
    conversation: str | None = typer.Option(None, "--conversation", help="Conversation id."),
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="module:attr of the app."),
) -> None:
    """Run captured cases against the booted app; non-zero exit on failure."""
    from agentkit.evals import load_captured

    async def _load():
        async with _eval_scope() as repos:
            return await load_captured(repos, conversation_id=conversation, name="captured")

    suite = asyncio.run(_load())
    if not suite.cases:
        typer.echo("no captured cases")
        return
    booted = load_bootstrap(bootstrap)
    booted.boot()
    report = asyncio.run(suite.run(booted))
    typer.echo(report.summary())
    if not report.passed:
        raise typer.Exit(code=1)


@app.command("eval:dataset")
def eval_dataset(
    name: str = typer.Argument(..., help="Dataset name."),
    conversation: str | None = typer.Option(
        None, "--conversation", help="Capture cases from a conversation."
    ),
    file: Path | None = typer.Option(None, "--file", help="Import cases from a JSON/YAML file."),
    limit: int = typer.Option(50, "--limit", help="Maximum pairs to capture."),
) -> None:
    """Create or update an eval dataset from a conversation or a file."""
    from agentkit.evals import capture_turns

    async def _run():
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
            return cases

    cases = asyncio.run(_run())
    typer.echo(f"dataset {name!r}: {len(cases)} case(s)")


@app.command("eval:grade")
def eval_grade(
    name: str = typer.Argument(..., help="Dataset name."),
    grader: str = typer.Option("exact", "--grader", help="exact | contains | schema | trace."),
    run_id: str | None = typer.Option(
        None, "--run", help="Grade a stored run trace instead of live cases."
    ),
) -> None:
    """Grade a dataset (or a stored run trace) with a reference grader."""
    import json

    from agentkit.evals import Case
    from agentkit.graders import grader_by_name, run_grader

    active = grader_by_name(grader)
    if active is None:
        typer.echo(f"unknown grader {grader!r}", err=True)
        raise typer.Exit(code=2)

    async def _run() -> list[dict]:
        async with _eval_scope() as repos:
            if run_id is not None:
                events = await repos.run_events.events(run_id)
                payload = [json.loads(row.data) for row in events]
                result = await run_grader(active, Case(name=run_id, input=""), payload)
                return [{"case": run_id, **result.to_dict()}]
            record = await repos.eval_datasets.get(name)
            if record is None:
                raise ValueError(f"no dataset {name!r}")
            cases = json.loads(record.cases or "[]")
            graded: list[dict] = []
            for index, raw in enumerate(cases):
                case = Case.from_dict(raw) if isinstance(raw, dict) else raw
                output = getattr(case, "expect", None) or ""
                result = await run_grader(active, case, output)
                graded.append({"case": getattr(case, "name", str(index)), **result.to_dict()})
            await repos.eval_runs.add(
                name, passed=all(item["passed"] for item in graded), report=graded
            )
            return graded

    try:
        graded = asyncio.run(_run())
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    for item in graded:
        mark = "✓" if item["passed"] else "✗"
        typer.echo(f"{mark} {item['case']}: {item.get('reason', '')}")
    if not all(item["passed"] for item in graded):
        raise typer.Exit(code=1)
