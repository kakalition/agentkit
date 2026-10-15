"""Observability via OpenTelemetry — self-hosted, **no account required**.

PydanticAI has no native instrumenter; its spans are produced through the
``logfire`` *library* (a dependency of PydanticAI) used purely as the
instrumenter. We always run it in **local mode** (``send_to_logfire=False``):
spans are never sent to logfire.dev or any hosted account. Export goes to your
own OpenTelemetry backend via the OTLP exporter.

Modes (``OBSERVABILITY``):

* ``off``     — disabled (default).
* ``console`` — print spans to the terminal (local, free).
* ``otlp``    — export over OTLP to a backend you run: **Arize Phoenix**
  (``http://127.0.0.1:6006/v1/traces``), **Jaeger**, **Grafana Tempo**,
  **Langfuse**, or an OpenTelemetry Collector. Set ``OTLP_ENDPOINT`` or
  ``OTEL_EXPORTER_OTLP_ENDPOINT``.

Requires the optional ``observability`` extra (OpenTelemetry OTLP HTTP exporter).
"""

from __future__ import annotations

import os
from typing import Any

from agentkit.config import AgentSettings, get_settings
from agentkit.contracts.observability import Tracer
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, ObservabilityDriver
from agentkit.support.manager import Manager

__all__ = [
    "ObservabilityManager",
    "Tracer",
    "setup_observability",
    "setup_logfire",
    "start_phoenix",
]

_phoenix_started = False


def setup_observability(settings: AgentSettings | None = None) -> bool:
    """Configure local span export + instrument PydanticAI. True if enabled.

    ``OBSERVABILITY=phoenix`` (the default) launches a local Arize Phoenix UI
    (no account) and sends spans to it, falling back to console output if the
    Phoenix package is not installed.
    """
    settings = settings or get_settings()
    mode = settings.observability.strip().lower() or "off"
    if mode == "off":
        return False
    try:
        import logfire

        if mode == "console":
            logfire.configure(send_to_logfire=False)
        elif mode == "otlp":
            logfire.configure(
                send_to_logfire=False,
                console=False,
                additional_span_processors=[_otlp_processor(settings)],
            )
        elif mode == "phoenix":
            endpoint = _ensure_phoenix(settings)
            if endpoint:
                logfire.configure(
                    send_to_logfire=False,
                    console=False,
                    additional_span_processors=[_exporter_processor(endpoint)],
                )
            else:  # Phoenix not installed -> still useful: console spans
                logfire.configure(send_to_logfire=False)
        else:
            return False
        logfire.instrument_pydantic_ai()
    except Exception:  # pragma: no cover - defensive
        return False
    return True


PHOENIX_PORT = 6006


def _phoenix_endpoint(settings: AgentSettings) -> str:
    return f"http://127.0.0.1:{_phoenix_port()}/v1/traces"


def _phoenix_port() -> int:
    return int(os.environ.get("PHOENIX_PORT", PHOENIX_PORT))


def _ensure_phoenix(settings: AgentSettings) -> str | None:
    """Launch the local Phoenix UI once per process; ``None`` if unavailable."""
    global _phoenix_started
    try:
        import phoenix  # noqa: F401
    except ImportError:
        return None
    if not _phoenix_started:
        try:
            start_phoenix(settings)
            _phoenix_started = True
        except Exception:  # already running or failed to start
            pass
    return _phoenix_endpoint(settings)


def start_phoenix(settings: AgentSettings | None = None, *, port: int | None = None) -> str:
    """Launch the local Arize Phoenix UI and return its OTLP traces endpoint."""
    import phoenix as px

    resolved = port or int(os.environ.get("PHOENIX_PORT", PHOENIX_PORT))
    os.environ["PHOENIX_PORT"] = str(resolved)
    # The very first launch initialises Phoenix's schema and can exceed the
    # server-start cap; a single retry reliably succeeds.
    last_error: Exception | None = None
    for _ in range(2):
        try:
            px.launch_app()
            return f"http://127.0.0.1:{resolved}/v1/traces"
        except Exception as exc:  # pragma: no cover - first-run slowness
            last_error = exc
    raise RuntimeError(f"failed to launch Phoenix: {last_error}")


def _exporter_processor(endpoint: str):  # pragma: no cover - needs OTEL deps
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    return BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))


def _otlp_processor(settings: AgentSettings):  # pragma: no cover - needs OTEL deps
    endpoint = settings.otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        return _exporter_processor(endpoint)
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    return BatchSpanProcessor(OTLPSpanExporter())


# Backwards-compatible aliases.
setup_logfire = setup_observability


class _ModeTracer:
    """A tracer driver that force-selects one ``OBSERVABILITY`` mode."""

    def __init__(self, mode: ObservabilityDriver) -> None:
        self.mode = mode

    def setup(self, settings: AgentSettings | None = None) -> bool:
        settings = settings or get_settings()
        override = settings
        copy = getattr(settings, "model_copy", None)
        if callable(copy):
            try:
                override = copy(update={"observability": self.mode})
            except Exception:  # pragma: no cover - non-pydantic settings
                override = settings
        return setup_observability(override)


class ObservabilityManager(Manager):
    """Resolves the configured tracer (the ``observability`` setting, default ``phoenix``)."""

    kind = DriverKind.OBSERVABILITY
    default_driver = ObservabilityDriver.PHOENIX

    @property
    def setting_name(self) -> str:
        return "observability"


@register_driver(DriverKind.OBSERVABILITY, ObservabilityDriver.PHOENIX)
def _phoenix_tracer_driver(app: Any) -> _ModeTracer:
    return _ModeTracer(ObservabilityDriver.PHOENIX)


@register_driver(DriverKind.OBSERVABILITY, ObservabilityDriver.CONSOLE)
def _console_tracer_driver(app: Any) -> _ModeTracer:
    return _ModeTracer(ObservabilityDriver.CONSOLE)


@register_driver(DriverKind.OBSERVABILITY, ObservabilityDriver.OTLP)
def _otlp_tracer_driver(app: Any) -> _ModeTracer:
    return _ModeTracer(ObservabilityDriver.OTLP)


@register_driver(DriverKind.OBSERVABILITY, ObservabilityDriver.OFF)
def _off_tracer_driver(app: Any) -> _ModeTracer:
    return _ModeTracer(ObservabilityDriver.OFF)
