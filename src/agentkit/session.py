"""Conversation history persistence + the chat runner.

History is stored via PydanticAI's ``ModelMessagesTypeAdapter``, keyed by a
conversation id. The runner requires ``deps.repos`` to expose ``messages`` and
``conversations`` stores (see :mod:`agentkit.db.repositories`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from agentkit.config import model_settings, usage_limits
from agentkit.deps import Deps

DEFAULT_MAX_HISTORY = 40


class MessageStore(Protocol):
    def list(self, conversation_id: str, limit: int | None = None) -> Any: ...
    def append(self, conversation_id: str, payloads: list[str]) -> int: ...
    def clear(self, conversation_id: str) -> None: ...


class ConversationStore(Protocol):
    def get_or_create(self, conversation_id: str, channel: str = "cli") -> Any: ...
    def touch(self, conversation_id: str) -> None: ...


def serialize_message(message: ModelMessage) -> str:
    return ModelMessagesTypeAdapter.dump_json([message]).decode()


def deserialize_messages(payloads: list[str]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for payload in payloads:
        messages.extend(ModelMessagesTypeAdapter.validate_json(payload))
    return messages


def load_history(
    repos: Any, conversation_id: str, *, max_messages: int = DEFAULT_MAX_HISTORY
) -> list[ModelMessage]:
    payloads = [m.payload for m in repos.messages.list(conversation_id)]
    if max_messages and len(payloads) > max_messages:
        payloads = payloads[-max_messages:]
    return deserialize_messages(payloads)


def save_new_messages(
    repos: Any, conversation_id: str, messages: list[ModelMessage], start_index: int
) -> int:
    new_messages = messages[start_index:]
    if not new_messages:
        return 0
    return repos.messages.append(conversation_id, [serialize_message(m) for m in new_messages])


@dataclass
class ChatResult:
    output: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    history_length: int = 0
    usage: dict[str, int] | None = None


class ChatRunner:
    """Run an agent against one conversation, persisting history."""

    def __init__(
        self,
        deps: Deps,
        *,
        agent: Agent[Any, str],
        conversation_id: str = "cli:default",
        max_history: int = DEFAULT_MAX_HISTORY,
    ) -> None:
        self.deps = deps
        self.agent = agent
        self.conversation_id = conversation_id
        self.max_history = max_history

    async def send(self, text: str) -> ChatResult:
        repos = self.deps.repos
        channel = self.conversation_id.split(":", 1)[0]
        repos.conversations.get_or_create(self.conversation_id, channel=channel)
        history = load_history(repos, self.conversation_id, max_messages=self.max_history)

        self.deps.artifacts.clear()
        result = await self.agent.run(
            text,
            deps=self.deps,
            message_history=history,
            model=self.deps.model,
            model_settings=model_settings(self.deps.settings),
            usage_limits=usage_limits(self.deps.settings),
        )
        all_messages = result.all_messages()
        save_new_messages(repos, self.conversation_id, all_messages, start_index=len(history))
        repos.conversations.touch(self.conversation_id)

        usage = self._record_usage(repos, result)
        return ChatResult(
            output=result.output if isinstance(result.output, str) else str(result.output),
            artifacts=list(self.deps.artifacts),
            history_length=len(all_messages),
            usage=usage,
        )

    def _record_usage(self, repos: Any, result: Any) -> dict[str, int] | None:
        """Record token usage (counts only) if the repos expose a usage store."""
        store = getattr(repos, "usage", None)
        if store is None:
            return None
        try:
            run_usage = result.usage()
        except Exception:  # pragma: no cover - defensive
            return None
        totals = {
            "requests": int(getattr(run_usage, "requests", 0) or 0),
            "input_tokens": int(getattr(run_usage, "request_tokens", 0) or 0),
            "output_tokens": int(getattr(run_usage, "response_tokens", 0) or 0),
            "total_tokens": int(getattr(run_usage, "total_tokens", 0) or 0),
        }
        store.add(
            conversation_id=self.conversation_id,
            kind="turn",
            model=self.deps.settings.model_name if self.deps.settings else "",
            **totals,
        )
        return totals

    def reset(self) -> None:
        self.deps.repos.messages.clear(self.conversation_id)
