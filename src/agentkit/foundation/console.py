"""The console kernel: collect class-based commands and install them.

Two install paths:

* :meth:`Kernel.register` builds a native Click group from the app's commands —
  used by ``App.install_commands`` and by app-discovered ``app/Console/Commands/``.
* :func:`install_command` installs a command onto a Typer app (generating a
  Typer-visible wrapper from the command's ``signature``), which is how the
  built-in CLI keeps its names/flags while delegating to a :class:`Command`.

A command whose signature needs a construct the grammar does not cover can
override :meth:`Command.build_click` and return a hand-written Click command (the
escape hatch).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import click
import typer

from agentkit.foundation.commands import Command, load_bootstrap
from agentkit.foundation.signature import (
    Argument,
    Option,
    ParsedInput,
    build_click_command,
    parse_signature,
)

__all__ = ["Kernel", "install_command"]


def run_awaitable(result: Any) -> Any:
    """Run an awaitable to completion when a click callback is synchronous."""
    if not inspect.isawaitable(result):
        return result
    from agentkit._sync import run_sync

    return run_sync(result)  # type: ignore[arg-type]


class Kernel:
    """Collects commands from the app + ``app/Console/Commands/`` and installs them."""

    def __init__(self, app: Any = None, base_path: str | Path = ".") -> None:
        self.app = app
        self.base_path = Path(base_path)

    # -- collection -----------------------------------------------------
    def commands(self, app: Any = None) -> list[Command]:
        app = app or self.app
        found: list[Command] = []
        seen: set[str] = set()
        for candidate in (getattr(app, "_commands", {}) or {}).values():
            instance = self._instantiate(candidate)
            if instance is not None and instance.command_name() not in seen:
                seen.add(instance.command_name())
                found.append(instance)
        for klass in self.discovered():
            instance = klass()
            if instance.command_name() not in seen:
                seen.add(instance.command_name())
                found.append(instance)
        return found

    def discovered(self) -> list[type[Command]]:
        from agentkit.foundation.discovery import discover_commands

        return list(discover_commands(self.base_path))

    @staticmethod
    def _instantiate(candidate: Any) -> Command | None:
        if isinstance(candidate, Command):
            return candidate
        if isinstance(candidate, type) and issubclass(candidate, Command):
            return candidate()
        return None

    # -- installation ---------------------------------------------------
    def click_command(self, command: Command, *, name_override: str | None = None) -> click.Command:
        override = getattr(command, "build_click", None)
        if callable(override):
            built = override()
            if built is not None:
                return built
        return compile_command(command, name_override=name_override)

    def group(self, app: Any = None, name: str = "agentkit", *, help: str | None = None) -> click.Group:
        group = click.Group(name=name, help=help)
        self.register(group, app)
        return group

    def build_group(
        self,
        name: str = "agentkit",
        *,
        app: Any = None,
        commands: list[Command] | None = None,
        help: str | None = None,  # noqa: A002 - Click's parameter name
    ) -> click.Group:
        """Build a Click group from ``commands`` (or the app's) honouring ``group``."""
        root = click.Group(name=name, help=help)
        subgroups: dict[str, click.Group] = {}
        collected = commands if commands is not None else self.commands(app)
        for command in collected:
            if command.hidden:
                continue
            if command.group:
                subgroup = subgroups.get(command.group)
                if subgroup is None:
                    subgroup = click.Group(name=command.group)
                    subgroups[command.group] = subgroup
                leaf = command.command_name().rsplit(":", 1)[-1]
                subgroup.add_command(self.click_command(command, name_override=leaf))
            else:
                root.add_command(self.click_command(command))
        for group_name, subgroup in subgroups.items():
            root.add_command(subgroup, name=group_name)
        return root

    def register(self, group: click.Group, app: Any = None) -> click.Group:
        for command in self.commands(app):
            if command.hidden:
                continue
            group.add_command(self.click_command(command))
        return group


def compile_command(command: Command, *, name_override: str | None = None) -> click.Command:
    """Compile a :class:`Command` into a Click command (signature → params)."""
    signature = command.command_signature()
    parsed_signature = parse_signature(signature)
    display_name = name_override or command.command_name()

    def invoke(parsed: ParsedInput) -> Any:
        app = _active_app(command)
        if app is not None:
            app.boot()
        return run_awaitable(command.call(parsed, app))

    if not parsed_signature.arguments and not parsed_signature.options:
        if _overrides_handle(command):

            def no_params() -> Any:
                app = _active_app(command)
                if app is not None:
                    app.boot()
                return run_awaitable(command.call(ParsedInput(), app))

            no_params.__name__ = display_name.replace(":", "_").replace("-", "_")
            no_params.__doc__ = command.command_description() or None
            return click.Command(
                name=display_name,
                callback=no_params,
                help=command.command_description(),
            )
        # A legacy command (``name`` + ``run(app)``) with no signature.

        def legacy() -> Any:
            app = _active_app(command)
            if app is not None:
                app.boot()
            command.run(app)
            return None

        legacy.__name__ = display_name.replace(":", "_").replace("-", "_")
        legacy.__doc__ = command.command_description() or None
        return click.Command(
            name=display_name, callback=legacy, help=command.command_description()
        )

    return build_click_command(
        signature,
        invoke,
        name=display_name,
        help=command.command_description(),
    )


def _overrides_handle(command: Command) -> bool:
    return type(command).handle is not Command.handle


def _active_app(command: Command) -> Any:
    """The app to run a command against: the command's own, the current, or bootstrap."""
    import os

    if command.app is not None:
        return command.app
    from agentkit.foundation.facade import get_current_app

    app = get_current_app()
    if app is not None:
        return app
    if os.environ.get("AGENTKIT_BOOTSTRAP"):
        return load_bootstrap()
    return None


def install_command(typer_app: Any, command: Command) -> None:
    """Install ``command`` onto a Typer app (generating a Typer wrapper)."""
    if command.signature or _overrides_handle(command):
        callback = _build_typer_function(command)
    else:
        callback = _legacy_typer_callback(command)
    typer_app.command(command.command_name(), help=command.command_description() or None)(callback)


def _legacy_typer_callback(command: Command) -> Any:
    def callback() -> None:
        app = _active_app(command)
        if app is not None:
            app.boot()
        command.run(app)

    callback.__name__ = command.command_name().replace(":", "_").replace("-", "_")
    callback.__doc__ = command.command_description() or None
    return callback


def _build_typer_function(command: Command) -> Any:
    """Generate a Typer-visible function with the command's signature params."""
    signature = parse_signature(command.command_signature())
    parameters: list[str] = []
    call: list[str] = []
    for argument in signature.arguments:
        parameters.append(_typer_argument_source(argument))
        call.append(f"{argument.name}={argument.name}")
    for option in signature.options:
        parameters.append(_typer_option_source(option))
        call.append(f"{option.name}={option.name}")

    source = (
        f"def __command({', '.join(parameters)}):\n"
        f"    return __invoke({', '.join(call)})"
    )
    namespace: dict[str, Any] = {
        "typer": typer,
        "__invoke": _typer_invoker(command, signature),
        "Path": Path,
    }
    code = compile(source, "<agentkit-command>", "exec", dont_inherit=True)
    exec(code, namespace)  # noqa: S102 - generated from a trusted signature string
    callback = namespace["__command"]
    callback.__name__ = command.command_name().replace(":", "_").replace("-", "_")
    callback.__doc__ = command.command_description() or None
    return callback


def _typer_invoker(command: Command, signature: Any) -> Any:
    argument_names = {argument.name for argument in signature.arguments}
    option_names = {option.name for option in signature.options}

    def invoke(**kwargs: Any) -> Any:
        parsed = ParsedInput(
            arguments={name: kwargs.get(name) for name in argument_names},
            options={name: kwargs.get(name) for name in option_names},
        )
        app = _active_app(command)
        if app is not None:
            app.boot()
        return run_awaitable(command.call(parsed, app))

    return invoke


def _typer_argument_source(argument: Argument) -> str:
    if argument.variadic:
        return f"{argument.name}: list[str] = typer.Argument(None)"
    if argument.required:
        return f"{argument.name}: str = typer.Argument(...)"
    if argument.has_default:
        return f"{argument.name}: str = typer.Argument({argument.default!r})"
    return f"{argument.name}: str | None = typer.Argument(None)"


def _typer_option_source(option: Option) -> str:
    if option.negative:
        decls = [f'"--{option.name}/--{option.negative}"']
    else:
        decls = [f'"--{option.name}"']
    if option.shortcut:
        decls.append(f'"-{option.shortcut}"')
    declaration = ", ".join(decls)
    if not option.takes_value:
        return f"{option.name}: bool = typer.Option(False, {declaration})"
    if option.has_default:
        annotation = _annotation_for(option.default)
        default = repr(option.default)
        return f"{option.name}: {annotation} | None = typer.Option({default}, {declaration})"
    return f"{option.name}: str | None = typer.Option(None, {declaration})"


def _annotation_for(default: Any) -> str:
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "float"
    return "str"
