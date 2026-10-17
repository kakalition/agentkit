"""Application commands (class-based) + boot-target resolution for the CLI.

A :class:`Command` is a small, app-facing unit. Declare a Laravel ``signature``
and a ``handle()`` method; the container injects ``handle``'s typed parameters::

    class MakeModel(Command):
        signature = "make:model {name} {--force}"
        description = "Create a model and migration."

        def handle(self, name: str, app: App) -> None:
            self.info(f"created {name}")

The command is compiled to a Click command (see
:mod:`agentkit.foundation.console`) and can also be installed onto a Typer app.
The legacy ``name`` + ``run(app)`` form keeps working.

``load_bootstrap`` resolves the app to boot (``AGENTKIT_BOOTSTRAP``, default
``bootstrap:app``).
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
import typing
from typing import Any

import click

from agentkit.foundation.signature import ParsedInput, parse_signature

DEFAULT_BOOTSTRAP = "bootstrap:app"

__all__ = ["Command", "ConsoleOutput", "DEFAULT_BOOTSTRAP", "install", "load_bootstrap"]


class ConsoleOutput:
    """Output helpers available to a command (``self.info`` …)."""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet

    def line(self, *values: Any) -> None:
        if not self.quiet:
            click.echo(" ".join(str(value) for value in values))

    def info(self, *values: Any) -> None:
        self.line(*values)

    def success(self, *values: Any) -> None:
        if not self.quiet:
            click.secho(" ".join(str(value) for value in values), fg="green")

    def warn(self, *values: Any) -> None:
        if not self.quiet:
            click.secho(" ".join(str(value) for value in values), fg="yellow", err=True)

    def error(self, *values: Any) -> None:
        if not self.quiet:
            click.secho(" ".join(str(value) for value in values), fg="red", err=True)

    def comment(self, *values: Any) -> None:
        if not self.quiet:
            click.secho(" ".join(str(value) for value in values), dim=True)

    def table(self, headers: list[str], rows: list[list[Any]]) -> None:
        if self.quiet:
            return
        widths: list[int] = []
        for index in range(len(headers)):
            candidates = [len(str(headers[index]))]
            candidates.extend(len(str(row[index])) for row in rows)
            widths.append(max(candidates))
        click.echo("  ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers))))
        click.echo("  ".join("-" * width for width in widths))
        for row in rows:
            click.echo("  ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))

    def ask(self, question: str, default: str | None = None) -> str:
        return click.prompt(question, default=default)

    def confirm(self, question: str, default: bool = False) -> bool:
        return click.confirm(question, default=default)

    def progress(self, total: int | None = None, label: str = "") -> Any:
        return click.progressbar(length=total or 0, label=label)


class Command:
    """Base class for a class-based command."""

    signature: str = ""
    name: str = ""
    description: str = ""
    aliases: tuple[str, ...] = ()
    hidden: bool = False
    group: str = ""

    #: legacy alias for ``description``.
    help: str = ""

    def __init__(self, app: Any = None) -> None:
        self.app = app
        self.output = ConsoleOutput()
        self.parsed = ParsedInput()

    # -- identity -------------------------------------------------------
    @classmethod
    def command_name(cls) -> str:
        if cls.name:
            return cls.name
        if cls.signature:
            return parse_signature(cls.signature).name
        return _kebab(cls.__name__)

    @classmethod
    def command_description(cls) -> str:
        return cls.description or cls.help or (cls.handle.__doc__ or "")

    @classmethod
    def command_signature(cls) -> str:
        return cls.signature or f"{cls.command_name()}"

    # -- input ----------------------------------------------------------
    def argument(self, name: str, default: Any = None) -> Any:
        return self.parsed.argument(name, default)

    def option(self, name: str, default: Any = None) -> Any:
        return self.parsed.option(name, default)

    # -- execution ------------------------------------------------------
    def handle(self, **kwargs: Any) -> Any:
        """Run the command. Override with typed params for container injection."""
        return self.run(self.app)

    def run(self, app: Any) -> None:
        """Legacy entry point (override when not using ``signature``/``handle``)."""
        raise NotImplementedError

    def call(self, parsed: ParsedInput, app: Any) -> Any:
        self.parsed = parsed
        self.app = app
        kwargs = _resolve_parameters(self, parsed, app)
        return self.handle(**kwargs)

    def invoke(self, **values: Any) -> Any:
        """Call :meth:`handle` with explicit values (used by Typer shims)."""
        from agentkit.foundation.console import run_awaitable

        self.parsed = ParsedInput(arguments=dict(values), options=dict(values))
        return run_awaitable(self.call(self.parsed, self.app))

    # -- output shortcuts -----------------------------------------------
    def line(self, *values: Any) -> None:
        self.output.line(*values)

    def info(self, *values: Any) -> None:
        self.output.info(*values)

    def success(self, *values: Any) -> None:
        self.output.success(*values)

    def warn(self, *values: Any) -> None:
        self.output.warn(*values)

    def error(self, *values: Any) -> None:
        self.output.error(*values)

    def comment(self, *values: Any) -> None:
        self.output.comment(*values)

    def table(self, headers: list[str], rows: list[list[Any]]) -> None:
        self.output.table(headers, rows)

    def ask(self, question: str, default: str | None = None) -> str:
        return self.output.ask(question, default)

    def confirm(self, question: str, default: bool = False) -> bool:
        return self.output.confirm(question, default)


def _kebab(name: str) -> str:
    out: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index and not name[index - 1].isupper():
            out.append("-")
        out.append(char.lower())
    return "".join(out).removesuffix("-command")


def _resolve_parameters(command: Command, parsed: ParsedInput, app: Any) -> dict[str, Any]:
    """Resolve ``handle``'s parameters from the CLI input, then the container."""
    try:
        signature = inspect.signature(command.handle)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return {}
    try:
        hints = typing.get_type_hints(command.handle)
    except Exception:  # pragma: no cover - unresolvable annotations
        hints = {}
    container = getattr(app, "container", None)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name in {"self", "args", "kwargs"} or parameter.kind in (
            parameter.VAR_POSITIONAL,
            parameter.VAR_KEYWORD,
        ):
            continue
        if name in parsed.arguments:
            kwargs[name] = _coerce(parsed.arguments[name], hints.get(name, parameter.annotation))
            continue
        option_key = name if name in parsed.options else name.replace("_", "-")
        if option_key in parsed.options:
            value = parsed.options[option_key]
            if value is None and parameter.default is not inspect.Parameter.empty:
                continue
            kwargs[name] = _coerce(value, hints.get(name, parameter.annotation))
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        annotation = hints.get(name, parameter.annotation)
        resolved = _resolve_type(annotation, container, app)
        if resolved is not _MISSING:
            kwargs[name] = resolved
    return kwargs


def _coerce(value: Any, annotation: Any) -> Any:
    """Coerce a CLI string to the handler's declared type (Path/int/list/…)."""
    if value is None or annotation is inspect.Parameter.empty or annotation is Any:
        return value
    import pathlib
    import types
    import typing

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        non_none = [arg for arg in args if arg is not type(None)]
        if len(non_none) == 1:
            return _coerce(value, non_none[0])
        return value
    if origin in (list, tuple, set) or (origin is not None and getattr(origin, "__name__", "") == "Sequence"):
        item_type = args[0] if args else Any
        items = value if isinstance(value, (list, tuple)) else [value]
        coerced = [_coerce(item, item_type) for item in items]
        return tuple(coerced) if origin is tuple else coerced
    if annotation in (pathlib.Path,):
        return pathlib.Path(value)
    if annotation is bool:
        return bool(value)
    if annotation is int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if annotation is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if annotation is str:
        return value
    return value


_MISSING: Any = object()


def _resolve_type(annotation: Any, container: Any, app: Any) -> Any:
    if container is None:
        return _MISSING
    if annotation is not inspect.Parameter.empty:
        try:
            return container.make(annotation)
        except Exception:  # noqa: BLE001 - fall through to name binding
            pass
    return _MISSING


def _add_cwd_to_path() -> None:
    """Make the current project importable, so ``bootstrap:app`` resolves.

    Console scripts run with the script's directory on ``sys.path``, not the
    working directory, so ``agentkit serve`` from a project root would otherwise
    fail to import its own ``bootstrap.py``.
    """
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


def load_bootstrap(target: str | None = None) -> Any:
    """Import and return the app named by ``target`` (``module:attr``)."""
    from agentkit.foundation.application import App

    reference = target or os.environ.get("AGENTKIT_BOOTSTRAP", DEFAULT_BOOTSTRAP)
    module_name, _, attr = reference.partition(":")
    _add_cwd_to_path()
    module = importlib.import_module(module_name)
    obj = getattr(module, attr) if attr else module
    if isinstance(obj, App):
        return obj
    app = obj() if callable(obj) else obj
    if not isinstance(app, App):
        raise TypeError(f"bootstrap {reference!r} did not yield an App")
    return app


def install(typer_app: Any, commands: list[Any]) -> None:
    """Register app commands as Typer subcommands (each boots the app)."""
    from agentkit.foundation.console import install_command

    for command in commands:
        instance = command() if isinstance(command, type) else command
        install_command(typer_app, instance)
