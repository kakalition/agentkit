"""WS7 — class-based channels."""

from __future__ import annotations

import sys
from pathlib import Path

from agentkit import App, Channel, Service
from agentkit.foundation import discovery
from agentkit.runtime import Runtime


class EchoChannel(Channel):
    name = "echo"

    def handle(self) -> Service:
        def run() -> None:
            return None

        return Service("echo", run)


def _app(runtime: Runtime) -> App:
    app = App(name="chan", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    return app


def test_channel_class_services(runtime: Runtime) -> None:
    app = _app(runtime)
    app.channel("echo", EchoChannel)
    services = app.channel_services()
    assert services and services[0].name == "echo"


def test_channel_instance_services(runtime: Runtime) -> None:
    app = _app(runtime)
    app.channel("echo", EchoChannel())
    assert len(app.channel_services()) == 1


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_channel_classes(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _write(root / "app" / "__init__.py", "")
    _write(root / "app" / "Channels" / "__init__.py", "")
    _write(
        root / "app" / "Channels" / "TelegramChannel.py",
        "from agentkit import Channel\n\n\n"
        "class TelegramChannel(Channel):\n    name = 'telegram'\n\n"
        "    def handle(self):\n        return None\n",
    )
    resolved = str(root.resolve())
    try:
        found = discovery.discover_channels(root)
        names = [name for name, _ in found]
        assert "telegram" in names
    finally:
        sys.path[:] = [entry for entry in sys.path if entry != resolved]
        for name, module in list(sys.modules.items()):
            source = getattr(module, "__file__", None)
            if source and resolved in source:
                sys.modules.pop(name, None)
