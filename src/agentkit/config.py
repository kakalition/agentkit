"""Settings, model construction, and per-run resilience knobs.

The model layer is deliberately generic: any OpenAI-compatible endpoint works,
and timeouts/retries live on the underlying async OpenAI client.
"""

from __future__ import annotations

import contextlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentkit.posture import Posture
from agentkit.support.kinds import (
    AgentMiddlewareDriver,
    AudioDriver,
    AuthDriver,
    CacheDriver,
    CatalogDriver,
    ChannelDriver,
    CheckpointDriver,
    ChunkerDriver,
    CodeExecDriver,
    CommsDriver,
    ComputerDriver,
    ContextDriver,
    DatabaseDriver,
    DatasetDriver,
    DurabilityDriver,
    EmbeddingsDriver,
    EvalGraderDriver,
    EvalsReporterDriver,
    GraphDriver,
    GuardrailDriver,
    IngestDriver,
    LearningExtractorDriver,
    LearningSinkDriver,
    LearningStrategyDriver,
    MemoryDriver,
    NotificationChannelDriver,
    ObservabilityDriver,
    PairingDriver,
    PlanningDriver,
    PricingDriver,
    PromptsDriver,
    QueueDriverKind,
    RateLimitDriver,
    RealtimeDriver,
    RecallDriver,
    RerankerDriver,
    RetrieverDriver,
    SchedulerDriver,
    SearchDriver,
    SpeakerDriver,
    StorageDriver,
    TaskDriver,
    VaultDriver,
    VectorStoreDriver,
    WorkingMemoryDriver,
)

DEFAULT_WORKSPACE_ROOT = "~/.agentkit"


def _default_workspace_root() -> Path:
    return Path(DEFAULT_WORKSPACE_ROOT).expanduser()


class AgentSettings(BaseSettings):
    """Base settings for an agentkit application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        enable_decoding=False,
        validate_by_name=True,
    )

    # identity
    agent_name: str = "assistant"
    owner_id: str = "owner"
    owner_name: str = "Owner"

    # model / provider
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    mistral_api_key: str | None = None
    ollama_base_url: str | None = None
    openrouter_api_key: str | None = None
    azure_api_key: str | None = None
    azure_endpoint: str | None = None
    azure_api_version: str | None = None
    #: Bedrock region; AWS credentials come from the standard boto3 chain
    #: (env vars, shared config, instance role), so only the region is pinned.
    bedrock_region: str | None = None
    aws_profile: str | None = None
    deepseek_api_key: str | None = None
    together_api_key: str | None = None
    fireworks_api_key: str | None = None
    cerebras_api_key: str | None = None
    vercel_api_key: str | None = None
    model_name: str = "openai:gpt-4o-mini"
    #: ordered fallback models (``provider:model``) tried when the primary fails.
    model_fallbacks: list[str] = Field(default_factory=list)
    model_timeout: float = 60.0
    model_retries: int = 2
    usage_request_limit: int | None = None
    usage_total_tokens_limit: int | None = None

    # persona
    soul_file: str | None = None  # path to SOUL.md (default: <agent_home>/SOUL.md)

    # posture — the opinionated default layer set for ``.full()``. ``hybrid``
    # reproduces the historical behavior, so this is safe to leave at the default.
    agent_posture: Posture = Posture.HYBRID

    # working memory — thread-scoped scratch state (per conversation), opt-in.
    working_memory_enabled: bool = False
    working_memory_driver: WorkingMemoryDriver = WorkingMemoryDriver.MEMORY

    # vector store — nearest-neighbour search backend for semantic recall.
    vector_store_driver: VectorStoreDriver = VectorStoreDriver.REPOSITORY

    # memory — durable facts about the owner (name, preferences, …) the agent can
    # save and recall across conversations. Recall is semantic by default.
    memory_enabled: bool = True
    memory_driver: MemoryDriver = MemoryDriver.REPOSITORY
    memory_recall_driver: RecallDriver = RecallDriver.HYBRID
    memory_embedding_backend: EmbeddingsDriver = EmbeddingsDriver.SENTENCE_TRANSFORMERS
    memory_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    memory_embedding_device: str = "cpu"
    # optional prefixes for instruction-aware models (e.g. Qwen3/e5); empty for MiniLM
    memory_embedding_query_prompt: str = ""
    memory_embedding_document_prompt: str = ""
    # hybrid recall weights (similarity / recency / importance) + recency half-life
    memory_recall_similarity_weight: float = 0.6
    memory_recall_recency_weight: float = 0.2
    memory_recall_importance_weight: float = 0.2
    memory_recall_half_life_days: float = 30.0
    # consolidation
    memory_consolidate_duplicate_threshold: float = 0.92
    # memory nudges — every N turns, propose review-gated memories (0 = off).
    memory_nudge_every: int = 0

    # skills — discoverable ``SKILL.md`` folders the agent can load on demand.
    # ``skills_dir`` overrides the default roots (project ``./skills`` and
    # ``<agent_home>/skills``).
    skills_enabled: bool = True
    skills_dir: str | None = None

    # tool-output offload — when > 0, tool returns larger than this many tokens are
    # written to <agent_home>/artifacts/offload/ and previewed in history (0 = off).
    tool_output_offload_threshold: int = 0

    # native tools — first-class, agent-callable toolkits (see ``agentkit.toolkits``).
    # Each is opt-out: reachable capabilities stay deny-by-default (empty
    # allow-lists) and every write requires approval.
    db_tools_enabled: bool = True
    scheduler_tools_enabled: bool = True
    queue_tools_enabled: bool = True
    notification_tools_enabled: bool = True
    history_tools_enabled: bool = True
    usage_tools_enabled: bool = True
    knowledge_admin_enabled: bool = True
    skill_authoring_enabled: bool = True

    # self-learning — the reflect -> learn -> apply loop (see ``agentkit.learning``).
    learning_enabled: bool = True
    learning_reflect_cron: str = "0 4 * * *"
    learning_window: int = 20
    learning_skill_threshold: int = 3
    learning_auto_skills: bool = False
    learning_max_lessons: int = 50
    # when true, lessons are stored ``proposed`` until approved (review inbox).
    # Review-gated by default: self-learning must not silently drift behavior.
    learning_require_review: bool = True
    # optional: gate learning on captured evals passing (see ``agentkit.evals``).
    learning_eval_gate: bool = False
    # driver selection for the learning subsystem (see ``agentkit.support.Manager``).
    learning_extractor_driver: LearningExtractorDriver = LearningExtractorDriver.MODEL
    learning_strategy_driver: LearningStrategyDriver = LearningStrategyDriver.REFLECT_APPLY
    learning_sink_driver: LearningSinkDriver = LearningSinkDriver.MEMORY

    # auth — opt-in. ``auth_enabled=False`` (default) keeps the local single-operator
    # behavior: every request runs as the settings owner with no roles. When enabled
    # requests must present an API key or a JWT (fail-closed).
    auth_enabled: bool = False
    auth_api_keys: Any = None  # JSON object or "name:key:owner:role|role;..." CSV
    auth_jwks_url: str | None = None
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_algorithms: str = "RS256"
    auth_owner_claim: str = "sub"
    auth_roles_claim: str = "roles"
    auth_default_owner: str = ""
    auth_required_roles: list[str] = Field(default_factory=list)
    auth_jwks_cache_ttl: float = 300.0
    auth_jwks_timeout: float = 10.0

    # metrics — Prometheus exposition at ``metrics_path`` (opt-in).
    metrics_enabled: bool = False
    metrics_path: str = "/metrics"

    # interfaces — OpenAI-compatible API and outbound webhooks (opt-in).
    openai_api_enabled: bool = False
    webhooks_enabled: bool = False

    # data lifecycle — export is safe; forget is destructive and opt-in.
    data_export_enabled: bool = True
    data_forget_enabled: bool = False

    # ingestion — guards for file/URL ingestion into the knowledge base.
    ingest_max_bytes: int = 5_000_000
    ingest_allowed_schemes: list[str] = Field(default_factory=lambda: ["http", "https"])

    # rate limiting — opt-in fixed-window limiter at the HTTP boundary (+ per-tool).
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 60
    rate_limit_tool_per_minute: int = 0  # 0 = no per-tool limit
    rate_limit_burst: int = 0

    # credentials vault — encrypt channel/provider secrets at rest (Fernet).
    credentials_enabled: bool = False
    credentials_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AGENTKIT_CREDENTIALS_KEY", "CREDENTIALS_KEY"),
    )

    # guardrails — scan tool results for prompt injection (opt-in) and optionally
    # wrap results from untrusted sources (web/MCP/A2A) so the model treats them as data.
    guardrails_enabled: bool = False
    guardrails_wrap_untrusted: bool = False

    # human-in-the-loop approvals
    approvals_enabled: bool = True
    # route approvals through the in-process queue so a UI can decide them.
    approval_ui_enabled: bool = False
    # multi-agent: peer tools (send_to/ask_agent/broadcast/handoff_to)
    subagents_enabled: bool = False
    mailbox_durable: bool = False
    max_handoffs: int = 3

    # prompts — a file-backed prompt registry (``prompts/<name>.md``).
    prompts_dir: str | None = None

    # queue — when enabled, ``app.dispatch(job)`` pushes to the DB queue and a
    # worker (``agentkit queue:work``) processes it; otherwise jobs run inline.
    queue_enabled: bool = False
    queue_default: str = "default"

    # drivers — pluggable implementations selected per subsystem (see
    # ``agentkit.support.Manager``). Existing classes are the default drivers.
    cache_driver: CacheDriver = CacheDriver.ARRAY
    prompts_driver: PromptsDriver = PromptsDriver.FILE
    pricing_driver: PricingDriver = PricingDriver.GENAI
    ingest_driver: IngestDriver = IngestDriver.DEFAULT
    audio_driver: AudioDriver = AudioDriver.OPENAI
    database_driver: DatabaseDriver = DatabaseDriver.SQLITE
    queue_driver: QueueDriverKind = QueueDriverKind.DATABASE
    scheduler_driver: SchedulerDriver = SchedulerDriver.DBOS
    search_driver: SearchDriver = SearchDriver.FTS
    storage_driver: StorageDriver = StorageDriver.LOCAL
    rate_limit_driver: RateLimitDriver = RateLimitDriver.DATABASE
    durability_driver: DurabilityDriver = DurabilityDriver.DBOS
    # Temporal connection (``durability_driver=temporal``; needs the ``temporal`` extra)
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "agentkit"
    auth_driver: AuthDriver = AuthDriver.DEFAULT
    vault_driver: VaultDriver = VaultDriver.FERNET
    guardrails_driver: GuardrailDriver = GuardrailDriver.REGEX
    chunker_driver: ChunkerDriver = ChunkerDriver.SEMANTIC
    retriever_driver: RetrieverDriver = RetrieverDriver.REPOSITORY
    reranker_driver: RerankerDriver = RerankerDriver.IDENTITY
    comms_driver: CommsDriver = CommsDriver.MAILBOX
    speaker_driver: SpeakerDriver = SpeakerDriver.ROUND_ROBIN
    tasks_driver: TaskDriver = TaskDriver.MEMORY
    planning_driver: PlanningDriver = PlanningDriver.SINGLE
    context_driver: ContextDriver = ContextDriver.ISOLATED
    agent_middleware_driver: AgentMiddlewareDriver = AgentMiddlewareDriver.NOOP
    graph_driver: GraphDriver = GraphDriver.SEQUENTIAL
    code_executor_driver: CodeExecDriver = CodeExecDriver.LOCAL
    evals_reporter_driver: EvalsReporterDriver = EvalsReporterDriver.TEXT
    channel_driver: ChannelDriver = ChannelDriver.LOG
    notification_channel_driver: NotificationChannelDriver = NotificationChannelDriver.LOG
    checkpoint_driver: CheckpointDriver = CheckpointDriver.REPOSITORY
    computer_driver: ComputerDriver = ComputerDriver.LOOPBACK
    realtime_driver: RealtimeDriver = RealtimeDriver.LOOPBACK
    catalog_driver: CatalogDriver = CatalogDriver.LOCAL
    dataset_driver: DatasetDriver = DatasetDriver.REPOSITORY
    eval_grader_driver: EvalGraderDriver = EvalGraderDriver.EXACT
    # gateway DM pairing — in-memory by default; ``repository`` persists pairings.
    pairing_driver: PairingDriver = PairingDriver.MEMORY
    # online scoring — grade live run traces with a registered grader (opt-in).
    online_scoring_enabled: bool = False
    online_scoring_grader: str = "trace"

    # run tracing — uniform RunEvents for the Playground + trace grading. Cheap
    # (in-memory buffered) and flushed to the ``run_events`` table when enabled.
    run_trace_enabled: bool = True
    run_events_retention: int = 2000

    # checkpoints — time travel over graph/session runs (opt-in; bounded retention).
    checkpoints_enabled: bool = False
    checkpoint_retention: int = 50

    # computer-use / realtime / catalog (see the corresponding driver kinds)
    computer_headless: bool = True
    computer_timeout_ms: int = 30_000
    realtime_model: str | None = None
    catalog_dir: str | None = None
    catalog_url: str | None = None
    catalog_repo: str | None = None
    catalog_ref: str = "main"
    catalog_path: str = "catalog.json"

    # chat channels — extra gateways + DM pairing
    mattermost_webhook_url: str | None = None
    mattermost_base_url: str | None = None
    mattermost_token: str | None = None
    linear_api_key: str | None = None
    webhook_url: str | None = None
    channel_pairing_enabled: bool = False

    # remote code execution (optional drivers)
    ssh_host: str | None = None
    singularity_image: str = "python:3.12-slim"

    # S3 filesystem (``storage_driver=s3``; needs the ``s3`` extra)
    s3_bucket: str | None = None
    s3_prefix: str = ""
    s3_region: str | None = None
    s3_endpoint_url: str | None = None

    # storage — agents live under ``workspace_root``; ``agent_home`` defaults to
    # ``workspace_root/<agent_name>`` and can be overridden with ``AGENT_HOME``.
    workspace_root: Path = Field(
        default_factory=_default_workspace_root,
        validation_alias=AliasChoices("AGENTKIT_WORKSPACE_ROOT", "AGENTKIT_HOME"),
    )
    agent_home: Path | None = None
    database_url: str | None = None
    libsql_auth_token: str | None = None

    # operator web UI, served by the agent process itself (loopback only)
    webui_enabled: bool = True
    webui_host: str = "127.0.0.1"
    webui_port: int = 8787

    # observability — on by default with a local Phoenix UI (self-hosted, no account)
    observability: ObservabilityDriver = ObservabilityDriver.PHOENIX
    otlp_endpoint: str | None = None
    log_level: str = "INFO"
    log_json: bool = False

    # channels / protocols
    telegram_bot_token: str | None = None
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)
    # turn UX — acknowledge the message with a reaction and keep an ever-changing
    # status line alive while the model works (both toggleable).
    telegram_seen_reaction: bool = True
    telegram_live_status: bool = True
    telegram_typing_action: bool = True
    telegram_status_interval_s: float = 2.5
    # Slack (socket mode; needs the ``slack`` extra)
    slack_bot_token: str | None = None
    slack_app_token: str | None = None
    slack_allowed_channel_ids: list[str] = Field(default_factory=list)
    # Discord (needs the ``discord`` extra)
    discord_bot_token: str | None = None
    discord_allowed_guild_ids: list[int] = Field(default_factory=list)
    # Email (stdlib only: imaplib/smtplib)
    email_imap_host: str | None = None
    email_imap_port: int = 993
    email_imap_user: str | None = None
    email_imap_password: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_from: str | None = None
    email_poll_interval_s: float = 30.0
    email_allowed_senders: list[str] = Field(default_factory=list)
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

    @field_validator(
        "slack_allowed_channel_ids",
        "email_allowed_senders",
        "auth_required_roles",
        "ingest_allowed_schemes",
        mode="before",
    )
    @classmethod
    def _split_string_ids(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part for part in value.replace(",", " ").split() if part]
        return value

    @field_validator("discord_allowed_guild_ids", mode="before")
    @classmethod
    def _split_guild_ids(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(part) for part in value.replace(",", " ").split() if part]
        return value

    @field_validator("agent_home", "workspace_root", mode="before")
    @classmethod
    def _expand(cls, value: object) -> object:
        return Path(value).expanduser() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _resolve_agent_home(self) -> AgentSettings:
        if self.agent_home is None:
            self.agent_home = self.workspace_root / self.agent_name
        return self

    # derived
    @property
    def home(self) -> Path:
        """The resolved agent home (``agent_home`` or ``workspace_root/agent_name``)."""
        if self.agent_home is None:  # pragma: no cover - set by the model validator
            raise RuntimeError("agent_home was not resolved")
        return self.agent_home

    @property
    def db_path(self) -> Path:
        return self.home / "agent.db"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+libsql:///{self.db_path}"

    @property
    def artifacts_dir(self) -> Path:
        return self.home / "artifacts"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings()


def build_model(settings: AgentSettings | None = None):
    """Build the PydanticAI model for ``settings.model_name`` (``provider:model``).

    A thin wrapper over :func:`agentkit.model_providers.resolve_model`, which
    dispatches on the provider prefix (openai, anthropic, google, groq, mistral,
    ollama, and any registered provider). When ``model_fallbacks`` is set, the
    primary is wrapped in a PydanticAI ``FallbackModel`` tried in order.
    """
    from agentkit.model_providers import resolve_model

    settings = settings or get_settings()
    primary = resolve_model(settings.model_name, settings)
    fallbacks = [str(name) for name in (getattr(settings, "model_fallbacks", None) or []) if name]
    if not fallbacks:
        return primary
    models = [primary]
    for name in fallbacks:
        with contextlib.suppress(Exception):
            models.append(resolve_model(name, settings))
    if len(models) < 2:
        return primary
    from pydantic_ai.models.fallback import FallbackModel

    try:
        return FallbackModel(*models)
    except Exception:  # pragma: no cover - defensive
        return primary


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
