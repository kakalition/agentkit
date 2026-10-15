"""Unified orchestrator/supervisor over a registry of agents.

One implementation drives both names (``Orchestrator`` and ``Supervisor`` are
aliases): the roster comes from an :class:`~agentkit.agents.registry.AgentRegistry`
of handles, routing picks a handle by name *or* capability, delegation forwards
``deps``/``usage``/``model``, and ``agent.*`` lifecycle events are emitted on the
app dispatcher.

    from agentkit import Orchestrator

    orch = Orchestrator(name="lead", instructions="route")
    orch.add_specialist(writer, tool_name="write")
    agent = orch.build()

PydanticAI v2 removed ``Agent.as_tool``; the supported core pattern is a tool
that calls ``specialist.run(...)`` and forwards ``deps``/``usage``/``model``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any

from pydantic_ai import Agent, RunContext

from agentkit.agents.handle import AgentHandle
from agentkit.agents.registry import AgentRegistry
from agentkit.deps import Deps

__all__ = [
    "Orchestrator",
    "Supervisor",
    "delegate",
    "make_delegate",
    "run_all_agents",
]

ROUTER_INSTRUCTIONS = (
    "You are an orchestrator. Route each request to the most appropriate "
    "specialist by calling its tool, then synthesize a final answer from their "
    "output. Available specialists:\n{roster}"
)


def _tool_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "agent"


async def delegate(ctx: RunContext[Deps], specialist: Agent[Any, str], request: str) -> str:
    """Run a specialist agent and return its reply (forwards deps/usage/model)."""
    result = await specialist.run(request, deps=ctx.deps, usage=ctx.usage, model=ctx.deps.model)
    return result.output


def make_delegate(specialist: Agent[Any, str], *, tool_name: str, description: str):
    """Create a delegation tool function for ``specialist``."""

    async def tool(ctx: RunContext[Deps], request: str) -> str:
        return await delegate(ctx, specialist, request)

    tool.__name__ = tool_name
    tool.__doc__ = description
    return tool


class Orchestrator:
    """An agent that routes requests to registered specialist handles."""

    def __init__(
        self,
        *,
        name: str = "orchestrator",
        instructions: str | None = None,
        deps_type: type = Deps,
        output_type: Any = str,
        model: Any = None,
        capabilities: list[Any] | None = None,
        registry: AgentRegistry | None = None,
        events: Any = None,
        fallbacks: list[str] | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.fallbacks = list(fallbacks or [])
        self._registry = registry or AgentRegistry()
        self._instructions = instructions or ROUTER_INSTRUCTIONS
        self.agent: Agent[Any, str] = Agent(
            name=name,
            deps_type=deps_type,
            output_type=output_type,
            instructions=self._instructions,
            model=model,
            capabilities=capabilities or [],
        )

    # -- roster ---------------------------------------------------------
    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    def add_specialist(
        self,
        specialist: Any,
        *,
        tool_name: str | None = None,
        description: str = "",
        capabilities: tuple[str, ...] | list[str] = (),
        name: str | None = None,
    ) -> Orchestrator:
        """Register ``specialist`` and expose it as a delegation tool."""
        resolved = name or tool_name or getattr(specialist, "name", None) or "agent"
        handle = AgentHandle.local(
            specialist,
            name=resolved,
            description=description,
            capabilities=capabilities,
        )
        self._register_handle(handle, tool_label=tool_name or resolved)
        return self

    def register(self, handle: AgentHandle, **options: Any) -> Orchestrator:
        """Register a handle (local or remote) and expose its delegation tool."""
        self._register_handle(handle, tool_label=handle.name)
        return self

    def _register_handle(self, handle: AgentHandle, *, tool_label: str) -> None:
        self._registry.register(handle)
        self.agent.tool(self._delegation_tool(handle, tool_label))

    def tool(self, function: Any) -> Orchestrator:
        """Register a plain tool on the orchestrator."""
        self.agent.tool(function)
        return self

    def route(self, capability: str) -> AgentHandle | None:
        """The handle best matching ``capability`` (name or capability)."""
        return self._registry.resolve(capability)

    def build(self) -> Agent[Any, str]:
        return self.agent

    # -- delegation -----------------------------------------------------
    def _delegation_tool(self, handle: AgentHandle, tool_label: str) -> Any:
        orchestrator = self

        async def tool(ctx: RunContext[Deps], request: str) -> str:
            return await orchestrator.invoke(ctx, handle.name, request)

        tool.__name__ = _tool_name(tool_label)
        tool.__doc__ = handle.description or f"Delegate to {handle.name}."
        return tool

    async def invoke(self, ctx: RunContext[Deps], name: str, request: str) -> str:
        """Delegate to ``name`` (with ordered fallbacks), emitting lifecycle events."""
        handle = self._registry.get(name) or self._registry.resolve(name)
        if handle is None:
            await self._emit("agent.error", agent=name, error="unknown agent")
            return f"unknown agent {name!r}; choose one of {', '.join(self._registry.names())}"
        await self._emit("agent.started", agent=handle.name, task=request)
        try:
            if handle.is_remote or handle.agent is not None:
                reply = await handle.invoke(ctx, request)
            else:  # pragma: no cover - defensive
                reply = f"(agent {handle.name!r} has no implementation)"
        except Exception as exc:
            await self._emit("agent.error", agent=handle.name, error=str(exc))
            reply = await self._fallback(ctx, request)
        await self._emit("agent.finished", agent=handle.name)
        return reply

    async def _fallback(self, ctx: RunContext[Deps], request: str) -> str:
        for name in self.fallbacks:
            handle = self._registry.get(name)
            if handle is None:
                continue
            try:
                return await handle.invoke(ctx, request)
            except Exception:  # pragma: no cover - defensive
                continue
        return "(delegation failed)"

    async def _emit(self, event: str, **payload: Any) -> None:
        if self.events is None:
            return
        dispatch = getattr(self.events, "dispatch_async", None)
        if dispatch is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - observers must not break delegation
            await dispatch(event, **payload)


class Supervisor(Orchestrator):
    """Backward-compatible alias that builds a roster from a mapping."""

    def __init__(
        self,
        agents: Mapping[str, Any] | None = None,
        *,
        name: str = "supervisor",
        instructions: str | None = None,
        output_type: Any = str,
        model: Any = None,
        registry: AgentRegistry | None = None,
        events: Any = None,
    ) -> None:
        super().__init__(
            name=name,
            instructions=instructions,
            output_type=output_type,
            model=model,
            registry=registry,
            events=events,
        )
        for key, agent in (agents or {}).items():
            self.add_specialist(
                agent, name=key, tool_name=_tool_name(key), description=f"Delegate to {key}"
            )


async def run_all_agents(
    agents: Mapping[str, Any], task: str, *, deps: Any = None, model: Any = None
) -> dict[str, str]:
    """Run every agent on ``task`` (sequentially) and collect outputs."""
    registry = AgentRegistry(
        AgentHandle.local(agent, name=name) for name, agent in agents.items()
    )
    results: dict[str, str] = {}
    for handle in registry.list():
        results[handle.name] = await handle.invoke(_Ctx(deps, model), task)
    return results


class _Ctx:
    """Minimal run context for :meth:`AgentHandle.invoke` outside a model run."""

    def __init__(self, deps: Any, model: Any = None) -> None:
        self.deps = deps
        self.usage = None
        if deps is not None and model is not None and getattr(deps, "model", None) is None:
            deps.model = model
