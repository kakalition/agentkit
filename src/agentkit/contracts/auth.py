"""The auth contract — resolve a presented credential into an actor."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["AuthStrategy"]


@runtime_checkable
class AuthStrategy(Protocol):
    """Authenticate a request or a raw token."""

    async def authenticate(
        self, *, authorization: str | None = None, query_token: str | None = None
    ) -> Any: ...

    async def resolve_token(self, token: str) -> Any: ...

    def default_actor(self) -> Any: ...
