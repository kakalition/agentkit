"""Prometheus metrics (opt-in via ``METRICS_ENABLED``).

Metrics are no-ops until :func:`enable` is called, so importing this module is
free and library code can call the helpers unconditionally. The registry is the
default one, exposed at ``/metrics`` by the web UI.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

_ENABLED = False
_METRICS: dict[str, Any] = {}


def enable(settings: Any = None) -> bool:
    """Turn metrics on (respecting ``settings.metrics_enabled`` when given)."""
    global _ENABLED
    if settings is not None and not getattr(settings, "metrics_enabled", False):
        return False
    _enabled_impl()
    _ENABLED = True
    return True


def _enabled_impl() -> None:
    if _METRICS:
        return
    from prometheus_client import Counter, Gauge, Histogram

    _METRICS.update(
        turns=Counter("agentkit_turns_total", "Chat turns by outcome.", ["status"]),
        turn_seconds=Histogram("agentkit_turn_seconds", "Wall time of a chat turn."),
        tool_errors=Counter("agentkit_tool_errors_total", "Tool errors.", ["tool"]),
        queue_depth=Gauge("agentkit_queue_depth", "Pending jobs per queue.", ["queue"]),
        scheduler_runs=Counter(
            "agentkit_scheduler_runs_total", "Scheduler task runs.", ["task", "status"]
        ),
        cost=Counter("agentkit_cost_usd_total", "Estimated model cost (USD)."),
    )


def is_enabled() -> bool:
    return _ENABLED


def record_turn(status: str, seconds: float | None = None) -> None:
    if not _ENABLED:
        return
    _METRICS["turns"].labels(status=status).inc()
    if seconds is not None:
        _METRICS["turn_seconds"].observe(seconds)


def record_tool_error(tool: str) -> None:
    if _ENABLED:
        _METRICS["tool_errors"].labels(tool=tool).inc()


def record_queue_depth(queue: str, depth: int) -> None:
    if _ENABLED:
        _METRICS["queue_depth"].labels(queue=queue).set(depth)


def record_scheduler_run(task: str, status: str) -> None:
    if _ENABLED:
        _METRICS["scheduler_runs"].labels(task=task, status=status).inc()


def record_cost(amount: float) -> None:
    if _ENABLED and amount:
        _METRICS["cost"].inc(float(amount))


@contextmanager
def time_turn() -> Any:
    start = time.perf_counter()
    try:
        yield
    finally:
        record_turn("ok", time.perf_counter() - start)


def render() -> str:
    from prometheus_client import generate_latest

    return generate_latest().decode("utf-8")


def content_type() -> str:
    from prometheus_client import CONTENT_TYPE_LATEST

    return CONTENT_TYPE_LATEST


__all__ = [
    "content_type",
    "enable",
    "is_enabled",
    "record_cost",
    "record_queue_depth",
    "record_scheduler_run",
    "record_tool_error",
    "record_turn",
    "render",
    "time_turn",
]
