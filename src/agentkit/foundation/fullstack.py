"""``FullStackProvider`` — the framework "everything wired" provider.

The analog of a starter-kit ``AppServiceProvider``: ``register`` only declares
config sections; ``boot`` performs effects **only for configured layers** and
never raises when a layer is unconfigured (it logs and skips). Register it with::

    from agentkit import App, FullStackProvider

    app = App("assistant").providers([FullStackProvider])
    # or: app.fullstack()
"""

from __future__ import annotations

from typing import Any

from agentkit.foundation.config import Section
from agentkit.foundation.provider import Provider
from agentkit.logging import get_logger

__all__ = [
    "ChannelsSection",
    "FullStackProvider",
    "InteropSection",
    "LearningSection",
    "MemorySection",
    "QueueSection",
]

log = get_logger("agentkit.fullstack")


class MemorySection(Section):
    env_prefix = "AGENTKIT_MEMORY_"
    enabled: bool = True
    consolidation_cron: str = "0 3 * * *"


class LearningSection(Section):
    env_prefix = "AGENTKIT_LEARNING_"
    enabled: bool = True
    reflect_cron: str = "0 4 * * *"


class ChannelsSection(Section):
    env_prefix = "AGENTKIT_CHANNELS_"
    enabled: bool = True


class InteropSection(Section):
    env_prefix = "AGENTKIT_INTEROP_"
    enabled: bool = True


class QueueSection(Section):
    env_prefix = "AGENTKIT_QUEUE_"
    enabled: bool = False


class FullStackProvider(Provider):
    """Wires memory, channels, interop and the queue from settings/config."""

    def register(self, app: Any) -> None:
        """Declare config sections (no side effects)."""
        app.config("memory", MemorySection)
        app.config("learning", LearningSection)
        app.config("channels", ChannelsSection)
        app.config("interop", InteropSection)
        app.config("queue", QueueSection)

    def boot(self, app: Any) -> None:
        settings = app.settings
        self._hydrate_credentials(app, settings)
        self._register_memory(app, settings)
        self._register_learning(app, settings)
        self._register_channels(app, settings)
        self._register_agents(app, settings)
        self._register_interop(app, settings)
        self._register_webhooks(app, settings)

    def _hydrate_credentials(self, app: Any, settings: Any) -> None:
        """Load vault secrets into empty settings fields (vault first)."""
        if not getattr(settings, "credentials_enabled", False):
            return
        try:
            from agentkit.security.credentials import hydrate_credentials

            hydrated = hydrate_credentials(settings, app.runtime)
            if hydrated:
                log.debug("fullstack: hydrated %d credential(s)", len(hydrated))
        except Exception:  # pragma: no cover - never fatal
            log.exception("fullstack: could not hydrate credentials")

    # -- memory ---------------------------------------------------------
    def _register_memory(self, app: Any, settings: Any) -> None:
        if not getattr(settings, "memory_enabled", True):
            return
        try:
            from agentkit.consolidation import CONSOLIDATE_TASK, register_consolidate_task
            from agentkit.scheduler import TASKS

            register_consolidate_task()
            section = app.config("memory")
            cron = getattr(section, "consolidation_cron", "0 3 * * *")
            app.schedule(CONSOLIDATE_TASK, name="memory-consolidate").cron(cron)
            log.debug("fullstack: registered %s (%s)", CONSOLIDATE_TASK, CONSOLIDATE_TASK in TASKS)
        except Exception:  # pragma: no cover - never fatal
            log.exception("fullstack: could not register memory consolidation")

    # -- learning -------------------------------------------------------
    def _register_learning(self, app: Any, settings: Any) -> None:
        if not getattr(settings, "learning_enabled", True):
            return
        try:
            from agentkit.learning import LESSON_TASK, register_reflect_task
            from agentkit.scheduler import TASKS

            register_reflect_task()
            section = app.config("learning")
            cron = (
                getattr(section, "reflect_cron", None)
                or getattr(settings, "learning_reflect_cron", "0 4 * * *")
            )
            app.schedule(LESSON_TASK, name="learning-reflect").cron(cron)
            log.debug("fullstack: registered %s (%s)", LESSON_TASK, LESSON_TASK in TASKS)
        except Exception:  # pragma: no cover - never fatal
            log.exception("fullstack: could not register self-learning")

    # -- channels -------------------------------------------------------
    def _register_channels(self, app: Any, settings: Any) -> None:
        for name, configure in (
            ("telegram", self._telegram),
            ("slack", self._slack),
            ("email", self._email),
            ("discord", self._discord),
        ):
            gateway = configure(app, settings)
            if gateway is None:
                log.debug("fullstack: channel %s not configured; skipping", name)
                continue
            app.channel(name, _service_factory(gateway))
            _register_notifier_sender(app, name)

    def _register_webhooks(self, app: Any, settings: Any) -> None:
        if not getattr(settings, "webhooks_enabled", False):
            return
        try:
            from agentkit.webhooks import WebhookDispatcher

            dispatcher = WebhookDispatcher(app.runtime)
            dispatcher.subscribe(app.events)
            app._webhook_dispatcher = dispatcher
            log.debug("fullstack: outbound webhooks enabled")
        except Exception:  # pragma: no cover - never fatal
            log.exception("fullstack: could not wire webhooks")

    def _telegram(self, app: Any, settings: Any) -> Any:
        if not getattr(settings, "telegram_bot_token", None):
            return None
        from agentkit.gateways.telegram import TelegramGateway

        return TelegramGateway(app)

    def _slack(self, app: Any, settings: Any) -> Any:
        if not (getattr(settings, "slack_bot_token", None) and getattr(settings, "slack_app_token", None)):
            return None
        from agentkit.gateways.slack import SlackGateway

        return SlackGateway(app)

    def _email(self, app: Any, settings: Any) -> Any:
        if not (getattr(settings, "email_imap_host", None) and getattr(settings, "email_smtp_host", None)):
            return None
        from agentkit.gateways.email import EmailGateway

        return EmailGateway(app)

    def _discord(self, app: Any, settings: Any) -> Any:
        if not getattr(settings, "discord_bot_token", None):
            return None
        from agentkit.gateways.discord import DiscordGateway

        return DiscordGateway(app)

    # -- agents / mailbox ----------------------------------------------
    def _register_agents(self, app: Any, settings: Any) -> None:
        if not getattr(settings, "subagents_enabled", False):
            return
        try:
            from agentkit.agents.mailbox import Mailbox
            from agentkit.agents.registry import AgentRegistry

            registry = getattr(app, "_agent_registry", None) or AgentRegistry()
            mailbox = getattr(app, "_mailbox", None) or Mailbox(
                registry,
                durable=bool(getattr(settings, "mailbox_durable", False)),
                events=app.events,
            )
            app._agent_registry = registry
            app._mailbox = mailbox
            app.container.instance("agents", registry)
            app.container.instance("mailbox", mailbox)
            log.debug("fullstack: agent registry + mailbox wired")
        except Exception:  # pragma: no cover - never fatal
            log.exception("fullstack: could not wire the agent registry")

    # -- interop --------------------------------------------------------
    def _register_interop(self, app: Any, settings: Any) -> None:
        if getattr(app, "_a2a", None) is None and getattr(settings, "peers_file", None):
            try:
                from agentkit.a2a.client import build_a2a_client

                app._a2a = build_a2a_client(settings)
                log.debug("fullstack: A2A peers configured")
            except Exception:  # pragma: no cover - never fatal
                log.exception("fullstack: could not configure A2A peers")


def _service_factory(gateway: Any) -> Any:
    def factory(app: Any) -> Any:
        return gateway.service()

    return factory


def _register_notifier_sender(app: Any, name: str) -> None:
    def sender(notification: Any, *, conversation_id: str | None = None) -> str:
        text = getattr(notification, f"to_{name}", notification.content)()
        log.info("notify[%s]: %s", name, text)
        return text

    app.notifier.channel(name, sender)


def fullstack(app: Any) -> Any:
    """``app.fullstack()`` sugar: register :class:`FullStackProvider`."""
    return app.providers([FullStackProvider])
