"""The pricing contract — estimate USD cost for a model/usage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["PriceProvider"]


@runtime_checkable
class PriceProvider(Protocol):
    """Estimate cost in USD for a model's token usage."""

    def cost(self, model: str, *, input_tokens: int = 0, output_tokens: int = 0) -> float: ...
