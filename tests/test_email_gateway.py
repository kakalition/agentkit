from __future__ import annotations

from types import SimpleNamespace

from agentkit.gateways.email import EmailGateway, parse_message

RAW = (
    b"From: Ada <ada@example.com>\r\n"
    b"To: bot@example.com\r\n"
    b"Subject: Hello\r\n"
    b"Message-ID: <abc@example.com>\r\n"
    b"References: <root@example.com>\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"what is the time?\r\n"
)


class FakeApp:
    settings = SimpleNamespace(agent_name="mail")

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def answer(self, conversation_id: str, text: str) -> object:
        self.calls.append((conversation_id, text))
        return SimpleNamespace(output=f"echo: {text}")


class FakeSMTP:
    def __init__(self) -> None:
        self.sent: list[object] = []
        self.quit_called = False

    def send_message(self, message) -> None:
        self.sent.append(message)

    def quit(self) -> None:
        self.quit_called = True


def _settings(**overrides):
    base = {
        "email_imap_host": "imap.example.com",
        "email_imap_user": "bot@example.com",
        "email_imap_password": "secret",
        "email_smtp_host": "smtp.example.com",
        "email_from": "bot@example.com",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_parse_message_extracts_fields():
    parsed = parse_message(RAW)
    assert parsed["sender"] == "ada@example.com"
    assert parsed["subject"] == "Hello"
    assert parsed["body"] == "what is the time?"
    assert parsed["message_id"] == "<abc@example.com>"
    assert parsed["references"] == "<root@example.com>"


async def test_handle_message_runs_turn_and_replies():
    app = FakeApp()
    smtp = FakeSMTP()
    gateway = EmailGateway(
        app,
        settings=_settings(),
        fetcher=lambda: [parse_message(RAW)],
        smtp_factory=lambda: smtp,
    )
    result = await gateway.handle_message(parse_message(RAW))
    assert result.output == "echo: what is the time?"
    assert app.calls == [("email:<root@example.com>", "what is the time?")]
    assert smtp.sent, "expected an SMTP reply"
    assert smtp.sent[0]["To"] == "ada@example.com"
    assert smtp.sent[0]["References"] == "<root@example.com>"


async def test_allowed_senders_blocks():
    app = FakeApp()
    gateway = EmailGateway(
        app,
        settings=_settings(),
        fetcher=lambda: [],
        allowed_senders=["someone@else.com"],
    )
    assert await gateway.handle_message(parse_message(RAW)) is None
    assert app.calls == []


async def test_poll_once_processes_fetch_queue():
    app = FakeApp()
    smtp = FakeSMTP()
    queue = [parse_message(RAW)]
    gateway = EmailGateway(
        app,
        settings=_settings(),
        fetcher=lambda: list(queue),
        smtp_factory=lambda: smtp,
    )
    messages = gateway.fetch_new()
    assert len(messages) == 1
    for message in messages:
        await gateway.handle_message(message)
    assert app.calls and smtp.sent
