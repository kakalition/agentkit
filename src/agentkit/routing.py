"""Model routing and fallback.

Pick a model per turn from declarative rules, with optional fallback models used
when the chosen one fails::

    from agentkit import ModelRouter

    router = (
        ModelRouter()
        .route("openai:gpt-5-mini", when=lambda ctx: ctx is not None and len(ctx.text) < 500)
        .route("openai:gpt-5", when=lambda ctx: True)
        .otherwise("openai:gpt-4o-mini")
        .with_fallbacks("openai:gpt-4o")
    )
    app.model_resolver(router)          # called with a Turn context each turn

A router is callable (``router(context) -> model``), so any
``callable(context) -> model`` resolver works too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = ["ModelRouter", "Route"]


@dataclass
class Route:
    model: Any
    when: Callable[[Any], bool] | None = None
    label: str = ""


class ModelRouter:
    """Choose a model from ordered rules, with optional fallbacks."""

    def __init__(self, model: Any = None, *, default: Any = None) -> None:
        self._routes: list[Route] = []
        self._default = default if default is not None else model
        self._fallbacks: list[Any] = []
        if model is not None or default is not None:
            baseline = default if default is not None else model
            self._routes.append(Route(baseline, None, "default"))

    def route(
        self, model: Any, *, when: Callable[[Any], bool] | None = None, label: str = ""
    ) -> ModelRouter:
        self._routes.append(Route(model, when, label))
        return self

    def otherwise(self, model: Any) -> ModelRouter:
        """The model used when no route matches."""
        self._default = model
        return self

    def with_fallbacks(self, *models: Any) -> ModelRouter:
        """Fallback models tried in order when the selected model fails."""
        self._fallbacks = list(models)
        return self

    def select(self, context: Any = None) -> Any:
        model: Any = None
        for route in self._routes:
            if route.when is None or route.when(context):
                model = route.model
                break
        if model is None:
            model = self._default
        if model is None:
            return None
        return self._wrap(model)

    def _wrap(self, model: Any) -> Any:
        if not self._fallbacks:
            return model
        try:
            from pydantic_ai.models.fallback import FallbackModel

            return FallbackModel(model, *self._fallbacks)
        except Exception:  # pragma: no cover - defensive
            return model

    def resolve(self, context: Any = None) -> Any:
        return self.select(context)

    def __call__(self, context: Any = None) -> Any:
        return self.select(context)
