"""Typed driver identifiers — no string constants.

Every subsystem *kind* and every driver *name* is a :class:`enum.StrEnum`, so
registration, selection, and settings are checked by the type system (and by
pydantic at settings load) instead of by convention.

    class CacheManager(Manager):
        kind = DriverKind.CACHE
        default_driver = CacheDriver.ARRAY

    @register_driver(DriverKind.CACHE, CacheDriver.NULL)
    def _null(app): ...

Because ``StrEnum`` members *are* strings, ``CacheDriver.ARRAY == "array"`` and
``f"{CacheDriver.ARRAY}" == "array"``, so existing settings/env values keep
working while the code gains real types.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AgentMiddlewareDriver",
    "AudioDriver",
    "AuthDriver",
    "CacheDriver",
    "CatalogDriver",
    "ChannelDriver",
    "CheckpointDriver",
    "ChunkerDriver",
    "CodeExecDriver",
    "CommsDriver",
    "ComputerDriver",
    "ContextDriver",
    "DatabaseDriver",
    "DatasetDriver",
    "DriverKind",
    "DurabilityDriver",
    "EmbeddingsDriver",
    "EvalGraderDriver",
    "EvalsReporterDriver",
    "GraphDriver",
    "GuardrailDriver",
    "IngestDriver",
    "LearningExtractorDriver",
    "LearningSinkDriver",
    "LearningStrategyDriver",
    "MemoryDriver",
    "NotificationChannelDriver",
    "ObservabilityDriver",
    "PlanningDriver",
    "PricingDriver",
    "PromptsDriver",
    "QueueDriverKind",
    "RateLimitDriver",
    "RealtimeDriver",
    "RecallDriver",
    "RerankerDriver",
    "RetrieverDriver",
    "SchedulerDriver",
    "SearchDriver",
    "SpeakerDriver",
    "StorageDriver",
    "TaskDriver",
    "VaultDriver",
]


class DriverKind(StrEnum):
    """The subsystem a driver belongs to (the registry key prefix)."""

    AGENT_MIDDLEWARE = "agent_middleware"
    AUDIO = "audio"
    AUTH = "auth"
    CACHE = "cache"
    CATALOG = "catalog"
    CHANNEL = "channel"
    CHECKPOINT = "checkpoint"
    CHUNKER = "chunker"
    CODEEXEC = "codeexec"
    COMMS = "comms"
    COMPUTER = "computer"
    CONTEXT = "context"
    DATABASE = "database"
    DATASET = "dataset"
    DURABILITY = "durability"
    EMBEDDINGS = "embeddings"
    EVAL_GRADER = "eval_grader"
    EVALS_REPORTER = "evals_reporter"
    GRAPH = "graph"
    GUARDRAILS = "guardrails"
    INGEST = "ingest"
    LEARNING_EXTRACTOR = "learning_extractor"
    LEARNING_SINK = "learning_sink"
    LEARNING_STRATEGY = "learning_strategy"
    MEMORY = "memory"
    MEMORY_RECALL = "memory_recall"
    NOTIFICATION_CHANNEL = "notification_channel"
    OBSERVABILITY = "observability"
    PLANNING = "planning"
    PRICING = "pricing"
    PROMPTS = "prompts"
    QUEUE = "queue"
    RATELIMIT = "ratelimit"
    REALTIME = "realtime"
    RERANKER = "reranker"
    RETRIEVER = "retriever"
    SCHEDULER = "scheduler"
    SEARCH = "search"
    SPEAKER = "speaker"
    STORAGE = "storage"
    TASKS = "tasks"
    VAULT = "vault"


class CacheDriver(StrEnum):
    ARRAY = "array"
    NULL = "null"


class PromptsDriver(StrEnum):
    FILE = "file"
    MEMORY = "memory"


class EmbeddingsDriver(StrEnum):
    SENTENCE_TRANSFORMERS = "sentence-transformers"
    FASTEMBED = "fastembed"
    HASH = "hash"
    NONE = "none"


class MemoryDriver(StrEnum):
    REPOSITORY = "repository"
    IN_MEMORY = "in_memory"


class RecallDriver(StrEnum):
    HYBRID = "hybrid"
    KEYWORD = "keyword"
    RECENCY = "recency"


class ChunkerDriver(StrEnum):
    SEMANTIC = "semantic"
    FIXED = "fixed"


class RetrieverDriver(StrEnum):
    REPOSITORY = "repository"
    MEMORY = "memory"


class RerankerDriver(StrEnum):
    IDENTITY = "identity"
    LEXICAL = "lexical"


class StorageDriver(StrEnum):
    LOCAL = "local"
    MEMORY = "memory"
    S3 = "s3"


class QueueDriverKind(StrEnum):
    DATABASE = "database"
    SYNC = "sync"


class SchedulerDriver(StrEnum):
    DBOS = "dbos"
    MEMORY = "memory"


class SearchDriver(StrEnum):
    FTS = "fts"
    SCAN = "scan"


class SpeakerDriver(StrEnum):
    ROUND_ROBIN = "round_robin"
    MODERATOR = "moderator"
    ALL = "all"
    SELECTOR = "selector"
    MANUAL = "manual"


class DurabilityDriver(StrEnum):
    DBOS = "dbos"
    TEMPORAL = "temporal"


class DatabaseDriver(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class ObservabilityDriver(StrEnum):
    PHOENIX = "phoenix"
    CONSOLE = "console"
    OTLP = "otlp"
    OFF = "off"


class PricingDriver(StrEnum):
    GENAI = "genai"
    STATIC = "static"


class RateLimitDriver(StrEnum):
    DATABASE = "database"
    MEMORY = "memory"


class AuthDriver(StrEnum):
    DEFAULT = "default"
    ANONYMOUS = "anonymous"


class VaultDriver(StrEnum):
    FERNET = "fernet"
    ENV = "env"


class GuardrailDriver(StrEnum):
    REGEX = "regex"
    MODERATION = "moderation"


class IngestDriver(StrEnum):
    DEFAULT = "default"
    TEXT = "text"


class AudioDriver(StrEnum):
    OPENAI = "openai"


class LearningExtractorDriver(StrEnum):
    MODEL = "model"
    HEURISTIC = "heuristic"


class LearningStrategyDriver(StrEnum):
    REFLECT_APPLY = "reflect_apply"
    NONE = "none"


class LearningSinkDriver(StrEnum):
    MEMORY = "memory"


class CommsDriver(StrEnum):
    MAILBOX = "mailbox"
    BROADCAST = "broadcast"
    SWARM = "swarm"
    PIPELINE = "pipeline"
    HANDOFF = "handoff"
    HUB = "hub"
    MESH = "mesh"
    HIERARCHY = "hierarchy"
    OUTBOX = "outbox"
    BLACKBOARD = "blackboard"
    PUBSUB = "pubsub"
    GROUPCHAT = "groupchat"


class ContextDriver(StrEnum):
    ISOLATED = "isolated"
    SHARED = "shared"
    SUMMARIZED = "summarized"


class TaskDriver(StrEnum):
    MEMORY = "memory"


class PlanningDriver(StrEnum):
    SINGLE = "single"
    BATCHED = "batched"


class AgentMiddlewareDriver(StrEnum):
    NOOP = "noop"
    LOGGING = "logging"


class GraphDriver(StrEnum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CHECKPOINTED = "checkpointed"


class CodeExecDriver(StrEnum):
    LOCAL = "local"
    DOCKER = "docker"
    JUPYTER = "jupyter"
    E2B = "e2b"
    SSH = "ssh"
    MODAL = "modal"
    DAYTONA = "daytona"
    VERCEL = "vercel"
    SINGULARITY = "singularity"


class EvalsReporterDriver(StrEnum):
    TEXT = "text"
    JSON = "json"
    PYDANTIC = "pydantic"


class ChannelDriver(StrEnum):
    LOG = "log"
    TELEGRAM = "telegram"
    SLACK = "slack"
    EMAIL = "email"
    DISCORD = "discord"
    MATTERMOST = "mattermost"
    LINEAR = "linear"
    WEBHOOK = "webhook"


class NotificationChannelDriver(StrEnum):
    LOG = "log"
    CONVERSATION = "conversation"
    TELEGRAM = "telegram"


class CheckpointDriver(StrEnum):
    MEMORY = "memory"
    REPOSITORY = "repository"
    FILE = "file"


class ComputerDriver(StrEnum):
    LOOPBACK = "loopback"
    PLAYWRIGHT = "playwright"


class RealtimeDriver(StrEnum):
    LOOPBACK = "loopback"
    PYDANTIC_AI = "pydantic_ai"


class CatalogDriver(StrEnum):
    LOCAL = "local"
    SKILLS = "skills"
    GIT = "git"
    HTTP = "http"


class DatasetDriver(StrEnum):
    MEMORY = "memory"
    REPOSITORY = "repository"


class EvalGraderDriver(StrEnum):
    EXACT = "exact"
    CONTAINS = "contains"
    SCHEMA = "schema"
    LLM_JUDGE = "llm_judge"
