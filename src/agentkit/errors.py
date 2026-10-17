"""A small error taxonomy shared across surfaces (MCP, A2A, CLI, tools).

Errors carry a stable ``code`` so callers (and other agents) can react without
parsing messages.
"""

from __future__ import annotations

from typing import Any


class AgentKitError(Exception):
    code = "error"
    http_status = 500

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail is not None:
            payload["detail"] = self.detail
        return {"error": payload}


class ConfigurationError(AgentKitError):
    code = "configuration_error"


class InvalidInput(AgentKitError):
    code = "invalid_input"
    http_status = 400


class NotFound(AgentKitError):
    code = "not_found"
    http_status = 404


class Conflict(AgentKitError):
    code = "conflict"
    http_status = 409


class PermissionDenied(AgentKitError):
    code = "permission_denied"
    http_status = 403


class RateLimited(AgentKitError):
    code = "rate_limited"
    http_status = 429


class DependencyMissing(AgentKitError):
    code = "dependency_missing"
    http_status = 503


class UpstreamError(AgentKitError):
    code = "upstream_error"
    http_status = 502


class ContentBlocked(AgentKitError):
    """Raised when moderation blocks input or output."""

    code = "content_blocked"
    http_status = 422


class BudgetExceeded(AgentKitError):
    """Raised when a token/cost/request budget is exhausted."""

    code = "budget_exceeded"
    http_status = 429


class SteeringUnavailable(AgentKitError):
    """Raised when steering is requested but no turn is in flight."""

    code = "steering_unavailable"
    http_status = 409
