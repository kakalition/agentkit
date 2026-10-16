"""Self-learning: a closed **reflect -> learn -> apply** loop.

The agent distils durable *lessons* ("when X, do Y"), preferences, and facts from
its own conversation history, then applies them in future turns:

* **Reflect** — :func:`reflect` reads a window of a conversation and extracts
  lessons/preferences/facts with a model (JSON-only, mirroring
  :meth:`agentkit.compaction.Compactor._model_extract`) or an offline heuristic,
  and is idempotent per conversation + window via a ``learning_runs`` record.
* **Learn** — lessons are stored as procedural memories (deduped via
  ``near_duplicates``/``merge``), preferences merge into the owner profile, and
  facts become memories. PII/secrets are redacted before storage.
* **Apply** — :func:`lessons_digest` is injected into the instructions by
  ``Agent.learning()``/``Agent.full()``, so learned behavior changes the next turn;
  recurring lessons can be distilled into a ``SKILL.md``.

Reflection runs on demand (the ``reflect`` tool, ``agentkit learning:reflect``)
and durably (the ``learning:reflect`` scheduler task registered by
:class:`~agentkit.foundation.fullstack.FullStackProvider`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext

from agentkit.contracts.learning import Extractor, LearningSink, LearningStrategy
from agentkit.deps import Deps
from agentkit.guardrails import redact, redact_pii
from agentkit.support import register_driver
from agentkit.support.kinds import (
    DriverKind,
    LearningExtractorDriver,
    LearningSinkDriver,
    LearningStrategyDriver,
)
from agentkit.support.manager import Manager

__all__ = [
    "LESSON_GUIDE",
    "LESSON_KIND",
    "LESSON_TASK",
    "Extractor",
    "HeuristicExtractor",
    "LearningSignals",
    "LearningSink",
    "LearningStrategy",
    "MemorySink",
    "ModelExtractor",
    "NoopStrategy",
    "ReflectApplyStrategy",
    "approve_lesson",
    "attach_learning",
    "lessons_digest",
    "propose_memories",
    "proposed_lessons",
    "reflect",
    "register_reflect_task",
    "reject_lesson",
]

LESSON_TASK = "learning:reflect"
LESSON_KIND = "procedural"
REFLECT_SECTIONS = ("lessons", "preferences", "facts")
DEFAULT_WINDOW = 20
DEFAULT_MAX_LESSONS = 50
DEFAULT_SKILL_THRESHOLD = 3
_MAX_ITEM = 240

LESSON_GUIDE = (
    "You learn from experience. After finishing a task, record a reusable lesson "
    "with the `learn` tool (write it as \"when X, do Y\"). Use `reflect` to review "
    "recent turns and distil lessons, `list_lessons` to see what you have learned, "
    "and `forget_lesson` to drop a bad lesson by id. Apply learned lessons unless "
    "the current request says otherwise."
)

_PREF_RE = re.compile(
    r"\b(i prefer|i like|i don't like|i dislike|i use|call me|"
    r"i'd rather|i would rather|please use)\b",
    re.IGNORECASE,
)
_LESSON_RE = re.compile(
    r"\b(always|never|make sure|instead|from now on|next time|"
    r"when \w+.*\bdo\b|prefer to|be sure to|remember to)\b",
    re.IGNORECASE,
)
_FACT_RE = re.compile(
    r"\b(my name is|my \w+ is|we use|the project is|i live in|i work at)\b",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _truncate(text: str, limit: int = _MAX_ITEM) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _importance(text: str) -> float:
    return round(min(0.9, 0.5 + len(text) / 500.0), 3)


def _redact_items(items: Any) -> list[str]:
    """Redact PII/secrets from extracted items, drop empties/duplicates."""
    out: list[str] = []
    for item in items or []:
        text = _truncate(redact(redact_pii(str(item).strip())))
        if text and text not in out:
            out.append(text)
    return out


def _signature(payloads: list[str], window: int) -> str:
    digest = hashlib.sha1("\n".join(payloads).encode("utf-8")).hexdigest()
    return f"{window}:{digest}"


# ---------------------------------------------------------------------------
# Signals (event-driven, non-blocking)
# ---------------------------------------------------------------------------


@dataclass
class LearningSignals:
    """A bounded, redacted ring buffer of learning signals from the event bus."""

    capacity: int = 200
    events: deque = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.events.maxlen != self.capacity:
            self.events = deque(self.events, maxlen=self.capacity)

    def record(self, event: str, **payload: Any) -> None:
        detail = _truncate(json.dumps(payload, default=str))
        self.events.append({"event": event, "detail": redact(redact_pii(detail))})

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return list(self.events)[-limit:]

    def subscribe(self, dispatcher: Any, events: tuple[str, ...] = ("turn.end", "agent.error")) -> None:
        """Feed the buffer from an app dispatcher (listeners are sync)."""

        def listener(**payload: Any) -> None:
            self.record("event", **payload)

        for name in events:
            dispatcher.listen(name, listener)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _heuristic_extract(messages: list[Any]) -> dict[str, list[str]]:
    from agentkit.compaction import transcript

    out: dict[str, list[str]] = {"lessons": [], "preferences": [], "facts": []}
    for sentence in _SENTENCE_RE.split(transcript(messages)):
        text = sentence.strip()
        if not text or len(text) > 400:
            continue
        if _PREF_RE.search(text):
            out["preferences"].append(_truncate(text))
        elif _LESSON_RE.search(text):
            out["lessons"].append(_truncate(text))
        elif _FACT_RE.search(text):
            out["facts"].append(_truncate(text))
    return {key: value for key, value in out.items() if value}


async def _model_extract(model: Any, raw_text: str) -> dict[str, list[str]]:
    from pydantic_ai import Agent

    schema = ", ".join(f'"{key}"' for key in REFLECT_SECTIONS)
    agent: Agent[Any, str] = Agent(
        model,
        output_type=str,
        instructions=(
            "Extract durable, reusable learning from the conversation below. Respond "
            f"with ONLY a JSON object whose keys are a subset of {{{schema}}} and whose "
            "values are arrays of short strings. lessons are procedural rules of the "
            'form "when X, do Y"; preferences are the user\'s likes/dislikes; facts are '
            "durable truths about the user or project. Never include secrets or "
            "credentials. Do not add commentary."
        ),
    )
    result = await agent.run(raw_text)
    payload = json.loads(result.output if isinstance(result.output, str) else str(result.output))
    if not isinstance(payload, dict):
        raise ValueError("reflection was not a JSON object")
    return {
        key: [_truncate(str(item)) for item in value]
        for key, value in payload.items()
        if key in REFLECT_SECTIONS and isinstance(value, list)
    }


async def _extract(messages: list[Any], model: Any) -> dict[str, list[str]]:
    if model is not None:
        try:
            from agentkit.compaction import transcript

            return await _model_extract(model, transcript(messages))
        except Exception:  # pragma: no cover - fall back to heuristics
            return _heuristic_extract(messages)
    return _heuristic_extract(messages)


# ---------------------------------------------------------------------------
# Storage + application
# ---------------------------------------------------------------------------


async def _dedupe_lessons(store: Any, threshold: float = 0.9) -> int:
    """Merge near-duplicate lessons; returns how many were folded away."""
    groups = await store.near_duplicates(threshold, kind=LESSON_KIND)
    merged = 0
    for group in groups:
        canonical = max(group, key=lambda m: (float(m.importance or 0.0), len(m.content)))
        others = [m for m in group if m.id != canonical.id]
        merged += len(others)
        if others:
            await store.merge(canonical, others)
    return merged


async def _merge_preferences(repos: Any, items: list[str]) -> None:
    profile_repo = getattr(repos, "profile", None)
    if profile_repo is None:
        return
    profile = await profile_repo.get()
    current: dict[str, Any] = {}
    if profile is not None and profile.preferences:
        try:
            parsed = json.loads(profile.preferences)
            if isinstance(parsed, dict):
                current = parsed
        except ValueError:
            current = {}
    for item in items:
        key = _SLUG_RE.sub("_", item.lower()).strip("_")[:40] or f"pref_{len(current)}"
        current[key] = item
    await profile_repo.set(preferences=current)


def _skills_root(settings: Any) -> Any:
    from agentkit.skills import SkillRegistry

    registry = SkillRegistry.from_settings(settings)
    return registry.roots[0] if registry.roots else None


async def _distill(
    repos: Any, settings: Any, threshold: int, write: bool
) -> tuple[list[dict[str, Any]], list[str]]:
    """Find recurring lessons; optionally synthesize a SKILL.md for each."""
    store = getattr(repos, "memories", None)
    if store is None:
        return [], []
    groups = await store.near_duplicates(0.9, kind=LESSON_KIND)
    candidates: list[dict[str, Any]] = []
    written: list[str] = []
    root = _skills_root(settings)
    for group in groups:
        if len(group) < max(2, threshold):
            continue
        seed = max(group, key=lambda m: (float(m.importance or 0.0), len(m.content)))
        name = _SLUG_RE.sub("-", seed.content.lower()).strip("-")[:40] or "lesson"
        candidates.append(
            {"name": name, "count": len(group), "lessons": [m.content for m in group[:3]]}
        )
        if write and root is not None:
            from agentkit.skills import write_skill_file

            write_skill_file(
                root,
                name,
                description=seed.content[:120],
                body="Learned procedure:\n"
                + "\n".join(f"- {memory.content}" for memory in group),
            )
            written.append(name)
    return candidates, written


async def reflect(
    repos: Any,
    *,
    model: Any = None,
    conversation_id: str | None = None,
    window: int | None = None,
    dry_run: bool = False,
    settings: Any = None,
    auto_skills: bool | None = None,
    skill_threshold: int | None = None,
) -> dict[str, Any]:
    """Distil lessons/preferences/facts from a conversation window.

    Idempotent per conversation + window (re-running is cheap and non-duplicating).
    Returns a summary dict (counts, merged, skill candidates/written).
    """
    if settings is None:
        from agentkit.config import get_settings

        settings = get_settings()
    window = int(window or getattr(settings, "learning_window", DEFAULT_WINDOW) or DEFAULT_WINDOW)
    threshold = int(
        skill_threshold
        if skill_threshold is not None
        else getattr(settings, "learning_skill_threshold", DEFAULT_SKILL_THRESHOLD)
    )
    write_skills = bool(
        auto_skills if auto_skills is not None else getattr(settings, "learning_auto_skills", False)
    )
    max_lessons = int(
        getattr(settings, "learning_max_lessons", DEFAULT_MAX_LESSONS) or DEFAULT_MAX_LESSONS
    )
    require_review = bool(getattr(settings, "learning_require_review", True))
    lesson_status = "proposed" if require_review else "active"

    result: dict[str, Any] = {
        "conversation_id": conversation_id,
        "skipped": False,
        "lessons": 0,
        "preferences": 0,
        "facts": 0,
        "merged": 0,
        "skill_candidates": [],
        "skills": [],
    }

    if conversation_id is None:
        conversations = await repos.conversations.list(limit=1)
        conversation_id = conversations[0].id if conversations else None
        result["conversation_id"] = conversation_id
    if conversation_id is None:
        return result

    payloads = [row.payload for row in await repos.messages.list(conversation_id, limit=window)]
    signature = _signature(payloads, window)
    runs = getattr(repos, "learning_runs", None)
    if runs is not None and await runs.seen(conversation_id, signature):
        result["skipped"] = True
        return result
    if not payloads:
        return result

    from agentkit.session import deserialize_messages

    extracted = await _extract(deserialize_messages(payloads), model)
    lessons = _redact_items(extracted.get("lessons", []))[:max_lessons]
    preferences = _redact_items(extracted.get("preferences", []))
    facts = _redact_items(extracted.get("facts", []))
    result.update(lessons=len(lessons), preferences=len(preferences), facts=len(facts))
    if dry_run:
        result["dry_run"] = True
        return result

    store = getattr(repos, "memories", None)
    candidates: list[dict[str, Any]] = []
    written: list[str] = []
    if store is not None:
        for lesson in lessons:
            await store.add(
                lesson,
                kind=LESSON_KIND,
                importance=_importance(lesson),
                source_conversation_id=conversation_id,
                status=lesson_status,
            )
            await _emit("learning.lesson", conversation_id=conversation_id, text=lesson)
        for fact in facts:
            await store.add(fact, kind="fact", source_conversation_id=conversation_id)
        for preference in preferences:
            await store.add(
                preference,
                kind="preference",
                importance=0.6,
                source_conversation_id=conversation_id,
            )
        # Distil recurring lessons *before* deduping (a merged lesson is one signal).
        candidates, written = await _distill(repos, settings, threshold, write_skills)
        result["merged"] = await _dedupe_lessons(store)

    if preferences:
        await _merge_preferences(repos, preferences)

    result["skill_candidates"] = candidates
    result["skills"] = written

    if runs is not None:
        await runs.record(
            conversation_id,
            signature=signature,
            lessons=len(lessons),
            preferences=len(preferences),
            facts=len(facts),
            detail=json.dumps(candidates, default=str),
        )
    await _emit(
        "learning.reflected",
        conversation_id=conversation_id,
        lessons=len(lessons),
        preferences=len(preferences),
        facts=len(facts),
    )
    return result


async def propose_memories(
    repos: Any,
    *,
    model: Any = None,
    conversation_id: str | None = None,
    window: int | None = None,
    settings: Any = None,
) -> list[int]:
    """Queue durable facts/preferences from a conversation for review.

    Unlike :func:`reflect` (which applies facts immediately), every candidate is
    stored ``proposed`` and only applied once approved — this is the "nudge" path
    used by :mod:`agentkit.nudges`. Returns the ids of the proposed memories.
    """
    if settings is None:
        from agentkit.config import get_settings

        settings = get_settings()
    window = int(window or getattr(settings, "learning_window", DEFAULT_WINDOW) or DEFAULT_WINDOW)
    store = getattr(repos, "memories", None)
    if conversation_id is None or store is None:
        return []
    payloads = [row.payload for row in await repos.messages.list(conversation_id, limit=window)]
    if not payloads:
        return []
    from agentkit.session import deserialize_messages

    extracted = await _extract(deserialize_messages(payloads), model)
    proposed: list[int] = []
    for fact in _redact_items(extracted.get("facts", []))[:10]:
        row = await store.add(
            fact, kind="fact", status="proposed", source_conversation_id=conversation_id
        )
        proposed.append(row.id)
    for preference in _redact_items(extracted.get("preferences", []))[:10]:
        row = await store.add(
            preference,
            kind="preference",
            status="proposed",
            source_conversation_id=conversation_id,
        )
        proposed.append(row.id)
    if proposed:
        await _emit("memory.nudge", conversation_id=conversation_id, proposed=len(proposed))
    return proposed


async def lessons_digest(repos: Any, *, limit: int | None = None) -> str | None:
    """A capped, importance-ranked digest of learned lessons, or ``None``."""
    store = getattr(repos, "memories", None)
    if store is None:
        return None
    rows = list(await store.list(kind=LESSON_KIND, status="active"))
    if not rows:
        return None
    rows.sort(key=lambda row: (float(row.importance or 0.0), int(row.access_count or 0)), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    lines = ["Lessons learned (apply when relevant):"]
    lines.extend(f"- #{row.id} {row.content}" for row in rows)
    return "\n".join(lines)


async def proposed_lessons(repos: Any) -> list[Any]:
    """Lessons awaiting review (only meaningful with ``learning_require_review``)."""
    store = getattr(repos, "memories", None)
    if store is None:
        return []
    return await store.proposed(kind=LESSON_KIND)


async def approve_lesson(repos: Any, lesson_id: int) -> bool:
    """Promote a proposed lesson to ``active`` so it is applied."""
    store = getattr(repos, "memories", None)
    if store is None:
        return False
    return await store.set_status(lesson_id, "active")


async def reject_lesson(repos: Any, lesson_id: int) -> bool:
    """Mark a proposed lesson ``rejected`` so it is never applied."""
    store = getattr(repos, "memories", None)
    if store is None:
        return False
    return await store.set_status(lesson_id, "rejected")


async def _emit(event: str, **payload: Any) -> None:
    from agentkit.foundation.facade import emit

    await emit(event, **payload)


async def _reflect_for_ctx(ctx: RunContext[Deps], settings: Any) -> dict[str, Any]:
    """The ``reflect`` tool body (kept at module scope so it can call :func:`reflect`)."""
    return await reflect(
        ctx.deps.repos,
        model=ctx.deps.model,
        conversation_id=ctx.deps.conversation_id,
        settings=getattr(ctx.deps, "settings", settings),
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def attach_learning(agent: Any, *, settings: Any = None) -> Any:
    """Register the learning tools + lessons digest on a built agent (idempotent)."""
    if getattr(agent, "_agentkit_learning_attached", False):
        return agent

    @agent.tool
    async def learn(ctx: RunContext[Deps], insight: str, kind: str = "lesson") -> str:
        """Record a reusable lesson (or preference/fact) right after a task.

        Args:
            insight: The lesson, written as "when X, do Y".
            kind: One of lesson (default), preference, fact.
        """
        store = getattr(getattr(ctx.deps, "repos", None), "memories", None)
        if store is None:
            return "learning is unavailable"
        memory_kind = {
            "lesson": LESSON_KIND,
            "procedural": LESSON_KIND,
            "preference": "preference",
            "fact": "fact",
        }.get(kind, LESSON_KIND)
        text = _truncate(redact(redact_pii((insight or "").strip())))
        if not text:
            return "nothing to learn"
        deps_settings = getattr(ctx.deps, "settings", settings)
        require_review = bool(getattr(deps_settings, "learning_require_review", True))
        status = "proposed" if require_review and memory_kind == LESSON_KIND else "active"
        row = await store.add(
            text,
            kind=memory_kind,
            importance=_importance(text),
            source_conversation_id=ctx.deps.conversation_id,
            status=status,
        )
        await _emit("learning.lesson", conversation_id=ctx.deps.conversation_id, text=text)
        return f"learned as #{row.id}" + (" (pending review)" if status == "proposed" else "")

    @agent.tool
    async def reflect(ctx: RunContext[Deps]) -> str:
        """Review recent turns and distil durable lessons."""
        summary = await _reflect_for_ctx(ctx, settings)
        return json.dumps(summary, default=str)

    @agent.tool
    async def list_lessons(ctx: RunContext[Deps], limit: int = 20) -> str:
        """List the lessons you have learned.

        Args:
            limit: Maximum lessons to list.
        """
        store = getattr(getattr(ctx.deps, "repos", None), "memories", None)
        if store is None:
            return "(learning unavailable)"
        rows = await store.list(kind=LESSON_KIND, status="active")
        if not rows:
            return "(no lessons yet)"
        rows.sort(key=lambda row: float(row.importance or 0.0), reverse=True)
        return "\n".join(f"#{row.id} {row.content}" for row in rows[: max(1, int(limit))])

    @agent.tool
    async def forget_lesson(ctx: RunContext[Deps], id: int) -> str:
        """Delete a lesson by id.

        Args:
            id: The lesson id (from list_lessons).
        """
        store = getattr(getattr(ctx.deps, "repos", None), "memories", None)
        if store is None:
            return "(learning unavailable)"
        return "forgotten" if await store.forget(id) else "no such lesson"

    @agent.instructions
    async def _learning_instructions(ctx: RunContext[Deps]) -> str | None:
        parts = [LESSON_GUIDE]
        digest = await lessons_digest(getattr(ctx.deps, "repos", None))
        if digest:
            parts.append(digest)
        return "\n\n".join(parts)

    agent._agentkit_learning_attached = True  # type: ignore[attr-defined]
    return agent


def register_reflect_task() -> str:
    """Register the durable ``learning:reflect`` scheduler task (idempotent)."""
    from agentkit.scheduler import TASKS, task

    if LESSON_TASK in TASKS:
        return LESSON_TASK

    @task(LESSON_TASK)
    async def _reflect() -> dict[str, Any]:
        from agentkit.runtime import build_runtime, repositories

        runtime = build_runtime()
        async with repositories(runtime) as repos:
            return await reflect(repos, settings=runtime.settings)

    return LESSON_TASK


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


class HeuristicExtractor:
    """An offline extractor: keyword/template heuristics, no model call."""

    async def extract(self, messages: list[Any], model: Any = None) -> dict[str, list[str]]:
        return _heuristic_extract(messages)


class ModelExtractor:
    """The default extractor: a JSON model call, falling back to heuristics."""

    async def extract(self, messages: list[Any], model: Any = None) -> dict[str, list[str]]:
        return await _extract(messages, model)


class ReflectApplyStrategy:
    """The default strategy: the full ``reflect`` pass (extract → store → digest)."""

    async def run(self, repos: Any, **options: Any) -> dict[str, Any]:
        return await reflect(repos, **options)


class NoopStrategy:
    """A strategy that never learns (for deterministic, specialized agents)."""

    async def run(self, repos: Any, **options: Any) -> dict[str, Any]:
        return {"skipped": True, "lessons": 0, "preferences": 0, "facts": 0, "strategy": "none"}


class MemorySink:
    """The default sink: lessons/facts/preferences into owner memories."""

    async def store(self, repos: Any, items: dict[str, list[str]], **options: Any) -> int:
        store = getattr(repos, "memories", None)
        if store is None:
            return 0
        settings = options.get("settings")
        conversation_id = options.get("conversation_id")
        require_review = bool(getattr(settings, "learning_require_review", True))
        lesson_status = "proposed" if require_review else "active"
        added = 0
        for lesson in items.get("lessons", []):
            await store.add(
                lesson,
                kind=LESSON_KIND,
                importance=_importance(lesson),
                source_conversation_id=conversation_id,
                status=lesson_status,
            )
            added += 1
        for fact in items.get("facts", []):
            await store.add(fact, kind="fact", source_conversation_id=conversation_id)
            added += 1
        for preference in items.get("preferences", []):
            await store.add(
                preference,
                kind="preference",
                importance=0.6,
                source_conversation_id=conversation_id,
            )
            added += 1
        return added


class LearningExtractorManager(Manager):
    """Resolves the configured extractor (``learning_extractor_driver``, default ``model``)."""

    kind = DriverKind.LEARNING_EXTRACTOR
    default_driver = LearningExtractorDriver.MODEL


class LearningStrategyManager(Manager):
    """Resolves the learning strategy (``learning_strategy_driver``, default ``reflect_apply``)."""

    kind = DriverKind.LEARNING_STRATEGY
    default_driver = LearningStrategyDriver.REFLECT_APPLY


class LearningSinkManager(Manager):
    """Resolves the learning sink (``learning_sink_driver``, default ``memory``)."""

    kind = DriverKind.LEARNING_SINK
    default_driver = LearningSinkDriver.MEMORY


@register_driver(DriverKind.LEARNING_EXTRACTOR, LearningExtractorDriver.MODEL)
def _model_extractor_driver(app: Any) -> ModelExtractor:
    return ModelExtractor()


@register_driver(DriverKind.LEARNING_EXTRACTOR, LearningExtractorDriver.HEURISTIC)
def _heuristic_extractor_driver(app: Any) -> HeuristicExtractor:
    return HeuristicExtractor()


@register_driver(DriverKind.LEARNING_STRATEGY, LearningStrategyDriver.REFLECT_APPLY)
def _reflect_apply_strategy_driver(app: Any) -> ReflectApplyStrategy:
    return ReflectApplyStrategy()


@register_driver(DriverKind.LEARNING_STRATEGY, LearningStrategyDriver.NONE)
def _noop_strategy_driver(app: Any) -> NoopStrategy:
    return NoopStrategy()


@register_driver(DriverKind.LEARNING_SINK, LearningSinkDriver.MEMORY)
def _memory_sink_driver(app: Any) -> MemorySink:
    return MemorySink()
