"""Health/readiness checks and graceful-shutdown helpers."""

from __future__ import annotations

import contextlib
import inspect
import signal
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType
from typing import Any

from starlette.responses import JSONResponse
from starlette.routing import Route


@dataclass
class Check:
    name: str
    fn: Callable[[], Any]


async def run_checks(checks: list[Check]) -> tuple[bool, dict[str, bool]]:
    results: dict[str, bool] = {}
    for check in checks:
        try:
            outcome = check.fn()
            if inspect.isawaitable(outcome):
                outcome = await outcome
            results[check.name] = bool(outcome)
        except Exception:  # pragma: no cover - defensive
            results[check.name] = False
    return all(results.values()), results


def db_check(runtime: Any, *, name: str = "db") -> Check:
    """Readiness check that the database is reachable."""

    async def _check() -> bool:
        from sqlmodel import select

        async with runtime.session_factory() as session:  # type: ignore[attr-defined]
            await session.exec(select(1))
        return True

    return Check(name, _check)


def health_routes(checks: list[Check] | None = None) -> list[Route]:
    """``/healthz`` (liveness) and ``/readyz`` (readiness)."""
    checks = checks or []

    async def healthz(request: Any) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def readyz(request: Any) -> JSONResponse:
        ok, results = await run_checks(checks)
        return JSONResponse(
            {"status": "ok" if ok else "error", "checks": results},
            status_code=200 if ok else 503,
        )

    return [Route("/healthz", healthz), Route("/readyz", readyz)]


def install_signal_handlers(on_shutdown: Callable[[], None]) -> None:
    """Call ``on_shutdown`` once on SIGINT/SIGTERM (best effort)."""

    def _handler(signum: int, frame: FrameType | None) -> None:
        on_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError, OSError):  # non-main thread
            signal.signal(sig, _handler)
