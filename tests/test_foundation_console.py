"""WS2 — class-based console: Command, Kernel, signature→Click/Typer."""

from __future__ import annotations

import typer
from click.testing import CliRunner as ClickRunner
from typer.testing import CliRunner

from agentkit import App, Command
from agentkit.foundation.console import Kernel, install_command
from agentkit.runtime import Runtime


class GreetCommand(Command):
    signature = "greet {name} {--loud} {--times=1}"
    description = "Greet someone."

    def handle(self) -> None:
        prefix = "HI " if self.option("loud") else "hi "
        times = int(self.option("times") or 1)
        for _ in range(times):
            self.info(prefix + str(self.argument("name")))


class VersionCommand(Command):
    signature = "version"
    description = "Print the version."

    def handle(self) -> None:
        self.info("agentkit v-test")


class NeedyCommand(Command):
    signature = "needy"

    def handle(self, app: App) -> None:
        self.info(f"app={app.name}")


# -- signature → Click ------------------------------------------------------
def test_kernel_compiles_signature_to_click() -> None:
    command = Kernel().click_command(GreetCommand())
    result = ClickRunner().invoke(command, ["Ada", "--loud", "--times", "2"])
    assert result.exit_code == 0, result.output
    assert result.output == "HI Ada\nHI Ada\n"


def test_kernel_click_command_for_no_param_command() -> None:
    result = ClickRunner().invoke(Kernel().click_command(VersionCommand()), [])
    assert result.exit_code == 0
    assert "v-test" in result.output


# -- signature → Typer (install path) --------------------------------------
def test_install_command_on_typer() -> None:
    app = typer.Typer()
    install_command(app, GreetCommand())
    install_command(app, VersionCommand())
    result = CliRunner().invoke(app, ["greet", "Grace"])
    assert result.exit_code == 0, result.output
    assert result.output == "hi Grace\n"


# -- container injection ----------------------------------------------------
def test_command_handle_receives_app(runtime: Runtime) -> None:
    app = App(name="console", settings=runtime.settings, discover=False)
    app.boot()
    command = NeedyCommand(app=app)
    result = ClickRunner().invoke(Kernel(app).click_command(command), [])
    assert result.exit_code == 0, result.output
    assert "app=console" in result.output


def test_kernel_collects_registered_commands(runtime: Runtime) -> None:
    app = App(name="console", settings=runtime.settings, discover=False)
    app.commands([GreetCommand, VersionCommand])
    app.boot()
    commands = Kernel(app).commands()
    assert {command.command_name() for command in commands} >= {"greet", "version"}


def test_app_console_returns_kernel(runtime: Runtime) -> None:
    app = App(name="console", settings=runtime.settings, discover=False)
    app.boot()
    commands = app.console().commands(app)
    assert isinstance(commands, list)
