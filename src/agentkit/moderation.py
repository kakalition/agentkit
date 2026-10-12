"""Content moderation and PII handling.

    from agentkit import App
    from agentkit.moderation import ModerationPolicy, moderation_middleware

    policy = ModerationPolicy(banned=["self-harm"], redact_pii=True)
    app.middleware(moderation_middleware(policy))   # scans each turn's input

:class:`ModerationPolicy` combines banned terms, regexes and PII handling. The
middleware raises :class:`~agentkit.errors.ContentBlocked` before a disallowed
turn runs, and can redact PII in place. Use :func:`moderation_hooks` to scan
model output as well, and :func:`check_output` directly for one-off checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agentkit.errors import ContentBlocked
from agentkit.guardrails import redact_pii, scan_pii

__all__ = [
    "ModerationPolicy",
    "ModerationResult",
    "check_output",
    "moderation_hooks",
    "moderation_middleware",
]


@dataclass
class ModerationResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    text: str = ""
    pii: list[str] = field(default_factory=list)


@dataclass
class ModerationPolicy:
    """Banned terms/regexes plus PII handling."""

    banned: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    redact_pii: bool = False
    block_pii: bool = False
    case_sensitive: bool = False

    def __post_init__(self) -> None:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        self._banned = [re.compile(re.escape(term), flags) for term in self.banned]
        self._extra = [re.compile(pattern, flags) for pattern in self.patterns]

    def check(self, text: str) -> ModerationResult:
        text = text or ""
        reasons: list[str] = []
        for pattern in self._banned:
            if pattern.search(text):
                reasons.append(f"banned term: {pattern.pattern}")
        for pattern in self._extra:
            if pattern.search(text):
                reasons.append(f"blocked pattern: {pattern.pattern}")
        pii = scan_pii(text)
        if self.block_pii and pii:
            reasons.append(f"pii detected: {', '.join(pii)}")
        if self.redact_pii and pii:
            text = redact_pii(text, replacement="[redacted]")
        return ModerationResult(allowed=not reasons, reasons=reasons, text=text, pii=pii)


def check_output(text: str, policy: ModerationPolicy) -> str:
    """Return moderated output (redacted), raising when it is disallowed."""
    result = policy.check(text)
    if not result.allowed:
        raise ContentBlocked("output blocked by moderation", detail={"reasons": result.reasons})
    return result.text


def moderation_middleware(policy: ModerationPolicy) -> Any:
    """Turn middleware that screens (and optionally redacts) each input."""

    async def middleware(turn: Any, call_next: Any) -> Any:
        result = policy.check(getattr(turn, "text", "") or "")
        if not result.allowed:
            raise ContentBlocked("input blocked by moderation", detail={"reasons": result.reasons})
        if result.text and result.text != turn.text:
            turn.text = result.text
        return await call_next()

    return middleware


def moderation_hooks(policy: ModerationPolicy) -> Any:
    """A capability scanning model output (raises on disallowed content)."""
    from pydantic_ai.capabilities import Hooks

    hooks = Hooks()

    @hooks.on.after_output_validate
    async def _scan(ctx: Any, *, output_context: Any, output: Any) -> Any:
        if isinstance(output, str):
            check_output(output, policy)
        return output

    return hooks
