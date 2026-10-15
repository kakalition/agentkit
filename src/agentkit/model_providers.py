"""Multi-provider model registry.

``MODEL_NAME`` is ``provider:model`` (e.g. ``anthropic:claude-3-7-sonnet``).
:func:`resolve_model` dispatches on the prefix to the matching PydanticAI
provider/model; :func:`register_model_provider` lets an application add its own
prefix::

    from agentkit.model_providers import register_model_provider, resolve_model

    register_model_provider("my-provider", lambda model, settings: MyModel(model))
    model = resolve_model("my-provider:foo", settings)

Built-in prefixes: ``openai``, ``openai-compatible``, ``anthropic``, ``google``,
``groq``, ``mistral``, ``ollama``. A missing provider key raises
:class:`~agentkit.errors.ConfigurationError` naming the env var; an unknown
prefix raises it naming the supported set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentkit.errors import ConfigurationError

__all__ = [
    "register_model_provider",
    "resolve_model",
    "supported_prefixes",
]

ModelFactory = Callable[[str, Any], Any]
_REGISTRY: dict[str, ModelFactory] = {}


def register_model_provider(prefix: str, factory: ModelFactory) -> None:
    """Register (or replace) the factory for a ``MODEL_NAME`` prefix."""
    _REGISTRY[prefix] = factory


def supported_prefixes() -> list[str]:
    return sorted(_REGISTRY)


def _split(name: str) -> tuple[str, str]:
    prefix, sep, model = (name or "").partition(":")
    if not sep:
        return "openai", prefix.strip()
    return prefix.strip().lower(), model.strip()


def _require_key(settings: Any, attribute: str, env_var: str) -> str:
    value = getattr(settings, attribute, None)
    if not value:
        raise ConfigurationError(
            f"missing {env_var} for the selected model provider (set {env_var} in the environment)"
        )
    return str(value)


# -- built-in factories -----------------------------------------------------


def _openai(model: str, settings: Any) -> Any:
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.model_timeout,
        max_retries=settings.model_retries,
    )
    return OpenAIChatModel(model, provider=OpenAIProvider(openai_client=client))


def _openai_compatible(model: str, settings: Any) -> Any:
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if not settings.openai_base_url:
        raise ConfigurationError(
            "missing OPENAI_BASE_URL for the openai-compatible provider"
        )
    client = AsyncOpenAI(
        api_key=settings.openai_api_key or "not-needed",
        base_url=settings.openai_base_url,
        timeout=settings.model_timeout,
        max_retries=settings.model_retries,
    )
    return OpenAIChatModel(model, provider=OpenAIProvider(openai_client=client))


def _anthropic(model: str, settings: Any) -> Any:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    api_key = _require_key(settings, "anthropic_api_key", "ANTHROPIC_API_KEY")
    return AnthropicModel(model, provider=AnthropicProvider(api_key=api_key))


def _google(model: str, settings: Any) -> Any:
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    api_key = _require_key(settings, "google_api_key", "GOOGLE_API_KEY")
    return GoogleModel(model, provider=GoogleProvider(api_key=api_key))


def _groq(model: str, settings: Any) -> Any:
    try:
        from pydantic_ai.models.groq import GroqModel
        from pydantic_ai.providers.groq import GroqProvider
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ConfigurationError(
            "the groq provider needs the 'groq' package (pip install agentkit[groq])"
        ) from exc
    api_key = _require_key(settings, "groq_api_key", "GROQ_API_KEY")
    return GroqModel(model, provider=GroqProvider(api_key=api_key))


def _mistral(model: str, settings: Any) -> Any:
    try:
        from pydantic_ai.models.mistral import MistralModel
        from pydantic_ai.providers.mistral import MistralProvider
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ConfigurationError(
            "the mistral provider needs the 'mistralai' package (pip install agentkit[mistral])"
        ) from exc
    api_key = _require_key(settings, "mistral_api_key", "MISTRAL_API_KEY")
    return MistralModel(model, provider=MistralProvider(api_key=api_key))


def _ollama(model: str, settings: Any) -> Any:
    from pydantic_ai.models.ollama import OllamaModel
    from pydantic_ai.providers.ollama import OllamaProvider

    base_url = settings.ollama_base_url or "http://localhost:11434/v1"
    return OllamaModel(model, provider=OllamaProvider(base_url=base_url))


register_model_provider("openai", _openai)
register_model_provider("openai-compatible", _openai_compatible)
register_model_provider("anthropic", _anthropic)
register_model_provider("google", _google)
register_model_provider("groq", _groq)
register_model_provider("mistral", _mistral)
register_model_provider("ollama", _ollama)


def resolve_model(name: str, settings: Any = None) -> Any:
    """Build the PydanticAI model named by ``provider:model`` (or a bare model)."""
    if settings is None:
        from agentkit.config import get_settings

        settings = get_settings()
    prefix, model = _split(name)
    factory = _REGISTRY.get(prefix)
    if factory is None:
        raise ConfigurationError(
            f"unknown model provider prefix {prefix!r} in {name!r}; "
            f"supported: {', '.join(supported_prefixes())}"
        )
    if not model:
        raise ConfigurationError(f"model name missing in {name!r} (expected 'provider:model')")
    return factory(model, settings)
