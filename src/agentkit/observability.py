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
    """Configure local span export + instrument PydanticAI. True if enabled.

    ``OBSERVABILITY=phoenix`` launches a local Arize Phoenix UI (no account) and
    sends spans to it — zero-config.
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
            endpoint = start_phoenix(settings)
            logfire.configure(
                send_to_logfire=False,
                console=False,
                additional_span_processors=[_exporter_processor(endpoint)],
            )
        else:
            return False
        logfire.instrument_pydantic_ai()
    except Exception:  # pragma: no cover - defensive
        return False
    return True


PHOENIX_PORT = 6006


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
