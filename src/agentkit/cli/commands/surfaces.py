"""Surface commands: the terminal UI and MCP serving (class-based)."""

from __future__ import annotations

from agentkit.foundation import Command


class TuiCommand(Command):
    signature = "tui {--bootstrap=}"
    description = "Open the interactive terminal UI (needs the 'tui' extra)."

    def handle(self, bootstrap: str | None = None) -> None:
        from agentkit.tui import run_tui

        run_tui(bootstrap=bootstrap)


class McpServeCommand(Command):
    signature = "mcp:serve {--bootstrap=} {--transport=stdio} {--host=127.0.0.1} {--port=8765}"
    description = "Serve the booted agent over MCP (an ``ask`` tool)."

    def handle(
        self,
        bootstrap: str | None = None,
        transport: str = "stdio",
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        from agentkit.foundation.commands import load_bootstrap
        from agentkit.mcp.server import serve_agent

        booted = load_bootstrap(bootstrap)
        booted.boot()
        serve_agent(
            booted,
            transport=transport,
            host=host,
            port=port,
            authenticator=getattr(booted, "authenticator", None),
        )


COMMANDS: list[type] = [
    TuiCommand,
    McpServeCommand,
]
