from __future__ import annotations

from pathlib import Path

from agentkit import Agent
from agentkit.agents.groupchat import GroupChatRunner
from agentkit.agents.speaker import (
    AllSpeaker,
    ManualSpeaker,
    ModeratorSpeaker,
    RoundRobinSpeaker,
    SelectorSpeaker,
    SpeakerStrategy,
)
from agentkit.agents.team import MagenticTeam, TeamLedger
from agentkit.comms import GroupChatSpeaker, GroupChatTopology
from agentkit.config import AgentSettings
from agentkit.teams import build_team, register_team, resolve_team, team_tool


def _reply(name: str, text: str | None = None):
    async def call(prompt: str) -> str:
        return text if text is not None else f"{name}-reply"

    return call


def _settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings(agent_home=tmp_path, memory_embedding_backend="hash")


# -- speaker strategies -----------------------------------------------------
async def test_round_robin_rotates():
    speaker = RoundRobinSpeaker()
    roster = ["a", "b"]
    assert await speaker.select(roster, []) == ["a"]
    assert await speaker.select(roster, []) == ["b"]
    assert await speaker.select(roster, []) == ["a"]


async def test_moderator_and_all_and_manual():
    assert await ModeratorSpeaker("b").select(["a", "b"], []) == ["b"]
    assert await ModeratorSpeaker().select(["a", "b"], []) == ["a"]
    assert await AllSpeaker().select(["a", "b"], []) == ["a", "b"]
    manual = ManualSpeaker(["b", "a"])
    assert await manual.select(["a", "b"], []) == ["b"]
    assert await manual.select(["a", "b"], []) == ["a"]


async def test_selector_falls_back_without_model():
    assert await SelectorSpeaker().select(["a", "b"], []) == ["a"]
    assert await SelectorSpeaker().select([], []) == []


def test_speaker_conformance():
    assert isinstance(RoundRobinSpeaker(), SpeakerStrategy)


# -- group chat runner ------------------------------------------------------
async def test_groupchat_runner_records_transcript():
    runner = GroupChatRunner({"a": _reply("a"), "b": _reply("b")}, max_turns=2)
    result = await runner.run("solve it")
    assert result.turns == 2
    assert [turn["speaker"] for turn in result.transcript] == ["user", "a", "b"]
    assert result.output == "b-reply"


async def test_groupchat_runner_terminator_and_cap():
    runner = GroupChatRunner(
        {"a": _reply("a", "STOP")},
        max_turns=5,
        terminator=lambda reply, transcript: reply.startswith("STOP"),
    )
    result = await runner.run("go")
    assert result.turns == 1

    capped = GroupChatRunner({"a": _reply("a")}, max_turns=3)
    assert (await capped.run("go")).turns == 3


async def test_groupchat_runner_consensus_stops_early():
    runner = GroupChatRunner(
        {"a": _reply("a", "same"), "b": _reply("b", "same")},
        speaker=AllSpeaker(),
        max_turns=10,
    )
    result = await runner.run("decide")
    assert result.turns == 2  # one round of agreement, then stop


async def test_groupchat_topology_delegates_to_runner():
    topology = GroupChatTopology(speaker=GroupChatSpeaker.ALL)
    topology.register("a", _reply("a"))
    topology.register("b", _reply("b"))
    result = await topology.run("hi", max_turns=2)
    assert result.turns == 2
    assert result.transcript[0] == {"speaker": "user", "text": "hi"}


# -- manager-led team + ledger ----------------------------------------------
async def test_ledger_tracks_facts_plan_tasks():
    ledger = TeamLedger()
    ledger.add_fact("starting").set_plan(["one"])
    task = ledger.add_task("do it")
    assert ledger.pending() == [task]
    ledger.complete_task(task["id"], "done")
    assert ledger.pending() == []
    assert "Facts:" in ledger.render() and "Tasks:" in ledger.render()


async def test_magentic_team_maintains_ledger():
    team = MagenticTeam({"a": _reply("a", "first"), "b": _reply("b", "second")}, max_rounds=2)
    team.ledger.add_task("step one")
    result = await team.run("build it")
    assert result.rounds == 2
    assert any("a: first" in fact for fact in result.ledger.facts)
    assert all(task["status"] == "done" for task in result.ledger.tasks)


async def test_magentic_team_replans_on_stall():
    replanned: list[str] = []

    def manager(ledger: TeamLedger, stalled: str) -> list[str]:
        replanned.append(stalled)
        return ["try a different approach"]

    team = MagenticTeam(
        {"a": _reply("a", "same")}, manager=manager, max_rounds=5, stall_limit=2
    )
    result = await team.run("stuck task")
    assert result.rounds <= 3
    assert replanned  # manager was consulted on the stall
    assert any("stall detected" in fact for fact in result.ledger.facts)
    assert "try a different approach" in result.ledger.plan


# -- named team presets -----------------------------------------------------
async def test_team_presets_resolve_and_run():
    register_team("squad", {"a": _reply("a"), "b": _reply("b")})
    spec = resolve_team("squad")
    assert spec.kind == "groupchat"
    runner = build_team("squad", max_turns=2)
    result = await runner.run("go")
    assert result.turns == 2


def test_team_tool_is_namespaced_and_unique(tmp_path: Path):
    register_team("alpha", {"a": _reply("a")})
    register_team("beta", {"a": _reply("a")})
    assert team_tool("alpha").__name__ == "team_alpha"
    assert team_tool("beta").__name__ == "team_beta"

    settings = _settings(tmp_path)
    built = Agent.make("x").output(str).team("alpha").team("beta").build(settings=settings)
    tools = set(built._function_toolset.tools.keys())
    assert {"team_alpha", "team_beta"} <= tools


async def test_magentic_team_kind_builds():
    register_team("moonshot", {"a": _reply("a")}, kind="magentic")
    runner = build_team("moonshot", max_rounds=1)
    assert isinstance(runner, MagenticTeam)
