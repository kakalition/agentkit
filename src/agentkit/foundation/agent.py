"""The fluent agent builder — ``Agent.make("name").persona()...build()``.

``agentkit.Agent`` is a *builder*, not PydanticAI's ``Agent``. Application code
uses it to assemble a PydanticAI agent declaratively::

    from agentkit import Agent

    agent = (
        Agent.make("nudge")
        .persona()                 # SOUL.md
        .instructions(ORCHESTRATOR)
        .memory()
        .tool(handle_reminders)
        .output(str)
        .build()
    )

Internal agentkit modules keep importing ``pydantic_ai.Agent`` directly; only
this builder is the application-facing façade.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic_ai import Agent as PydanticAgent
from pydantic_ai import RunContext

from agentkit.approvals import approval_capability
from agentkit.deps import Deps
from agentkit.memory import attach_memory
from agentkit.orchestrator import make_delegate
from agentkit.soul import compose_instructions, load_soul


class Agent:
    """A fluent builder that assembles a :class:`pydantic_ai.Agent`."""

    def __init__(
        self,
        name: str,
        *,
        settings: Any = None,
        deps_type: type = Deps,
        model: Any = None,
        description: str | None = None,
        events: Any = None,
    ) -> None:
        self.name = name
        self._settings = settings
        self._deps_type = deps_type
        self._model = model
        self._description = description
        self._events = events
        self._persona = False
        self._persona_text: str | None = None
        self._persona_loader: Any = None
        self._retries: int | None = None
        self._instruction_parts: list[str] = []
        self._tools: list[tuple[Any, dict[str, Any]]] = []
        self._toolsets: list[Any] = []
        self._specialists: list[tuple[Any, str, str]] = []
        self._capabilities: list[Any] = []
        self._policies: list[Any] = []
        self._memory = False
        self._approvals = False
        self._output_type: Any = str
        self._output_validators: list[Any] = []
        self._clarify = False
        self._built: PydanticAgent[Any, Any] | None = None
        self._skills_requested = False
        self._skills_registry: Any = None
        self._skill_paths: list[Any] | None = None
        self._skills_enforce = False
        self._resolved_skills: Any = None
        self._workspace_requested = False
        self._workspace_sandbox: Any = None
        self._knowledge_requested = False
        self._knowledge_kb: Any = None
        self._knowledge_path: Any = None
        self._knowledge_index = True
        self._knowledge_limit = 5

    # -- construction ---------------------------------------------------
    @classmethod
    def make(cls, name: str, **kwargs: Any) -> Agent:
        return cls(name, **kwargs)

    # -- fluent API -----------------------------------------------------
    def persona(self, text: str | None = None, *, loader: Any = None) -> Agent:
        """Load the persona from SOUL.md (or use ``text`` verbatim).

        Pass ``loader`` (``settings -> str``) to source the persona elsewhere
        (e.g. an app-specific SOUL resolution); it is read live on every run.
        """
        self._persona = True
        self._persona_text = text
        self._persona_loader = loader
        return self

    def instructions(self, text: str) -> Agent:
        """Append a static instructions block (after the persona)."""
        self._instruction_parts.append(text)
        return self

    def prompt(self, prompt: Any, *, name: str | None = None, **variables: Any) -> Agent:
        """Append instructions from a prompt.

        ``prompt`` may be a :class:`~agentkit.prompts.PromptRegistry` (with
        ``name=``), a prompt directory, a ``.md`` file, or a raw template string.
        """
        path = Path(prompt) if isinstance(prompt, (str, Path)) else None
        if path is not None and path.is_dir():
            from agentkit.prompts import PromptRegistry

            if name is None:
                raise ValueError("name= is required when passing a prompt directory")
            return self.instructions(PromptRegistry([path]).discover().render(name, **variables))
        if path is not None and path.is_file():
            from agentkit.prompts import load_prompt_file

            return self.instructions(load_prompt_file(path).render(**variables))
        if hasattr(prompt, "render") and name is not None:
            return self.instructions(prompt.render(name, **variables))
        text = str(prompt)
        if variables:
            text = text.format(**variables)
        return self.instructions(text)

    def tool(
        self,
        function: Any,
        *,
        requires_approval: bool = False,
        retries: int | None = None,
        timeout: float | None = None,
        sequential: bool = False,
        defer_loading: bool = False,
        cache_ttl: float | None = None,
    ) -> Agent:
        if cache_ttl is not None:
            from agentkit.cache import cached_tool

            function = cached_tool(function, ttl=cache_ttl)
        options: dict[str, Any] = {}
        if requires_approval:
            options["requires_approval"] = True
        if retries is not None:
            options["retries"] = retries
        if timeout is not None:
            options["timeout"] = timeout
        if sequential:
            options["sequential"] = True
        if defer_loading:
            options["defer_loading"] = True
        self._tools.append((function, options))
        return self

    def tools(self, *functions: Any, **options: Any) -> Agent:
        for function in functions:
            self.tool(function, **options)
        return self

    def toolset(self, toolset: Any) -> Agent:
        """Attach a PydanticAI toolset (MCP, function toolset, …)."""
        self._toolsets.append(toolset)
        return self

    def specialist(self, agent: Any, *, name: str, description: str) -> Agent:
        """Register ``agent`` as a delegation tool (usage is forwarded)."""
        self._specialists.append((agent, name, description))
        return self

    def orchestrate(
        self, specialists: Mapping[str, tuple[Any, str]] | Iterable[tuple[Any, str, str]] | None = None
    ) -> Agent:
        """Register several specialists at once.

        Accepts either ``{tool_name: (agent, description)}`` or an iterable of
        ``(agent, tool_name, description)``. With no argument it is a no-op
        marker documenting that this agent is an orchestrator.
        """
        if specialists is None:
            return self
        items = specialists.items() if isinstance(specialists, Mapping) else specialists
        for item in items:
            if isinstance(specialists, Mapping):
                tool_name, (agent, description) = item  # type: ignore[misc]
                self.specialist(agent, name=tool_name, description=description)
            else:
                agent, tool_name, description = item  # type: ignore[misc]
                self.specialist(agent, name=tool_name, description=description)
        return self

    def memory(self, enabled: bool = True) -> Agent:
        self._memory = enabled
        return self

    def skills(
        self,
        registry: Any = None,
        *,
        paths: list[Any] | None = None,
        enforce: bool = False,
    ) -> Agent:
        """Attach a :class:`~agentkit.skills.SkillRegistry`.

        With no argument, skills are discovered from the settings roots
        (``skills_dir``, else ``./skills`` and ``<agent_home>/skills``). With
        ``enforce=True`` a ``ToolPolicy`` restricts tools to each skill's declared
        ``allowed-tools`` (locked mode).
        """
        self._skills_requested = True
        self._skills_registry = registry
        self._skill_paths = paths
        self._skills_enforce = enforce
        return self

    def workspace(
        self, root: Any = None, *, sandbox: Any = None, read_only: bool = False
    ) -> Agent:
        """Give the agent a sandboxed workspace (filesystem + command tools).

        Accepts a :class:`~agentkit.sandbox.Sandbox`, a path, or ``sandbox=``.
        Adds ``read_file``/``list_files``/``write_file``/``run_command``.
        """
        from agentkit.sandbox import coerce_sandbox

        self._workspace_requested = True
        target = sandbox if sandbox is not None else root
        if target is None:
            raise ValueError("workspace() needs a root path or a Sandbox")
        self._workspace_sandbox = coerce_sandbox(target, read_only=read_only)
        return self

    def knowledge(
        self,
        kb: Any = None,
        *,
        path: Any = None,
        index: bool = True,
        limit: int = 5,
    ) -> Agent:
        """Attach retrieval-augmented generation over a :class:`~agentkit.knowledge.KnowledgeBase`.

        ``kb`` may be a ``KnowledgeBase`` or a file/directory path (indexed at
        build time). Adds a ``search_knowledge`` tool, plus the source listing in
        the instructions when ``index=True``.
        """
        self._knowledge_requested = True
        if isinstance(kb, (str, Path)):
            self._knowledge_path = kb
            self._knowledge_kb = None
        else:
            self._knowledge_kb = kb
            self._knowledge_path = path
        self._knowledge_index = index
        self._knowledge_limit = limit
        return self

    def approvals(self, enabled: bool = True) -> Agent:
        self._approvals = enabled
        return self

    def policy(self, policy: Any) -> Agent:
        self._policies.append(policy)
        return self

    def capability(self, capability: Any) -> Agent:
        self._capabilities.append(capability)
        return self

    def _capability_from(self, name: str, **options: Any) -> Agent:
        import pydantic_ai.capabilities as caps

        factory = getattr(caps, name)
        self._capabilities.append(factory(**options))
        return self

    def web_search(self, **options: Any) -> Agent:
        """Add native web search (provider-native, with a local fallback)."""
        return self._capability_from("WebSearch", **options)

    def web_fetch(self, **options: Any) -> Agent:
        """Add native web fetch (read a URL into the model's context)."""
        return self._capability_from("WebFetch", **options)

    def x_search(self, **options: Any) -> Agent:
        """Add native X/Twitter search."""
        return self._capability_from("XSearch", **options)

    def thinking(self, effort: Any = True, **options: Any) -> Agent:
        """Enable extended thinking (``effort``: True/False/low/medium/high)."""
        return self._capability_from("Thinking", effort=effort, **options)

    def caching(self, retention: Any = True, **options: Any) -> Agent:
        """Enable prompt/response caching."""
        return self._capability_from("Caching", retention=retention, **options)

    def tool_search(self, **options: Any) -> Agent:
        """Let the model discover relevant tools on demand (tool RAG)."""
        return self._capability_from("ToolSearch", **options)

    def image_generation(self, **options: Any) -> Agent:
        """Add image generation."""
        return self._capability_from("ImageGeneration", **options)

    def instrumentation(self, settings: Any = None, **options: Any) -> Agent:
        """Attach PydanticAI's instrumentation capability (spans/metrics)."""
        if settings is None:
            return self._capability_from("Instrumentation", **options)
        return self._capability_from("Instrumentation", settings=settings, **options)

    def sandbox(self, working_dir: Any, **options: Any) -> Agent:
        """Give the agent a sandboxed local workspace rooted at ``working_dir``."""
        return self._capability_from("LocalWorkspace", working_dir=working_dir, **options)

    def native_tool(self, tool: Any, **options: Any) -> Agent:
        """Expose a provider-native tool."""
        return self._capability_from("NativeTool", tool=tool, **options)

    def output(self, output_type: Any) -> Agent:
        self._output_type = output_type
        return self

    def output_validator(self, function: Any) -> Agent:
        """Register a structured-output validator (``(ctx, output) -> output``)."""
        self._output_validators.append(function)
        return self

    def clarify(self, enabled: bool = True) -> Agent:
        """Add the ``ask_user`` clarification tool (wire with ``app.clarify(...)``)."""
        self._clarify = enabled
        return self

    def model(self, model: Any) -> Agent:
        self._model = model
        return self

    def retries(self, count: int) -> Agent:
        self._retries = count
        return self

    # -- build ----------------------------------------------------------
    def build(
        self, *, settings: Any = None, model: Any = None, events: Any = None
    ) -> PydanticAgent[Any, Any]:
        """Assemble and return the PydanticAI agent (cached after the first build)."""
        if self._built is not None:
            return self._built
        from agentkit.foundation.middleware import lifecycle_hooks, policy_hooks

        resolved_settings = settings or self._settings
        resolved_model = model or self._model

        if self._skills_requested:
            self._resolved_skills = self._resolve_skills(resolved_settings)

        instructions = self._instructions(resolved_settings)
        capabilities = [*self._capabilities]
        capabilities.append(lifecycle_hooks(events or self._events))
        if self._approvals:
            capabilities.append(approval_capability)
        capabilities.extend(policy_hooks(policy) for policy in self._policies)
        if self._skills_enforce and self._resolved_skills is not None:
            from agentkit.policy import ToolPolicy

            policy = self._resolved_skills.tool_policy()
            if isinstance(policy, ToolPolicy) and policy.allow:
                capabilities.append(policy_hooks(policy))

        built: PydanticAgent[Any, Any] = PydanticAgent(
            resolved_model,
            output_type=self._output_type,
            instructions=instructions,
            deps_type=self._deps_type,
            name=self.name,
            description=self._description,
            retries=self._retries,
            capabilities=capabilities or None,
            toolsets=self._toolsets or None,
        )
        for tool, options in self._tools:
            if options:
                built.tool(**options)(tool)
            else:
                built.tool(tool)
        for validator in self._output_validators:
            built.output_validator(validator)
        if self._clarify:
            from agentkit.hitl import clarification_tool

            built.tool(clarification_tool())
        for specialist, tool_name, description in self._specialists:
            built.tool(make_delegate(specialist, tool_name=tool_name, description=description))
        if self._memory:
            attach_memory(built)
        self._attach_skills(built, resolved_settings)
        self._attach_knowledge(built, resolved_settings)
        self._attach_workspace(built)
        self._built = built
        return built

    def _resolve_skills(self, settings: Any) -> Any:
        if settings is not None and getattr(settings, "skills_enabled", True) is False:
            return None
        from agentkit.skills import SkillRegistry

        registry = self._skills_registry
        if registry is None:
            registry = (
                SkillRegistry.from_paths(self._skill_paths)
                if self._skill_paths
                else SkillRegistry.from_settings(settings)
            )
        registry.discover()
        return registry

    def _attach_skills(self, agent: PydanticAgent[Any, Any], settings: Any) -> None:
        if not self._skills_requested:
            return
        registry = self._resolved_skills
        if registry is None or len(registry) == 0:
            return

        @agent.instructions
        def _skills_instructions(ctx: RunContext[Any]) -> str | None:
            return registry.index() or None

        @agent.tool
        async def list_skills(ctx: RunContext[Any]) -> str:
            """List the available skills (name and description)."""
            return registry.index() or "No skills available."

        @agent.tool
        async def load_skill(ctx: RunContext[Any], name: str) -> str:
            """Load a skill's full instructions by name.

            Args:
                name: The skill name to load.
            """
            return registry.load(name)

        @agent.tool
        async def read_skill_file(ctx: RunContext[Any], name: str, path: str) -> str:
            """Read a support file bundled with a skill.

            Args:
                name: The skill the file belongs to.
                path: The file's path relative to the skill directory.
            """
            return registry.read_file(name, path)

    def _attach_knowledge(self, agent: PydanticAgent[Any, Any], settings: Any) -> None:
        if not self._knowledge_requested:
            return
        from agentkit.knowledge import KnowledgeBase

        kb = self._knowledge_kb
        if kb is None:
            kb = KnowledgeBase(settings=settings)
            if self._knowledge_path is not None:
                target = Path(self._knowledge_path).expanduser()
                if target.is_dir():
                    kb.add_directory(target)
                elif target.is_file():
                    kb.add_file(target)
        default_limit = self._knowledge_limit

        if self._knowledge_index:

            @agent.instructions
            def _knowledge_instructions(ctx: RunContext[Any]) -> str | None:
                return kb.index() or None

        @agent.tool
        async def search_knowledge(ctx: RunContext[Any], query: str, limit: int | None = None) -> str:
            """Search indexed knowledge for passages relevant to the query.

            Args:
                query: What to look for.
                limit: Maximum passages to return (default 5).
            """
            return kb.format_hits(kb.search(query, limit=limit or default_limit))

    def _attach_workspace(self, agent: PydanticAgent[Any, Any]) -> None:
        if not self._workspace_requested:
            return
        from agentkit.sandbox import render_command

        sandbox = self._workspace_sandbox

        @agent.tool
        async def read_file(ctx: RunContext[Any], path: str) -> str:
            """Read a file from the workspace.

            Args:
                path: Path relative to the workspace root.
            """
            try:
                return await sandbox.read(path)
            except Exception as exc:
                return f"ERROR: {exc}"

        @agent.tool
        async def list_files(ctx: RunContext[Any], path: str = ".") -> str:
            """List entries in a workspace directory.

            Args:
                path: Directory relative to the workspace root (default ".").
            """
            try:
                return "\n".join(await sandbox.list(path)) or "(empty)"
            except Exception as exc:
                return f"ERROR: {exc}"

        @agent.tool
        async def write_file(ctx: RunContext[Any], path: str, content: str) -> str:
            """Write a file in the workspace.

            Args:
                path: Path relative to the workspace root.
                content: The file contents.
            """
            try:
                return f"wrote {await sandbox.write(path, content)}"
            except Exception as exc:
                return f"ERROR: {exc}"

        @agent.tool
        async def run_command(ctx: RunContext[Any], command: str) -> str:
            """Run a command in the workspace (no shell; argv is split safely).

            Args:
                command: The command line, e.g. "python script.py --flag".
            """
            try:
                return render_command(await sandbox.run(command))
            except Exception as exc:
                return f"ERROR: {exc}"

    def _instructions(self, settings: Any) -> Any:
        """Compose the instructions string, or a per-run callable when the persona
        must be read from the live SOUL every run."""
        static = "\n\n".join(part.strip() for part in self._instruction_parts if part)
        if not self._persona:
            return static or None
        if self._persona_text is not None:
            return "\n\n".join(part for part in [self._persona_text.strip(), static] if part)
        bound_settings = settings

        def dynamic(ctx: Any) -> str:
            live = getattr(getattr(ctx, "deps", None), "settings", None) or bound_settings
            soul = self._persona_loader(live) if self._persona_loader is not None else load_soul(live)
            return compose_instructions(soul, static)

        return dynamic

    # -- convenience ----------------------------------------------------
    @property
    def agent(self) -> PydanticAgent[Any, Any]:
        return self.build()

    @property
    def policies(self) -> list[Any]:
        return list(self._policies)

    def __repr__(self) -> str:
        state = "built" if self._built is not None else "unbuilt"
        return f"Agent.make({self.name!r}, {state})"


__all__ = ["Agent"]
