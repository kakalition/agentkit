"""Training commands: trajectory export and batch generation (class-based)."""

from __future__ import annotations

import json
from pathlib import Path

from agentkit.foundation import Command


class TrajectoryCommand(Command):
    signature = "trajectory {--conversation=} {--out=} {--compress} {--limit=50}"
    description = "Export conversation trajectories as JSONL (for training/evaluation)."

    async def handle(
        self,
        conversation: str | None = None,
        out: Path | None = None,
        compress: bool = False,
        limit: int = 50,
    ) -> None:
        from agentkit.config import get_settings
        from agentkit.runtime import build_runtime, repositories
        from agentkit.session import load_history
        from agentkit.trajectory import export_trajectory, iter_trajectories, render_jsonl

        settings = get_settings()
        runtime = build_runtime(settings)

        async with repositories(runtime) as repos:
            if conversation is not None:
                messages = await load_history(repos, conversation, max_messages=10_000)
                items = [export_trajectory(messages, compress=compress)] if messages else []
            else:
                items = [
                    item
                    async for item in iter_trajectories(
                        repos, limit_conversations=limit, compress=compress
                    )
                ]

        text = render_jsonl(items)
        if out is not None:
            out.write_text(text, encoding="utf-8")
            self.info(f"wrote {len(items)} trajectories to {out}")
        else:
            self.info(text)


class GenerateCommand(Command):
    signature = "generate {prompts} {--out=generations.jsonl} {--n=1} {--bootstrap=}"
    description = "Run the agent over a batch of prompts and write JSONL results."

    async def handle(
        self,
        prompts: Path,
        out: Path = Path("generations.jsonl"),
        n: int = 1,
        bootstrap: str | None = None,
    ) -> None:
        from agentkit.foundation.commands import load_bootstrap
        from agentkit.trajectory import render_jsonl

        prompt_list = _read_prompts(prompts)
        booted = load_bootstrap(bootstrap)
        booted.boot()

        results: list[dict] = []
        for index, prompt in enumerate(prompt_list):
            for sample in range(max(1, n)):
                result = await booted.run(
                    prompt, conversation_id=f"batch:{index}:{sample}", ephemeral=True
                )
                results.append({"prompt": prompt, "output": result.output, "usage": result.usage})

        out.write_text(render_jsonl(results), encoding="utf-8")
        self.info(f"wrote {len(results)} generations to {out}")


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


COMMANDS: list[type] = [
    TrajectoryCommand,
    GenerateCommand,
]
