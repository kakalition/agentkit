"""Project scaffolding and ``make:*`` generators (class-based commands)."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path

import typer

from agentkit.foundation import Command
from agentkit.foundation.generators import generate


class NewProjectCommand(Command):
    signature = "new {name} {--path=.} {--force} {--git/--no-git} {--full/--minimal} {--preset=} {--posture=}"
    description = "Create a new agentkit project from the default skeleton."

    def handle(
        self,
        name: str,
        path: Path = Path("."),
        force: bool = False,
        git: bool = True,
        full: bool = True,
        preset: str | None = None,
        posture: str | None = None,
    ) -> None:
        from agentkit.foundation.scaffold import scaffold_project

        if preset is not None and not full:
            self.error("--preset requires the full-stack project (drop --minimal)")
            raise typer.Exit(code=2)
        try:
            target = scaffold_project(
                name, Path(path), force=force, full=full, preset=preset, posture=posture
            )
        except (FileExistsError, ValueError) as exc:
            self.error(str(exc))
            raise typer.Exit(code=1) from exc

        if git:
            with contextlib.suppress(Exception):
                subprocess.run(["git", "init"], cwd=target, capture_output=True, check=False)
                subprocess.run(["git", "add", "-A"], cwd=target, capture_output=True, check=False)

        self.info(f"Created {target}")
        self.info("Next steps:")
        self.info(f"  cd {target}")
        self.info("  cp .env.example .env   # then set OPENAI_API_KEY")
        self.info("  uv sync                # or: pip install -e .")
        self.info("  agentkit tinker        # chat with your agent")


class GeneratorCommand(Command):
    """Base for the ``make:*`` scaffolding commands."""

    kind: str = ""

    def handle(self, name: str, path: Path = Path("."), force: bool = False) -> None:
        try:
            written = generate(self.kind, name, directory=Path(path), force=force)
        except FileExistsError as exc:
            self.error(str(exc))
            raise typer.Exit(code=1) from exc
        self.info(f"created {written}")


class MakeAgentCommand(GeneratorCommand):
    kind = "agent"
    signature = "make:agent {name} {--path=.} {--force}"
    description = "Scaffold an agent builder module."


class MakeProviderCommand(GeneratorCommand):
    kind = "provider"
    signature = "make:provider {name} {--path=.} {--force}"
    description = "Scaffold a service provider."


class MakeToolCommand(GeneratorCommand):
    kind = "tool"
    signature = "make:tool {name} {--path=.} {--force}"
    description = "Scaffold a tool function."


class MakePolicyCommand(GeneratorCommand):
    kind = "policy"
    signature = "make:policy {name} {--path=.} {--force}"
    description = "Scaffold a tool policy."


class MakeChannelCommand(GeneratorCommand):
    kind = "channel"
    signature = "make:channel {name} {--path=.} {--force}"
    description = "Scaffold a channel factory."


class MakeCommandCommand(GeneratorCommand):
    kind = "command"
    signature = "make:command {name} {--path=.} {--force}"
    description = "Scaffold a provider command."


class MakeModelCommand(GeneratorCommand):
    kind = "model"
    signature = "make:model {name} {--path=.} {--force}"
    description = "Scaffold a ``Model`` table."


COMMANDS: list[type] = [
    NewProjectCommand,
    MakeAgentCommand,
    MakeProviderCommand,
    MakeToolCommand,
    MakePolicyCommand,
    MakeChannelCommand,
    MakeCommandCommand,
    MakeModelCommand,
]
