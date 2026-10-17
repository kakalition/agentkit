"""Runtime commands: serve, up, and the interactive tinker REPL (class-based)."""

from __future__ import annotations

import contextlib

import typer

from agentkit.foundation import Command
from agentkit.foundation.commands import load_bootstrap


class ServeCommand(Command):
    signature = "serve {--bootstrap=} {--scheduler/--no-scheduler} {--webui/--no-webui}"
    description = "Boot the app and run its channels (plus the web UI)."

    def handle(
        self, bootstrap: str | None = None, scheduler: bool = True, webui: bool = True
    ) -> None:
        try:
            booted = load_bootstrap(bootstrap)
        except (ImportError, AttributeError, TypeError) as exc:
            self.error(
                f"could not load app ({exc}); set AGENTKIT_BOOTSTRAP or create a "
                "'bootstrap.py' exposing `app`."
            )
            raise typer.Exit(code=1) from exc
        booted.boot()
        with contextlib.suppress(Exception):  # observability is optional
            from agentkit.observability import setup_observability

            setup_observability(booted.settings)
        if scheduler:
            from agentkit import scheduler as sched

            sched.init_scheduler(booted.settings, repos_factory=booted.repos_factory)
        booted.serve(webui=webui)


class UpCommand(Command):
    signature = "up {--bootstrap=}"
    description = "Alias for ``serve``."

    def handle(self, bootstrap: str | None = None) -> None:
        ServeCommand().invoke(bootstrap=bootstrap, scheduler=True, webui=True)


class TinkerCommand(Command):
    signature = "tinker {--bootstrap=} {--conversation-id=cli:tinker} {--ephemeral}"
    description = "Interactive REPL: chat with the booted app."

    def handle(
        self,
        bootstrap: str | None = None,
        conversation_id: str = "cli:tinker",
        ephemeral: bool = False,
    ) -> None:
        import asyncio

        booted = load_bootstrap(bootstrap)
        booted.boot()
        self.info("agentkit tinker — type 'exit' to quit.")
        while True:
            try:
                line = input("agentkit> ")
            except (EOFError, KeyboardInterrupt):
                self.info("")
                break
            if not line.strip():
                continue
            if line.strip().lower() in {"exit", "quit", ":q"}:
                break
            result = asyncio.run(
                booted.run(line, conversation_id=conversation_id, ephemeral=ephemeral)
            )
            self.info(result.output)


COMMANDS: list[type] = [
    ServeCommand,
    UpCommand,
    TinkerCommand,
]
