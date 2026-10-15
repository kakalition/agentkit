"""JWT/JWKS verification (opt-in, used when ``auth_jwks_url`` is configured).

The signing keys are fetched once from the JWKS endpoint and cached with a TTL;
an unknown ``kid`` triggers one refetch to pick up key rotation. Verification is
fail-closed: any error is surfaced as :class:`JWTError`, never an allow.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import jwt

from agentkit.security import JWT, Actor


class JWTError(Exception):
    """Raised when a token cannot be trusted (malformed, expired, bad signature)."""


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part for part in value.replace(",", " ").split() if part)
    return tuple(str(part) for part in value)


class JWKSVerifier:
    """Verify bearer JWTs against a JWKS endpoint, mapping claims to an Actor."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str | None = None,
        audience: str | None = None,
        algorithms: Any = ("RS256",),
        owner_claim: str = "sub",
        roles_claim: str = "roles",
        default_owner: str = "",
        cache_ttl: float = 300.0,
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.algorithms = _as_tuple(algorithms) or ("RS256",)
        self.owner_claim = owner_claim
        self.roles_claim = roles_claim
        self.default_owner = default_owner
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self._client = client
        self._keys: dict[str, Any] | None = None
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _fetch(self) -> None:
        client = self._client or httpx.AsyncClient()
        try:
            response = await client.get(self.jwks_url, timeout=self.timeout)
            response.raise_for_status()
            document = response.json()
        except Exception as exc:  # httpx errors, malformed JSON, non-200
            raise JWTError(f"could not load JWKS: {type(exc).__name__}") from exc
        finally:
            if self._client is None:
                await client.aclose()
        keys: dict[str, Any] = {}
        for key_data in document.get("keys", []):
            try:
                py_jwk = jwt.PyJWK(key_data)
            except Exception:  # pragma: no cover - unsupported key type  # nosec B110
                continue
            kid = key_data.get("kid") or getattr(py_jwk, "key_id", "") or ""
            keys[str(kid)] = py_jwk
        if not keys:
            raise JWTError("JWKS contained no usable keys")
        self._keys = keys
        self._fetched_at = time.monotonic()

    async def _get_key(self, kid: str | None) -> Any:
        async with self._lock:
            now = time.monotonic()
            keys = self._keys
            if keys is None:
                need_fetch = True
            else:
                need_fetch = (now - self._fetched_at) > self.cache_ttl or (
                    bool(kid) and str(kid) not in keys
                )
            if need_fetch:
                await self._fetch()
            assert self._keys is not None
            if kid and str(kid) in self._keys:
                return self._keys[str(kid)]
            if kid:
                raise JWTError("token signed by an unknown key")
            return next(iter(self._keys.values()))

    async def verify(self, token: str) -> Actor:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise JWTError("malformed token") from exc
        signing_key = await self._get_key(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key=signing_key.key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": self.audience is not None},
            )
        except jwt.PyJWTError as exc:
            raise JWTError("invalid token") from exc
        owner = claims.get(self.owner_claim) or claims.get("email") or self.default_owner
        if not owner:
            raise JWTError("token has no owner claim")
        return Actor(
            owner_id=str(owner),
            subject=str(claims.get("sub") or owner),
            roles=frozenset(_as_tuple(claims.get(self.roles_claim))),
            method=JWT,
        )


__all__ = ["JWKSVerifier", "JWTError"]
