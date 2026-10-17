"""Laravel command ``signature`` parsing, and compilation to a Click command.

A signature is a name plus argument/option tokens::

    "make:model {name} {--force} {--F|full} {--o|owner=} {names*}"

* ``{name}`` — required argument; ``{name?}`` optional; ``{name=default}`` optional
  with a default; ``{names*}`` an array (``{names?*}`` optional).
* ``{--force}`` — boolean flag; ``{--F|full}`` adds a shortcut; ``{--owner=}``
  takes a value; ``{--owner=default}`` takes a value with a default.

The supported grammar is the Laravel-familiar subset described above (no ``{--*}``
array options in v1). :func:`build_click_command` turns a parsed signature into a
Click command whose callback receives a :class:`ParsedInput`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import click

__all__ = [
    "Argument",
    "Option",
    "ParsedInput",
    "Signature",
    "build_click_command",
    "parse_signature",
]

_TOKEN = re.compile(r"\{([^{}]*)\}")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


@dataclass(frozen=True)
class Argument:
    """A positional command argument."""

    name: str
    required: bool = True
    variadic: bool = False
    default: Any = None
    has_default: bool = False


@dataclass(frozen=True)
class Option:
    """A command option (flag or value option)."""

    name: str
    shortcut: str | None = None
    takes_value: bool = False
    variadic: bool = False
    default: Any = None
    has_default: bool = False
    negative: str | None = None


@dataclass
class Signature:
    """A parsed command signature."""

    name: str
    arguments: list[Argument] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> Signature:
        return parse_signature(text)

    def argument(self, name: str) -> Argument | None:
        return next((arg for arg in self.arguments if arg.name == name), None)

    def option(self, name: str) -> Option | None:
        return next((opt for opt in self.options if opt.name == name), None)

    def has_arguments(self) -> bool:
        return bool(self.arguments)

    def has_options(self) -> bool:
        return bool(self.options)

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return self.name


def _parse_argument(content: str) -> Argument:
    body = content.strip()
    variadic = body.endswith("*")
    if variadic:
        body = body[:-1]
    optional = body.endswith("?")
    if optional:
        body = body[:-1]
    has_default = "=" in body
    default: Any = None
    if has_default:
        body, _, raw = body.partition("=")
        default = _unquote(raw)
    required = not optional and not has_default
    return Argument(
        name=body.strip(),
        required=required,
        variadic=variadic,
        default=default,
        has_default=has_default,
    )


def _parse_option(content: str) -> Option:
    body = content.strip()
    if body.startswith("--"):
        body = body[2:]
    variadic = body.endswith("*")
    if variadic:
        body = body[:-1]
    takes_value = "=" in body
    default: Any = None
    has_default = False
    if takes_value:
        body, _, raw = body.partition("=")
        if raw.strip():
            has_default = True
            default = _unquote(raw)
    negative: str | None = None
    if not takes_value and "/" in body:
        body, _, neg = body.partition("/")
        negative = neg.strip().lstrip("-") or None
    parts = [part.strip() for part in body.split("|") if part.strip()]
    if len(parts) >= 2:
        shortcut, name = parts[0], parts[1]
    else:
        shortcut, name = None, parts[0] if parts else ""
    return Option(
        name=name,
        shortcut=shortcut,
        takes_value=takes_value,
        variadic=variadic,
        default=default,
        has_default=has_default,
        negative=negative,
    )


def parse_signature(text: str) -> Signature:
    """Parse ``text`` into a :class:`Signature` (name, arguments, options)."""
    tokens = [match.group(1).strip() for match in _TOKEN.finditer(text)]
    name = _TOKEN.sub("", text).strip()
    arguments: list[Argument] = []
    options: list[Option] = []
    for token in tokens:
        if not token:
            continue
        if token.startswith("--"):
            options.append(_parse_option(token))
        else:
            arguments.append(_parse_argument(token))
    return Signature(name=name, arguments=arguments, options=options)


# -- Click compilation ------------------------------------------------------


@dataclass
class ParsedInput:
    """Resolved argument/option values passed to a command handler."""

    arguments: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    def argument(self, name: str, default: Any = None) -> Any:
        return self.arguments.get(name, default)

    def option(self, name: str, default: Any = None) -> Any:
        return self.options.get(name, default)

    def flag(self, name: str) -> bool:
        return bool(self.options.get(name, False))

    def __getitem__(self, key: str) -> Any:
        if key in self.arguments:
            return self.arguments[key]
        return self.options[key]

    def __contains__(self, key: str) -> bool:
        return key in self.arguments or key in self.options


def build_click_command(
    signature: Signature | str,
    handler: Callable[[ParsedInput], Any],
    *,
    name: str | None = None,
    help: str | None = None,  # noqa: A002 - Click's parameter name
) -> click.Command:
    """Compile ``signature`` into a Click command invoking ``handler(parsed)``.

    ``handler`` receives one :class:`ParsedInput`; its return value becomes the
    command's return value.
    """
    parsed = parse_signature(signature) if isinstance(signature, str) else signature
    params: list[click.Parameter] = []
    argument_names: list[str] = []
    option_bindings: list[tuple[str, str]] = []

    for argument in parsed.arguments:
        attrs: dict[str, Any] = {"required": argument.required}
        if argument.has_default:
            attrs["default"] = argument.default
        params.append(click.Argument([argument.name], nargs=-1 if argument.variadic else 1, **attrs))
        argument_names.append(argument.name)

    for option in parsed.options:
        if option.negative:
            decls = [f"--{option.name}/--{option.negative}"]
        else:
            decls = [f"--{option.name}"]
        if option.shortcut:
            decls.append(f"-{option.shortcut}")
        attrs = {"is_flag": not option.takes_value, "multiple": option.variadic}
        if option.takes_value and option.has_default:
            attrs["default"] = option.default
        elif option.takes_value:
            attrs["default"] = None
        click_option = click.Option(decls, **attrs)
        params.append(click_option)
        option_bindings.append((option.name, click_option.name))

    def _callback(**kwargs: Any) -> Any:
        arguments = {arg_name: kwargs.get(arg_name) for arg_name in argument_names}
        options = {logical: kwargs.get(dest) for logical, dest in option_bindings}
        return handler(ParsedInput(arguments=arguments, options=options))

    command = click.Command(
        name=name or parsed.name,
        params=params,
        callback=_callback,
        help=help,
    )
    command.__doc__ = help
    return command
