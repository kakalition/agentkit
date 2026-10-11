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

from agentkit.config import AgentSettings, get_settings


def setup_observability(settings: AgentSettings | None = None) -> bool:
    """Configure local span export + instrument PydanticAI. True if enabled."""
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


# Backwards-compatible aliases.
setup_logfire = setup_observability
