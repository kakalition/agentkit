"""The self-learning contracts — extract, strategize, and sink."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["Extractor", "LearningSink", "LearningStrategy"]


@runtime_checkable
class Extractor(Protocol):
    """Distil lessons/preferences/facts from a conversation window."""

    async def extract(
        self, messages: list[Any], model: Any = None
    ) -> dict[str, list[str]]: ...


@runtime_checkable
class LearningStrategy(Protocol):
    """Run the reflect -> learn -> apply loop over a repository."""

    async def run(self, repos: Any, **options: Any) -> dict[str, Any]: ...


@runtime_checkable
class LearningSink(Protocol):
    """Persist extracted signals (lessons/preferences/facts)."""

    async def store(self, repos: Any, items: dict[str, list[str]], **options: Any) -> int: ...
