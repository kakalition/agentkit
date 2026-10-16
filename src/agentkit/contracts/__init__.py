"""Runtime-checkable Protocols — the contracts every driver implements.

One module per subsystem. Contracts hold only what a driver must provide: the
minimal method surface, expressed as :class:`typing.Protocol` so drivers need not
inherit from anything. Conformance is proven by ``isinstance(driver, Contract)``
(runtime-checkable) plus the shared tests under ``tests/contracts``.
"""

from agentkit.contracts.audio import Speech, Synthesizer, Transcriber
from agentkit.contracts.auth import AuthStrategy
from agentkit.contracts.cache import CacheContract
from agentkit.contracts.catalog import Catalog, CatalogItem
from agentkit.contracts.channels import Channel, NotificationChannel
from agentkit.contracts.checkpoint import CheckpointStore
from agentkit.contracts.codeexec import CodeExecutor
from agentkit.contracts.comms import Topology
from agentkit.contracts.computer import Computer
from agentkit.contracts.database import Dialect
from agentkit.contracts.durability import Durability
from agentkit.contracts.embeddings import EmbedderContract
from agentkit.contracts.eval_dataset import Dataset, Grader
from agentkit.contracts.evals import Reporter
from agentkit.contracts.graph import GraphExecutor
from agentkit.contracts.guardrails import Scanner
from agentkit.contracts.ingest import DocumentLoader
from agentkit.contracts.learning import Extractor, LearningSink, LearningStrategy
from agentkit.contracts.memory import MemoryStore, RecallStrategy
from agentkit.contracts.middleware import AgentMiddleware
from agentkit.contracts.observability import Tracer
from agentkit.contracts.pricing import PriceProvider
from agentkit.contracts.prompts import PromptStore
from agentkit.contracts.queue import QueueDriver
from agentkit.contracts.rag import Chunker, Reranker, Retriever
from agentkit.contracts.ratelimit import RateLimiterContract
from agentkit.contracts.realtime import RealtimeSession
from agentkit.contracts.run import RunRecorder, RunStore
from agentkit.contracts.scheduler import SchedulerDriver
from agentkit.contracts.search import SearchHit, SearchIndex
from agentkit.contracts.speaker import SpeakerStrategy
from agentkit.contracts.spec import Spec
from agentkit.contracts.storage import FileSystem
from agentkit.contracts.subagent import ContextStrategy
from agentkit.contracts.tasks import PlanningStrategy, TaskStore
from agentkit.contracts.vault import Vault

__all__ = [
    "AgentMiddleware",
    "AuthStrategy",
    "CacheContract",
    "Catalog",
    "CatalogItem",
    "Channel",
    "CheckpointStore",
    "Chunker",
    "CodeExecutor",
    "Computer",
    "ContextStrategy",
    "Dataset",
    "Dialect",
    "DocumentLoader",
    "Durability",
    "EmbedderContract",
    "Extractor",
    "FileSystem",
    "Grader",
    "GraphExecutor",
    "LearningSink",
    "LearningStrategy",
    "MemoryStore",
    "NotificationChannel",
    "PlanningStrategy",
    "PriceProvider",
    "PromptStore",
    "QueueDriver",
    "RateLimiterContract",
    "RealtimeSession",
    "RecallStrategy",
    "Reporter",
    "Reranker",
    "Retriever",
    "RunRecorder",
    "RunStore",
    "Scanner",
    "SchedulerDriver",
    "SearchHit",
    "SearchIndex",
    "SpeakerStrategy",
    "Spec",
    "Speech",
    "Synthesizer",
    "TaskStore",
    "Topology",
    "Tracer",
    "Transcriber",
    "Vault",
]

