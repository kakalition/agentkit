"""Settings, model construction, and per-run resilience knobs.

The model layer is deliberately generic: any OpenAI-compatible endpoint works,
and timeouts/retries live on the underlying async OpenAI client.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_home() -> Path:
    return Path("~/.local/share/agentkit").expanduser()


class AgentSettings(BaseSettings):
    """Base settings for an agentkit application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        enable_decoding=False,
    )

    # identity
    agent_name: str = "assistant"
    owner_id: str = "owner"
    owner_name: str = "Owner"

    # model / provider
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    model_name: str = "openai:gpt-4o-mini"
    model_timeout: float = 60.0
    model_retries: int = 2
    usage_request_limit: int | None = None
    usage_total_tokens_limit: int | None = None

    # storage
    agent_home: Path = Field(default_factory=_default_home)
    database_url: str | None = None
    libsql_auth_token: str | None = None

    # observability
    observability: str = "off"
    logfire_token: str | None = None
    otlp_endpoint: str | None = None
    log_level: str = "INFO"

    # channels / protocols
    telegram_bot_token: str | None = None
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)
    a2a_public_url: str = "http://127.0.0.1:9000"
    a2a_card_name: str = "Agent"
    a2a_host: str = "127.0.0.1"
    a2a_port: int = 9000
    peers_file: str | None = None
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8765

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(part) for part in value.replace(",", " ").split() if part]
        return value

    @field_validator("agent_home", mode="before")
    @classmethod
    def _expand(cls, value: object) -> object:
        return Path(value).expanduser() if isinstance(value, str) else value

    # derived
    @property
    def db_path(self) -> Path:
        return self.agent_home / "agent.db"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+libsql:///{self.db_path}"

    @property
    def artifacts_dir(self) -> Path:
        return self.agent_home / "artifacts"

    def ensure_dirs(self) -> None:
        self.agent_home.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings()


def build_model(settings: AgentSettings | None = None):
    """Build the PydanticAI model with transport timeout and retries."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = settings or get_settings()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.model_timeout,
        max_retries=settings.model_retries,
    )
    provider = OpenAIProvider(openai_client=client)
    model_name = settings.model_name
    if model_name.startswith("openai:"):
        model_name = model_name.split(":", 1)[1]
    return OpenAIChatModel(model_name, provider=provider)


def model_settings(settings: AgentSettings | None = None):
    """Per-request model settings (timeout)."""
    from pydantic_ai.settings import ModelSettings

    settings = settings or get_settings()
    return ModelSettings(timeout=settings.model_timeout)


def usage_limits(settings: AgentSettings | None = None):
    """Per-run usage caps, or ``None`` when unlimited."""
    from pydantic_ai.usage import UsageLimits

    settings = settings or get_settings()
    if settings.usage_request_limit is None and settings.usage_total_tokens_limit is None:
        return None
    return UsageLimits(
        request_limit=settings.usage_request_limit,
        total_tokens_limit=settings.usage_total_tokens_limit,
    )
