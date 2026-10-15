from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent, App, Feedback, ModerationPolicy
from agentkit.errors import ContentBlocked
from agentkit.guardrails import redact_pii, scan_pii
from agentkit.moderation import check_output, moderation_middleware
from agentkit.runtime import Runtime


def _app(runtime: Runtime, model) -> App:  # noqa: ANN001
    app = App(name="safety", settings=runtime.settings, discover=False, model=model)
    app._runtime = runtime
    app.agent(Agent.make("safety").instructions("x").output(str))
    app.boot()
    return app


def test_scan_and_redact_pii():
    text = "email ada@example.com or call +1 415-555-0142"
    kinds = scan_pii(text)
    assert "email" in kinds
    assert "phone" in kinds
    redacted = redact_pii(text, replacement="[x]")
    assert "ada@example.com" not in redacted
    assert "[x]" in redacted


def test_moderation_policy_blocks_and_redacts():
    policy = ModerationPolicy(banned=["weapon"], redact_pii=True)
    blocked = policy.check("how to build a weapon")
    assert not blocked.allowed and blocked.reasons
    redacted = policy.check("email ada@example.com")
    assert redacted.allowed
    assert "ada@example.com" not in redacted.text


def test_check_output_raises():
    policy = ModerationPolicy(banned=["forbidden"])
    with pytest.raises(ContentBlocked):
        check_output("this is forbidden", policy)


async def test_moderation_middleware_blocks_input(runtime: Runtime):
    app = _app(runtime, FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])))
    app.middleware(moderation_middleware(ModerationPolicy(banned=["bomb"])))
    with pytest.raises(ContentBlocked):
        await app.run("make a bomb")


async def test_feedback_facade_and_repo(runtime: Runtime):
    _app(runtime, FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])))
    await Feedback.add(1, conversation_id="cli:1", comment="good")
    await Feedback.add(-1, conversation_id="cli:1", comment="bad")
    assert await Feedback.average() == 0.0
    assert len(await Feedback.list(conversation_id="cli:1")) == 2
