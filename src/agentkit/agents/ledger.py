"""Member-facing ledger tools for a managed team.

The team manager owns the plan and task creation (:class:`~agentkit.agents.team.ManagedTeam`);
members get a voice, not plan-write authority. These tools expose the *active*
shared ledger (``deps.extras["team_ledger"]``) to local members so they can:

* ``read_ledger()`` — see the facts, plan, and tasks.
* ``write_ledger(fact=..., complete=...)`` — append a (deduped) fact or complete a
  task they own. There is deliberately no ``plan``/task-creation argument.

The tools are attached idempotently with :func:`attach_team_ledger`; they resolve
the ledger at call time, so a member that runs without a shared ledger (a plain
callable, a remote peer, no deps) gets a clear ``"no active ledger"`` string
instead of an exception.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai import RunContext

from agentkit.deps import Deps

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agentkit.agents.team import TeamLedger

__all__ = ["attach_team_ledger", "read_ledger", "write_ledger"]


def _ledger_of(ctx: Any) -> TeamLedger | None:
    deps = getattr(ctx, "deps", None)
    if deps is None:
        return None
    return deps.extras.get("team_ledger")


def _member_of(ctx: Any) -> str | None:
    deps = getattr(ctx, "deps", None)
    if deps is None:
        return None
    return deps.extras.get("team_member")


async def read_ledger(ctx: RunContext[Deps]) -> str:
    """Read the shared team ledger (facts, plan, tasks)."""
    ledger = _ledger_of(ctx)
    if ledger is None:
        return "no active ledger"
    return ledger.render()


async def write_ledger(
    ctx: RunContext[Deps],
    *,
    fact: str | None = None,
    complete: int | None = None,
    _member: str | None = None,
) -> str:
    """Write to the shared team ledger: append a fact and/or complete a task.

    Args:
        ctx: The run context (carries the shared ledger).
        fact: A short fact to record (deduped).
        complete: The id of a task you own to mark done.
        _member: The calling member's name (bound at attach time).
    """
    ledger = _ledger_of(ctx)
    if ledger is None:
        return "no active ledger"
    member = _member if _member is not None else _member_of(ctx)
    notes: list[str] = []
    wrote = False

    if fact:
        ledger.add_fact(fact)
        notes.append("recorded fact")
        wrote = True

    if complete is not None:
        task = next((t for t in ledger.tasks if t.get("id") == complete), None)
        if task is None:
            notes.append(f"no task #{complete}")
        else:
            owner = task.get("owner")
            if owner is not None and owner != member:
                return (
                    f"rejected: task #{complete} is owned by {owner!r}; "
                    f"you are {member!r} — propose a change as a fact instead"
                )
            ledger.complete_task(complete, fact or "")
            notes.append(f"completed task #{complete}")
            wrote = True

    if not notes:
        return ledger.render()

    deps = getattr(ctx, "deps", None)
    if wrote and deps is not None:
        deps.extras["team_ledger_wrote"] = True
    return "\n".join([*notes, "", ledger.render()])


def _tool_target(agent: Any) -> Any:
    """The object that exposes ``.tool`` (a PydanticAI agent or the builder)."""
    if hasattr(agent, "tool"):
        return agent
    inner = getattr(agent, "agent", None)
    if inner is not None and hasattr(inner, "tool"):
        return inner
    return None


def attach_team_ledger(agent: Any, *, name: str | None = None) -> Any:
    """Register ``read_ledger`` / ``write_ledger`` on ``agent`` (idempotent).

    Works on anything with ``.tool`` (a PydanticAI agent or the ``Agent`` builder)
    or on :class:`~agentkit.agents.handle.AgentHandle` (via its ``.agent``). A plain
    callable or remote handle has no tools and is returned unchanged. The calling
    member's ``name`` is bound into the write tool for ownership checks.
    """
    target = _tool_target(agent)
    if target is None:
        return agent
    if getattr(target, "_agentkit_team_ledger_attached", False):
        return agent

    async def _tool_read(ctx: RunContext[Deps]) -> str:
        return await read_ledger(ctx)

    _tool_read.__name__ = "read_ledger"

    async def _tool_write(
        ctx: RunContext[Deps], fact: str | None = None, complete: int | None = None
    ) -> str:
        return await write_ledger(ctx, fact=fact, complete=complete, _member=name)

    _tool_write.__name__ = "write_ledger"

    target.tool(_tool_read)
    target.tool(_tool_write)
    target._agentkit_team_ledger_attached = True  # type: ignore[attr-defined]
    return agent
