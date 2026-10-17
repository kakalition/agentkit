"""Native usage/audit toolkit: read-only token accounting and the audit trail."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.toolkits._common import repos_of

__all__ = ["_attach_usage"]

MAX_LIMIT = 1000
_WINDOWS = {"all": None, "today": 1, "24h": 1, "7d": 7, "30d": 30}


def _since(window: str) -> datetime | None:
    days = _WINDOWS.get((window or "all").lower())
    if days is None:
        return None
    return datetime.now(UTC) - timedelta(days=days)


def _attach_usage(agent: Any, *, flag: str = "usage_tools_enabled") -> Any:
    """Register the usage/audit tools on a built PydanticAI agent (idempotent)."""
    if getattr(agent, "_agentkit_usage_attached", False):
        return agent

    @agent.tool
    async def usage_summary(ctx: RunContext[Deps], window: str = "all") -> str:
        """Summarize token usage and estimated cost over a window.

        Args:
            window: One of all, today, 24h, 7d, 30d.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        return json.dumps(await repos.usage.totals(since=_since(window)), default=str)

    @agent.tool
    async def audit_trail(ctx: RunContext[Deps], limit: int = 20) -> str:
        """Show recent audit-log entries (newest last).

        Args:
            limit: Maximum entries to return.
        """
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        rows = await repos.audit.entries(limit=max(1, min(int(limit), MAX_LIMIT)))
        if not rows:
            return "(empty audit log)"
        return json.dumps(
            [
                {
                    "seq": row.seq,
                    "action": row.action,
                    "target": row.target,
                    "actor": row.actor,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ],
            default=str,
        )

    @agent.tool
    async def verify_audit(ctx: RunContext[Deps]) -> str:
        """Verify the audit log's hash chain is intact."""
        repos = repos_of(ctx)
        if repos is None:
            return "ERROR: no repositories"
        return "audit log intact" if await repos.audit.verify() else "audit log TAMPERED"

    agent._agentkit_usage_attached = True  # type: ignore[attr-defined]
    return agent
