"""Named server-side actions a panel can invoke.

Actions keep panel behavior on the server (``POST /api/studio/actions/{id}``): the
SPA sends a JSON body and never executes remote code. A handler is
``(body, ctx) -> dict`` (sync or async), where ``ctx`` is the web UI context.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

__all__ = ["ACTIONS", "ActionRegistry", "register_action", "run_action"]


class ActionRegistry:
    """A last-wins registry of named action handlers."""

    def __init__(self) -> None:
        self._actions: dict[str, Callable[..., Any]] = {}

    def register(self, action_id: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        self._actions[str(action_id)] = handler
        return handler

    def get(self, action_id: str) -> Callable[..., Any] | None:
        return self._actions.get(action_id)

    def ids(self) -> list[str]:
        return sorted(self._actions)

    def clear(self) -> None:
        self._actions.clear()


ACTIONS = ActionRegistry()


def register_action(action_id: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator form: ``@register_action("run-panel")``."""

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        return ACTIONS.register(action_id, handler)

    return decorator


async def run_action(action_id: str, body: Any, ctx: Any = None) -> Any:
    """Invoke a registered action, awaiting its result when needed."""
    handler = ACTIONS.get(action_id)
    if handler is None:
        raise KeyError(action_id)
    result = handler(body, ctx)
    if inspect.isawaitable(result):
        result = await result
    return result
