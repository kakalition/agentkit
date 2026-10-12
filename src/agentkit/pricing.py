"""Model cost estimation, backed by Pydantic's ``genai_prices``.

``genai_prices`` maintains a live-updated price database, so agentkit does not
ship (or maintain) its own table. Use :func:`estimate_cost` directly, or the
:class:`Pricing` wrapper to add per-model overrides::

    from agentkit import estimate_cost, default_pricing

    estimate_cost("openai:gpt-4o-mini", input_tokens=1200, output_tokens=400)
    default_pricing().set("openai:gpt-4o-mini", input=0.00015, output=0.0006)

PydanticAI already attaches a cost to ``RunUsage`` (``run_usage.cost``); that is
preferred when present and this is the fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genai_prices import Usage as _Usage
from genai_prices import calc_price as _calc_price

__all__ = ["ModelPrice", "Pricing", "default_pricing", "estimate_cost", "set_default_pricing"]

# Provider ids genai_prices recognises; used to route a ``provider:model`` ref.
_KNOWN_PROVIDERS = {
    "openai",
    "anthropic",
    "google",
    "google-vertex",
    "groq",
    "mistral",
    "deepseek",
    "xai",
    "cohere",
    "openrouter",
    "aws",
    "azure",
}


def normalize_model(model: str) -> str:
    """Drop a provider prefix (``openai:gpt-4o`` -> ``gpt-4o``)."""
    return (model or "").split(":", 1)[-1].strip()


def _provider_of(model: str) -> str | None:
    provider, sep, _ = (model or "").partition(":")
    if sep and provider in _KNOWN_PROVIDERS:
        return provider
    return None


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000 tokens (an explicit override)."""

    input_per_1k: float = 0.0
    output_per_1k: float = 0.0


def estimate_cost(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    provider_id: str | None = None,
) -> float | None:
    """Estimated USD cost for a model/usage via ``genai_prices`` (``None`` if unknown)."""
    if not model:
        return None
    provider = provider_id or _provider_of(model)
    ref = normalize_model(model)
    try:
        calculated = _calc_price(
            _Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            ref,
            provider_id=provider,
        )
    except Exception:
        return None
    return round(float(calculated.total_price), 8)


class Pricing:
    """A thin ``genai_prices`` facade with optional per-model overrides."""

    def __init__(self, prices: dict[str, ModelPrice] | None = None) -> None:
        self._overrides: dict[str, ModelPrice] = {}
        if prices:
            self._overrides.update({normalize_model(k).lower(): v for k, v in prices.items()})

    def set(
        self,
        model: str,
        price: ModelPrice | None = None,
        *,
        input: float | None = None,  # noqa: A002 - ergonomic kwarg name
        output: float | None = None,
    ) -> Pricing:
        """Override the price for ``model`` (``ModelPrice`` or explicit rates)."""
        if price is None:
            price = ModelPrice(input or 0.0, output or 0.0)
        self._overrides[normalize_model(model).lower()] = price
        return self

    def get(self, model: str) -> ModelPrice:
        """The override price, or a zero :class:`ModelPrice` (no override)."""
        return self._overrides.get(normalize_model(model).lower(), ModelPrice())

    def has_override(self, model: str) -> bool:
        return normalize_model(model).lower() in self._overrides

    def cost(self, model: str, *, input_tokens: int = 0, output_tokens: int = 0) -> float:
        """Cost in USD: the override when set, else ``genai_prices``, else 0.0."""
        if self.has_override(model):
            price = self.get(model)
            total = (input_tokens / 1000.0) * price.input_per_1k + (
                output_tokens / 1000.0
            ) * price.output_per_1k
            return round(total, 8)
        return estimate_cost(model, input_tokens=input_tokens, output_tokens=output_tokens) or 0.0


_default = Pricing()


def default_pricing() -> Pricing:
    """The process-wide pricing registry used by usage accounting."""
    return _default


def set_default_pricing(pricing: Pricing) -> Pricing:
    global _default
    _default = pricing
    return pricing


def usage_cost(run_usage: Any, model: str) -> float:
    """Prefer PydanticAI's own ``RunUsage.cost``; else estimate via genai_prices."""
    reported = getattr(run_usage, "cost", None)
    if reported is not None:
        try:
            return round(float(reported), 8)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            pass
    return default_pricing().cost(
        model,
        input_tokens=int(getattr(run_usage, "request_tokens", 0) or 0),
        output_tokens=int(getattr(run_usage, "response_tokens", 0) or 0),
    )
