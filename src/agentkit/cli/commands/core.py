"""Core commands: version, about, and the operator web UI."""

from __future__ import annotations

from agentkit import __version__
from agentkit.config import get_settings
from agentkit.foundation import Command


class VersionCommand(Command):
    signature = "version"
    description = "Print the agentkit version."

    def handle(self) -> None:
        self.info(f"agentkit {__version__}")


class AboutCommand(Command):
    signature = "about"
    description = "Show the agentkit version and the resolved agent home/model."

    def handle(self) -> None:
        settings = get_settings()
        self.info(f"agentkit {__version__}")
        self.info(f"agent home: {settings.home}")
        self.info(f"model: {settings.model_name}")


class WebuiCommand(Command):
    signature = "webui {--host=} {--port=}"
    description = "Serve the operator web UI for the agent in the current environment."

    def handle(self) -> None:
        from agentkit.webui.server import serve_webui

        settings = get_settings()
        host = self.option("host")
        port = self.option("port")
        self.info(
            f"agentkit webui at http://{host or settings.webui_host}:{port or settings.webui_port}"
        )
        serve_webui(settings=settings, host=host, port=port)


class ApiCommand(Command):
    signature = "api {--host=} {--port=}"
    description = "Alias for ``webui`` (serve the API + SPA)."

    def handle(self) -> None:
        WebuiCommand().invoke(host=self.option("host"), port=self.option("port"))


COMMANDS: list[type] = [
    VersionCommand,
    AboutCommand,
    WebuiCommand,
    ApiCommand,
]
