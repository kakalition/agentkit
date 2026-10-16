"""A manager-led team with a shared ledger (the "magentic" pattern).

:class:`MagenticTeam` runs a bounded round loop over a roster, keeping a
:class:`TeamLedger` of facts, a plan, and a task list. It picks the next speaker,
records progress, and replans when a member stalls; the ledger is the durable
"what has been established / what remains" state between rounds.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agentkit.agents.groupchat import GroupChatRunner
from agentkit.agents.speaker import RoundRobinSpeaker

__all__ = ["MagenticTeam", "TeamLedger", "TeamRunResult"]


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


class MagenticTeam:
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
    ) -> None:
        self.roster = dict(roster)
        self.manager = manager
        self.speaker = speaker or RoundRobinSpeaker()
        self.max_rounds = max_rounds
        self.stall_limit = stall_limit
        self.ledger = ledger or TeamLedger()
        self.instructions = instructions

    async def run(self, task: str, *, ctx: Any = None) -> TeamRunResult:
        """Run the team on ``task``; returns the output, ledger, and transcript."""
        self.ledger.add_fact(f"Task: {task}")
        if not self.ledger.plan:
            self.ledger.set_plan([task])

        runner = GroupChatRunner(
            self.roster,
            speaker=self.speaker,
            max_turns=1,
            instructions=self.instructions,
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
            reply = await runner._reply(name, prompt, ctx)  # noqa: SLF001 - shared runner helper
            transcript.append({"speaker": name, "text": reply})
            progressed = bool(reply.strip()) and reply.strip() != last.strip()
            if progressed:
                self.ledger.add_fact(f"{name}: {reply[:200]}")
                pending = self.ledger.pending()
                if pending:
                    self.ledger.complete_task(pending[0]["id"], reply[:200])
                stall = 0
            else:
                stall += 1
                self._replan(name)
                if stall >= self.stall_limit:
                    break
            last = reply
        output = transcript[-1]["text"] if transcript else ""
        return TeamRunResult(output=output, ledger=self.ledger, transcript=transcript, rounds=rounds)

    def _replan(self, stalled: str) -> None:
        self.ledger.add_fact(f"stall detected after {stalled}")
        if self.manager is not None:
            try:
                steps = self.manager(self.ledger, stalled)
                if steps:
                    self.ledger.set_plan(list(steps))
            except Exception:  # pragma: no cover - manager best effort
                pass

    def _prompt(self, task: str, name: str, transcript: list[dict[str, str]]) -> str:
        header = self.instructions or (
            "You are part of a team working a task. Use the ledger; do not repeat."
        )
        lines = [header, "", self.ledger.render(), "", f"Task: {task}", "", "Transcript:"]
        lines.extend(f"{turn['speaker']}: {turn['text']}" for turn in transcript)
        lines.append("")
        lines.append(f"You are {name}. Your reply:")
        return "\n".join(lines)
