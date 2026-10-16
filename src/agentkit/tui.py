"""An interactive terminal UI for a booted agent (needs the ``tui`` extra).

    agentkit tui

Type a prompt, see the reply. The `textual` package is an optional extra; a
missing install raises :class:`~agentkit.errors.ConfigurationError` naming it.
"""

from __future__ import annotations

from agentkit.errors import ConfigurationError

__all__ = ["run_tui"]


def run_tui(*, bootstrap: str | None = None, conversation_id: str = "tui:default") -> None:
    """Run the interactive TUI against the booted app."""
    try:
        from textual.app import App
        from textual.widgets import Input, RichLog
    except ImportError as exc:
        raise ConfigurationError(
            "the TUI needs the 'tui' extra (pip install agentkit[tui])"
        ) from exc

    from agentkit.foundation.commands import load_bootstrap

    booted = load_bootstrap(bootstrap)
    booted.boot()

    class AgentTUI(App):  # pragma: no cover - interactive
        """A minimal chat TUI: prompt above, transcript below."""

        BINDINGS = [("ctrl+q", "quit", "Quit")]
        CSS = "#log { height: 1fr; }"

        def compose(self):  # noqa: ANN201
            yield RichLog(id="log", markup=True, wrap=True)
            yield Input(placeholder="Ask the agent… (ctrl+q to quit)", id="prompt")

        async def on_input_submitted(self, event: Input.Submitted) -> None:
            log = self.query_one("#log", RichLog)
            log.write(f"[bold]you:[/bold] {event.value}")
            event.input.value = ""
            result = await booted.run(event.value, conversation_id=conversation_id)
            log.write(f"[bold green]agent:[/bold green] {result.output}")

    AgentTUI().run()
