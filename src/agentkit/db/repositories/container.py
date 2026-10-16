"""The repository container: one async session, every owner-scoped repo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from sqlmodel.ext.asyncio.session import AsyncSession

from agentkit.db.repositories.api_keys import APIKeyRepo
from agentkit.db.repositories.checkpoints import CheckpointRepo
from agentkit.db.repositories.conversations import A2ATaskRepo, ConversationRepo, MessageRepo
from agentkit.db.repositories.credentials import CredentialRepo
from agentkit.db.repositories.definitions import DefinitionRepo
from agentkit.db.repositories.eval_suites import (
    EvalDatasetRepo,
    EvalGraderRepo,
    EvalRunRepo,
)
from agentkit.db.repositories.evals import EvalCaptureRepo
from agentkit.db.repositories.feedback import FeedbackRepo
from agentkit.db.repositories.knowledge import KnowledgeRepo
from agentkit.db.repositories.learning import LearningRunRepo
from agentkit.db.repositories.memory import MemoryRepo, OwnerProfileRepo
from agentkit.db.repositories.ratelimit import RateWindowRepo
from agentkit.db.repositories.run_events import RunEventRepo
from agentkit.db.repositories.scheduling import ScheduledJobRepo
from agentkit.db.repositories.team_specs import TeamSpecRepo
from agentkit.db.repositories.usage import AuditRepo, UsageRepo
from agentkit.db.repositories.webhooks import WebhookDeliveryRepo, WebhookRepo


@dataclass
class Repositories:
    """Base container. Domain apps add their own repos (e.g. ``self.transactions``).

    Declare extra repositories with a class attribute — the base attaches them
    automatically::

        class AppRepositories(Repositories):
            repositories = {"reminders": ReminderRepo}
    """

    repositories: ClassVar[dict[str, type]] = {}

    session: AsyncSession
    owner_id: str

    def __post_init__(self) -> None:
        self.conversations = ConversationRepo(self.session, self.owner_id)
        self.messages = MessageRepo(self.session, self.owner_id)
        self.a2a = A2ATaskRepo(self.session, self.owner_id)
        self.schedules = ScheduledJobRepo(self.session, self.owner_id)
        self.team_specs = TeamSpecRepo(self.session, self.owner_id)
        self.definitions = DefinitionRepo(self.session, self.owner_id)
        self.usage = UsageRepo(self.session, self.owner_id)
        self.audit = AuditRepo(self.session, self.owner_id)
        self.memories = MemoryRepo(self.session, self.owner_id)
        self.profile = OwnerProfileRepo(self.session, self.owner_id)
        self.knowledge = KnowledgeRepo(self.session, self.owner_id)
        self.feedback = FeedbackRepo(self.session, self.owner_id)
        self.learning_runs = LearningRunRepo(self.session, self.owner_id)
        self.api_keys = APIKeyRepo(self.session, self.owner_id)
        self.credentials = CredentialRepo(self.session, self.owner_id)
        self.rate_windows = RateWindowRepo(self.session, self.owner_id)
        self.evals_capture = EvalCaptureRepo(self.session, self.owner_id)
        self.eval_datasets = EvalDatasetRepo(self.session, self.owner_id)
        self.eval_graders = EvalGraderRepo(self.session, self.owner_id)
        self.eval_runs = EvalRunRepo(self.session, self.owner_id)
        self.run_events = RunEventRepo(self.session, self.owner_id)
        self.checkpoints = CheckpointRepo(self.session, self.owner_id)
        self.webhooks = WebhookRepo(self.session, self.owner_id)
        self.webhook_deliveries = WebhookDeliveryRepo(self.session, self.owner_id)
        for attribute, repo_class in type(self).repositories.items():
            setattr(self, attribute, repo_class(self.session, self.owner_id))
        from agentkit.foundation.queue import QueueRepo

        self.queue = QueueRepo(self.session, self.owner_id)
