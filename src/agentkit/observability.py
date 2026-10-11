"""Optional observability via Logfire / OpenTelemetry.

Modes (``OBSERVABILITY``): ``off`` | ``console`` (local, free) | ``otlp`` (any
OpenTelemetry backend) | ``logfire`` (cloud free tier). Requires the optional
``observability`` extra; otherwise a no-op.
"""

from __future__ import annotations

import os

from agentkit.config import AgentSettings, get_settings


def setup_logfire(settings: AgentSettings | None = None) -> bool:
    settings = settings or get_settings()
    mode = settings.observability.strip().lower() or "off"
    token = settings.logfire_token or os.environ.get("LOGFIRE_TOKEN")
    if mode == "off":
        if not token:
            return False
        mode = "logfire"
    try:
        import logfire
    except ImportError:
        return False
    try:
        if mode == "logfire":
            if not token:
                return False
            logfire.configure(token=token)
        elif mode == "console":
            logfire.configure(send_to_logfire=False)
        elif mode == "otlp":
            logfire.configure(
                send_to_logfire=False,
                console=False,
                additional_span_processors=[_otlp_processor(settings)],
            )
        else:
            return False
        logfire.instrument_pydantic_ai()
    except Exception:  # pragma: no cover - defensive
        return False
    return True


def _otlp_processor(settings: AgentSettings):  # pragma: no cover - needs OTEL deps
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = settings.otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
    return BatchSpanProcessor(exporter)
