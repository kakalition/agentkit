"""History compaction: shrink long conversations while keeping enough context.

The naive approach ("summarize everything older, keep the last N messages")
either drops facts the model still needs or re-summarizes the whole history every
turn (expensive, and summaries erode as they are re-compressed). :class:`Compactor`
takes the approach used by long-running agents (Hermes-style rolling memory):

**Three tiers**
1. **Pinned** — high-value *verbatim* messages (user constraints, durable facts,
   identifiers/paths). They are small and must survive exactly.
2. **Verbatim recent** — the newest messages, up to a share of the token budget,
   so the conversation still *reads* naturally and the model keeps local flow.
3. **Folded** — everything else is extracted into a structured, sectioned
   summary and then dropped.

**Structured rolling memory** — the summary is not a free-form blob but a set of
sections (objective, facts, constraints, decisions, tool results, open threads,
timeline). Each turn only the *newly dropped* messages are folded in and merged
(deduped), so compaction stays cheap and does not drift. Sections are rendered
back in priority order until the summary budget is spent, so under pressure the
model keeps the objective and facts and loses only the chatter.

Works offline with a heuristic extractor; pass ``model=`` (or ``summarize=``) for
model-based extraction::

    from agentkit import App, Compactor

    app.history_processor(Compactor(max_tokens=8000, keep_recent=0.45))

:func:`summarize_older` and :func:`truncating_processor` remain as simple
alternatives.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
)

__all__ = ["Compactor", "SECTIONS", "summarize_older", "transcript", "truncating_processor"]

# Rendered in this order — earlier sections are kept when the budget is tight.
SECTIONS: list[tuple[str, str]] = [
    ("objective", "Objective"),
    ("facts", "Facts"),
    ("constraints", "Constraints & preferences"),
    ("decisions", "Decisions"),
    ("tools", "Tool results"),
    ("open", "Open threads"),
    ("timeline", "Recent history"),
]

_FACT_RE = re.compile(
    r"\b(my name is|call me|i prefer|i like|i use|i'm|i am|remember that|note that|"
    r"my \w+ is|we use|the project is)\b",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"\b(always|never|must|mustn't|should|shouldn't|don't|do not|avoid|only|make sure|"
    r"keep it|prefer)\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"\b(let's|lets|we'll|we will|i'll|i will|decided|go with|switch to|use the|instead)\b",
    re.IGNORECASE,
)
_GOAL_RE = re.compile(r"\b(i want to|i need to|help me|can you|please|could you)\b", re.IGNORECASE)
_IDENT_RE = re.compile(r"(\b\d[\w.,:/+-]*\b|/[\w./-]+|\b[\w.-]+\.\w{1,5}\b)")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _encoder() -> Any:
    """A cached tokenizer (``tiktoken``) or ``None`` when unavailable."""
    global _ENCODER, _ENCODER_TRIED
    if not _ENCODER_TRIED:
        _ENCODER_TRIED = True
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:  # pragma: no cover - offline / not installed
            _ENCODER = None
    return _ENCODER


_ENCODER: Any = None
_ENCODER_TRIED = False


def estimate_tokens(text: str) -> int:
    """Estimate tokens with ``tiktoken`` when available, else ~4 chars/token."""
    if not text:
        return 0
    encoder = _encoder()
    if encoder is not None:
        try:
            return max(1, len(encoder.encode(text)))
        except Exception:  # pragma: no cover - defensive
            pass
    return max(1, (len(text) + 3) // 4)


def transcript(messages: list[ModelMessage]) -> str:
    """A plain-text rendering of messages (text parts only)."""
    lines: list[str] = []
    for message in messages:
        role = "user" if isinstance(message, ModelRequest) else "assistant"
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, str) and content.strip():
                lines.append(f"{role}: {content.strip()}")
    return "\n".join(lines)


def _message_text(message: ModelMessage) -> str:
    chunks: list[str] = []
    for part in getattr(message, "parts", []):
        content = getattr(part, "content", None)
        if isinstance(content, str):
            chunks.append(content)
    return "\n".join(chunks).strip()


def _message_tokens(message: ModelMessage) -> int:
    return estimate_tokens(_message_text(message)) or 1


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _message_hash(message: ModelMessage) -> str:
    payload = ModelMessagesTypeAdapter.dump_json([message])
    return hashlib.sha1(payload).hexdigest()


def _dedupe_append(target: list[str], items: list[str], *, cap: int) -> None:
    seen = {item.lower() for item in target}
    for item in items:
        item = item.strip()
        if item and item.lower() not in seen:
            target.append(item)
            seen.add(item.lower())
    if len(target) > cap:
        del target[: len(target) - cap]


def _truncate(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@dataclass
class _State:
    """Rolling structured memory for one conversation."""

    sections: dict[str, list[str]] = field(default_factory=lambda: {key: [] for key, _ in SECTIONS})
    folded: set[str] = field(default_factory=set)

    def merge(self, extracted: dict[str, list[str]], *, cap: int) -> None:
        for key, items in extracted.items():
            if key in self.sections and items:
                _dedupe_append(self.sections[key], items, cap=cap)

    def render(self, budget_tokens: int) -> str:
        lines: list[str] = []
        used = 0
        for key, title in SECTIONS:
            items = self.sections.get(key) or []
            if not items:
                continue
            header = f"{title}:"
            cost = estimate_tokens(header) + 1
            if used + cost > budget_tokens:
                break
            block = [header]
            for item in items:
                line = f"- {item}"
                cost = estimate_tokens(line) + 1
                if used + cost > budget_tokens:
                    break
                block.append(line)
                used += cost
            lines.extend(block)
            used += estimate_tokens(header) + 1
        return "\n".join(lines)

    def is_empty(self) -> bool:
        return not any(self.sections.values())


class Compactor:
    """A tiered, rolling, structured history processor.

    Callable as ``messages -> messages``; wire it with
    :meth:`agentkit.foundation.App.history_processor`.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 8000,
        keep_recent: float = 0.45,
        pinned_token_ratio: float = 0.2,
        summary_token_ratio: float = 0.25,
        model: Any = None,
        summarize: Callable[[str, str], Any] | None = None,
        section_cap: int = 24,
    ) -> None:
        self.max_tokens = max_tokens
        self.keep_recent = keep_recent  # share of the budget kept verbatim (by tokens)
        self.pinned_token_ratio = pinned_token_ratio
        self.summary_token_ratio = summary_token_ratio
        self.model = model
        self.summarize = summarize
        self.section_cap = section_cap
        self._state = _State()
        # Per-conversation rolling state (a shared Compactor must not leak memory
        # between conversations). The default state serves conversation_id=None.
        self._states: dict[str, _State] = {}

    # -- callable seam --------------------------------------------------
    def reset(self, conversation_id: str | None = None) -> None:
        """Forget the rolling summary (e.g. on a new conversation)."""
        if conversation_id is None:
            self._state = _State()
        else:
            self._states.pop(conversation_id, None)

    def _state_for(self, conversation_id: str | None) -> _State:
        if conversation_id is None:
            return self._state
        state = self._states.get(conversation_id)
        if state is None:
            state = _State()
            self._states[conversation_id] = state
        return state

    @property
    def summary(self) -> str:
        return self._state.render(budget_tokens=10**9)

    async def compact(
        self, messages: list[ModelMessage], *, conversation_id: str | None = None
    ) -> list[ModelMessage]:
        state = self._state_for(conversation_id)
        messages = list(messages)
        if self._total_tokens(messages) <= self.max_tokens:
            return messages

        recent_budget = int(self.max_tokens * self.keep_recent)
        recent = self._take_recent(messages, recent_budget)
        droppable = messages[: len(messages) - len(recent)]

        pinned_budget = int(self.max_tokens * self.pinned_token_ratio)
        pinned = self._take_pinned(droppable, pinned_budget)
        pinned_ids = {id(message) for message in pinned}
        to_fold = [m for m in droppable if id(m) not in pinned_ids]

        new = [m for m in to_fold if _message_hash(m) not in state.folded]
        if new:
            extracted = await self._extract(new, state)
            if extracted:
                state.merge(extracted, cap=self.section_cap)
            if state.is_empty():
                state.sections["timeline"].append(
                    f"{len(new)} earlier message(s) omitted during compaction"
                )
            for message in new:
                state.folded.add(_message_hash(message))

        summary_budget = int(self.max_tokens * self.summary_token_ratio)
        rendered = state.render(budget_tokens=summary_budget) if not state.is_empty() else ""
        result: list[ModelMessage] = []
        if rendered:
            result.append(
                ModelRequest(parts=[SystemPromptPart(content=f"Conversation memory:\n{rendered}")])
            )
        result.extend(pinned)
        result.extend(recent)
        return result

    async def __call__(
        self, messages: list[ModelMessage], *, conversation_id: str | None = None
    ) -> list[ModelMessage]:
        return await self.compact(messages, conversation_id=conversation_id)

    # -- tiers ----------------------------------------------------------
    def _total_tokens(self, messages: list[ModelMessage]) -> int:
        return sum(_message_tokens(message) for message in messages)

    def _take_recent(self, messages: list[ModelMessage], budget: int) -> list[ModelMessage]:
        recent: list[ModelMessage] = []
        used = 0
        for message in reversed(messages):
            cost = _message_tokens(message)
            if recent and used + cost > budget:
                break
            recent.insert(0, message)
            used += cost
        return recent

    def _take_pinned(self, messages: list[ModelMessage], budget: int) -> list[ModelMessage]:
        pinned: list[ModelMessage] = []
        used = 0
        for message in messages:
            if not self._is_pinned(message):
                continue
            cost = _message_tokens(message)
            if used + cost > budget and pinned:
                break
            pinned.append(message)
            used += cost
        return pinned

    @staticmethod
    def _is_pinned(message: ModelMessage) -> bool:
        """Pinned = a short user message carrying a fact, constraint, or identifier."""
        if not isinstance(message, ModelRequest):
            return False
        text = _message_text(message)
        if not text or len(text) > 600:
            return False
        return bool(_FACT_RE.search(text) or _CONSTRAINT_RE.search(text))

    # -- extraction -----------------------------------------------------
    async def _extract(self, messages: list[ModelMessage], state: _State) -> dict[str, list[str]]:
        raw_text = transcript(messages)
        if self.summarize is not None:
            result = self.summarize(self.summary, raw_text)
            if inspect.isawaitable(result):
                result = await result
            return self._coerce(result, state)
        if self.model is not None:
            try:
                return await self._model_extract(raw_text, state)
            except Exception:  # pragma: no cover - fall back to heuristics
                return self._heuristic_extract(messages)
        return self._heuristic_extract(messages)

    def _coerce(self, result: Any, state: _State) -> dict[str, list[str]]:
        if isinstance(result, dict):
            return {key: list(value) for key, value in result.items() if key in state.sections}
        return self._heuristic_from_text(str(result))

    async def _model_extract(self, raw_text: str, state: _State) -> dict[str, list[str]]:
        from pydantic_ai import Agent

        schema = ", ".join(f'"{key}"' for key, _ in SECTIONS)
        agent: Agent[Any, str] = Agent(
            self.model,
            output_type=str,
            instructions=(
                "Extract durable memory from the conversation turns below. Respond with "
                f"ONLY a JSON object whose keys are a subset of {{{schema}}} and whose "
                "values are arrays of short strings. Keep facts, constraints, decisions, "
                "and tool results; skip chit-chat. Do not add commentary."
            ),
        )
        result = await agent.run(raw_text)
        payload = json.loads(result.output if isinstance(result.output, str) else str(result.output))
        if not isinstance(payload, dict):
            raise ValueError("summary was not a JSON object")
        return {
            key: [_truncate(str(item)) for item in value]
            for key, value in payload.items()
            if key in state.sections and isinstance(value, list)
        }

    def _heuristic_from_text(self, text: str) -> dict[str, list[str]]:
        return {"timeline": [_truncate(text)]} if text.strip() else {}

    def _heuristic_extract(self, messages: list[ModelMessage]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {"objective": [], "facts": [], "constraints": [], "decisions": [], "tools": [], "open": [], "timeline": []}
        for message in messages:
            if isinstance(message, ModelResponse):
                self._extract_tools(message, out)
            text = _message_text(message)
            if not text:
                continue
            is_user = isinstance(message, ModelRequest)
            for sentence in _sentences(text):
                short = _truncate(sentence, 200)
                if not is_user:
                    if sentence.rstrip().endswith("?"):
                        out["open"].append(short)
                    continue
                if _GOAL_RE.search(sentence) and len(out["objective"]) < 3:
                    out["objective"].append(short)
                elif _FACT_RE.search(sentence):
                    out["facts"].append(short)
                elif _CONSTRAINT_RE.search(sentence):
                    out["constraints"].append(short)
                elif _DECISION_RE.search(sentence):
                    out["decisions"].append(short)
                elif sentence.rstrip().endswith("?"):
                    out["open"].append(short)
                elif _IDENT_RE.search(sentence) and len(short) <= 120:
                    out["facts"].append(short)
        return {key: value for key, value in out.items() if value}

    @staticmethod
    def _extract_tools(message: ModelResponse, out: dict[str, list[str]]) -> None:
        for part in getattr(message, "parts", []):
            name = getattr(part, "tool_name", None)
            content = getattr(part, "content", None)
            if name and content is not None:
                out["tools"].append(f"{name}: {_truncate(str(content))}")


# ---------------------------------------------------------------------------
# Simple alternatives (kept for back-compat)
# ---------------------------------------------------------------------------


def summarize_older(
    *,
    keep_recent: int = 8,
    threshold: int = 24,
    model: Any = None,
    summarize: Callable[[list[ModelMessage]], Any] | None = None,
    header: str = "Earlier conversation summary",
) -> Callable[[list[ModelMessage]], Any]:
    """Summarize all but the most recent ``keep_recent`` messages into one note."""

    async def processor(messages: list[ModelMessage]) -> list[ModelMessage]:
        messages = list(messages)
        if len(messages) <= threshold or keep_recent <= 0:
            return messages
        older, recent = messages[:-keep_recent], messages[-keep_recent:]
        if not older:
            return messages
        if summarize is not None:
            summary = summarize(older)
            if inspect.isawaitable(summary):
                summary = await summary
        elif model is not None:
            from pydantic_ai import Agent

            agent: Agent[Any, str] = Agent(model, output_type=str, instructions=SUMMARY_INSTRUCTIONS)
            outcome = await agent.run(transcript(older))
            summary = outcome.output
        else:
            summary = transcript(older)
        text = str(summary).strip()
        if not text:
            return recent
        note = ModelRequest(parts=[SystemPromptPart(content=f"{header}: {text}")])
        return [note, *recent]

    return processor


def truncating_processor(
    max_messages: int = 20,
) -> Callable[[list[ModelMessage]], list[ModelMessage]]:
    """Drop all but the most recent ``max_messages`` messages."""

    def processor(messages: list[ModelMessage]) -> list[ModelMessage]:
        return list(messages)[-max_messages:] if max_messages > 0 else list(messages)

    return processor


SUMMARY_INSTRUCTIONS = (
    "You compress conversation history. Summarize the messages below in a few "
    "sentences, preserving durable facts, decisions, names, numbers, and any "
    "open threads. Do not add commentary."
)
