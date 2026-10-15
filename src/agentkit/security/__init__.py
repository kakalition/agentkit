"""Identity primitives for opt-in authentication and RBAC.

The local-first default is unchanged: with auth disabled the runtime runs as a
single :class:`Actor` derived from ``settings.owner_id`` and carries no roles.
An :class:`Actor` is the resolved identity for one request/run — it names the
tenant (``owner_id``), the authenticated ``subject``, any ``roles``, and how the
identity was established (``method``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

NONE = "none"
API_KEY = "api_key"
JWT = "jwt"


@dataclass(frozen=True, slots=True)
class Actor:
    """A resolved identity: the tenant key plus its provenance."""

    owner_id: str
    subject: str = ""
    roles: frozenset[str] = field(default_factory=frozenset)
    method: str = NONE

    def has_role(self, *roles: str) -> bool:
        """True when the actor holds any of ``roles`` (empty query always True)."""
        if not roles:
            return True
        return bool(self.roles.intersection(roles))

    def with_roles(self, *roles: str) -> Actor:
        return replace(self, roles=self.roles.union(roles))

    @property
    def authenticated(self) -> bool:
        return self.method != NONE


def system_actor(settings: Any) -> Actor:
    """The default actor for a settings object (used when auth is disabled)."""
    owner = getattr(settings, "owner_id", "owner") or "owner"
    return Actor(owner_id=owner, subject=owner, method=NONE)


__all__ = ["API_KEY", "JWT", "NONE", "Actor", "system_actor"]
