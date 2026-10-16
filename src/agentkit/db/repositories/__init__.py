"""Owner-scoped async repositories.

One :class:`Repositories` container bundles every repository over a single async
session. Application domain repositories subclass it::

    class AppRepositories(Repositories):
        repositories = {"reminders": ReminderRepo}

Import surface (``from agentkit.db.repositories import Repositories``) is stable;
the implementation is split by concern across the modules in this package.
"""

from __future__ import annotations

from agentkit.db.repositories.container import Repositories
from agentkit.db.repositories.conversations import A2ATaskRepo, ConversationRepo, MessageRepo
from agentkit.db.repositories.feedback import FeedbackRepo
from agentkit.db.repositories.knowledge import KnowledgeRepo
from agentkit.db.repositories.learning import LearningRunRepo
from agentkit.db.repositories.memory import MEMORY_KINDS, MemoryRepo, OwnerProfileRepo
from agentkit.db.repositories.scheduling import ScheduledJobRepo
from agentkit.db.repositories.team_specs import TeamSpecRepo
from agentkit.db.repositories.usage import AuditRepo, UsageRepo

__all__ = [
    "A2ATaskRepo",
    "AuditRepo",
    "ConversationRepo",
    "FeedbackRepo",
    "KnowledgeRepo",
    "LearningRunRepo",
    "MEMORY_KINDS",
    "MemoryRepo",
    "MessageRepo",
    "OwnerProfileRepo",
    "Repositories",
    "ScheduledJobRepo",
    "TeamSpecRepo",
    "UsageRepo",
]
