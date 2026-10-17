"""One authenticator composing API keys and JWT/JWKS behind a single seam.

Resolution order for a presented token: static (config/env) API key → DB API key
(optional ``db_lookup``) → JWT. Results are :class:`~agentkit.security.Actor`
values. When ``auth_enabled`` is false authentication is never required and the
settings owner is returned (today's local-first behavior).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agentkit.contracts.auth import AuthStrategy
from agentkit.errors import PermissionDenied
from agentkit.security import API_KEY, Actor, system_actor
from agentkit.security.jwt import JWKSVerifier, JWTError
from agentkit.security.keys import hash_key, parse_api_keys
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import AuthDriver, DriverKind
from agentkit.support.manager import Manager


class AuthError(PermissionDenied):
    """Raised when a request is unauthenticated (401) or lacks a role (403)."""

    code = "unauthorized"
    http_status = 401


class ForbiddenError(PermissionDenied):
    """Raised when an authenticated actor is missing a required role (403)."""

    code = "forbidden"
    http_status = 403


DBLookup = Callable[[str], Awaitable[Actor | None]]


def _bearer(authorization: str | None, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


class Authenticator:
    """Resolve a presented credential into an :class:`Actor`."""

    def __init__(
        self,
        settings: Any,
        *,
        db_lookup: DBLookup | None = None,
        jwks_verifier: JWKSVerifier | None = None,
    ) -> None:
        self.settings = settings
        self._db_lookup = db_lookup
        self._static: dict[str, Actor] = {}
        for spec in parse_api_keys(getattr(settings, "auth_api_keys", None)):
            if spec.key:
                self._static[hash_key(spec.key)] = Actor(
                    owner_id=spec.owner_id or settings.owner_id,
                    subject=spec.name,
                    roles=frozenset(spec.roles),
                    method=API_KEY,
                )
        self._jwks = jwks_verifier
        if self._jwks is None and getattr(settings, "auth_jwks_url", None):
            self._jwks = JWKSVerifier(
                jwks_url=settings.auth_jwks_url,
                issuer=settings.auth_issuer,
                audience=settings.auth_audience,
                algorithms=settings.auth_algorithms,
                owner_claim=settings.auth_owner_claim,
                roles_claim=settings.auth_roles_claim,
                default_owner=settings.auth_default_owner,
                cache_ttl=settings.auth_jwks_cache_ttl,
                timeout=settings.auth_jwks_timeout,
            )

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "auth_enabled", False))

    def default_actor(self) -> Actor:
        return system_actor(self.settings)

    async def resolve_token(self, token: str) -> Actor | None:
        digest = hash_key(token)
        actor = self._static.get(digest)
        if actor is not None:
            return actor
        if self._db_lookup is not None:
            actor = await self._db_lookup(digest)
            if actor is not None:
                return actor
        if self._jwks is not None:
            try:
                return await self._jwks.verify(token)
            except JWTError:
                return None
        return None

    async def authenticate(
        self, *, authorization: str | None = None, query_token: str | None = None
    ) -> Actor | None:
        token = _bearer(authorization, query_token)
        if not token:
            return None
        return await self.resolve_token(token)

    async def authenticate_request(self, request: Any) -> Actor:
        """Return the request's actor; enforce auth when enabled (fail-closed)."""
        actor = await self.authenticate(
            authorization=request.headers.get("authorization"),
            query_token=request.query_params.get("access_token"),
        )
        if actor is not None:
            return actor
        if not self.enabled:
            return self.default_actor()
        raise AuthError("authentication required")


def ensure_roles(actor: Actor, roles: tuple[str, ...]) -> Actor:
    if roles and not actor.has_role(*roles):
        raise ForbiddenError(
            "insufficient role", detail={"required": list(roles), "held": sorted(actor.roles)}
        )
    return actor


def require_roles(*roles: str) -> Callable[[Any], Awaitable[Actor]]:
    """A FastAPI dependency: authenticate the request and require a role."""
    from agentkit.webui.auth import authenticator_of

    async def dependency(request: Any) -> Actor:
        actor = await authenticator_of(request).authenticate_request(request)
        return ensure_roles(actor, roles)

    return dependency


class AnonymousAuth:
    """An auth driver that never authenticates; always the default actor."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def default_actor(self) -> Actor:
        return system_actor(self.settings)

    async def resolve_token(self, token: str) -> Actor | None:
        return None

    async def authenticate(
        self, *, authorization: str | None = None, query_token: str | None = None
    ) -> Actor | None:
        return None


class AuthManager(Manager):
    """Resolves the configured auth driver (``auth_driver``, default ``default``)."""

    kind = DriverKind.AUTH
    default_driver = AuthDriver.DEFAULT


@register_driver(DriverKind.AUTH, AuthDriver.DEFAULT)
class DefaultAuthDriver(Driver):
    def build(self) -> Authenticator:
        app = self.app
        return Authenticator(app.settings)
@register_driver(DriverKind.AUTH, AuthDriver.ANONYMOUS)
class AnonymousAuthDriver(Driver):
    def build(self) -> AnonymousAuth:
        app = self.app
        return AnonymousAuth(app.settings)
__all__ = [
    "AnonymousAuth",
    "AuthError",
    "AuthManager",
    "AuthStrategy",
    "Authenticator",
    "ForbiddenError",
    "ensure_roles",
    "require_roles",
]
