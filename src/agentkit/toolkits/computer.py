"""Native computer-use toolkit: approval-gated browser tools.

    from agentkit.toolkits.computer import attach_computer_tools

    _attach_computer_tools(agent)          # uses the configured computer driver
    _attach_computer_tools(agent, LoopbackComputer(), requires_approval=False)

Every tool is approval-gated by default; egress policy still applies.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from agentkit.deps import Deps
from agentkit.toolkits._common import app_of

__all__ = ["_attach_computer_tools"]


def _computer_of(ctx: RunContext[Deps], fallback: Any) -> Any:
    if fallback is not None:
        return fallback
    app = app_of(ctx)
    if app is not None and hasattr(app, "manager"):
        try:
            return app.manager("computer").driver()
        except Exception:  # pragma: no cover - defensive
            return None
    return None


def _attach_computer_tools(
    agent: Any, computer: Any = None, *, requires_approval: bool = True
) -> Any:
    """Register ``browser_*`` tools on ``agent`` (approval-gated by default)."""

    def tool(function: Any) -> Any:
        if requires_approval:
            return agent.tool(requires_approval=True)(function)
        return agent.tool(function)

    @tool
    async def browser_goto(ctx: RunContext[Deps], url: str) -> str:
        """Navigate the browser to a URL and return a page snapshot.

        Args:
            url: The absolute URL to open.
        """
        target = _computer_of(ctx, computer)
        if target is None:
            return "no computer driver configured"
        return await target.goto(url)

    @tool
    async def browser_snapshot(ctx: RunContext[Deps]) -> str:
        """Return a text snapshot of the current page."""
        target = _computer_of(ctx, computer)
        if target is None:
            return "no computer driver configured"
        return await target.snapshot()

    @tool
    async def browser_click(ctx: RunContext[Deps], selector: str) -> str:
        """Click an element on the current page.

        Args:
            selector: A CSS selector for the element.
        """
        target = _computer_of(ctx, computer)
        if target is None:
            return "no computer driver configured"
        return await target.click(selector)

    @tool
    async def browser_type(ctx: RunContext[Deps], selector: str, text: str) -> str:
        """Type text into an element on the current page.

        Args:
            selector: A CSS selector for the input element.
            text: The text to enter.
        """
        target = _computer_of(ctx, computer)
        if target is None:
            return "no computer driver configured"
        return await target.type(selector, text)

    @tool
    async def browser_screenshot(ctx: RunContext[Deps]) -> str:
        """Take a screenshot of the current page (returns a byte count)."""
        target = _computer_of(ctx, computer)
        if target is None:
            return "no computer driver configured"
        image = await target.screenshot()
        size = len(image) if hasattr(image, "__len__") else 0
        return f"screenshot captured ({size} bytes)"

    @tool
    async def browser_evaluate(ctx: RunContext[Deps], expression: str) -> str:
        """Evaluate a JavaScript expression in the page and return its result.

        Args:
            expression: The JavaScript expression to evaluate.
        """
        target = _computer_of(ctx, computer)
        if target is None:
            return "no computer driver configured"
        result = await target.evaluate(expression)
        return result if isinstance(result, str) else str(result)

    return agent
