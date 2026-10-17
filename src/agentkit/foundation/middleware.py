"""Built-in middleware for the lifecycle seams.

Two layers:

* **Agent capabilities** (via PydanticAI ``Hooks``) that observe tool execution —
  :func:`lifecycle_hooks` (emits ``tool.start``/``tool.end``),
  :func:`policy_hooks` (enforces :class:`~agentkit.policy.ToolPolicy`),
  :func:`guardrails_hooks` (scans tool results for prompt injection).
* **Turn middleware** for the :class:`~agentkit.foundation.pipeline.Pipeline`
  around :meth:`App.run` — :func:`logging_middleware`.

The standalone functions in :mod:`agentkit.policy` / :mod:`agentkit.guardrails`
remain and keep working; these simply wire them into the turn.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic_ai.capabilities import Hooks

from agentkit.guardrails import scan_injection
from agentkit.logging import get_logger

log = get_logger("agentkit.middleware")


def _resolve_dispatcher(explicit: Any) -> Any:
    if explicit is not None:
        return explicit
    from agentkit.foundation.facade import get_current_app

    try:
        app = get_current_app()
    except Exception:  # pragma: no cover - defensive
        return None
    return getattr(app, "events", None)


async def _dispatch(dispatcher: Any, event: str, **payload: Any) -> None:
    if dispatcher is None:
        return
    try:
        await dispatcher.dispatch_async(event, **payload)
    except Exception:  # a listener must never break tool execution
        log.exception("event listener for %s failed", event)


def lifecycle_hooks(dispatcher: Any = None) -> Hooks:
    """A capability emitting ``tool.start`` / ``tool.end`` for every tool call."""
    hooks = Hooks()

    @hooks.on.before_tool_execute
    async def _before(ctx: Any, *, call: Any, tool_def: Any, args: Any) -> Any:
        await _dispatch(_resolve_dispatcher(dispatcher), "tool.start", tool=tool_def.name, args=args)
        return args

    @hooks.on.after_tool_execute
    async def _after(ctx: Any, *, call: Any, tool_def: Any, args: Any, result: Any) -> Any:
        await _dispatch(
            _resolve_dispatcher(dispatcher),
            "tool.end",
            tool=tool_def.name,
            result=result,
        )
        return result

    return hooks


def policy_hooks(policy: Any) -> Hooks:
    """A capability enforcing a :class:`~agentkit.policy.ToolPolicy`.

    Tools requiring approval are expected to be marked ``requires_approval=True``
    and wired through :data:`agentkit.approvals.approval_capability`; this hook
    enforces ``deny`` decisions and role requirements (RBAC) against the run's
    :class:`~agentkit.security.Actor`.
    """
    hooks = Hooks()

    @hooks.on.before_tool_execute
    async def _enforce(ctx: Any, *, call: Any, tool_def: Any, args: Any) -> Any:
        deps = getattr(ctx, "deps", None)
        policy.check(tool_def.name, actor=getattr(deps, "actor", None))
        return args

    return hooks


def guardrails_hooks(
    on_injection: Any = None, *, wrap_untrusted: bool = False, label: str = "untrusted"
) -> Hooks:
    """A capability scanning tool results for prompt-injection signals.

    Emits ``guardrails.injection`` (via ``on_injection`` or the current app's
    dispatcher) and logs a warning. When ``wrap_untrusted`` is set, string results
    are wrapped so the model treats them as data, never instructions.
    """
    from agentkit.guardrails import wrap_untrusted as _wrap

    hooks = Hooks()

    @hooks.on.after_tool_execute
    async def _scan(ctx: Any, *, call: Any, tool_def: Any, args: Any, result: Any) -> Any:
        signals = scan_injection(result if isinstance(result, str) else str(result))
        if signals:
            log.warning("possible prompt injection from tool %s: %s", tool_def.name, signals)
            handler = on_injection or _resolve_dispatcher(None)
            await _dispatch(handler, "guardrails.injection", tool=tool_def.name, signals=signals)
        if wrap_untrusted and isinstance(result, str):
            return _wrap(result, label=label)
        return result

    return hooks


def logging_middleware(logger: Any = None) -> Any:
    """Turn middleware logging each turn's id, length and duration."""
    logger = logger or log

    async def middleware(turn: Any, call_next: Any) -> Any:
        start = time.perf_counter()
        result = await call_next()
        logger.info(
            "turn %s took %.3fs",
            getattr(turn, "conversation_id", "?"),
            time.perf_counter() - start,
        )
        return result

    return middleware


class LoggingMiddleware:
    """Class form of :func:`logging_middleware` (implements the turn ``Middleware``)."""

    def __init__(self, logger: Any = None) -> None:
        self.logger = logger or log

    async def handle(self, turn: Any, call_next: Any) -> Any:
        start = time.perf_counter()
        result = await call_next()
        self.logger.info(
            "turn %s took %.3fs",
            getattr(turn, "conversation_id", "?"),
            time.perf_counter() - start,
        )
        return result

    async def __call__(self, turn: Any, call_next: Any) -> Any:
        return await self.handle(turn, call_next)


class PolicyMiddleware:
    """Class form of :func:`policy_hooks` (a tool-execution capability)."""

    def __init__(self, policy: Any) -> None:
        self.policy = policy

    def hooks(self) -> Hooks:
        return policy_hooks(self.policy)


class GuardrailsMiddleware:
    """Class form of :func:`guardrails_hooks` (a tool-execution capability)."""

    def __init__(
        self, on_injection: Any = None, *, wrap_untrusted: bool = False, label: str = "untrusted"
    ) -> None:
        self.on_injection = on_injection
        self.wrap_untrusted = wrap_untrusted
        self.label = label

    def hooks(self) -> Hooks:
        return guardrails_hooks(
            self.on_injection, wrap_untrusted=self.wrap_untrusted, label=self.label
        )


__all__ = [
    "GuardrailsMiddleware",
    "LoggingMiddleware",
    "PolicyMiddleware",
    "guardrails_hooks",
    "lifecycle_hooks",
    "logging_middleware",
    "policy_hooks",
]
