"""Validation — Laravel-style rules for tool input and job payloads.

    from agentkit import validate, Rule

    data = validate(
        {"when": "in 5 minutes", "text": "stretch"},
        {
            "text": ["required", "string", "max:200"],
            "when": ["required", "string"],
        },
    )

Rules are strings (``"required"``, ``"min:3"``) or callables. Each field's rule
set is compiled to a Pydantic :class:`~pydantic.TypeAdapter` (custom validators
plus ``EmailStr`` / ``StringConstraints``) and validation raises
:class:`ValidationError` with a per-field error map.

Blank values (``None`` or ``""``) skip every rule except ``required``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, EmailStr, StringConstraints, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticCustomError

from agentkit.errors import InvalidInput

__all__ = ["Rule", "ValidationError", "validate"]


class ValidationError(InvalidInput):
    code = "validation_error"


_EMAIL = TypeAdapter(EmailStr)


def _predicate_error(message: str | None) -> None:
    if message:
        raise PydanticCustomError("agentkit_rule", message)


class Rule:
    """Built-in validation rules (Pydantic-backed predicates)."""

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
        return (
            None if isinstance(value, (int, float)) and not isinstance(value, bool)
            else "must be a number"
        )

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
        adapter: TypeAdapter[str] = TypeAdapter(Annotated[str, StringConstraints(pattern=pattern)])

        def rule(value: Any) -> str | None:
            if not isinstance(value, str):
                return f"must match {pattern}"
            try:
                adapter.validate_python(value)
            except PydanticValidationError:
                return f"must match {pattern}"
            return None

        return rule

    @staticmethod
    def email(value: Any) -> str | None:
        if not isinstance(value, str):
            return "must be an email"
        try:
            _EMAIL.validate_python(value)
        except PydanticValidationError:
            return "must be an email"
        return None


def _resolve_rule(spec: Any) -> Callable[[Any], str | None]:
    """Return a ``value -> message-or-None`` predicate for one rule spec."""
    if callable(spec):
        return spec
    name, _, argument = str(spec).partition(":")
    if name == "min":
        return Rule.min(int(argument))
    if name == "max":
        return Rule.max(int(argument))
    if name == "between":
        low, high = argument.split(",")
        return Rule.between(int(low), int(high))
    if name in {"in", "one_of"}:
        return Rule.one_of(*argument.split(","))
    if name == "regex":
        return Rule.regex(argument)
    if name in {"string", "integer", "number", "boolean", "email"}:
        return getattr(Rule, name)
    raise ValueError(f"unknown validation rule: {spec!r}")


def _skip_blank(predicate: Callable[[Any], str | None]) -> Callable[[Any], Any]:
    def validator(value: Any) -> Any:
        if value is None or value == "":
            return value
        _predicate_error(predicate(value))
        return value

    return validator


def _required(value: Any) -> Any:
    _predicate_error(Rule.required(value))
    return value


def _adapter(specs: list[Any]) -> TypeAdapter[Any]:
    validators: list[Any] = []
    for spec in specs:
        if spec == "required":
            validators.append(BeforeValidator(_required))
        else:
            validators.append(AfterValidator(_skip_blank(_resolve_rule(spec))))
    annotation = Annotated[(Any, *validators)]
    adapter: TypeAdapter[Any] = TypeAdapter(annotation)
    return adapter


def validate(data: dict[str, Any], rules: dict[str, list[Any]]) -> dict[str, Any]:
    """Validate ``data`` against ``rules``; return the data or raise."""
    errors: dict[str, list[str]] = {}
    for field, field_rules in rules.items():
        adapter = _adapter(list(field_rules))
        try:
            adapter.validate_python(data.get(field))
        except PydanticValidationError as exc:
            for error in exc.errors():
                errors.setdefault(field, []).append(f"the {field} field {error['msg']}")
    if errors:
        raise ValidationError("validation failed", detail={"errors": errors})
    return data
