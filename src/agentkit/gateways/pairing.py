"""DM pairing: let an unknown user claim a bot with a short code.

A bot with no allow-list accepts anyone; with a *pairing* registry it instead
sends an unpaired user a code, and only lets them talk once they confirm it. The
registry is in-memory by default (pairings do not survive a restart);
``pairing_driver=repository`` swaps in a database-backed registry so pairings
survive a restart (and are shared across processes).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agentkit._sync import run_sync
from agentkit.support import Driver, register_driver
from agentkit.support.kinds import DriverKind, PairingDriver
from agentkit.support.manager import Manager

__all__ = ["PairingManager", "PairingRegistry", "RepositoryPairingRegistry"]


class PairingRegistry:
    """Issues and verifies short pairing codes per external user id."""

    def __init__(
        self,
        *,
        code_ttl_s: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.code_ttl_s = code_ttl_s
        self._clock = clock
        self._pending: dict[str, tuple[str, float]] = {}
        self._paired: set[str] = set()

    def request(self, external_id: object, *, code: str | None = None) -> str:
        """Issue (or reissue) a pairing code for ``external_id`` and return it."""
        key = str(external_id)
        resolved = code or f"{random.randint(0, 999999):06d}"
        self._pending[key] = (resolved, self._clock() + self.code_ttl_s)
        return resolved

    def confirm(self, external_id: object, code: str) -> bool:
        """Confirm ``code`` for ``external_id`` (single use, TTL-bounded)."""
        key = str(external_id)
        entry = self._pending.get(key)
        if entry is None:
            return False
        issued, expires = entry
        if self._clock() > expires or code != issued:
            return False
        self._pending.pop(key, None)
        self._paired.add(key)
        return True

    def is_paired(self, external_id: object) -> bool:
        return str(external_id) in self._paired

    def unpair(self, external_id: object) -> bool:
        key = str(external_id)
        self._pending.pop(key, None)
        if key in self._paired:
            self._paired.discard(key)
            return True
        return False

    def paired(self) -> list[str]:
        return sorted(self._paired)


class RepositoryPairingRegistry:
    """A database-backed pairing registry (``pairing_driver=repository``).

    Same synchronous API as :class:`PairingRegistry`, but pairings persist to the
    ``gateway_pairings`` table (one session per operation, via the sync seam), so
    they survive a restart. ``scope`` names the channel so external ids from two
    gateways cannot collide.
    """

    def __init__(
        self,
        app: Any,
        *,
        scope: str = "default",
        code_ttl_s: float = 900.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app = app
        self.scope = scope
        self.code_ttl_s = code_ttl_s
        self._clock = clock

    def _expires_at(self) -> datetime:
        return datetime.fromtimestamp(self._clock() + self.code_ttl_s, UTC)

    def request(self, external_id: object, *, code: str | None = None) -> str:
        resolved = code or f"{random.randint(0, 999999):06d}"
        expires_at = self._expires_at()
        run_sync(self._request(str(external_id), resolved, expires_at))
        return resolved

    def confirm(self, external_id: object, code: str) -> bool:
        now = datetime.fromtimestamp(self._clock(), UTC)
        return bool(run_sync(self._confirm(str(external_id), code, now)))

    def is_paired(self, external_id: object) -> bool:
        return bool(run_sync(self._is_paired(str(external_id))))

    def unpair(self, external_id: object) -> bool:
        return bool(run_sync(self._unpair(str(external_id))))

    def paired(self) -> list[str]:
        return list(run_sync(self._paired()))

    async def _request(self, external_id: str, code: str, expires_at: datetime) -> None:
        async with self.app.repositories() as repos:
            await repos.pairing.request(self.scope, external_id, code, expires_at)

    async def _confirm(self, external_id: str, code: str, now: datetime) -> bool:
        async with self.app.repositories() as repos:
            return await repos.pairing.confirm(self.scope, external_id, code, now)

    async def _is_paired(self, external_id: str) -> bool:
        async with self.app.repositories() as repos:
            return await repos.pairing.is_paired(self.scope, external_id)

    async def _unpair(self, external_id: str) -> bool:
        async with self.app.repositories() as repos:
            return await repos.pairing.unpair(self.scope, external_id)

    async def _paired(self) -> list[str]:
        async with self.app.repositories() as repos:
            return await repos.pairing.paired(self.scope)


class PairingManager(Manager):
    """Resolves the configured pairing registry (``pairing_driver``, default ``memory``)."""

    kind = DriverKind.PAIRING
    default_driver = PairingDriver.MEMORY

    def create_memory_driver(self, app: Any) -> PairingRegistry:
        return PairingRegistry()

    def create_repository_driver(self, app: Any) -> RepositoryPairingRegistry:
        return RepositoryPairingRegistry(app)


@register_driver(DriverKind.PAIRING, PairingDriver.MEMORY)
class MemoryPairingDriver(Driver):
    def build(self) -> PairingRegistry:
        return PairingRegistry()


@register_driver(DriverKind.PAIRING, PairingDriver.REPOSITORY)
class RepositoryPairingDriver(Driver):
    def build(self) -> RepositoryPairingRegistry:
        app = self.app
        return RepositoryPairingRegistry(app)
