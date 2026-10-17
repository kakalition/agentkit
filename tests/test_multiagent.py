from __future__ import annotations

from pathlib import Path

from agentkit.agents.groupchat import GroupChatRunner
from agentkit.agents.speaker import (
    AllSpeaker,
    ManualSpeaker,
    ModeratorSpeaker,
    RoundRobinSpeaker,
    SelectorSpeaker,
    SpeakerStrategy,
)
from agentkit.agents.team import ManagedTeam, TeamLedger
from agentkit.comms import GroupChatSpeaker, GroupChatTopology
from agentkit.config import AgentSettings
from agentkit.foundation.agent import Agent
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


async def test_managed_team_maintains_ledger():
    team = ManagedTeam({"a": _reply("a", "first"), "b": _reply("b", "second")}, max_rounds=2)
    team.ledger.add_task("step one")
    result = await team.run("build it")
    assert result.rounds == 2
    assert any("a: first" in fact for fact in result.ledger.facts)
    assert all(task["status"] == "done" for task in result.ledger.tasks)


async def test_managed_team_replans_on_stall():
    replanned: list[str] = []

    def manager(ledger: TeamLedger, stalled: str) -> list[str]:
        replanned.append(stalled)
        return ["try a different approach"]

    team = ManagedTeam(
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


async def test_managed_team_kind_builds():
    register_team("moonshot", {"a": _reply("a")}, kind="managed")
    runner = build_team("moonshot", max_rounds=1)
    assert isinstance(runner, ManagedTeam)


# -- model-driven manager + member ledger -----------------------------------
async def test_managed_llm_planner_updates_plan():
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    model = FunctionModel(
        lambda m, i: ModelResponse(parts=[TextPart("step alpha\nstep beta")])
    )
    team = ManagedTeam({"a": _reply("a", "same")}, planner_model=model, max_rounds=5, stall_limit=2)
    result = await team.run("stuck task")
    assert "step alpha" in result.ledger.plan
    assert "step beta" in result.ledger.plan
    descriptions = [task["description"] for task in result.ledger.tasks]
    assert "step alpha" in descriptions and "step beta" in descriptions


async def test_manager_plan_materializes_deduped_tasks():
    team = ManagedTeam(
        {"a": _reply("a", "same")},
        manager=lambda ledger, stalled: ["one", "two", "one"],
        max_rounds=2,
    )
    result = await team.run("t")
    descriptions = [task["description"] for task in result.ledger.tasks]
    assert descriptions.count("one") == 1
    assert "two" in descriptions
    assert all(task["status"] in ("pending", "done") for task in result.ledger.tasks)


async def test_ledger_tool_fact_and_ownership():
    from types import SimpleNamespace

    from agentkit.agents.ledger import read_ledger, write_ledger
    from agentkit.deps import Deps

    ledger = TeamLedger()
    ledger.add_task("unowned")  # id 1
    ledger.add_task("mine", owner="a")  # id 2
    ledger.add_task("theirs", owner="b")  # id 3
    deps = Deps(settings=None, extras={"team_ledger": ledger})
    ctx = SimpleNamespace(deps=deps)

    await write_ledger(ctx, fact="hello", _member="a")
    assert "hello" in ledger.facts
    assert deps.extras["team_ledger_wrote"] is True

    assert "completed task #1" in await write_ledger(ctx, complete=1, _member="a")  # unowned
    assert ledger.tasks[0]["status"] == "done"
    assert "completed task #2" in await write_ledger(ctx, complete=2, _member="a")  # own
    assert ledger.tasks[1]["status"] == "done"

    rejected = await write_ledger(ctx, complete=3, _member="a")
    assert "rejected" in rejected and "b" in rejected
    assert ledger.tasks[2]["status"] != "done"

    assert "hello" in await read_ledger(ctx)
    assert "no task #99" in await write_ledger(ctx, complete=99, _member="a")


async def test_ledger_tools_report_no_active_ledger():
    from types import SimpleNamespace

    from agentkit.agents.ledger import read_ledger, write_ledger
    from agentkit.deps import Deps

    ctx = SimpleNamespace(deps=Deps(settings=None))
    assert await read_ledger(ctx) == "no active ledger"
    assert await write_ledger(ctx, fact="x") == "no active ledger"

    bare = SimpleNamespace()
    assert await read_ledger(bare) == "no active ledger"
    assert await write_ledger(bare, fact="x") == "no active ledger"


def test_attach_team_ledger_is_idempotent_and_noop_for_callables():
    from agentkit.agents.ledger import TeamLedgerCapability

    class FakeAgent:
        def __init__(self):
            self.tools: list[str] = []

        def tool(self, function):
            self.tools.append(function.__name__)

    agent = FakeAgent()
    TeamLedgerCapability(name="a").install(agent)
    TeamLedgerCapability(name="a").install(agent)
    assert agent.tools == ["read_ledger", "write_ledger"]

    async def callable_member(prompt: str) -> str:
        return prompt

    assert TeamLedgerCapability().install(callable_member) is callable_member


async def test_member_ledger_write_suppresses_heuristic():
    from types import SimpleNamespace

    from agentkit.deps import Deps

    class LedgerWriter:
        def __init__(self, member: str) -> None:
            self.member = member

        async def run(self, task, *, deps=None, usage=None, model=None):  # noqa: ANN001, ANN003
            from agentkit.agents.ledger import write_ledger

            await write_ledger(
                SimpleNamespace(deps=deps),
                fact=f"{self.member}-fact",
                complete=1,
                _member=self.member,
            )
            return f"{self.member}-reply"

    ctx = SimpleNamespace(deps=Deps(settings=None))
    team = ManagedTeam({"a": LedgerWriter("a")}, max_rounds=1)
    result = await team.run("build", ctx=ctx)

    assert "a-fact" in result.ledger.facts
    # The auto-fact heuristic did not also fire for this round.
    assert not any(fact.startswith("a: ") for fact in result.ledger.facts)
    assert result.ledger.tasks[0]["status"] == "done"
