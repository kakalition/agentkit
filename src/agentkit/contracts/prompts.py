"""The prompt-store contract — a named, versioned, renderable prompt registry."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["PromptStore"]


@runtime_checkable
class PromptStore(Protocol):
    """Resolve and render named prompts."""

    def get(self, name: str) -> Any | None: ...

    def names(self) -> list[str]: ...

    def render(self, name: str, **variables: Any) -> str: ...

    def register(self, prompt: Any) -> Any: ...
