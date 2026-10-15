"""Channel drivers: the built-in gateways as selectable ``channel`` drivers.

``log`` is the safe default (it writes to the structured log); ``telegram``,
``slack``, ``email`` and ``discord`` wrap the concrete gateways. Select with
``channel_driver`` or register your own with ``app.extend("channel", …)``.
"""

from __future__ import annotations

from typing import Any

from agentkit.gateways.base import Gateway
from agentkit.logging import get_logger
from agentkit.support import register_driver
from agentkit.support.kinds import ChannelDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = ["ChannelManager", "LogChannel"]


class LogChannel(Gateway):
    """The default channel: log every outbound message, deliver nothing."""

    name = "log"

    async def start(self) -> None:
        return None

    async def send(self, conversation_id: str, text: str) -> None:
        get_logger("agentkit.channels").info("[%s] %s", conversation_id, text)


class ChannelManager(Manager):
    """Resolves the configured chat channel (``channel_driver``, default ``log``)."""

    kind = DriverKind.CHANNEL
    default_driver = ChannelDriver.LOG


@register_driver(DriverKind.CHANNEL, ChannelDriver.LOG)
def _log_channel_driver(app: Any) -> LogChannel:
    return LogChannel(app, settings=getattr(app, "settings", None))


@register_driver(DriverKind.CHANNEL, ChannelDriver.TELEGRAM)
def _telegram_channel_driver(app: Any) -> Any:
    from agentkit.gateways.telegram import TelegramGateway

    return TelegramGateway(app, settings=getattr(app, "settings", None))


@register_driver(DriverKind.CHANNEL, ChannelDriver.SLACK)
def _slack_channel_driver(app: Any) -> Any:
    from agentkit.gateways.slack import SlackGateway

    return SlackGateway(app, settings=getattr(app, "settings", None))


@register_driver(DriverKind.CHANNEL, ChannelDriver.EMAIL)
def _email_channel_driver(app: Any) -> Any:
    from agentkit.gateways.email import EmailGateway

    return EmailGateway(app, settings=getattr(app, "settings", None))


@register_driver(DriverKind.CHANNEL, ChannelDriver.DISCORD)
def _discord_channel_driver(app: Any) -> Any:
    from agentkit.gateways.discord import DiscordGateway

    return DiscordGateway(app, settings=getattr(app, "settings", None))
