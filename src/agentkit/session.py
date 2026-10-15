"""Conversation history persistence + the chat runner.

History is stored via PydanticAI's ``ModelMessagesTypeAdapter``, keyed by a
conversation id. The runner requires ``deps.repos`` to expose ``messages`` and
``conversations`` stores (see :mod:`agentkit.db.repositories`).
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)

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


async def load_history(
    repos: Any, conversation_id: str, *, max_messages: int = DEFAULT_MAX_HISTORY
) -> list[ModelMessage]:
    payloads = [m.payload for m in await repos.messages.list(conversation_id)]
    if max_messages and len(payloads) > max_messages:
        payloads = payloads[-max_messages:]
    return deserialize_messages(payloads)


async def save_new_messages(
    repos: Any, conversation_id: str, messages: list[ModelMessage], start_index: int
) -> int:
    new_messages = messages[start_index:]
    if not new_messages:
        return 0
    return await repos.messages.append(conversation_id, [serialize_message(m) for m in new_messages])


def _tool_calls(messages: list[ModelMessage]) -> list[str]:
    """Tool names called during a run (for evals/telemetry)."""
    names: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart):
                names.append(part.tool_name)
    return names


def _content_repr(value: Any) -> str:
    """A short text preview of a possibly-multimodal user message."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        texts = [part for part in value if isinstance(part, str)]
        media = sum(1 for part in value if not isinstance(part, str))
        if media:
            texts.append(f"[{media} attachment(s)]")
        return " ".join(texts).strip()
    return str(value)


def last_user_prompt(messages: list[ModelMessage]) -> tuple[str, int] | None:
    """Return ``(text, index)`` of the most recent user prompt, or ``None``."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, ModelRequest):
            continue
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                return part.content, index
    return None


def _accepts_conversation(processor: Any) -> bool:
    """Whether a history processor accepts a ``conversation_id`` keyword."""
    try:
        parameters = inspect.signature(processor).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins etc.
        return False
    return "conversation_id" in parameters


@dataclass
class ChatResult:
    output: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    history_length: int = 0
    usage: dict[str, Any] | None = None
    tool_calls: list[str] = field(default_factory=list)


@dataclass
class StreamEvent:
    """One increment of a streamed turn.

    ``kind`` is one of ``"text"`` (``text`` carries the delta), ``"tool"``
    (``tool`` names it), or ``"final"`` (``result`` carries the :class:`ChatResult`).
    """

    kind: str
    text: str = ""
    tool: str = ""
    result: ChatResult | None = None


class ChatRunner:
    """Run an agent against one conversation, persisting history."""

    def __init__(
        self,
        deps: Deps,
        *,
        agent: Agent[Any, str],
        conversation_id: str = "cli:default",
        max_history: int = DEFAULT_MAX_HISTORY,
        history_processor: Any = None,
    ) -> None:
        self.deps = deps
        self.agent = agent
        self.conversation_id = conversation_id
        self.max_history = max_history
        self.history_processor = history_processor
        # Make the conversation id available to tools (e.g. to deliver later).
        self.deps.extras["conversation_id"] = conversation_id

    async def send(self, text: Any) -> ChatResult:
        from agentkit import metrics

        repos, channel, history = await self._begin(text)
        self.deps.artifacts.clear()
        try:
            result = await self.agent.run(
                text,
                deps=self.deps,
                message_history=history,
                model=self.deps.model,
                model_settings=model_settings(self.deps.settings),
                usage_limits=usage_limits(self.deps.settings),
            )
        except Exception:
            metrics.record_turn("error")
            raise
        return await self._finish(
            repos, channel, history, result.all_messages(), result.output, self._usage_of(result)
        )

    async def stream(self, text: Any) -> AsyncIterator[StreamEvent]:
        """Run one turn, yielding :class:`StreamEvent` increments then the final result."""
        repos, channel, history = await self._begin(text)
        self.deps.artifacts.clear()
        async with self.agent.run_stream(
            text,
            deps=self.deps,
            message_history=history,
            model=self.deps.model,
            model_settings=model_settings(self.deps.settings),
            usage_limits=usage_limits(self.deps.settings),
        ) as streamed:
            async for chunk in streamed.stream_text(delta=True):
                if chunk:
                    yield StreamEvent("text", text=chunk)
            output = await streamed.get_output()
            all_messages = streamed.all_messages()
            run_usage = getattr(streamed, "usage", None)
        chat_result = await self._finish(repos, channel, history, all_messages, output, run_usage)
        yield StreamEvent("final", result=chat_result)

    async def resume(self, deferred_tool_results: Any, text: str | None = None) -> ChatResult:
        """Continue a turn that deferred tool calls (approvals/clarification)."""
        repos, channel, history = await self._begin(text or "")
        result = await self.agent.run(
            text,
            deps=self.deps,
            message_history=history,
            deferred_tool_results=deferred_tool_results,
            model=self.deps.model,
            model_settings=model_settings(self.deps.settings),
            usage_limits=usage_limits(self.deps.settings),
        )
        return await self._finish(
            repos, channel, history, result.all_messages(), result.output, self._usage_of(result)
        )

    async def _begin(self, text: Any) -> tuple[Any, str, list[ModelMessage]]:
        repos = self.deps.repos
        channel = self.conversation_id.split(":", 1)[0]
        await repos.conversations.get_or_create(self.conversation_id, channel=channel)
        history = await load_history(repos, self.conversation_id, max_messages=self.max_history)
        if self.history_processor is not None:
            if _accepts_conversation(self.history_processor):
                processed = self.history_processor(history, conversation_id=self.conversation_id)
            else:
                processed = self.history_processor(history)
            if inspect.isawaitable(processed):
                processed = await processed
            history = list(processed)

        from agentkit.foundation.facade import emit

        preview = text if isinstance(text, str) else _content_repr(text)
        await emit("turn.start", conversation_id=self.conversation_id, channel=channel, text=preview)
        await emit(
            "channel.message", conversation_id=self.conversation_id, channel=channel, text=preview
        )
        return repos, channel, history

    async def _finish(
        self,
        repos: Any,
        channel: str,
        history: list[ModelMessage],
        all_messages: list[ModelMessage],
        output: Any,
        run_usage: Any,
    ) -> ChatResult:
        await save_new_messages(repos, self.conversation_id, all_messages, start_index=len(history))
        await repos.conversations.touch(self.conversation_id)
        usage = await self._record_usage(repos, run_usage)
        artifacts = list(self.deps.artifacts)
        try:
            from agentkit.multimodal import collect_artifacts

            for generated in collect_artifacts(all_messages):
                if generated not in artifacts:
                    artifacts.append(generated)
        except Exception:  # pragma: no cover - defensive
            pass
        chat_result = ChatResult(
            output=output if isinstance(output, str) else str(output),
            artifacts=artifacts,
            history_length=len(all_messages),
            usage=usage,
            tool_calls=_tool_calls(all_messages),
        )
        from agentkit import metrics
        from agentkit.foundation.facade import emit

        metrics.record_turn("ok")
        await emit(
            "turn.end",
            conversation_id=self.conversation_id,
            channel=channel,
            output=chat_result.output,
            usage=usage,
            history_length=chat_result.history_length,
        )
        return chat_result

    @staticmethod
    def _usage_of(result: Any) -> Any:
        try:
            return result.usage()
        except Exception:  # pragma: no cover - defensive
            return None

    async def _record_usage(self, repos: Any, run_usage: Any) -> dict[str, Any] | None:
        """Record token usage + estimated cost if the repos expose a usage store."""
        store = getattr(repos, "usage", None)
        if store is None or run_usage is None:
            return None
        from agentkit.pricing import usage_cost

        model_name = self.deps.settings.model_name if self.deps.settings else ""
        totals: dict[str, Any] = {
            "requests": int(getattr(run_usage, "requests", 0) or 0),
            "input_tokens": int(getattr(run_usage, "request_tokens", 0) or 0),
            "output_tokens": int(getattr(run_usage, "response_tokens", 0) or 0),
            "total_tokens": int(getattr(run_usage, "total_tokens", 0) or 0),
        }
        cost = usage_cost(run_usage, model_name)
        totals["cost_usd"] = cost
        from agentkit import metrics

        metrics.record_cost(cost)
        await store.add(
            conversation_id=self.conversation_id,
            kind="turn",
            model=model_name,
            cost_usd=cost,
            **{key: totals[key] for key in ("requests", "input_tokens", "output_tokens", "total_tokens")},
        )
        return totals

    async def reset(self) -> None:
        await self.deps.repos.messages.clear(self.conversation_id)
