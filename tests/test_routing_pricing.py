from __future__ import annotations

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from agentkit import Agent, App, ModelPrice, ModelRouter, Pricing, default_pricing


def test_pricing_cost_and_normalization():
    pricing = Pricing()
    pricing.set("openai:gpt-4o-mini", input=0.001, output=0.002)
    assert pricing.cost("gpt-4o-mini", input_tokens=1000, output_tokens=1000) == 0.003
    # provider prefix is ignored on both set and get
    assert pricing.cost("openai:gpt-4o-mini", input_tokens=1000) == 0.001
    pricing.set("custom", ModelPrice(0.5, 1.0))
    assert pricing.cost("custom", input_tokens=2000, output_tokens=1000) == 2.0


def test_pricing_longest_match_prefers_specific_model():
    pricing = Pricing()
    pricing.set("gpt-4o", input=1.0)
    pricing.set("gpt-4o-mini", input=0.1)
    assert pricing.get("gpt-4o-mini").input_per_1k == 0.1


def test_default_pricing_has_known_models():
    assert default_pricing().cost("openai:gpt-4o-mini", input_tokens=1000) > 0


def test_model_router_selects_by_predicate():
    a, b = object(), object()
    router = (
        ModelRouter()
        .route(a, when=lambda ctx: ctx is not None and ctx == "short")
        .route(b)
        .otherwise("fallback")
    )
    assert router.select("short") is a
    assert router.select("long") is b
    empty = ModelRouter().otherwise("d")
    assert empty.select() == "d"
    assert empty("anything") == "d"


def test_model_router_with_fallbacks_returns_a_model():
    def fn(m, i):  # noqa: ANN001
        return ModelResponse(parts=[TextPart("ok")])

    primary = FunctionModel(fn)
    router = ModelRouter(primary).with_fallbacks(FunctionModel(fn))
    selected = router.select()
    assert selected is not None


async def test_app_model_resolver_receives_turn_context(runtime):
    seen = []

    def resolver(context):
        seen.append(context)
        return FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("routed")]))

    app = App(name="route", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.agent(Agent.make("route").instructions("x").output(str))
    app.model_resolver(resolver)
    app.boot()

    result = await app.run("hello")
    assert result.output == "routed"
    assert seen and seen[0].text == "hello"
    assert seen[0].conversation_id == "cli:default"
