"""agentkit console entry point: workspace management, web UI, and an
Artisan-style CLI (``make:*`` generators, ``serve``/``tinker``/``inspect``)."""

from __future__ import annotations

import contextlib
import json
import subprocess
from pathlib import Path

import typer

from agentkit import __version__
from agentkit.config import get_settings
from agentkit.foundation.commands import load_bootstrap
from agentkit.foundation.generators import generate
from agentkit.workspace import default_workspace_root, detect_legacy, migrate, workspace_dir

app = typer.Typer(
    add_completion=False,
    help="agentkit — workspace management, the operator web UI, and app scaffolding.",
    no_args_is_help=True,
)
workspace_app = typer.Typer(no_args_is_help=True, help="Inspect and migrate agent workspaces.")
app.add_typer(workspace_app, name="workspace")
skills_app = typer.Typer(no_args_is_help=True, help="Inspect discovered skills.")
app.add_typer(skills_app, name="skills")
knowledge_app = typer.Typer(no_args_is_help=True, help="Index and search knowledge (RAG).")
app.add_typer(knowledge_app, name="knowledge")


@app.command()
def version() -> None:
    """Print the agentkit version."""
    typer.echo(f"agentkit {__version__}")


@app.command()
def about() -> None:
    """Show the agentkit version and the resolved agent home/model."""
    settings = get_settings()
    typer.echo(f"agentkit {__version__}")
    typer.echo(f"agent home: {settings.home}")
    typer.echo(f"model: {settings.model_name}")


@app.command()
def webui(
    host: str | None = typer.Option(None, help="Bind host (default: settings)."),
    port: int | None = typer.Option(None, help="Bind port (default: settings)."),
) -> None:
    """Serve the operator web UI for the agent in the current environment."""
    from agentkit.webui.server import serve_webui

    settings = get_settings()
    typer.echo(f"agentkit webui at http://{host or settings.webui_host}:{port or settings.webui_port}")
    serve_webui(settings=settings, host=host, port=port)


@app.command()
def api(
    host: str | None = typer.Option(None, help="Bind host (default: settings)."),
    port: int | None = typer.Option(None, help="Bind port (default: settings)."),
) -> None:
    """Alias for ``webui`` (serve the API + SPA)."""
    webui(host=host, port=port)


# ---------------------------------------------------------------------------
# Runtime commands
# ---------------------------------------------------------------------------


@app.command()
def serve(
    bootstrap: str | None = typer.Option(
        None, "--bootstrap", help="module:attr (default: $AGENTKIT_BOOTSTRAP or bootstrap:app)."
    ),
    scheduler: bool = typer.Option(
        True, "--scheduler/--no-scheduler", help="Also run the durable scheduler worker."
    ),
    webui: bool = typer.Option(True, "--webui/--no-webui", help="Also serve the operator web UI."),
) -> None:
    """Boot the app and run its channels (plus the web UI)."""
    try:
        booted = load_bootstrap(bootstrap)
    except (ImportError, AttributeError, TypeError) as exc:
        typer.echo(
            f"could not load app ({exc}); set AGENTKIT_BOOTSTRAP or create a "
            "'bootstrap.py' exposing `app`.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    booted.boot()
    with contextlib.suppress(Exception):  # observability is optional
        from agentkit.observability import setup_observability

        setup_observability(booted.settings)
    if scheduler:
        from agentkit import scheduler as sched

        sched.init_scheduler(booted.settings, repos_factory=booted.repos_factory)
    booted.serve(webui=webui)


@app.command()
def up(
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="Boot target (default: bootstrap:app)."),
) -> None:
    """Alias for ``serve``."""
    serve(bootstrap=bootstrap)


@app.command()
def tinker(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    conversation_id: str = typer.Option("cli:tinker", help="Conversation id to keep history under."),
) -> None:
    """Interactive REPL: chat with the booted app."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    typer.echo("agentkit tinker — type 'exit' to quit.")
    while True:
        try:
            line = input("agentkit> ")
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            break
        if not line.strip():
            continue
        if line.strip().lower() in {"exit", "quit", ":q"}:
            break
        result = asyncio.run(booted.run(line, conversation_id=conversation_id))
        typer.echo(result.output)


@app.command()
def inspect(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show the booted app's agent, tools, channels, commands and config."""
    booted = load_bootstrap(bootstrap)
    booted.boot()
    agent = booted.agent()
    toolset = getattr(agent, "_function_toolset", None)
    data = {
        "name": booted.name,
        "agent": getattr(agent, "name", None),
        "tools": sorted(getattr(toolset, "tools", {}).keys()),
        "channels": sorted(booted.channels()),
        "commands": sorted(booted._commands),
        "config": sorted(booted._config_schemas),
    }
    if as_json:
        typer.echo(json.dumps(data, indent=2))
        return
    typer.echo(f"app: {data['name']}")
    typer.echo(f"agent: {data['agent']}")
    typer.echo(f"tools: {', '.join(data['tools']) or '(none)'}")
    typer.echo(f"channels: {', '.join(data['channels']) or '(none)'}")
    typer.echo(f"commands: {', '.join(data['commands']) or '(none)'}")
    typer.echo(f"config: {', '.join(data['config']) or '(none)'}")


@app.command("schedule:list")
def schedule_list(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """List the booted app's durable scheduled jobs."""
    from agentkit import Schedule

    booted = load_bootstrap(bootstrap)
    booted.boot()
    jobs = Schedule.list()
    if not jobs:
        typer.echo("(no scheduled jobs)")
        return
    for job in jobs:
        state = "on" if job["enabled"] else "off"
        typer.echo(f"  {job['name']:<20} {job['schedule']:<16} -> {job['task']} [{state}]")


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


@app.command("new")
def new_project(
    name: str = typer.Argument(..., help="Project name, e.g. my-agent."),
    path: Path = typer.Option(
        Path("."), "--path", help="Parent directory to create the project in."
    ),
    force: bool = typer.Option(False, "--force", help="Write into a non-empty directory."),
    git: bool = typer.Option(True, "--git/--no-git", help="Initialise a git repository."),
) -> None:
    """Create a new agentkit project from the default skeleton."""
    from agentkit.foundation.scaffold import scaffold_project

    try:
        target = scaffold_project(name, path, force=force)
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if git:
        with contextlib.suppress(Exception):
            subprocess.run(["git", "init"], cwd=target, capture_output=True, check=False)
            subprocess.run(["git", "add", "-A"], cwd=target, capture_output=True, check=False)

    typer.echo(f"Created {target}")
    typer.echo("Next steps:")
    typer.echo(f"  cd {target}")
    typer.echo("  cp .env.example .env   # then set OPENAI_API_KEY")
    typer.echo("  uv sync                # or: pip install -e .")
    typer.echo("  agentkit tinker        # chat with your agent")


def _run_generate(kind: str, name: str, path: Path, force: bool) -> None:
    try:
        written = generate(kind, name, directory=path, force=force)
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"created {written}")


@app.command("make:agent")
def make_agent(
    name: str = typer.Argument(..., help="Agent name, e.g. notes."),
    path: Path = typer.Option(Path("."), "--path", help="Project directory to write into."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Scaffold an agent builder module."""
    _run_generate("agent", name, path, force)


@app.command("make:provider")
def make_provider(
    name: str = typer.Argument(..., help="Provider name, e.g. notes."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a service provider."""
    _run_generate("provider", name, path, force)


@app.command("make:tool")
def make_tool(
    name: str = typer.Argument(..., help="Tool name, e.g. add_note."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a tool function."""
    _run_generate("tool", name, path, force)


@app.command("make:channel")
def make_channel(
    name: str = typer.Argument(..., help="Channel name, e.g. slack."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a channel factory."""
    _run_generate("channel", name, path, force)


@app.command("make:command")
def make_command(
    name: str = typer.Argument(..., help="Command name, e.g. sync."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a provider command."""
    _run_generate("command", name, path, force)


@app.command("make:model")
def make_model(
    name: str = typer.Argument(..., help="Model name, e.g. note."),
    path: Path = typer.Option(Path("."), "--path"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Scaffold a ``Model`` table."""
    _run_generate("model", name, path, force)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@skills_app.command("list")
def skills_list(
    path: list[Path] | None = typer.Option(
        None, "--path", help="Skill root (repeatable; default: settings roots)."
    ),
) -> None:
    """List the skills discovered under the configured roots."""
    from agentkit.skills import SkillRegistry

    registry = (
        SkillRegistry.from_paths(path) if path else SkillRegistry.from_settings()
    ).discover()
    if len(registry) == 0:
        typer.echo("(no skills found)")
        return
    for skill in registry.all():
        typer.echo(f"  {skill.name:<24} {skill.description}  ({skill.path})")


@skills_app.command("show")
def skills_show(
    name: str = typer.Argument(..., help="Skill name."),
    path: list[Path] | None = typer.Option(None, "--path", help="Skill root (repeatable)."),
) -> None:
    """Show one skill's full instructions (and bundled files)."""
    from agentkit.skills import SkillRegistry

    registry = (
        SkillRegistry.from_paths(path) if path else SkillRegistry.from_settings()
    ).discover()
    skill = registry.get(name)
    if skill is None:
        typer.echo(f"no skill named {name!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(skill.render())


# ---------------------------------------------------------------------------
# Knowledge (RAG)
# ---------------------------------------------------------------------------


@knowledge_app.command("add")
def knowledge_add(
    path: Path = typer.Argument(..., help="File or directory to index."),
    pattern: str = typer.Option("**/*.md", help="Glob when indexing a directory."),
) -> None:
    """Index a file or directory into the knowledge base."""
    from agentkit import KnowledgeBase

    kb = KnowledgeBase.from_settings()
    added = kb.add_directory(path, pattern=pattern) if path.is_dir() else kb.add_file(path)
    typer.echo(f"indexed {added} chunk(s)")


@knowledge_app.command("add-text")
def knowledge_add_text(
    text: str = typer.Argument(..., help="Text to index."),
    source: str = typer.Option("", "--source", help="Label for this text."),
) -> None:
    """Index a literal string."""
    from agentkit import KnowledgeBase

    added = KnowledgeBase.from_settings().add(text, source=source)
    typer.echo(f"indexed {added} chunk(s)")


@knowledge_app.command("search")
def knowledge_search(
    query: str = typer.Argument(..., help="Query text."),
    limit: int = typer.Option(5, help="Maximum passages."),
) -> None:
    """Search indexed knowledge."""
    from agentkit import KnowledgeBase

    kb = KnowledgeBase.from_settings()
    typer.echo(kb.format_hits(kb.search(query, limit=limit)))


@knowledge_app.command("list")
def knowledge_list() -> None:
    """List indexed sources."""
    from agentkit import KnowledgeBase

    kb = KnowledgeBase.from_settings()
    sources = kb.sources()
    if not sources:
        typer.echo("(nothing indexed)")
        return
    for source in sources:
        typer.echo(f"  {source} ({kb.count(source)} chunks)")


# ---------------------------------------------------------------------------
# Evaluations
# ---------------------------------------------------------------------------


@app.command("eval")
def eval_command(
    path: Path = typer.Argument(..., help="Eval suite file (.json/.yaml)."),
    bootstrap: str | None = typer.Option(None, "--bootstrap", help="module:attr of the app."),
) -> None:
    """Run an evaluation suite against the booted app."""
    import asyncio

    from agentkit import EvalSuite

    suite = EvalSuite.from_file(path)
    booted = load_bootstrap(bootstrap)
    booted.boot()
    report = asyncio.run(suite.run(booted))
    typer.echo(report.summary())
    if not report.passed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@app.command("queue:work")
def queue_work(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
    queue: str | None = typer.Option(None, "--queue", help="Queue name (default: settings)."),
    once: bool = typer.Option(False, "--once", help="Process what's available, then exit."),
    sleep: float = typer.Option(2.0, "--sleep", help="Seconds to wait when the queue is empty."),
    max_jobs: int = typer.Option(0, "--max-jobs", help="Stop after N jobs (0 = unlimited)."),
) -> None:
    """Process queued jobs (requires ``QUEUE_ENABLED=true``)."""
    import asyncio

    booted = load_bootstrap(bootstrap)
    booted.boot()
    if not getattr(booted.settings, "queue_enabled", False):
        typer.echo("queue is disabled; set QUEUE_ENABLED=true to enable it", err=True)
        raise typer.Exit(code=1)

    async def drain() -> int:
        processed = 0
        while True:
            ran = await booted.queue.run_once(queue)
            if ran:
                processed += 1
                if max_jobs and processed >= max_jobs:
                    return processed
            elif once:
                return processed
            else:
                await asyncio.sleep(sleep)

    processed = asyncio.run(drain())
    typer.echo(f"processed {processed} job(s)")


@app.command("queue:failed")
def queue_failed(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """List failed jobs."""
    booted = load_bootstrap(bootstrap)
    booted.boot()
    rows = booted.queue.failed()
    if not rows:
        typer.echo("(no failed jobs)")
        return
    for row in rows:
        typer.echo(f"  #{row.id} {row.queue} {row.job} (attempts {row.attempts}): {row.error}")


@app.command("queue:retry")
def queue_retry(
    job_id: int = typer.Argument(..., help="The failed job id."),
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Requeue a failed job."""
    booted = load_bootstrap(bootstrap)
    booted.boot()
    if booted.queue.retry(job_id):
        typer.echo(f"requeued job #{job_id}")
    else:
        typer.echo(f"no failed job #{job_id}", err=True)
        raise typer.Exit(code=1)


@app.command("queue:flush")
def queue_flush(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Delete all failed jobs."""
    booted = load_bootstrap(bootstrap)
    booted.boot()
    typer.echo(f"flushed {booted.queue.flush()} failed job(s)")


@app.command("schedule:run")
def schedule_run(
    bootstrap: str | None = typer.Option(None, "--bootstrap"),
) -> None:
    """Run any due scheduled jobs right now (catch-up)."""
    from agentkit import Schedule

    booted = load_bootstrap(bootstrap)
    booted.boot()
    ran = Schedule.run_due()
    typer.echo(f"ran {len(ran)} job(s)" + (f": {', '.join(ran)}" if ran else ""))


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


@workspace_app.command("list")
def workspace_list(
    root: Path | None = typer.Option(None, help="Workspace root (default: ~/.agentkit)."),
) -> None:
    """List agent homes under the workspace root (and any legacy data)."""
    base = root.expanduser() if root else default_workspace_root()
    typer.echo(f"workspace root: {base}")
    names: list[str] = []
    if base.is_dir():
        names = sorted(p.name for p in base.iterdir() if p.is_dir())
    if not names:
        typer.echo("  (no agent homes yet)")
    for name in names:
        home = workspace_dir(name, root=base)
        has_db = any(home.glob("*.db"))
        typer.echo(f"  {name}: {home}{'' if has_db else ' (no database)'}")
    legacy_names = _legacy_agent_names()
    for name in legacy_names:
        where = detect_legacy(name)
        if where is not None and not (base / name).exists():
            typer.echo(f"  {name}: legacy data at {where} (run: agentkit workspace migrate {name})")


@workspace_app.command("migrate")
def workspace_migrate(
    name: str = typer.Argument(..., help="Agent name, e.g. calliope."),
    root: Path | None = typer.Option(None, help="Workspace root (default: ~/.agentkit)."),
    copy: bool = typer.Option(False, "--copy", help="Copy instead of move."),
) -> None:
    """Move legacy ``~/.local/share/...`` data under the workspace root."""
    from agentkit.errors import Conflict

    try:
        summary = migrate(name, root=root, move=not copy)
    except Conflict as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not summary["migrated"]:
        typer.echo(f"nothing to migrate for {name} ({summary['reason']})")
        return
    verb = "copied" if summary["mode"] == "copy" else "moved"
    typer.echo(f"{verb} {summary['items']} from {summary['source']} -> {summary['target']}")


def _legacy_agent_names() -> list[str]:
    """Agents still stored in the legacy *shared* home (``~/.local/share/agentkit``).

    Agent-specific legacy homes (``~/.local/share/<name>``) are not enumerated —
    too many unrelated apps live there; migrate those explicitly by name.
    """
    base = Path("~/.local/share/agentkit").expanduser()
    if not base.is_dir():
        return []
    names = {path.stem for path in base.glob("*.db")}
    names.discard("agentkit")
    return sorted(names)


def main() -> None:
    from agentkit.logging import setup_logging

    setup_logging(get_settings())
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
