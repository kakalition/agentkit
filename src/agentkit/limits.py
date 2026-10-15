"""Budgets and rate limits over recorded usage.

    from agentkit import App
    from agentkit.limits import Budget

    app.budget(Budget(max_cost=5.0, max_tokens=1_000_000, window_seconds=86400))

Before each turn the app checks recorded usage (optionally per conversation or
over a rolling window) and raises :class:`~agentkit.errors.BudgetExceeded` when a
limit is reached.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agentkit.errors import BudgetExceeded

__all__ = ["Budget", "check_budget"]


@dataclass
class Budget:
    """A spend/usage ceiling. ``None`` fields are unbounded."""

    max_tokens: int | None = None
    max_cost: float | None = None
    max_requests: int | None = None
    window_seconds: int | None = None
    per_conversation: bool = False

    def violations(self, totals: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        if self.max_tokens is not None and int(totals.get("total_tokens", 0)) >= self.max_tokens:
            reasons.append(f"tokens {totals.get('total_tokens')} >= {self.max_tokens}")
        if self.max_cost is not None and float(totals.get("cost_usd", 0.0)) >= self.max_cost:
            reasons.append(f"cost {totals.get('cost_usd')} >= {self.max_cost}")
        if (
            self.max_requests is not None
            and int(totals.get("requests", 0)) >= self.max_requests
        ):
            reasons.append(f"requests {totals.get('requests')} >= {self.max_requests}")
        return reasons


async def check_budget(
    repos: Any, budget: Budget, *, conversation_id: str | None = None
) -> dict[str, Any]:
    """Raise :class:`BudgetExceeded` if recorded usage already meets ``budget``."""
    since = None
    if budget.window_seconds is not None:
        since = datetime.now(UTC) - timedelta(seconds=budget.window_seconds)
    store = getattr(repos, "usage", None)
    if store is None:
        return {}
    scope = conversation_id if budget.per_conversation else None
    if scope is not None:
        rows = await store.list(limit=None)
        totals = _totals_for(rows, scope, since)
    else:
        totals = await store.totals(since=since)
    reasons = budget.violations(totals)
    if reasons:
        raise BudgetExceeded("budget exceeded", detail={"reasons": reasons, "totals": totals})
    return totals


def _totals_for(rows: list[Any], conversation_id: str, since: Any) -> dict[str, Any]:
    totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
    for row in rows:
        if getattr(row, "conversation_id", None) != conversation_id:
            continue
        if since is not None and getattr(row, "created_at", None) is not None:
            created = row.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if created < since:
                continue
        totals["requests"] += int(getattr(row, "requests", 0) or 0)
        totals["input_tokens"] += int(getattr(row, "input_tokens", 0) or 0)
        totals["output_tokens"] += int(getattr(row, "output_tokens", 0) or 0)
        totals["total_tokens"] += int(getattr(row, "total_tokens", 0) or 0)
        totals["cost_usd"] += float(getattr(row, "cost_usd", 0.0) or 0.0)
    totals["cost_usd"] = round(totals["cost_usd"], 8)
    return totals
