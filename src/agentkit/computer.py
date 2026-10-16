"""Computer-use drivers — a headless browser (Playwright) or an in-memory loopback.

``LoopbackComputer`` is a deterministic, dependency-free implementation used by
tests and the default ``computer_driver=loopback``. ``PlaywrightComputer``
lazy-imports ``playwright`` on first use and raises
:class:`~agentkit.errors.ConfigurationError` naming the ``browser`` extra when it
is missing (construction stays import-safe).
"""

from __future__ import annotations

from typing import Any

from agentkit.contracts.computer import Computer
from agentkit.errors import ConfigurationError
from agentkit.support import register_driver
from agentkit.support.kinds import ComputerDriver, DriverKind
from agentkit.support.manager import Manager

__all__ = [
    "Computer",
    "ComputerManager",
    "LoopbackComputer",
    "PlaywrightComputer",
    "attach_computer",
]


def _missing_extra(extra: str) -> ConfigurationError:
    return ConfigurationError(
        f"this computer driver needs the {extra!r} extra (pip install agentkit[{extra}])"
    )


class LoopbackComputer:
    """An in-memory computer: records actions and returns synthetic snapshots."""

    def __init__(self, *, start_url: str = "about:blank") -> None:
        self.url = start_url
        self.history: list[str] = []
        self._elements: dict[str, str] = {}

    async def goto(self, url: str) -> str:
        self.url = url
        self.history.append(f"goto:{url}")
        return self._page()

    async def snapshot(self) -> str:
        return self._page()

    async def click(self, selector: str) -> str:
        self.history.append(f"click:{selector}")
        return f"clicked {selector}"

    async def type(self, selector: str, text: str) -> str:
        self._elements[selector] = text
        self.history.append(f"type:{selector}={text}")
        return f"typed {len(text)} char(s) into {selector}"

    async def screenshot(self) -> Any:
        self.history.append("screenshot")
        return b""

    async def evaluate(self, expression: str) -> Any:
        self.history.append(f"evaluate:{expression}")
        return {"url": self.url, "expression": expression}

    async def close(self) -> None:
        self.history.append("close")

    def _page(self) -> str:
        lines = [f"# {self.url}"]
        if self._elements:
            lines.append("Fields:")
            lines.extend(f"- {selector}: {value!r}" for selector, value in self._elements.items())
        return "\n".join(lines)


class PlaywrightComputer:
    """A headless-browser computer backed by Playwright (optional ``browser`` extra)."""

    def __init__(self, *, headless: bool = True, timeout_ms: int = 30_000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._page: Any = None
        self._browser: Any = None
        self._playwright: Any = None

    async def _ensure(self) -> Any:
        if self._page is not None:
            return self._page
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - exercised only with the extra
            raise _missing_extra("browser") from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    async def goto(self, url: str) -> str:
        page = await self._ensure()
        await page.goto(url)
        return await self.snapshot()

    async def snapshot(self) -> str:
        page = await self._ensure()
        return await page.content()

    async def click(self, selector: str) -> str:
        page = await self._ensure()
        await page.click(selector)
        return f"clicked {selector}"

    async def type(self, selector: str, text: str) -> str:
        page = await self._ensure()
        await page.fill(selector, text)
        return f"typed {len(text)} char(s) into {selector}"

    async def screenshot(self, *, path: str | None = None) -> Any:
        page = await self._ensure()
        return await page.screenshot(path=path, full_page=True)

    async def evaluate(self, expression: str) -> Any:
        page = await self._ensure()
        return await page.evaluate(expression)

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None


class ComputerManager(Manager):
    """Resolves the configured computer driver (``computer_driver``)."""

    kind = DriverKind.COMPUTER
    default_driver = ComputerDriver.LOOPBACK

    def create_loopback_driver(self, app: Any) -> LoopbackComputer:
        return LoopbackComputer()

    def create_playwright_driver(self, app: Any) -> PlaywrightComputer:
        return PlaywrightComputer(
            headless=bool(getattr(app.settings, "computer_headless", True)),
            timeout_ms=int(getattr(app.settings, "computer_timeout_ms", 30_000) or 30_000),
        )


@register_driver(DriverKind.COMPUTER, ComputerDriver.LOOPBACK)
def _loopback_computer_driver(app: Any) -> LoopbackComputer:
    return LoopbackComputer()


@register_driver(DriverKind.COMPUTER, ComputerDriver.PLAYWRIGHT)
def _playwright_computer_driver(app: Any) -> PlaywrightComputer:
    return PlaywrightComputer(
        headless=bool(getattr(app.settings, "computer_headless", True)),
        timeout_ms=int(getattr(app.settings, "computer_timeout_ms", 30_000) or 30_000),
    )


def attach_computer(agent: Any, computer: Any = None, *, requires_approval: bool = True) -> Any:
    """Attach the approval-gated browser tools to an agent (see ``toolkits.computer``)."""
    from agentkit.toolkits.computer import attach_computer_tools

    return attach_computer_tools(agent, computer, requires_approval=requires_approval)
