"""A manager-led team with a shared ledger.

:class:`ManagedTeam` runs a bounded round loop over a roster, keeping a
:class:`TeamLedger` of facts, a plan, and a task list. It picks the next speaker,
records progress, and replans when a member stalls; the ledger is the durable
"what has been established / what remains" state between rounds.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agentkit.agents.groupchat import GroupChatRunner
from agentkit.agents.ledger import TeamLedgerCapability
from agentkit.agents.speaker import RoundRobinSpeaker

__all__ = ["ManagedTeam", "TeamLedger", "TeamRunResult"]


@dataclass
class TeamLedger:
    """Facts, a plan, and a task list maintained across team rounds."""

    facts: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def add_fact(self, fact: str) -> TeamLedger:
        if fact and fact not in self.facts:
            self.facts.append(fact)
        return self

    def set_plan(self, steps: list[str]) -> TeamLedger:
        self.plan = [step for step in steps if step]
        return self

    def add_task(self, description: str, *, owner: str | None = None) -> dict[str, Any]:
        task = {
            "id": len(self.tasks) + 1,
            "description": description,
            "owner": owner,
            "status": "pending",
            "result": "",
        }
        self.tasks.append(task)
        return task

    def complete_task(self, task_id: int, result: str = "") -> bool:
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = "done"
                task["result"] = result
                return True
        return False

    def pending(self) -> list[dict[str, Any]]:
        return [task for task in self.tasks if task["status"] != "done"]

    def render(self) -> str:
        lines = ["Ledger:"]
        if self.facts:
            lines.append("Facts:")
            lines.extend(f"- {fact}" for fact in self.facts)
        if self.plan:
            lines.append("Plan:")
            lines.extend(f"- {step}" for step in self.plan)
        if self.tasks:
            lines.append("Tasks:")
            lines.extend(
                f"- #{task['id']} [{task['status']}] {task['description']}" for task in self.tasks
            )
        return "\n".join(lines)


@dataclass
class TeamRunResult:
    output: str
    ledger: TeamLedger
    transcript: list[dict[str, str]] = field(default_factory=list)
    rounds: int = 0


class ManagedTeam:
    """A manager-led team: pick a speaker, record progress, replan on stall."""

    def __init__(
        self,
        roster: Mapping[str, Any],
        *,
        manager: Callable[[TeamLedger, str], list[str]] | None = None,
        speaker: Any = None,
        max_rounds: int = 8,
        stall_limit: int = 2,
        ledger: TeamLedger | None = None,
        instructions: str | None = None,
        planner_model: Any = None,
        planner_agent: Any = None,
        recorder: Any = None,
    ) -> None:
        self.roster = dict(roster)
        self.manager = manager
        self.speaker = speaker or RoundRobinSpeaker()
        self.max_rounds = max_rounds
        self.stall_limit = stall_limit
        self.ledger = ledger or TeamLedger()
        self.instructions = instructions
        self.planner_model = planner_model
        self.planner_agent = planner_agent
        self.recorder = recorder

    async def run(self, task: str, *, ctx: Any = None) -> TeamRunResult:
        """Run the team on ``task``; returns the output, ledger, and transcript."""
        self.ledger.add_fact(f"Task: {task}")
        if not self.ledger.plan:
            self.ledger.set_plan([task])
            self._materialize_tasks([task])
        self._attach_ledger(ctx)

        runner = GroupChatRunner(
            self.roster,
            speaker=self.speaker,
            max_turns=1,
            instructions=self.instructions,
            recorder=self.recorder,
        )
        transcript: list[dict[str, str]] = [{"speaker": "user", "text": task}]
        last = ""
        stall = 0
        rounds = 0
        for round_index in range(1, self.max_rounds + 1):
            rounds = round_index
            speakers = await self.speaker.select(list(self.roster), transcript, context=ctx)
            chosen = [name for name in speakers if name in self.roster]
            if not chosen:
                break
            name = chosen[0]
            prompt = self._prompt(task, name, transcript)
            self._mark_member(ctx, name)
            self._reset_write_marker(ctx)
            reply = await runner._reply(name, prompt, ctx)  # noqa: SLF001 - shared runner helper
            transcript.append({"speaker": name, "text": reply})
            self._record("turn", text=reply, data={"speaker": name, "round": round_index})
            progressed = bool(reply.strip()) and reply.strip() != last.strip()
            if progressed:
                if not self._took_write_marker(ctx):
                    self.ledger.add_fact(f"{name}: {reply[:200]}")
                    pending = self.ledger.pending()
                    if pending:
                        self.ledger.complete_task(pending[0]["id"], reply[:200])
                stall = 0
            else:
                stall += 1
                await self._replan(name)
                if stall >= self.stall_limit:
                    break
            last = reply
        output = transcript[-1]["text"] if transcript else ""
        return TeamRunResult(output=output, ledger=self.ledger, transcript=transcript, rounds=rounds)

    # -- shared ledger wiring -------------------------------------------
    def _record(self, kind: str, **fields: Any) -> None:
        if self.recorder is None:
            return
        try:
            from agentkit.runs import RunEvent

            self.recorder.record(RunEvent(kind=kind, **fields))
        except Exception:  # pragma: no cover - recorder errors are swallowed
            pass

    def _attach_ledger(self, ctx: Any) -> None:
        """Share the ledger with members and attach their ledger tools."""
        deps = getattr(ctx, "deps", None) if ctx is not None else None
        if deps is None:
            return
        deps.extras["team_ledger"] = self.ledger
        for member_name, member in self.roster.items():
            TeamLedgerCapability(name=member_name).install(member)

    @staticmethod
    def _deps_extras(ctx: Any) -> dict[str, Any] | None:
        deps = getattr(ctx, "deps", None) if ctx is not None else None
        return None if deps is None else deps.extras

    def _mark_member(self, ctx: Any, name: str) -> None:
        extras = self._deps_extras(ctx)
        if extras is not None:
            extras["team_member"] = name

    def _reset_write_marker(self, ctx: Any) -> None:
        extras = self._deps_extras(ctx)
        if extras is not None:
            extras.pop("team_ledger_wrote", None)

    def _took_write_marker(self, ctx: Any) -> bool:
        extras = self._deps_extras(ctx)
        if extras is None:
            return False
        return bool(extras.pop("team_ledger_wrote", False))

    def _materialize_tasks(self, steps: list[str]) -> None:
        """Create one deduped pending task per plan step (manager owns tasks)."""
        existing = {task.get("description") for task in self.ledger.tasks}
        for step in steps:
            if step and step not in existing:
                self.ledger.add_task(step)
                existing.add(step)

    def _active_manager(self) -> Any:
        if self.manager is not None:
            return self.manager
        if self.planner_model is not None or self.planner_agent is not None:
            return self._llm_manager
        return None

    async def _replan(self, stalled: str) -> None:
        self.ledger.add_fact(f"stall detected after {stalled}")
        manager = self._active_manager()
        if manager is not None:
            try:
                steps = manager(self.ledger, stalled)
                if inspect.isawaitable(steps):
                    steps = await steps
                if steps:
                    self.ledger.set_plan(list(steps))
                    self._materialize_tasks(list(steps))
            except Exception:  # pragma: no cover - manager best effort
                pass

    async def _llm_manager(self, ledger: TeamLedger, stalled: str) -> list[str]:
        """A model-driven manager: prompt the planner for a fresh plan."""
        prompt = (
            "You are the manager of a team working a task. Use the ledger below "
            "and revise the plan. Respond with one plan step per line, no "
            "commentary, no numbering.\n\n"
            f"{ledger.render()}\n\n"
            f"The member {stalled!r} appears stalled."
        )
        if self.planner_agent is not None:
            agent = self.planner_agent
            if not hasattr(agent, "run") and hasattr(agent, "build"):
                agent = agent.build()
            result = await agent.run(prompt)
            output = getattr(result, "output", result)
        else:
            from pydantic_ai import Agent as PydanticAgent

            agent = PydanticAgent(self.planner_model, output_type=str, instructions="Plan.")
            output = (await agent.run(prompt)).output
        return _parse_steps(output if isinstance(output, str) else str(output))

    def _prompt(self, task: str, name: str, transcript: list[dict[str, str]]) -> str:
        header = self.instructions or (
            "You are part of a team working a task. Use the ledger; do not repeat."
        )
        lines = [header, "", self.ledger.render(), "", f"Task: {task}", "", "Transcript:"]
        lines.extend(f"{turn['speaker']}: {turn['text']}" for turn in transcript)
        lines.append("")
        lines.append(f"You are {name}. Your reply:")
        return "\n".join(lines)


def _parse_steps(text: str) -> list[str]:
    """Parse a manager/planner response into clean plan steps (one per line)."""
    steps: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-*•").strip()
        if len(line) > 2 and line[0].isdigit() and line[1] in ".)":
            line = line[2:].strip()
        if line:
            steps.append(line)
    return steps
