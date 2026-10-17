"""Validation — Laravel-style rules for tool input and job payloads.

    from agentkit import validate, Rule

    data = validate(
        {"when": "in 5 minutes", "text": "stretch"},
        {
            "text": ["required", "string", "max:200"],
            "when": ["required", "string"],
        },
    )

Rules are strings (``"required"``, ``"min:3"``), callables, or
:class:`ValidationRule` objects. Each field's rule set is compiled to a Pydantic
:class:`~pydantic.TypeAdapter` (custom validators plus ``EmailStr`` /
``StringConstraints``) and validation raises :class:`ValidationError` with a
per-field error map.

Blank values (``None`` or ``""``) skip every rule except ``required``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Annotated, Any, ClassVar

from pydantic import AfterValidator, BeforeValidator, EmailStr, StringConstraints, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticCustomError

from agentkit.errors import InvalidInput

__all__ = [
    "Rule",
    "ValidationError",
    "ValidationRule",
    "ValidatesInput",
    "Validator",
    "validate",
    "validator",
]


class ValidationError(InvalidInput):
    code = "validation_error"


_EMAIL = TypeAdapter(EmailStr)


def _predicate_error(message: str | None) -> None:
    if message:
        raise PydanticCustomError("agentkit_rule", message)


#: Rule messages never leak into logs verbatim from here; they are surfaced in errors.
class ValidationRule(ABC):
    """A rule object validated as ``validate(attribute, value, fail)``.

    ``fail(message)`` records the (bare) message for the attribute, e.g.
    ``"is required"``. Set ``skips_blank = False`` for rules (like ``required``)
    that must still run when the value is blank.
    """

    skips_blank: bool = True

    @abstractmethod
    def validate(self, attribute: str, value: Any, fail: Callable[[str], None]) -> None:
        raise NotImplementedError

    async def validate_async(
        self, attribute: str, value: Any, fail: Callable[[str], None]
    ) -> None:
        self.validate(attribute, value, fail)

    def predicate(self, attribute: str = "value") -> Callable[[Any], str | None]:
        """A ``value -> message-or-None`` predicate usable by the string compiler."""

        def check(value: Any) -> str | None:
            messages: list[str] = []
            self.validate(attribute, value, messages.append)
            return messages[0] if messages else None

        return check

    def __call__(self, value: Any) -> str | None:
        return self.predicate()(value)


class _RequiredRule(ValidationRule):
    skips_blank = False

    def validate(self, attribute: str, value: Any, fail: Callable[[str], None]) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            fail("is required")


#: The canonical "required" rule object (also available as the ``"required"`` string).
required_rule = _RequiredRule()


class Rule:
    """Built-in validation rules — predicates plus object factories.

    The bare predicates (``Rule.required``, ``Rule.min(3)`` …) are callables that
    return a message or ``None``; the object factories (``Rule.in_``,
    ``Rule.unique``, ``Rule.exists``) return :class:`ValidationRule` instances.
    """

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

    #: Laravel spelling of ``one_of``.
    in_ = one_of

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

    # -- object factories (DB-backed; wired to repositories in WS5) ------
    @staticmethod
    def unique(
        model: Any,
        column: str,
        *,
        except_id: Any = None,
        message: str | None = None,
    ) -> ValidationRule:
        return Unique(model, column, except_id=except_id, message=message)

    @staticmethod
    def exists(model: Any, column: str, *, message: str | None = None) -> ValidationRule:
        return Exists(model, column, message=message)


# -- DB-backed rules --------------------------------------------------------

#: ``resolver(model, {column: value}) -> bool`` (True when a matching row exists).
_uniqueness_resolver: Callable[[type, dict[str, Any]], bool] | None = None


def set_uniqueness_resolver(
    resolver: Callable[[type, dict[str, Any]], bool] | None,
) -> None:
    """Install the resolver used by :class:`Unique` / :class:`Exists`.

    WS5 wires this to the active repositories; without one, the rules raise.
    """
    global _uniqueness_resolver
    _uniqueness_resolver = resolver


def _row_exists(model: type, filters: dict[str, Any]) -> bool:
    if _uniqueness_resolver is None:
        raise RuntimeError(
            "no uniqueness resolver configured; call set_uniqueness_resolver() "
            "(agentkit wires this when a database is available)"
        )
    return bool(_uniqueness_resolver(model, filters))


class Unique(ValidationRule):
    """The value must not already exist in ``model.column``."""

    def __init__(
        self,
        model: type,
        column: str,
        *,
        except_id: Any = None,
        message: str | None = None,
    ) -> None:
        self.model = model
        self.column = column
        self.except_id = except_id
        self.message = message

    def validate(self, attribute: str, value: Any, fail: Callable[[str], None]) -> None:
        if value is None or value == "":
            return
        filters = {self.column: value}
        if _row_exists(self.model, filters):
            fail(self.message or f"{attribute} has already been taken")


class Exists(ValidationRule):
    """The value must already exist in ``model.column``."""

    def __init__(self, model: type, column: str, *, message: str | None = None) -> None:
        self.model = model
        self.column = column
        self.message = message

    def validate(self, attribute: str, value: Any, fail: Callable[[str], None]) -> None:
        if value is None or value == "":
            return
        if not _row_exists(self.model, {self.column: value}):
            fail(self.message or f"the selected {attribute} is invalid")


def _resolve_rule(spec: Any) -> Callable[[Any], str | None]:
    """Return a ``value -> message-or-None`` predicate for one rule spec."""
    if isinstance(spec, ValidationRule):
        return spec.predicate()
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


def _must_run(predicate: Callable[[Any], str | None]) -> Callable[[Any], Any]:
    def validator(value: Any) -> Any:
        _predicate_error(predicate(value))
        return value

    return validator


def _is_required_spec(spec: Any) -> bool:
    return spec == "required" or spec is Rule.required or spec is required_rule


def _adapter(specs: list[Any]) -> TypeAdapter[Any]:
    validators: list[Any] = []
    for spec in specs:
        if _is_required_spec(spec):
            validators.append(BeforeValidator(_required))
        elif isinstance(spec, ValidationRule) and not spec.skips_blank:
            validators.append(BeforeValidator(_must_run(spec.predicate())))
        else:
            validators.append(AfterValidator(_skip_blank(_resolve_rule(spec))))
    annotation = Annotated[(Any, *validators)]
    adapter: TypeAdapter[Any] = TypeAdapter(annotation)
    return adapter


def _collect_errors(data: dict[str, Any], rules: dict[str, list[Any]]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for field, field_rules in rules.items():
        adapter = _adapter(list(field_rules))
        try:
            adapter.validate_python(data.get(field))
        except PydanticValidationError as exc:
            for error in exc.errors():
                errors.setdefault(field, []).append(f"the {field} field {error['msg']}")
    return errors


def validate(data: dict[str, Any], rules: dict[str, list[Any]]) -> dict[str, Any]:
    """Validate ``data`` against ``rules``; return the data or raise."""
    errors = _collect_errors(data, rules)
    if errors:
        raise ValidationError("validation failed", detail={"errors": errors})
    return data


class Validator:
    """The object form of :func:`validate` (Laravel's ``Validator``)."""

    def __init__(
        self,
        data: dict[str, Any],
        rules: dict[str, list[Any]],
        *,
        attribute_names: dict[str, str] | None = None,
    ) -> None:
        self.data = dict(data)
        self.rules = rules
        self.attribute_names = dict(attribute_names or {})
        self._errors: dict[str, list[str]] | None = None

    def _run(self) -> dict[str, list[str]]:
        if self._errors is None:
            self._errors = _collect_errors(self.data, self.rules)
        return self._errors

    def errors(self) -> dict[str, list[str]]:
        return self._run()

    def fails(self) -> bool:
        return bool(self._run())

    def passes(self) -> bool:
        return not self._run()

    def validate(self) -> dict[str, Any]:
        """Return the validated data, or raise :class:`ValidationError`."""
        errors = self._run()
        if errors:
            raise ValidationError("validation failed", detail={"errors": errors})
        return self.data

    # -- aliases --------------------------------------------------------
    def validated(self) -> dict[str, Any]:
        return self.validate()

    def safe(self) -> dict[str, Any]:
        return self.validate()

    def first(self, field: str) -> str | None:
        messages = self._run().get(field)
        return messages[0] if messages else None


def validator(data: dict[str, Any], rules: dict[str, list[Any]], **kwargs: Any) -> Validator:
    """Build a :class:`Validator` (the ``validator()`` helper)."""
    return Validator(data, rules, **kwargs)


class ValidatesInput:
    """Mixin giving a tool/job declarative input validation (Laravel's ``ValidatesRequests``).

        class CreateNote(Tool):
            rules = {"text": ["required", "max:200"]}

            def handle(self, ctx, text: str):
                self.validate_input({"text": text})
    """

    rules: ClassVar[dict[str, list[Any]]] = {}

    def validation_rules(self) -> dict[str, list[Any]]:
        return self.rules

    def validate_input(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate ``data`` against :attr:`rules`; returns the data or raises."""
        return validator(data, self.validation_rules()).validate()
