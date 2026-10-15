"""Durable per-owner memory: typed facts and a profile the agent should not forget.

Memories are plain rows in the same database as conversations (owner-scoped),
each with a CPU-computed embedding and a *kind* (``fact``, ``preference``,
``person``, ``date``, ``episodic``, ``procedural``). :func:`attach_memory` gives a
PydanticAI agent tools to save and recall them plus a dynamic instructions block
that lists what it already knows, so it can greet the user by name, keep their
preferences, and stop asking the same thing twice. Recall is a hybrid of semantic
similarity, recency, and importance; when no embedder is available it falls back
to keyword matching. See :mod:`agentkit.embeddings` and :mod:`agentkit.consolidation`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from pydantic_ai import Agent, RunContext

from agentkit.contracts.memory import MemoryStore, RecallStrategy
from agentkit.support import register_driver
from agentkit.support.kinds import DriverKind, MemoryDriver, RecallDriver
from agentkit.support.manager import Manager

DEFAULT_DIGEST_LIMIT = 50

_KIND_LABELS = {
    "fact": "Facts about the user",
    "preference": "Preferences",
    "person": "People",
    "date": "Important dates",
    "episodic": "Episodes",
    "procedural": "Procedures",
}

MEMORY_GUIDE = (
    "You have long-term memory about the user. When they tell you a durable fact "
    "(their name, preferences, important dates, how they like things done), save "
    "it with the `remember` tool (set `kind` to preference/person/date/… when "
    "relevant). Use `recall` to look something up, `remember_person` for people, "
    "`update_profile`/`get_profile` for their profile, and `forget_memory` to "
    "delete a fact by its id. Keep memories short and factual."
)


def _store(deps: Any) -> Any:
    return getattr(getattr(deps, "repos", None), "memories", None)


def _profile_store(deps: Any) -> Any:
    return getattr(getattr(deps, "repos", None), "profile", None)


def _enabled(deps: Any) -> bool:
    settings = getattr(deps, "settings", None)
    return bool(getattr(settings, "memory_enabled", True))


def _profile_line(profile: Any) -> str | None:
    if profile is None:
        return None
    parts = []
    for label, attribute in (
        ("name", "name"),
        ("timezone", "timezone"),
        ("locale", "locale"),
        ("notes", "notes"),
    ):
        value = getattr(profile, attribute, None)
        if value:
            parts.append(f"{label}={value}")
    if parts:
        return "Owner profile: " + ", ".join(parts)
    return None


async def memory_digest(repos: Any, *, limit: int = DEFAULT_DIGEST_LIMIT) -> str | None:
    """A grouped bullet list of everything remembered, or ``None`` if empty."""
    store = getattr(repos, "memories", None)
    if store is None or limit <= 0:
        return None
    lines: list[str] = []
    if hasattr(repos, "profile"):
        profile_line = _profile_line(await repos.profile.get())
        if profile_line:
            lines.append(profile_line)
    rows = await store.list(limit=limit)
    groups: dict[str, list[Any]] = {}
    for row in rows:
        groups.setdefault(getattr(row, "kind", "fact"), []).append(row)
    for kind in sorted(groups):
        header = _KIND_LABELS.get(kind, kind.title())
        lines.append(f"{header}:")
        lines.extend(f"- #{row.id} {row.content}" for row in groups[kind])
    if not lines:
        return None
    return "\n".join(lines)


def attach_memory(agent: Agent[Any, Any]) -> Agent[Any, Any]:
    """Register memory tools + a dynamic memory digest on ``agent`` (idempotent)."""
    if getattr(agent, "_agentkit_memory_attached", False):
        return agent

    @agent.tool
    async def remember(ctx: RunContext[Any], fact: str, kind: str = "fact") -> str:
        """Save a durable fact about the user (their name, preferences, dates, …).

        Args:
            fact: The fact to remember (short and factual).
            kind: One of fact, preference, person, date, episodic, procedural.
        """
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "memory is unavailable"
        try:
            row = await store.add(fact, kind=kind)
        except ValueError as exc:
            return f"could not remember: {exc}"
        return f"remembered as #{row.id}"

    @agent.tool
    async def remember_person(ctx: RunContext[Any], name: str, note: str = "") -> str:
        """Remember a person the user mentions.

        Args:
            name: The person's name.
            note: An optional detail about them.
        """
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "memory is unavailable"
        content = f"{name} — {note}" if note else name
        row = await store.add(content, kind="person")
        return f"remembered {name} as #{row.id}"

    @agent.tool
    async def recall(ctx: RunContext[Any], query: str, kind: str | None = None) -> str:
        """Look up what you already remember about the user.

        Args:
            query: What to look for.
            kind: Optionally restrict to one memory kind.
        """
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "(memory unavailable)"
        hits = await store.search(query, kind=kind)
        if not hits:
            return "(nothing remembered about that)"
        await store.record_use(hits)
        return "\n".join(f"{row.id}: {row.content}" for row in hits)

    @agent.tool
    async def forget_memory(ctx: RunContext[Any], memory_id: int) -> str:
        """Delete a remembered fact by its id."""
        store = _store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "memory is unavailable"
        return "forgotten" if await store.forget(memory_id) else "no such memory"

    @agent.tool
    async def update_profile(
        ctx: RunContext[Any],
        name: str | None = None,
        timezone: str | None = None,
        locale: str | None = None,
        notes: str | None = None,
        preferences: dict[str, str] | None = None,
    ) -> str:
        """Update the owner's profile (only the fields you pass are changed)."""
        store = _profile_store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "profile is unavailable"
        fields: dict[str, Any] = {}
        for key, value in (
            ("name", name),
            ("timezone", timezone),
            ("locale", locale),
            ("notes", notes),
            ("preferences", preferences),
        ):
            if value is not None:
                fields[key] = value
        if not fields:
            return "nothing to update"
        await store.set(**fields)
        return f"profile updated: {', '.join(sorted(fields))}"

    @agent.tool
    async def get_profile(ctx: RunContext[Any]) -> str:
        """Show the owner's stored profile."""
        store = _profile_store(ctx.deps)
        if store is None or not _enabled(ctx.deps):
            return "profile is unavailable"
        profile = await store.get()
        if profile is None:
            return "(no profile yet)"
        return (
            f"name={profile.name!r} timezone={profile.timezone!r} locale={profile.locale!r} "
            f"preferences={profile.preferences} notes={profile.notes!r}"
        )

    @agent.instructions
    async def _memory_instructions(ctx: RunContext[Any]) -> str | None:
        if not _enabled(ctx.deps):
            return None
        owner_name = getattr(getattr(ctx.deps, "settings", None), "owner_name", None)
        parts = [MEMORY_GUIDE]
        if owner_name and owner_name != "Owner":
            parts.append(f"The user's name is {owner_name}.")
        digest = await memory_digest(ctx.deps.repos)
        if digest:
            parts.append(digest)
        return "\n\n".join(parts)

    agent._agentkit_memory_attached = True  # type: ignore[attr-defined]
    return agent


# --------------------------------------------------------------------------
# Drivers
# --------------------------------------------------------------------------


class InMemoryStore:
    """An in-process memory store (no database); useful for ephemeral agents/tests."""

    def __init__(self) -> None:
        self._rows: dict[int, SimpleNamespace] = {}
        self._next = 1

    async def remember(self, content: str, *, kind: str = "fact") -> int:
        memory_id = self._next
        self._next += 1
        self._rows[memory_id] = SimpleNamespace(
            id=memory_id, content=content.strip(), kind=kind
        )
        return memory_id

    async def search(self, query: str, *, limit: int = 5) -> list[Any]:
        needle = (query or "").strip().lower()
        if not needle:
            return []
        hits = [
            row
            for row in self._rows.values()
            if needle in row.content.lower() or needle in row.kind.lower()
        ]
        return hits[:limit]

    async def all(self, limit: int | None = None) -> list[Any]:
        rows = list(self._rows.values())
        return rows[:limit] if limit is not None else rows

    async def forget(self, memory_id: int) -> bool:
        return self._rows.pop(memory_id, None) is not None

    async def digest(self, *, limit: int = DEFAULT_DIGEST_LIMIT) -> str | None:
        rows = await self.all(limit)
        if not rows:
            return None
        return "\n".join(f"- #{row.id} {row.content}" for row in rows)


class MemoryManager(Manager):
    """Resolves the configured memory store (``memory_driver``, default ``repository``)."""

    kind = DriverKind.MEMORY
    default_driver = MemoryDriver.REPOSITORY


@register_driver(DriverKind.MEMORY, MemoryDriver.REPOSITORY)
def _repository_memory_driver(app: Any) -> Any:
    from agentkit.foundation.facades import MemoryService

    return MemoryService(app)


@register_driver(DriverKind.MEMORY, MemoryDriver.IN_MEMORY)
def _in_memory_memory_driver(app: Any) -> InMemoryStore:
    return InMemoryStore()


def _recency(memory: Any, now: datetime, half_life_days: float) -> float:
    anchor = (
        getattr(memory, "last_used_at", None)
        or getattr(memory, "updated_at", None)
        or getattr(memory, "created_at", None)
    )
    if anchor is None:
        return 0.0
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    age_days = max((now - anchor).total_seconds(), 0.0) / 86400.0
    if half_life_days <= 0:
        return 1.0
    return float(2.0 ** (-age_days / half_life_days))


class HybridRecall:
    """The default recall: weighted similarity + recency + importance."""

    def __init__(self, settings: Any = None) -> None:
        self.settings = settings

    def score(self, query: str, similarity: float, memory: Any, now: Any) -> float:
        settings = self.settings
        w_sim = float(getattr(settings, "memory_recall_similarity_weight", 0.6))
        w_rec = float(getattr(settings, "memory_recall_recency_weight", 0.2))
        w_imp = float(getattr(settings, "memory_recall_importance_weight", 0.2))
        half_life = float(getattr(settings, "memory_recall_half_life_days", 30.0))
        return (
            w_sim * similarity
            + w_rec * _recency(memory, now, half_life)
            + w_imp * float(getattr(memory, "importance", 0.0) or 0.0)
        )


class KeywordRecall:
    """Ranks purely on keyword (substring) match."""

    def score(self, query: str, similarity: float, memory: Any, now: Any) -> float:
        return float(similarity)


class RecencyRecall:
    """Ranks purely on recency."""

    def __init__(self, settings: Any = None) -> None:
        self.settings = settings

    def score(self, query: str, similarity: float, memory: Any, now: Any) -> float:
        half_life = float(getattr(self.settings, "memory_recall_half_life_days", 30.0))
        return _recency(memory, now, half_life)


class MemoryRecallManager(Manager):
    """Resolves the configured recall strategy (``memory_recall_driver``, default ``hybrid``)."""

    kind = DriverKind.MEMORY_RECALL
    default_driver = RecallDriver.HYBRID


@register_driver(DriverKind.MEMORY_RECALL, RecallDriver.HYBRID)
def _hybrid_recall_driver(app: Any) -> HybridRecall:
    return HybridRecall(getattr(app, "settings", None))


@register_driver(DriverKind.MEMORY_RECALL, RecallDriver.KEYWORD)
def _keyword_recall_driver(app: Any) -> KeywordRecall:
    return KeywordRecall()


@register_driver(DriverKind.MEMORY_RECALL, RecallDriver.RECENCY)
def _recency_recall_driver(app: Any) -> RecencyRecall:
    return RecencyRecall(getattr(app, "settings", None))


__all__ = [
    "DEFAULT_DIGEST_LIMIT",
    "MEMORY_GUIDE",
    "HybridRecall",
    "InMemoryStore",
    "KeywordRecall",
    "MemoryManager",
    "MemoryRecallManager",
    "MemoryStore",
    "RecallStrategy",
    "RecencyRecall",
    "attach_memory",
    "memory_digest",
]
