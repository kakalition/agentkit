"""A real multi-agent group-chat runner.

Unlike :class:`~agentkit.comms.GroupChatTopology` (which routes one message to a
handler), :class:`GroupChatRunner` runs a turn loop: a
:class:`~agentkit.contracts.speaker.SpeakerStrategy` picks who speaks next, the
reply is appended to a shared transcript, and the loop ends on a max-turns cap, a
terminator, consensus, or an empty selection.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from agentkit.agents.speaker import RoundRobinSpeaker

__all__ = ["GroupChatResult", "GroupChatRunner"]


@dataclass
class GroupChatResult:
    """The outcome of a group-chat run."""

    output: str
    transcript: list[dict[str, str]] = field(default_factory=list)
    turns: int = 0


class GroupChatRunner:
    """Run a roster of agents in a shared group chat.

    ``agents`` maps a name to a local agent (anything with ``.run``), an
    :class:`~agentkit.agents.handle.AgentHandle`, or an async callable
    ``(str) -> str``.
    """

    def __init__(
        self,
        agents: Mapping[str, Any],
        *,
        speaker: Any = None,
        max_turns: int = 12,
        terminator: Callable[[str, list[dict[str, str]]], bool] | None = None,
        stop_on_consensus: bool = True,
        instructions: str | None = None,
        events: Any = None,
    ) -> None:
        self.agents = dict(agents)
        self.speaker = speaker or RoundRobinSpeaker()
        self.max_turns = max_turns
        self.terminator = terminator
        self.stop_on_consensus = stop_on_consensus
        self.instructions = instructions
        self.events = events

    async def run(self, task: str, *, ctx: Any = None) -> GroupChatResult:
        """Run the chat thread on ``task`` and return the transcript + last reply."""
        transcript: list[dict[str, str]] = [{"speaker": "user", "text": task}]
        turns = 0
        while turns < self.max_turns:
            roster = list(self.agents)
            speakers = await self.speaker.select(roster, transcript, context=ctx)
            chosen = [name for name in speakers if name in self.agents]
            if not chosen:
                break
            replies: list[str] = []
            for name in chosen:
                if turns >= self.max_turns:
                    break
                reply = await self._reply(name, self._prompt(task, transcript), ctx)
                transcript.append({"speaker": name, "text": reply})
                replies.append(reply)
                turns += 1
                await self._emit(name, reply)
                if self.terminator is not None and self.terminator(reply, transcript):
                    return GroupChatResult(self._last(transcript), transcript, turns)
            if self.stop_on_consensus and len(replies) > 1 and len(set(replies)) == 1:
                break
        return GroupChatResult(self._last(transcript), transcript, turns)

    # -- internals ------------------------------------------------------
    def _prompt(self, task: str, transcript: list[dict[str, str]]) -> str:
        header = self.instructions or (
            "You are in a group chat. Reply in turn, building on the transcript; "
            "be concise and do not repeat what has already been said."
        )
        lines = [header, "", f"Task: {task}", "", "Transcript:"]
        lines.extend(f"{turn['speaker']}: {turn['text']}" for turn in transcript)
        lines.append("")
        lines.append("Your reply:")
        return "\n".join(lines)

    async def _reply(self, name: str, prompt: str, ctx: Any) -> str:
        from agentkit.agents.handle import AgentHandle

        target = self.agents[name]
        if isinstance(target, AgentHandle):
            return await target.invoke(ctx, prompt)
        if callable(target) and not hasattr(target, "run") and not hasattr(target, "build"):
            result = target(prompt)
            if inspect.isawaitable(result):
                result = await result
            return result if isinstance(result, str) else str(result)
        return await AgentHandle.local(target, name=name).invoke(ctx, prompt)

    async def _emit(self, speaker: str, text: str) -> None:
        try:
            from agentkit.foundation.facade import emit

            await emit("agent.message", speaker=speaker, text=text)
        except Exception:  # pragma: no cover - events are best-effort
            pass

    @staticmethod
    def _last(transcript: list[dict[str, str]]) -> str:
        return transcript[-1]["text"] if transcript else ""
