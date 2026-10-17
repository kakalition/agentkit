"""Attribute casts for Eloquent-ish models.

A cast converts between the value stored in the database and the value exposed on
the model instance. Models declare them with a ``casts`` map::

    class Reminder(Model, table=True):
        casts = {"done": "bool", "meta": "json", "due_at": "datetime"}

The ``set`` direction runs before a write; the ``get`` direction runs after a read
(and on serialization). ``encrypted`` uses the app vault and never logs values.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import Any

from agentkit.foundation.collection import Collection

__all__ = [
    "ArrayCast",
    "AsCollection",
    "BoolCast",
    "Cast",
    "DateCast",
    "DateTimeCast",
    "EncryptedCast",
    "FloatCast",
    "IntCast",
    "JsonCast",
    "StringCast",
    "resolve_cast",
]


class Cast(ABC):
    """Base attribute cast: ``set`` on write, ``get`` on read."""

    @abstractmethod
    def get(self, model: Any, key: str, value: Any) -> Any:
        return value

    @abstractmethod
    def set(self, model: Any, key: str, value: Any) -> Any:
        return value

    def serialize(self, model: Any, key: str, value: Any) -> Any:
        return self.get(model, key, value)


class IntCast(Cast):
    def get(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else int(value)

    def set(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else int(value)


class FloatCast(Cast):
    def get(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else float(value)

    def set(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else float(value)


class StringCast(Cast):
    def get(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else str(value)

    def set(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else str(value)


class BoolCast(Cast):
    _TRUTHY = {"1", "true", "t", "yes", "y", "on"}

    def get(self, model: Any, key: str, value: Any) -> Any:
        return None if value is None else bool(value)

    def set(self, model: Any, key: str, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip().lower() in self._TRUTHY
        return bool(value)


class JsonCast(Cast):
    def get(self, model: Any, key: str, value: Any) -> Any:
        if value is None or not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def set(self, model: Any, key: str, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, default=str)


class ArrayCast(JsonCast):
    def get(self, model: Any, key: str, value: Any) -> Any:
        decoded = super().get(model, key, value)
        return decoded if decoded is not None else []


class AsCollection(JsonCast):
    """Decode JSON into a :class:`~agentkit.foundation.collection.Collection`."""

    def get(self, model: Any, key: str, value: Any) -> Any:
        decoded = super().get(model, key, value)
        if isinstance(decoded, Collection):
            return decoded
        if decoded is None:
            return Collection()
        return Collection(decoded if isinstance(decoded, (list, tuple)) else [decoded])


_LARAVEL_DATE_TOKENS = {
    "Y": "%Y",
    "y": "%y",
    "m": "%m",
    "n": "%m",
    "d": "%d",
    "j": "%d",
    "H": "%H",
    "G": "%H",
    "h": "%I",
    "g": "%I",
    "i": "%M",
    "s": "%S",
    "A": "%p",
    "a": "%p",
}


def _translate_format(fmt: str) -> str:
    """Translate Laravel date tokens (``Y-m-d``) to ``strftime`` directives."""
    if "%" in fmt:
        return fmt
    return "".join(_LARAVEL_DATE_TOKENS.get(char, char) for char in fmt)


class DateTimeCast(Cast):
    def __init__(self, fmt: str | None = None) -> None:
        self.fmt = _translate_format(fmt) if fmt else None

    def get(self, model: Any, key: str, value: Any) -> Any:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value

    def set(self, model: Any, key: str, value: Any) -> Any:
        if value is None:
            return None
        parsed = self.get(model, key, value)
        if self.fmt:
            return parsed.strftime(self.fmt) if isinstance(parsed, datetime) else value
        if isinstance(parsed, datetime) and parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def serialize(self, model: Any, key: str, value: Any) -> Any:
        parsed = self.get(model, key, value)
        return parsed.isoformat() if isinstance(parsed, datetime) else parsed


class DateCast(DateTimeCast):
    def get(self, model: Any, key: str, value: Any) -> Any:
        parsed = super().get(model, key, value)
        if isinstance(parsed, datetime):
            return parsed.date()
        if isinstance(parsed, str):
            try:
                return date.fromisoformat(parsed)
            except ValueError:
                return parsed
        return parsed


class EncryptedCast(Cast):
    """Encrypt on write / decrypt on read through the current app's vault.

    Values are never logged; a missing vault raises rather than storing plaintext.
    """

    def _vault(self) -> Any:
        from agentkit.foundation.facade import get_current_app

        app = get_current_app()
        vault = getattr(app, "vault", None) if app is not None else None
        if vault is None:
            raise RuntimeError("encrypted cast requires a booted App with a vault")
        return vault

    def get(self, model: Any, key: str, value: Any) -> Any:
        if value is None:
            return None
        return self._vault().decrypt(value)

    def set(self, model: Any, key: str, value: Any) -> Any:
        if value is None:
            return None
        return self._vault().encrypt(str(value))


_BUILTINS: dict[str, type[Cast]] = {
    "int": IntCast,
    "integer": IntCast,
    "float": FloatCast,
    "double": FloatCast,
    "decimal": FloatCast,
    "string": StringCast,
    "bool": BoolCast,
    "boolean": BoolCast,
    "json": JsonCast,
    "array": ArrayCast,
    "collection": AsCollection,
    "datetime": DateTimeCast,
    "date": DateCast,
    "timestamp": DateTimeCast,
    "immutable_datetime": DateTimeCast,
    "encrypted": EncryptedCast,
}


def resolve_cast(spec: Any) -> Cast:
    """Resolve a cast spec (string name, :class:`Cast` instance, or class) to a cast."""
    if isinstance(spec, Cast):
        return spec
    if isinstance(spec, type) and issubclass(spec, Cast):
        return spec()
    name = str(spec)
    base, _, argument = name.partition(":")
    builtin = _BUILTINS.get(base.lower())
    if builtin is None:
        raise ValueError(f"unknown cast: {spec!r}")
    if builtin is DateTimeCast and argument:
        return DateTimeCast(argument)
    return builtin()
