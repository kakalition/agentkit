"""Structured logging with correlation ids and redaction.

Every log line can carry a ``request_id`` (set via :func:`request_context`) so a
single turn's logs across tools/MCP/A2A can be correlated. Secrets and monetary
amounts are redacted from messages and from logged ``extra`` values.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agentkit_request_id", default=None
)

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}"
    r"|user_[A-Za-z0-9]{8,}"
    r"|gh[pousr]_[A-Za-z0-9]{8,}"
    r"|Bearer\s+\S+"
    r"|-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)
_AMOUNT_RE = re.compile(r"(?<![\w.])[$€£¥]?\d{1,3}(?:,\d{3})*\.\d{2}(?![\w.])")


def redact(text: str) -> str:
    """Redact secrets and monetary amounts from a string."""
    return _AMOUNT_RE.sub("[amount]", _SECRET_RE.sub("[redacted]", text))


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return request_id_var.get()


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """Bind a request id for the duration of a turn."""
    rid = request_id or new_request_id()
    token = request_id_var.set(rid)
    try:
        yield rid
    finally:
        request_id_var.reset(token)


class RedactingJsonFormatter(logging.Formatter):
    """Minimal JSON lines with a request id and redacted content."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = redact(value) if isinstance(value, str) else value
        return json.dumps(payload, default=str)


class RedactingTextFormatter(logging.Formatter):
    """Human-readable logs with redaction and a request id."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        rid = request_id_var.get()
        if rid:
            base = f"{base} [request_id={rid}]"
        return redact(base)


def setup_logging(settings: Any = None) -> None:
    """Configure the root logger from settings (``log_level``, ``log_json``)."""
    level = getattr(settings, "log_level", "INFO")
    as_json = bool(getattr(settings, "log_json", False))
    handler = logging.StreamHandler()
    if as_json:
        handler.setFormatter(RedactingJsonFormatter())
    else:
        handler.setFormatter(RedactingTextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper() if isinstance(level, str) else level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
