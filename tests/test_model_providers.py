from __future__ import annotations

import pytest

import agentkit.model_providers as mp
from agentkit.config import AgentSettings, build_model
from agentkit.errors import ConfigurationError
from agentkit.routing import ModelRouter


def _settings(**overrides) -> AgentSettings:
    return AgentSettings(_env_file=None, **overrides)


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_supported_prefixes_and_custom_registration():
    prefixes = mp.supported_prefixes()
    assert {"openai", "openai-compatible", "anthropic", "google", "groq", "mistral", "ollama"} <= set(
        prefixes
    )

    previous = mp._REGISTRY.get("demo")
    try:
        mp.register_model_provider("demo", lambda model, settings: f"demo:{model}")
        assert mp.resolve_model("demo:thing", _settings()) == "demo:thing"
    finally:
        if previous is None:
            mp._REGISTRY.pop("demo", None)
        else:  # pragma: no cover - defensive
            mp._REGISTRY["demo"] = previous


def test_resolve_openai_builds_client_and_model(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

    class FakeProvider:
        def __init__(self, **kwargs):
            captured["provider"] = kwargs

    class FakeModel:
        def __init__(self, name, provider=None):
            captured["model"] = (name, provider)

    import openai
    import pydantic_ai.models.openai as pom
    import pydantic_ai.providers.openai as pop

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(pop, "OpenAIProvider", FakeProvider)
    monkeypatch.setattr(pom, "OpenAIChatModel", FakeModel)

    settings = _settings(openai_api_key="sk-test", model_timeout=12.0, model_retries=4)
    mp.resolve_model("openai:gpt-4o-mini", settings)

    assert captured["client"]["api_key"] == "sk-test"
    assert captured["client"]["timeout"] == 12.0
    assert captured["client"]["max_retries"] == 4
    assert captured["model"][0] == "gpt-4o-mini"


def test_bare_name_defaults_to_openai(monkeypatch):
    captured: dict[str, object] = {}

    class FakeModel:
        def __init__(self, name, provider=None):
            captured["name"] = name

    import openai
    import pydantic_ai.models.openai as pom
    import pydantic_ai.providers.openai as pop

    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: object())
    monkeypatch.setattr(pop, "OpenAIProvider", lambda **kw: object())
    monkeypatch.setattr(pom, "OpenAIChatModel", FakeModel)

    mp.resolve_model("gpt-4o-mini", _settings(openai_api_key="k"))
    assert captured["name"] == "gpt-4o-mini"


def test_openai_compatible_requires_base_url():
    with pytest.raises(ConfigurationError, match="OPENAI_BASE_URL"):
        mp.resolve_model("openai-compatible:llama", _settings())


def test_missing_anthropic_key_names_env_var():
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        mp.resolve_model("anthropic:claude-3-7-sonnet", _settings())


def test_unknown_prefix_lists_supported(monkeypatch):
    with pytest.raises(ConfigurationError) as excinfo:
        mp.resolve_model("zhipu:glm-4", _settings())
    message = str(excinfo.value)
    assert "zhipu" in message
    assert "supported" in message
    assert "anthropic" in message


def test_missing_model_name():
    with pytest.raises(ConfigurationError, match="model name missing"):
        mp.resolve_model("openai:", _settings())


def test_resolve_ollama_uses_base_url(monkeypatch):
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, **kwargs):
            captured["provider"] = kwargs

    class FakeModel:
        def __init__(self, name, provider=None):
            captured["model"] = name

    import pydantic_ai.models.ollama as om
    import pydantic_ai.providers.ollama as op

    monkeypatch.setattr(op, "OllamaProvider", FakeProvider)
    monkeypatch.setattr(om, "OllamaModel", FakeModel)

    mp.resolve_model("ollama:llama3", _settings(ollama_base_url="http://example:11434/v1"))
    assert captured["provider"]["base_url"] == "http://example:11434/v1"
    assert captured["model"] == "llama3"


def test_build_model_delegates_to_resolve(monkeypatch):
    monkeypatch.setattr(mp, "resolve_model", lambda name, settings: f"resolved:{name}")
    settings = _settings(model_name="anthropic:claude")
    assert build_model(settings) == "resolved:anthropic:claude"


def test_router_holds_models_from_multiple_providers(monkeypatch):
    import openai
    import pydantic_ai.models.openai as pom
    import pydantic_ai.providers.openai as pop

    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: object())
    monkeypatch.setattr(pop, "OpenAIProvider", lambda **kw: object())
    monkeypatch.setattr(pom, "OpenAIChatModel", lambda name, provider=None: {"openai": name})

    monkeypatch.setattr(mp, "_REGISTRY", {**mp._REGISTRY, "demo": lambda m, s: {"demo": m}})

    small = mp.resolve_model("openai:gpt-4o-mini", _settings(openai_api_key="k"))
    large = mp.resolve_model("demo:big", _settings())
    router = ModelRouter().route(small, when=lambda ctx: ctx == "small").otherwise(large)
    assert router.select("small") == {"openai": "gpt-4o-mini"}
    assert router.select("other") == {"demo": "big"}
