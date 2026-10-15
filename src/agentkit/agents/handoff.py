"""Handoff: transfer control of a conversation to another agent.

Unlike delegation (which *returns* to the caller), a handoff moves the
conversation: by default the target agent receives the full transcript (same
conversation id/history); pass ``brief`` to hand over a focused summary instead.
Multi-hop chains are capped by ``max_handoffs`` to prevent loops.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext

from agentkit.agents.handle import AgentHandle
from agentkit.deps import Deps

__all__ = ["DEFAULT_MAX_HANDOFFS", "handoff", "handoff_tool"]

DEFAULT_MAX_HANDOFFS = 3


def _depth(deps: Any) -> int:
    if deps is None:
        return 0
    comms = getattr(deps, "comms", None)
    depth = int(getattr(comms, "handoff_depth", 0) or 0)
    extras = getattr(deps, "extras", None)
    if isinstance(extras, dict):
        depth = max(depth, int(extras.get("_handoff_depth", 0) or 0))
    return depth


def _max_handoffs(deps: Any, override: int | None) -> int:
    if override is not None:
        return override
    settings = getattr(deps, "settings", None)
    return int(getattr(settings, "max_handoffs", DEFAULT_MAX_HANDOFFS) or DEFAULT_MAX_HANDOFFS)


def _resolve_target(target: Any, registry: Any) -> AgentHandle | None:
    if isinstance(target, AgentHandle):
        return target
    if isinstance(target, str):
        if registry is None:
            return None
        return registry.resolve(target)
    if hasattr(target, "run") or hasattr(target, "build"):
        return AgentHandle.local(target)
    return None


async def _run_target(
    handle: AgentHandle,
    prompt: str,
    *,
    deps: Any,
    message_history: list[Any] | None,
) -> str:
    agent = handle.agent
    if agent is None:
        return f"(agent {handle.name!r} has no implementation)"
    runnable = agent
    if not hasattr(runnable, "run") and hasattr(runnable, "build"):
        runnable = runnable.build()
    usage = getattr(deps, "usage", None)
    model = getattr(deps, "model", None)
    result = await runnable.run(
        prompt, deps=deps, usage=usage, model=model, message_history=message_history
    )
    output = getattr(result, "output", result)
    return output if isinstance(output, str) else str(output)


async def handoff(
    target: Any,
    *,
    brief: str | None = None,
    ctx: Any = None,
    deps: Any = None,
    conversation_id: str | None = None,
    registry: Any = None,
    events: Any = None,
    max_handoffs: int | None = None,
) -> str:
    """Hand ``conversation_id`` over to ``target`` (handle, name, or agent)."""
    deps = deps or getattr(ctx, "deps", None)
    conversation_id = conversation_id or getattr(deps, "conversation_id", None)
    handle = _resolve_target(target, registry)
    if handle is None:
        return f"no such agent {target!r}"

    limit = _max_handoffs(deps, max_handoffs)
    depth = _depth(deps) + 1
    if depth > limit:
        if events is not None and hasattr(events, "dispatch_async"):
            await events.dispatch_async(
                "agent.error", agent=handle.name, error="max_handoffs exceeded"
            )
        return f"handoff limit reached (max {limit})"

    if deps is not None:
        comms = getattr(deps, "comms", None)
        if comms is not None:
            comms.handoff_depth = depth
        if hasattr(deps, "extras"):
            deps.extras["_handoff_depth"] = depth

    if events is not None and hasattr(events, "dispatch_async"):
        await events.dispatch_async(
            "agent.handoff",
            agent=handle.name,
            conversation_id=conversation_id,
            brief=brief is not None,
            depth=depth,
        )

    history = None
    prompt = brief or "Continue the conversation with the user."
    if brief is None and deps is not None and getattr(deps, "repos", None) is not None and conversation_id:
        from agentkit.session import load_history

        try:
            history = await load_history(deps.repos, conversation_id)
        except Exception:
            history = None

    return await _run_target(handle, prompt, deps=deps, message_history=history)


def handoff_tool(registry: Any, *, max_handoffs: int | None = None) -> Any:
    """A ``handoff_to(agent, brief=None)`` tool backed by ``registry``."""

    async def handoff_to(ctx: RunContext[Deps], agent: str, brief: str | None = None) -> str:
        """Transfer this conversation to another agent.

        Args:
            agent: The agent to hand the conversation to.
            brief: Optional focused summary instead of the full transcript.
        """
        return await handoff(
            agent, brief=brief, ctx=ctx, registry=registry, max_handoffs=max_handoffs
        )

    return handoff_to
