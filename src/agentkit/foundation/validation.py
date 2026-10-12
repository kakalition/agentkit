"""Validation — Laravel-style rules for tool input and job payloads.

    from agentkit import validate, Rule

    data = validate(
        {"when": "in 5 minutes", "text": "stretch"},
        {
            "text": ["required", "string", "max:200"],
            "when": ["required", "string"],
        },
    )

Rules are strings (``"required"``, ``"min:3"``) or callables. Validation raises
:class:`~agentkit.errors.ValidationError` with a per-field error map.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from agentkit.errors import InvalidInput

__all__ = ["Rule", "ValidationError", "validate"]


class ValidationError(InvalidInput):
    code = "validation_error"


def _fail(field: str, message: str) -> None:
    raise ValidationError(message, detail={"errors": {field: [message]}})


class Rule:
    """Built-in validation rules."""

    @staticmethod
    def required(value: Any) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "is required"
        return None

    @staticmethod
    def string(value: Any) -> str | None:
        return None if isinstance(value, str) else "must be a string"

    @staticmethod
    def integer(value: Any) -> str | None:
        return None if isinstance(value, int) and not isinstance(value, bool) else "must be an integer"

    @staticmethod
    def number(value: Any) -> str | None:
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else "must be a number"

    @staticmethod
    def boolean(value: Any) -> str | None:
        return None if isinstance(value, bool) else "must be a boolean"

    @staticmethod
    def min(length: int) -> Callable[[Any], str | None]:
        def rule(value: Any) -> str | None:
            try:
                ok = len(value) >= length if hasattr(value, "__len__") else value >= length
            except TypeError:
                return f"must be at least {length}"
            return None if ok else f"must be at least {length}"

        return rule

    @staticmethod
    def max(length: int) -> Callable[[Any], str | None]:
        def rule(value: Any) -> str | None:
            try:
                ok = len(value) <= length if hasattr(value, "__len__") else value <= length
            except TypeError:
                return f"must be at most {length}"
            return None if ok else f"must be at most {length}"

        return rule

    @staticmethod
    def between(low: int, high: int) -> Callable[[Any], str | None]:
        def rule(value: Any) -> str | None:
            return None if low <= value <= high else f"must be between {low} and {high}"

        return rule

    @staticmethod
    def one_of(*values: Any) -> Callable[[Any], str | None]:
        def rule(value: Any) -> str | None:
            return None if value in values else f"must be one of {list(values)}"

        return rule

    @staticmethod
    def regex(pattern: str) -> Callable[[Any], str | None]:
        compiled = re.compile(pattern)

        def rule(value: Any) -> str | None:
            return None if isinstance(value, str) and compiled.search(value) else f"must match {pattern}"

        return rule

    @staticmethod
    def email(value: Any) -> str | None:
        return None if isinstance(value, str) and re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+$", value) else "must be an email"


_BUILTINS: dict[str, Callable[[Any], str | None]] = {
    "required": Rule.required,
    "string": Rule.string,
    "integer": Rule.integer,
    "number": Rule.number,
    "boolean": Rule.boolean,
    "email": Rule.email,
}


def _resolve_rule(spec: Any) -> Callable[[Any], str | None]:
    if callable(spec):
        return spec
    name, _, argument = str(spec).partition(":")
    if name in {"min", "max"}:
        return Rule.min(int(argument)) if name == "min" else Rule.max(int(argument))
    if name == "between":
        low, high = argument.split(",")
        return Rule.between(int(low), int(high))
    if name in {"in", "one_of"}:
        return Rule.one_of(*argument.split(","))
    if name == "regex":
        return Rule.regex(argument)
    if name in _BUILTINS:
        return _BUILTINS[name]
    raise ValueError(f"unknown validation rule: {spec!r}")


def validate(data: dict[str, Any], rules: dict[str, list[Any]]) -> dict[str, Any]:
    """Validate ``data`` against ``rules``; return the data or raise."""
    errors: dict[str, list[str]] = {}
    for field, field_rules in rules.items():
        value = data.get(field)
        for spec in field_rules:
            rule = _resolve_rule(spec)
            if spec == "required":
                message = rule(value)
                if message:
                    errors.setdefault(field, []).append(f"the {field} field {message}")
                continue
            if value is None or value == "":
                continue
            message = rule(value)
            if message:
                errors.setdefault(field, []).append(f"the {field} field {message}")
    if errors:
        raise ValidationError("validation failed", detail={"errors": errors})
    return data
