"""Human-in-the-loop helpers: clarification and interrupt/resume.

* **Clarification** — the ``ask_user`` tool (added with ``Agent.make(...).clarify()``)
  asks a moderator a question through an app-supplied handler
  (``app.clarify(handler)``). With no handler it tells the model to ask the user
  directly in its reply, so the turn always completes cleanly.
* **Interrupt / resume** — pairs with tool approvals: a run that defers tool calls
  (``requires_approval=True``) can be resumed with ``App.resume(results)`` once the
  human answers, using PydanticAI's ``deferred_tool_results``.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext

__all__ = ["Clarification", "ask_user", "resolve_clarify"]


@dataclass
class Clarification:
    """A question the agent wants a human to answer."""

    question: str
    options: list[str] = field(default_factory=list)
    answer: str | None = None


def resolve_clarify(deps: Any) -> Any:
    """The clarification handler on ``deps`` (``extras['clarify']``), if any."""
    return getattr(deps, "extras", {}).get("clarify")


def ask_user(
    question: str,
    options: list[str] | None = None,
    *,
    deps: Any = None,
) -> Clarification:
    """Resolve a clarification synchronously against a handler, if one is set."""
    handler = resolve_clarify(deps)
    if handler is None:
        return Clarification(question=question, options=list(options or []))
    result = handler(question, list(options or []))
    if inspect.isawaitable(result):  # pragma: no cover - async handler misuse
        raise RuntimeError("clarify handler is async; use the tool form")
    return Clarification(question=question, options=list(options or []), answer=str(result))


def clarification_tool() -> Any:
    """Build the ``ask_user`` tool bound to the app's clarification handler."""

    async def ask_user(ctx: RunContext[Any], question: str, options: list[str] | None = None) -> str:
        """Ask the user a clarifying question and get their answer.

        Args:
            question: The question to ask.
            options: Optional suggested answers to offer.
        """
        handler = resolve_clarify(ctx.deps)
        if handler is None:
            hint = " (suggested options: " + ", ".join(options) + ")" if options else ""
            return (
                "No live user is available to answer right now. Ask this question "
                f"directly in your final reply and stop: {question}{hint}"
            )
        result = handler(question, list(options or []))
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    return ask_user
