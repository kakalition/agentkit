"""The database dialect contract — URL mapping and async engine creation."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Dialect"]


@runtime_checkable
class Dialect(Protocol):
    """Map a database URL to its async driver and build an async engine."""

    def async_url(self, url: str) -> str: ...

    def create_engine(
        self, url: str, *, auth_token: str | None = None, echo: bool = False
    ) -> Any: ...
