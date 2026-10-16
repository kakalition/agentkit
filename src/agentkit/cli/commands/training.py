"""Training commands: trajectory export and batch generation."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from agentkit.cli._app import app


@app.command("trajectory")
def trajectory(
    conversation: str | None = typer.Option(
        None, "--conversation", "-c", help="Export only this conversation id."
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help="Write JSONL here (default stdout)."),
    compress: bool = typer.Option(False, "--compress", help="Elide large tool outputs."),
    limit: int = typer.Option(50, "--limit", help="Max conversations to export."),
) -> None:
    """Export conversation trajectories as JSONL (for training/evaluation)."""
    import asyncio

    from agentkit.config import get_settings
    from agentkit.runtime import build_runtime, repositories
    from agentkit.session import load_history
    from agentkit.trajectory import export_trajectory, iter_trajectories, render_jsonl

    settings = get_settings()
    runtime = build_runtime(settings)

    async def collect() -> list[dict]:
        async with repositories(runtime) as repos:
            if conversation is not None:
                messages = await load_history(repos, conversation, max_messages=10_000)
                return [export_trajectory(messages, compress=compress)] if messages else []
            return [
                item
                async for item in iter_trajectories(
                    repos, limit_conversations=limit, compress=compress
                )
            ]

    items = asyncio.run(collect())
    text = render_jsonl(items)
    if out is not None:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {len(items)} trajectories to {out}")
    else:
        typer.echo(text)


def _read_prompts(path: Path) -> list[str]:
    prompts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except ValueError:
                prompts.append(line)
                continue
            prompts.append(str(parsed.get("prompt") or parsed.get("text") or line))
        else:
            prompts.append(line)
    return prompts


@app.command("generate")
def generate(
    prompts: Path = typer.Argument(..., exists=True, help="JSONL or text file of prompts."),
    out: Path = typer.Option(Path("generations.jsonl"), "--out", "-o"),
    n: int = typer.Option(1, "--n", help="Samples per prompt."),
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Run the agent over a batch of prompts and write JSONL results."""
    import asyncio

    from agentkit.foundation.commands import load_bootstrap
    from agentkit.trajectory import render_jsonl

    prompt_list = _read_prompts(prompts)
    booted = load_bootstrap(bootstrap)
    booted.boot()

    async def run_all() -> list[dict]:
        results: list[dict] = []
        for index, prompt in enumerate(prompt_list):
            for sample in range(max(1, n)):
                result = await booted.run(
                    prompt, conversation_id=f"batch:{index}:{sample}", ephemeral=True
                )
                results.append({"prompt": prompt, "output": result.output, "usage": result.usage})
        return results

    results = asyncio.run(run_all())
    out.write_text(render_jsonl(results), encoding="utf-8")
    typer.echo(f"wrote {len(results)} generations to {out}")
