from __future__ import annotations

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from agentkit.compaction import (
    Compactor,
    estimate_tokens,
    summarize_older,
    transcript,
    truncating_processor,
)


def _u(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _a(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def _long(word: str = "filler") -> str:
    return (word + " ") * 120


def _conversation(n: int) -> list:
    messages = [_u("My name is Ada. Always reply in French.")]
    for index in range(n):
        messages.append(_u(f"Question {index}: " + _long()))
        messages.append(_a(f"Answer {index}: " + _long()))
    return messages


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") >= 1


def test_transcript_renders_text_parts():
    text = transcript([_u("hi"), _a("hello")])
    assert "user: hi" in text
    assert "assistant: hello" in text


async def test_compactor_shrinks_and_keeps_pinned_and_facts():
    messages = _conversation(8)
    compactor = Compactor(max_tokens=300, keep_recent=0.4)
    result = await compactor.compact(messages)

    assert len(result) < len(messages)
    assert any(
        isinstance(getattr(part, "content", None), str)
        and "Conversation memory" in part.content
        for message in result
        for part in message.parts
    )
    # The pinned constraint/fact survives verbatim.
    joined = transcript(result)
    assert "My name is Ada" in joined
    assert compactor.summary  # rolling memory is populated


async def test_compactor_under_budget_is_unchanged():
    messages = [_u("short"), _a("reply")]
    compactor = Compactor(max_tokens=10_000)
    assert await compactor.compact(messages) == messages


async def test_compactor_rolling_does_not_duplicate():
    messages = _conversation(8)
    compactor = Compactor(max_tokens=300, keep_recent=0.4)
    await compactor.compact(messages)
    first = compactor.summary
    await compactor.compact(messages)
    assert compactor.summary == first  # nothing new folded, no drift


async def test_compactor_uses_injected_summarizer():
    calls = []

    def summarize(previous, text):  # noqa: ANN001
        calls.append(previous)
        return {"decisions": ["We will use SQLite"], "facts": ["Project is agentkit"]}

    compactor = Compactor(max_tokens=200, keep_recent=0.3, summarize=summarize)
    result = await compactor.compact(_conversation(6))
    assert calls
    joined = transcript(result)
    assert "We will use SQLite" in joined
    assert "Project is agentkit" in joined


async def test_compactor_heuristic_extracts_sections():
    messages = [
        _u("I prefer dark mode."),
        _a("Noted."),
        _u("Let's use Postgres."),
        _a("ok " + _long()),
        _u("What about indexes? " + _long()),
    ] + [_a(_long()) for _ in range(6)]
    compactor = Compactor(max_tokens=200, keep_recent=0.2)
    await compactor.compact(messages)
    summary = compactor.summary
    assert "prefer" in summary.lower() or "Postgres" in summary


async def test_truncating_processor():
    processor = truncating_processor(2)
    result = processor([_u("a"), _u("b"), _u("c")])
    assert len(result) == 2
    assert transcript(result).endswith("user: c")


async def test_summarize_older_note():
    processor = summarize_older(
        keep_recent=1, threshold=2, summarize=lambda old: "summary text"
    )
    result = await processor([_u("a"), _a("b"), _u("c")])
    assert isinstance(result[0].parts[0], SystemPromptPart)
    assert "summary text" in result[0].parts[0].content


async def test_compactor_state_is_per_conversation():
    """A shared Compactor must not leak rolling memory between conversations."""
    compactor = Compactor(max_tokens=200, keep_recent=0.3)
    a = [_u("My name is Ada.")] + [_u(_long()) for _ in range(4)]
    b = [_u("I prefer metric units.")] + [_u(_long()) for _ in range(4)]
    first = await compactor.compact(a, conversation_id="convo-a")
    assert compactor._states["convo-a"].folded  # state recorded for A only
    assert "convo-b" not in compactor._states

    await compactor.compact(b, conversation_id="convo-b")
    assert set(compactor._states) == {"convo-a", "convo-b"}
    # A's folded set is independent of B's.
    assert compactor._states["convo-a"].folded is not compactor._states["convo-b"].folded

    compactor.reset("convo-a")
    assert "convo-a" not in compactor._states
    assert "convo-b" in compactor._states
    assert transcript(first)  # sanity: produced output
