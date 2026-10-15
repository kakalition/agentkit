"""Email gateway using only the standard library (``imaplib``/``smtplib``).

Inbound mail is polled over IMAP and replies are sent over SMTP. A thread is
keyed by ``Message-ID``/``References`` so a reply stays in the same conversation.
Settings: ``email_imap_host/port/user/password``, ``email_smtp_host/port``,
``email_from``, ``email_poll_interval_s``, ``email_allowed_senders``.
"""

from __future__ import annotations

import asyncio
import contextlib
import email
from collections.abc import Callable, Sequence
from email.message import Message as EmailMessage
from email.utils import parseaddr
from typing import Any

from agentkit.gateways.base import Gateway, GatewayError

__all__ = ["EmailGateway", "parse_message"]


def _body_of(message: EmailMessage) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        return ""
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(message.get_content_charset() or "utf-8", errors="ignore")
    return str(message.get_payload() or "")


def parse_message(raw: bytes) -> dict[str, str]:
    """Parse a raw RFC822 message into ``{sender, subject, body, message_id, references}``."""
    message = email.message_from_bytes(raw)
    sender = parseaddr(message.get("From", ""))[1]
    return {
        "sender": sender,
        "subject": message.get("Subject", "") or "",
        "body": _body_of(message).strip(),
        "message_id": (message.get("Message-ID") or "").strip(),
        "references": (message.get("References") or "").strip(),
    }


class EmailGateway(Gateway):
    name = "email"

    def __init__(
        self,
        app: Any = None,
        *,
        settings: Any = None,
        imap_factory: Callable[[], Any] | None = None,
        smtp_factory: Callable[[], Any] | None = None,
        fetcher: Callable[[], list[dict[str, str]]] | None = None,
        allowed_senders: Sequence[str] | None = None,
        **kwargs: Any,
    ) -> None:
        settings = settings if settings is not None else getattr(app, "settings", None)
        if allowed_senders is None:
            allowed_senders = getattr(settings, "email_allowed_senders", []) or []
        super().__init__(
            app, settings=settings, allowed_channel_ids=allowed_senders, **kwargs
        )
        self._imap_factory = imap_factory
        self._smtp_factory = smtp_factory
        self._fetcher = fetcher
        self._recipients: dict[str, str] = {}
        self.poll_interval_s = float(getattr(settings, "email_poll_interval_s", 30.0) or 30.0)

    # -- transports -----------------------------------------------------
    def _imap(self) -> Any:
        import imaplib

        host = getattr(self.settings, "email_imap_host", None)
        if not host:
            raise GatewayError("EMAIL_IMAP_HOST is not set")
        connection = imaplib.IMAP4_SSL(host, int(getattr(self.settings, "email_imap_port", 993)))
        connection.login(
            getattr(self.settings, "email_imap_user", "") or "",
            getattr(self.settings, "email_imap_password", "") or "",
        )
        return connection

    def _smtp(self) -> Any:
        import smtplib

        host = getattr(self.settings, "email_smtp_host", None)
        if not host:
            raise GatewayError("EMAIL_SMTP_HOST is not set")
        server = smtplib.SMTP(host, int(getattr(self.settings, "email_smtp_port", 587)))
        with contextlib.suppress(Exception):
            server.starttls()
        user = getattr(self.settings, "email_imap_user", None)
        password = getattr(self.settings, "email_imap_password", None)
        if user and password:
            server.login(user, password)
        return server

    # -- inbound --------------------------------------------------------
    def fetch_new(self) -> list[dict[str, str]]:
        if self._fetcher is not None:
            return self._fetcher()
        connection = (self._imap_factory or self._imap)()
        try:
            connection.select("INBOX")
            status, data = connection.search(None, "UNSEEN")
            if status != "OK":
                return []
            messages: list[dict[str, str]] = []
            for num in (data[0] or b"").split():
                status, payload = connection.fetch(num, "(RFC822)")
                if status != "OK" or not payload:
                    continue
                raw = payload[0][1]
                if isinstance(raw, bytes):
                    messages.append(parse_message(raw))
            return messages
        finally:
            with contextlib.suppress(Exception):
                connection.logout()

    async def start(self) -> None:
        while True:
            messages = await asyncio.to_thread(self.fetch_new)
            for message in messages:
                with contextlib.suppress(Exception):
                    await self.handle_message(message)
            await asyncio.sleep(self.poll_interval_s)

    async def handle_message(self, message: dict[str, str]) -> Any:
        sender = message.get("sender", "")
        if not self.is_allowed(sender):
            return None
        thread = message.get("references") or message.get("message_id") or sender
        self._recipients[thread] = sender
        result = await self.run_turn(thread, message.get("body", ""))
        output = getattr(result, "output", None) or ""
        if output:
            await self.send(self.conversation_id(thread), output)
        return result

    # -- outbound -------------------------------------------------------
    async def send(self, conversation_id: str, text: str) -> None:
        thread = conversation_id.split(":", 1)[1] if ":" in conversation_id else conversation_id
        recipient = self._recipients.get(thread)
        if not recipient:
            raise GatewayError(f"no known recipient for email thread {thread!r}")
        sender = getattr(self.settings, "email_from", None) or getattr(
            self.settings, "email_imap_user", None
        )

        def _deliver() -> None:
            import email.message

            message = email.message.EmailMessage()
            message["From"] = sender or ""
            message["To"] = recipient
            message["Subject"] = "Re: your message"
            if thread:
                message["References"] = thread
            message.set_content(text)
            server = (self._smtp_factory or self._smtp)()
            try:
                server.send_message(message)
            finally:
                with contextlib.suppress(Exception):
                    server.quit()

        await asyncio.to_thread(_deliver)
