"""Class-based tools and toolkits (the declaration form of agent capabilities).

Tools and toolkits are the class-based face of the functional ``attach_*``
helpers. A :class:`Tool` exposes one agent-callable action; a :class:`Toolkit`
groups tools::

    class SearchNotes(Tool):
        name = "search_notes"
        description = "Search the notes."
        def handle(self, ctx, query: str) -> str: ...

    class NotesToolkit(Toolkit):
        name = "notes"
        tools = [SearchNotes]

    app.toolkits([NotesToolkit])

The functional ``agentkit.toolkits.attach_*`` helpers remain and are what the
built-in toolkit classes delegate to.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

__all__ = ["Capability", "Tool", "ToolGroup", "Toolkit", "resolve_tool", "toolkit_names"]

#: Re-exported for a single import path; defined in the leaf module to avoid cycles.
from agentkit.capability import Capability  # noqa: E402


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class Tool:
    """A class-based agent tool.

    Declare ``name``/``description`` (the description defaults to ``handle``'s
    docstring) and implement ``handle(self, ctx, ...)``; the parameters of
    ``handle`` (after ``ctx``) become the tool's input schema.
    """

    name: str = ""
    description: str = ""
    requires_approval: bool = False
    retries: int | None = None
    timeout: float | None = None
    sequential: bool = False
    defer_loading: bool = False
    cache_ttl: float | None = None

    def __init__(self, **options: Any) -> None:
        self.options = options

    # -- declaration -> function ---------------------------------------
    def tool_name(self) -> str:
        return self.name or type(self).__name__.lower()

    def tool_options(self) -> dict[str, Any]:
        options = {
            "name": self.tool_name(),
            "description": self.description or (self.handle.__doc__ or "").strip() or None,
        }
        for key in ("requires_approval", "retries", "timeout", "sequential", "defer_loading"):
            value = self.options.get(key, getattr(self, key))
            if value not in (None, False):
                options[key] = value
        if self.options.get("cache_ttl", self.cache_ttl) is not None:
            options["cache_ttl"] = self.options.get("cache_ttl", self.cache_ttl)
        return options

    def function(self) -> Callable[..., Any]:
        """The callable registered on the built agent (``handle``, bound)."""
        return self.handle

    def install(self, agent: Any) -> Any:
        """Register this tool on a built PydanticAI agent."""
        agent.tool(self.function(), **self.tool_options())
        return agent

    # -- override -------------------------------------------------------
    def handle(self, ctx: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


class Toolkit:
    """A named bundle of tools and/or native capability attachments."""

    name: ClassVar[str] = ""
    tools: ClassVar[Sequence[Any]] = ()

    def __init__(self, **options: Any) -> None:
        self.options = options

    def toolkit_name(self) -> str:
        return self.name or type(self).__name__.replace("Toolkit", "").lower()

    def tool_objects(self) -> list[Any]:
        return [resolve_tool(item) for item in self.tools]

    def install(self, agent: Any) -> Any:
        """Register the toolkit's tools on a built PydanticAI agent."""
        for item in self.tool_objects():
            if isinstance(item, Tool):
                item.install(agent)
            else:
                agent.tool(item)
        return agent


def resolve_tool(item: Any) -> Any:
    """Instantiate a ``Tool`` class, or pass a plain function/Tool through."""
    if isinstance(item, type) and issubclass(item, Tool):
        return item()
    return item


def toolkit_names() -> list[str]:
    from agentkit.toolkits import TOOLKITS

    return list(TOOLKITS)


#: Laravel spelling for a bundle of tools.
ToolGroup = Toolkit
