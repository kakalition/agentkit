"""The guardrail contract — scan and redact untrusted text."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["Scanner"]


@runtime_checkable
class Scanner(Protocol):
    """Scan text for unsafe content and optionally redact it."""

    def scan(self, text: str) -> list[str]: ...

    def redact(self, text: str) -> str: ...
