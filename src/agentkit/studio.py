"""The Studio's declarative team layer: author, materialize, run, export.

Agents in agentkit are live objects (a PydanticAI agent, an ``AgentHandle``, or a
callable), so a browser team builder cannot store them directly. :class:`TeamDefinition`
is the serializable half: a team's *shape* (name, runner kind, roster by name,
speaker strategy, limits, instructions). At run time the named members are resolved
back to live agents through a ``resolve`` callable — see :func:`run_team_definition`
and :func:`materialize_team` — or exported as Python via :func:`render_team_code`.

This powers the operator Studio: the persisted definition lives in
:class:`~agentkit.db.repositories.team_specs.TeamSpecRepo`; the playground runs it;
``render_team_code`` gives you the code to keep it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from agentkit.agents.speaker import (
    AllSpeaker,
    ManualSpeaker,
    ModeratorSpeaker,
    RoundRobinSpeaker,
    SelectorSpeaker,
)
from agentkit.agents.team import ManagedTeam, TeamLedger
from agentkit.teams import TEAM_KINDS

__all__ = [
    "SPEAKERS",
    "TeamDefinition",
    "TeamMember",
    "materialize_team",
    "render_team_code",
    "resolve_from_app",
    "run_team_definition",
    "speaker_for",
    "stub_member",
]

#: Speaker strategies a definition may select.
SPEAKERS = ("round_robin", "moderator", "all", "selector", "manual")


class TeamMember(BaseModel):
    """One roster slot, addressed by name (resolved to a live agent at run time)."""

    name: str
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("member name must not be empty")
        return value


class TeamDefinition(BaseModel):
    """A serializable team definition (the Studio team-builder payload).

    Registered as the ``team`` spec kind in :mod:`agentkit.specs.team`; ``kind``
    here is the *runner* kind (``groupchat`` | ``supervisor`` | ``managed``), which
    is why the spec protocol uses ``spec_kind`` (see
    :class:`~agentkit.contracts.spec.Spec`).
    """

    #: The spec kind this model satisfies (see :class:`~agentkit.contracts.spec.Spec`).
    spec_kind: ClassVar[str] = "team"

    name: str
    kind: str = "groupchat"
    members: list[TeamMember] = Field(default_factory=list)
    speaker: str = "round_robin"
    moderator: str | None = None
    manual_order: list[str] = Field(default_factory=list)
    max_turns: int = 12
    max_rounds: int = 8
    instructions: str | None = None

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("team name must not be empty")
        return value

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, value: str) -> str:
        if value not in TEAM_KINDS:
            raise ValueError(f"unknown team kind {value!r}; choose from {', '.join(TEAM_KINDS)}")
        return value

    @field_validator("speaker")
    @classmethod
    def _valid_speaker(cls, value: str) -> str:
        if value not in SPEAKERS:
            raise ValueError(f"unknown speaker {value!r}; choose from {', '.join(SPEAKERS)}")
        return value

    @model_validator(mode="after")
    def _unique_members(self) -> TeamDefinition:
        names = [member.name for member in self.members]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate member name(s): {', '.join(duplicates)}")
        if self.moderator is not None and self.moderator not in names:
            raise ValueError(f"moderator {self.moderator!r} is not a roster member")
        unknown = [name for name in self.manual_order if name not in names]
        if unknown:
            raise ValueError(f"manual_order names not in roster: {', '.join(unknown)}")
        return self

    @classmethod
    def from_json(cls, data: str) -> TeamDefinition:
        return cls.model_validate_json(data)

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        return cls.model_json_schema()

    def render(self, target: str = "python") -> str:
        from agentkit.specs.codegen import render_spec

        return render_spec(self, target)


# ---------------------------------------------------------------------------
# Materialization
# ---------------------------------------------------------------------------


def speaker_for(definition: TeamDefinition) -> Any:
    """Build the :class:`SpeakerStrategy` a definition selects."""
    if definition.kind == "supervisor" or definition.speaker == "moderator":
        return ModeratorSpeaker(definition.moderator)
    if definition.speaker == "all":
        return AllSpeaker()
    if definition.speaker == "selector":
        return SelectorSpeaker()
    if definition.speaker == "manual":
        return ManualSpeaker(definition.manual_order or [m.name for m in definition.members])
    return RoundRobinSpeaker()


def stub_member(name: str) -> Callable[[str], Any]:
    """A placeholder member for a name that resolves to no live agent."""

    async def member(prompt: str) -> str:
        return f"({name!r} is not a registered agent — wire it in code to run it)"

    member.__name__ = name or "member"
    return member


def resolve_from_app(app: Any) -> Callable[[str], Any]:
    """A member resolver over an app's agent registry (+ its primary agent)."""
    registry = getattr(app, "_agent_registry", None) if app is not None else None
    primary = None
    if app is not None:
        try:
            primary = app.agent()
        except Exception:  # pragma: no cover - no primary agent
            primary = None

    def resolve(name: str) -> Any:
        if registry is not None:
            handle = registry.get(name)
            if handle is not None:
                return handle
        if primary is not None and getattr(primary, "name", None) == name:
            return primary
        return stub_member(name)

    return resolve


def materialize_team(
    definition: TeamDefinition,
    resolve: Callable[[str], Any] | None = None,
    *,
    recorder: Any = None,
) -> Any:
    """Build a runnable runner (``run(task, ctx=...)``) for a definition."""
    resolve = resolve or (lambda name: stub_member(name))
    roster: dict[str, Any] = {member.name: resolve(member.name) for member in definition.members}
    speaker = speaker_for(definition)
    if definition.kind == "managed":
        return ManagedTeam(
            roster,
            speaker=speaker,
            max_rounds=definition.max_rounds,
            instructions=definition.instructions,
            recorder=recorder,
        )
    from agentkit.agents.groupchat import GroupChatRunner

    return GroupChatRunner(
        roster,
        speaker=speaker,
        max_turns=definition.max_turns,
        instructions=definition.instructions,
        recorder=recorder,
    )


def _ledger_view(ledger: TeamLedger) -> dict[str, Any]:
    return {"facts": list(ledger.facts), "plan": list(ledger.plan), "tasks": list(ledger.tasks)}


async def run_team_definition(
    definition: TeamDefinition,
    prompt: str,
    *,
    resolve: Callable[[str], Any] | None = None,
    ctx: Any = None,
    recorder: Any = None,
) -> dict[str, Any]:
    """Run a definition and return a plain result (output/transcript/ledger)."""
    runner = materialize_team(definition, resolve, recorder=recorder)
    result = await runner.run(prompt, ctx=ctx)
    transcript = list(getattr(result, "transcript", []))
    rounds = getattr(result, "rounds", None)
    if rounds is None:
        rounds = getattr(result, "turns", 0)
    ledger = getattr(result, "ledger", None)
    if recorder is not None:
        with contextlib.suppress(Exception):
            await recorder.flush()
    return {
        "team": definition.name,
        "kind": definition.kind,
        "output": getattr(result, "output", ""),
        "rounds": rounds,
        "transcript": transcript,
        "ledger": _ledger_view(ledger) if ledger is not None else None,
    }


# ---------------------------------------------------------------------------
# Python export
# ---------------------------------------------------------------------------


def _ident(name: str) -> str:
    ident = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name).strip("_") or "agent"
    if ident[0].isdigit():
        ident = f"agent_{ident}"
    return ident


def render_team_code(definition: TeamDefinition) -> str:
    """Generate the Python that rebuilds a definition with real agents."""
    lines = [
        f"# Generated by agentkit Studio — team {definition.name!r}",
        "from agentkit import Agent, build_team, register_team",
        "",
        "register_team(",
        f"    {definition.name!r},",
        "    {",
    ]
    for member in definition.members:
        note = f"  # {member.description}" if member.description else ""
        lines.append(f"        {member.name!r}: {_ident(member.name)},{note}")
    lines += ["    },", f"    kind={definition.kind!r},", ")", ""]

    options: list[str] = []
    if definition.kind != "supervisor" and definition.speaker != "round_robin":
        options.append(f"speaker={definition.speaker!r}")
    if definition.kind == "managed":
        options.append(f"max_rounds={definition.max_rounds}")
    else:
        options.append(f"max_turns={definition.max_turns}")
    lines.append(f"runner = build_team({definition.name!r}, {', '.join(options)})")
    lines.append('result = await runner.run("your task")')
    lines.append("")
    lines.append(f"# Or expose it to the primary agent as a `team_{_ident(definition.name)}` tool:")
    lines.append(
        f'agent = Agent.make("lead").team({definition.name!r}).output(str)  # -> team_{_ident(definition.name)}'
    )
    return "\n".join(lines) + "\n"
