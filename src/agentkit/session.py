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
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    UserPromptPart,
)

from agentkit.config import get_settings, model_settings, usage_limits
from agentkit.deps import Deps
from agentkit.errors import SteeringUnavailable

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


def _model_used(messages: list[ModelMessage]) -> str | None:
    """The model name that produced the last response (fallback-aware)."""
    for message in reversed(messages):
        name = getattr(message, "model_name", None)
        if name:
            return str(name)
    return None


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
    #: the model that produced the final response (fallback chains may differ).
    model: str | None = None


@dataclass
class StreamEvent:
    """One increment of a streamed turn.

    ``kind`` is one of ``"text"`` (``text`` carries the delta), ``"tool"``
    (``tool`` names it), ``"compaction"`` (``text`` describes a shrunken history
    window), or ``"final"`` (``result`` carries the :class:`ChatResult`).
    """

    kind: str
    text: str = ""
    tool: str = ""
    result: ChatResult | None = None


def _text_delta(event: Any) -> str | None:
    """Extract the incremental text carried by a model stream event."""
    if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
        return event.part.content or None
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        return event.delta.content_delta or None
    return None


@dataclass
class TurnHandle:
    """A live handle to an in-flight PydanticAI run.

    Wraps the running ``AgentRun`` so callers can inject a message mid-turn via
    :meth:`enqueue` (PydanticAI's first-class pending-message queue). ``asap``
    interrupts before the next model request; ``when_idle`` queues to the end.
    """

    conversation_id: str
    run: Any

    @property
    def run_id(self) -> str | None:
        return getattr(self.run, "run_id", None)

    def enqueue(self, text: Any, *, priority: str = "asap") -> str | None:
        return self.run.enqueue(text, priority=priority)


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
        persist: bool = True,
        recorder: Any = None,
        checkpointer: Any = None,
    ) -> None:
        self.deps = deps
        self.agent = agent
        self.conversation_id = conversation_id
        self.max_history = max_history
        self.history_processor = history_processor
        self.persist = persist
        # Optional run-trace recorder (see ``agentkit.runs``); no-op when absent.
        self.recorder = recorder
        # Optional checkpoint store (see ``agentkit.checkpoints``); no-op when absent.
        self.checkpointer = checkpointer
        # Set by ``_begin`` when a history processor shrank the window.
        self._compaction: dict[str, int] | None = None
        # The live run handle while a turn is in flight (for ``steer``).
        self._turn: TurnHandle | None = None
        # Make the conversation id available to tools (e.g. to deliver later).
        self.deps.extras["conversation_id"] = conversation_id

    # -- steering -------------------------------------------------------
    @property
    def turn(self) -> TurnHandle | None:
        """The live handle for the in-flight turn, or ``None`` when idle."""
        return self._turn

    async def steer(self, text: Any, *, priority: str = "asap") -> str | None:
        """Inject a message into the in-flight turn (see :class:`TurnHandle`).

        Raises :class:`~agentkit.errors.SteeringUnavailable` when no turn is
        running.
        """
        handle = self._turn
        if handle is None:
            raise SteeringUnavailable(
                f"no turn is running for conversation {self.conversation_id!r}"
            )
        enqueue_id = handle.enqueue(text, priority=priority)
        preview = text if isinstance(text, str) else _content_repr(text)
        self._record("steer", text=preview, data={"priority": priority})
        from agentkit.foundation.facade import emit

        await emit(
            "turn.steer",
            conversation_id=self.conversation_id,
            text=preview,
            priority=priority,
            enqueue_id=enqueue_id,
        )
        return enqueue_id

    # -- run tracing ----------------------------------------------------
    def _record(self, kind: str, **fields: Any) -> None:
        if self.recorder is None:
            return
        try:
            from agentkit.runs import RunEvent

            self.recorder.record(RunEvent(kind=kind, **fields))
        except Exception:  # pragma: no cover - recorder errors are swallowed
            pass

    def _record_final(self, chat_result: ChatResult) -> None:
        if self.recorder is None:
            return
        for tool in chat_result.tool_calls:
            self._record("tool", tool=tool)
        self._record(
            "final",
            text=chat_result.output,
            data={
                "output": chat_result.output,
                "usage": chat_result.usage,
                "tool_calls": list(chat_result.tool_calls),
                "history_length": chat_result.history_length,
            },
        )

    async def _flush_recorder(self) -> None:
        if self.recorder is None:
            return
        try:
            flush = getattr(self.recorder, "flush", None)
            if flush is not None:
                await flush()
        except Exception:  # pragma: no cover - recorder errors are swallowed
            pass

    def _effective_settings(self) -> Any:
        """Settings for this turn, preferring the owning app's overrides."""
        extras = getattr(self.deps, "extras", None) or {}
        app = extras.get("app")
        return (
            getattr(app, "settings", None)
            or getattr(self.deps, "settings", None)
            or get_settings()
        )

    async def _auto_score(self, repos: Any) -> None:
        """Grade this run's trace when online scoring is enabled (opt-in, best-effort)."""
        try:
            settings = self._effective_settings()
            if not bool(getattr(settings, "online_scoring_enabled", False)):
                return
            run_id = str(getattr(self.recorder, "run_id", "") or self.conversation_id or "")
            if not run_id:
                return
            from agentkit.scorers import score_run

            await score_run(
                repos,
                run_id,
                grader_name=str(getattr(settings, "online_scoring_grader", "trace") or "trace"),
            )
        except Exception:  # pragma: no cover - scoring must never break a turn
            pass

    async def _checkpoint(self, label: str, state: Any) -> None:
        if self.checkpointer is None:
            return
        try:
            latest = await self.checkpointer.latest(self.conversation_id)
            seq = (int(getattr(latest, "seq", -1)) + 1) if latest is not None else 0
            await self.checkpointer.put(self.conversation_id, seq, state, label=label)
        except Exception:  # pragma: no cover - checkpoint errors are swallowed
            pass

    def _history_state(self, messages: list[ModelMessage], **extra: Any) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "messages": len(messages),
            "history": [serialize_message(message) for message in messages],
            **extra,
        }

    def _finish_state(self, chat_result: ChatResult) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "output": chat_result.output,
            "history_length": chat_result.history_length,
            "tool_calls": list(chat_result.tool_calls),
        }

    async def send(self, text: Any) -> ChatResult:
        from agentkit import metrics

        repos, channel, history = await self._begin(text)
        self._record("start", text=text if isinstance(text, str) else _content_repr(text))
        await self._checkpoint("start", self._history_state(history))
        self.deps.artifacts.clear()
        try:
            async with self.agent.iter(
                text,
                deps=self.deps,
                message_history=history,
                model=self.deps.model,
                model_settings=model_settings(self.deps.settings),
                usage_limits=usage_limits(self.deps.settings),
            ) as run:
                self._turn = TurnHandle(self.conversation_id, run)
                try:
                    async for _node in run:
                        pass
                finally:
                    self._turn = None
                result = run.result
        except Exception:
            metrics.record_turn("error")
            self._record("error", text=str(text)[:200])
            await self._flush_recorder()
            raise
        assert result is not None
        chat_result = await self._finish(
            repos, channel, history, result.all_messages(), result.output, self._usage_of(result)
        )
        await self._checkpoint("finish", self._finish_state(chat_result))
        self._record_final(chat_result)
        await self._flush_recorder()
        await self._auto_score(repos)
        return chat_result

    async def stream(self, text: Any) -> AsyncIterator[StreamEvent]:
        """Run one turn, yielding :class:`StreamEvent` increments then the final result."""
        repos, channel, history = await self._begin(text)
        self._record("start", text=text if isinstance(text, str) else _content_repr(text))
        await self._checkpoint("start", self._history_state(history))
        self.deps.artifacts.clear()
        if self._compaction:
            dropped = self._compaction["messages"]
            self._record("compaction", text=f"context compacted ({dropped} messages)")
            yield StreamEvent("compaction", text=f"context compacted ({dropped} messages)")
        async with self.agent.iter(
            text,
            deps=self.deps,
            message_history=history,
            model=self.deps.model,
            model_settings=model_settings(self.deps.settings),
            usage_limits=usage_limits(self.deps.settings),
        ) as run:
            self._turn = TurnHandle(self.conversation_id, run)
            try:
                async for node in run:
                    if not self.agent.is_model_request_node(node):
                        continue
                    async with node.stream(run.ctx) as streamed:
                        async for event in streamed:
                            chunk = _text_delta(event)
                            if chunk:
                                yield StreamEvent("text", text=chunk)
            finally:
                self._turn = None
            result = run.result
        assert result is not None
        chat_result = await self._finish(
            repos, channel, history, result.all_messages(), result.output, self._usage_of(result)
        )
        await self._checkpoint("finish", self._finish_state(chat_result))
        self._record_final(chat_result)
        await self._flush_recorder()
        await self._auto_score(repos)
        yield StreamEvent("final", result=chat_result)

    async def resume(self, deferred_tool_results: Any, text: str | None = None) -> ChatResult:
        """Continue a turn that deferred tool calls (approvals/clarification)."""
        repos, channel, history = await self._begin(text or "")
        self._record("start", text=text or "")
        await self._checkpoint("start", self._history_state(history))
        result = await self.agent.run(
            text,
            deps=self.deps,
            message_history=history,
            deferred_tool_results=deferred_tool_results,
            model=self.deps.model,
            model_settings=model_settings(self.deps.settings),
            usage_limits=usage_limits(self.deps.settings),
        )
        chat_result = await self._finish(
            repos, channel, history, result.all_messages(), result.output, self._usage_of(result)
        )
        await self._checkpoint("finish", self._finish_state(chat_result))
        self._record_final(chat_result)
        await self._flush_recorder()
        await self._auto_score(repos)
        return chat_result

    async def _begin(self, text: Any) -> tuple[Any, str, list[ModelMessage]]:
        repos = self.deps.repos
        channel = self.conversation_id.split(":", 1)[0]
        self._compaction = None
        self.deps.extras["ephemeral"] = not self.persist
        if self.persist:
            await repos.conversations.get_or_create(self.conversation_id, channel=channel)
            history = await load_history(repos, self.conversation_id, max_messages=self.max_history)
        else:
            history = []
        if self.history_processor is not None:
            before = list(history)
            if _accepts_conversation(self.history_processor):
                processed = self.history_processor(history, conversation_id=self.conversation_id)
            else:
                processed = self.history_processor(history)
            if inspect.isawaitable(processed):
                processed = await processed
            history = list(processed)
            if len(history) < len(before):
                from agentkit.compaction import estimate_tokens, transcript

                saved = estimate_tokens(transcript(before)) - estimate_tokens(transcript(history))
                self._compaction = {
                    "messages": len(before) - len(history),
                    "tokens": max(saved, 0),
                }

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
        if self.persist:
            self._offload_large_outputs(all_messages)
            await save_new_messages(
                repos, self.conversation_id, all_messages, start_index=len(history)
            )
            await repos.conversations.touch(self.conversation_id)
            usage = await self._record_usage(repos, run_usage)
        else:
            usage = self._usage_totals(run_usage)
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
            model=_model_used(all_messages),
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
            usage = result.usage
            return usage() if callable(usage) else usage
        except Exception:  # pragma: no cover - defensive
            return None

    def _offload_large_outputs(self, all_messages: list[ModelMessage]) -> None:
        """Move over-threshold tool returns to disk (see :mod:`agentkit.offload`)."""
        settings = self.deps.settings
        threshold = int(getattr(settings, "tool_output_offload_threshold", 0) or 0)
        if threshold <= 0:
            return
        from agentkit.offload import offload_messages

        offload_messages(
            all_messages,
            root=getattr(settings, "artifacts_dir", "."),
            conversation_id=self.conversation_id,
            threshold_tokens=threshold,
        )

    def _usage_totals(self, run_usage: Any) -> dict[str, Any] | None:
        """Token/cost/context telemetry for a run (no persistence)."""
        if run_usage is None:
            return None
        from agentkit.pricing import usage_cost

        model_name = self.deps.settings.model_name if self.deps.settings else ""
        input_tokens = int(getattr(run_usage, "request_tokens", 0) or 0)
        totals: dict[str, Any] = {
            "requests": int(getattr(run_usage, "requests", 0) or 0),
            "input_tokens": input_tokens,
            "output_tokens": int(getattr(run_usage, "response_tokens", 0) or 0),
            "total_tokens": int(getattr(run_usage, "total_tokens", 0) or 0),
            "cache_read_tokens": int(getattr(run_usage, "cache_read_tokens", 0) or 0),
            "context_tokens": input_tokens,
            "context_window": self._context_window(),
            "compacted_messages": int((self._compaction or {}).get("messages", 0)),
        }
        totals["cost_usd"] = usage_cost(run_usage, model_name)
        return totals

    def _context_window(self) -> int | None:
        """Best-effort model context window (``None`` when unknown)."""
        try:
            profile = getattr(self.deps.model, "profile", None)
            return int(getattr(profile, "max_input_tokens", 0) or 0) or None
        except Exception:  # pragma: no cover - defensive
            return None

    async def _record_usage(self, repos: Any, run_usage: Any) -> dict[str, Any] | None:
        """Record token usage + estimated cost if the repos expose a usage store."""
        store = getattr(repos, "usage", None)
        totals = self._usage_totals(run_usage)
        if totals is None:
            return None
        from agentkit import metrics

        metrics.record_cost(totals["cost_usd"])
        if store is None:
            return totals
        model_name = self.deps.settings.model_name if self.deps.settings else ""
        await store.add(
            conversation_id=self.conversation_id,
            kind="turn",
            model=model_name,
            cost_usd=totals["cost_usd"],
            **{
                key: totals[key]
                for key in (
                    "requests",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "cache_read_tokens",
                    "context_tokens",
                    "context_window",
                )
            },
        )
        return totals

    async def reset(self) -> None:
        await self.deps.repos.messages.clear(self.conversation_id)
