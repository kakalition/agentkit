"""Web-UI authentication wiring (opt-in).

Installs an HTTP middleware that resolves the request's :class:`Actor` and stores
it on ``request.state.actor``; when auth is enabled an unauthenticated ``/api``
request is rejected (fail-closed). The SPA, static assets, health and docs stay
public.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentkit.ratelimit import build_limiter
from agentkit.security import API_KEY, Actor
from agentkit.security.authenticator import Authenticator, AuthError, ForbiddenError

PUBLIC_PATHS = frozenset({"/api/health"})
PUBLIC_PREFIXES = ("/api/docs", "/api/openapi.json")


def make_db_lookup(runtime: Any) -> Any:
    """A hash → Actor lookup backed by the ``api_keys`` table."""

    async def lookup(key_hash: str) -> Actor | None:
        from agentkit.runtime import repositories

        async with repositories(runtime) as repos:
            row = await repos.api_keys.resolve(key_hash)
            if row is None or row.revoked_at is not None:
                return None
            if row.id is not None:
                await repos.api_keys.touch(row.id)
            roles = json.loads(row.roles or "[]")
            return Actor(
                owner_id=row.owner_id,
                subject=row.name,
                roles=frozenset(str(role) for role in roles),
                method=API_KEY,
            )

    return lookup


def authenticator_of(request: Request) -> Authenticator:
    return request.app.state.webui.authenticator  # type: ignore[no-any-return]


async def require_actor(request: Request) -> Actor:
    """A dependency enforcing auth and returning the request's actor."""
    return await authenticator_of(request).authenticate_request(request)


def _is_public(path: str) -> bool:
    if not path.startswith("/api"):
        return True
    if path in PUBLIC_PATHS:
        return True
    return path.startswith(PUBLIC_PREFIXES)


def install_auth(app: FastAPI, *, runtime: Any, settings: Any) -> Authenticator:
    authenticator = Authenticator(settings, db_lookup=make_db_lookup(runtime))
    app.state.webui.authenticator = authenticator

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next: Any) -> Any:
        if _is_public(request.url.path):
            return await call_next(request)
        try:
            actor = await authenticator.authenticate_request(request)
        except AuthError as exc:
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}}, status_code=401
            )
        except ForbiddenError as exc:
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}}, status_code=403
            )
        request.state.actor = actor
        return await call_next(request)

    return authenticator


def install_rate_limit(app: FastAPI, *, runtime: Any, settings: Any) -> Any:
    """Install the fixed-window limiter (429 + ``Retry-After``); no-op when off.

    Added before :func:`install_auth` so it runs *after* authentication and can
    key on the resolved actor.
    """
    limiter = build_limiter(settings, runtime)
    app.state.webui.rate_limiter = limiter
    if limiter is None:
        return None

    @app.middleware("http")
    async def _rate_middleware(request: Request, call_next: Any) -> Any:
        if not request.url.path.startswith("/api") or _is_public(request.url.path):
            return await call_next(request)
        actor = getattr(request.state, "actor", None)
        owner = actor.owner_id if actor is not None else None
        decision = await limiter.hit(f"http:{request.method}", owner_id=owner)
        if not decision.allowed:
            return JSONResponse(
                {
                    "error": {
                        "code": "rate_limited",
                        "message": "rate limit exceeded",
                        "retry_after": decision.retry_after,
                    }
                },
                status_code=429,
                headers={"Retry-After": str(decision.retry_after)},
            )
        return await call_next(request)

    return limiter


__all__ = [
    "authenticator_of",
    "install_auth",
    "install_rate_limit",
    "make_db_lookup",
    "require_actor",
]
