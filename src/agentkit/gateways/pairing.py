"""DM pairing: let an unknown user claim a bot with a short code.

A bot with no allow-list accepts anyone; with a *pairing* registry it instead
sends an unpaired user a code, and only lets them talk once they confirm it. The
registry is in-memory by default (pairings do not survive a restart), with hooks
to persist it.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

__all__ = ["PairingRegistry"]


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
