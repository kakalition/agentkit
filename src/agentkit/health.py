"""Health/readiness checks and graceful-shutdown helpers."""

from __future__ import annotations

import contextlib
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
    fn: Callable[[], bool]


def run_checks(checks: list[Check]) -> tuple[bool, dict[str, bool]]:
    results: dict[str, bool] = {}
    for check in checks:
        try:
            results[check.name] = bool(check.fn())
        except Exception:  # pragma: no cover - defensive
            results[check.name] = False
    return all(results.values()), results


def db_check(runtime: Any, *, name: str = "db") -> Check:
    """Readiness check that the database is reachable."""

    def _check() -> bool:
        with runtime.session_factory() as session:  # type: ignore[attr-defined]
            session.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True

    return Check(name, _check)


def health_routes(checks: list[Check] | None = None) -> list[Route]:
    """``/healthz`` (liveness) and ``/readyz`` (readiness)."""
    checks = checks or []

    async def healthz(request: Any) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def readyz(request: Any) -> JSONResponse:
        ok, results = run_checks(checks)
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
