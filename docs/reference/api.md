# Public API

Everything below is importable directly from `agentkit`.

```python
from agentkit import App, Agent, Provider, Memory, Model, SkillRegistry
```

## Application

| Name | What it is |
| --- | --- |
| `App` | the application container |
| `Provider` | a service provider base class |
| `Command` | a CLI command base class |
| `Section` | a layered configuration section |
| `Container` | the underlying service container |
| `ChannelSpec` | a registered channel |
| `Turn` | the per-turn object passed to middleware and model resolvers |
| `Service` | a long-running service for `run_all` / channels |

Related: `discover_providers`, `load_bootstrap`, `scaffold_project`,
`package_name`, `run_all`, `current_app`, `using`.

## Agents & the builder

| Name | What it is |
| --- | --- |
| `Agent` | the fluent agent builder (not PydanticAI's `Agent`) |
| `Orchestrator` | specialist-delegation helper |
| `make_delegate`, `delegate` | build a delegation tool from an agent |
| `Deps`, `ApprovalCallback`, `ApprovalRequest` | the run-context payload |
| `AgentApp` | deprecated shim over `App` |

## Laravel-style bases & primitives

| Name | What it is |
| --- | --- |
| `Provider` | service provider (`register`/`boot`) |
| `Repository`, `RepositoryQuery` | data-access base with CRUD for free |
| `Model`, `Query` | thin SQLModel table base |
| `ScheduleBuilder` | fluent scheduler (`app.schedule(...).every_minute()`) |
| `Notification`, `Notifier`, `SentNotification` | notifications over channels |
| `Job` | dispatchable work (`await app.dispatch(job)`) |
| `Cache`, `CacheStore` | the cache facade + in-process store |
| `Storage`, `Filesystem` | the storage facade + root-confined filesystem |
| `Rule`, `ValidationError`, `validate` | input validation |
| `Listener`, `Middleware` | event-listener and turn-middleware base classes |
| `Command` | CLI command base |

## Tools & capabilities

`ToolPolicy`, `ALLOW`, `APPROVE`, `DENY`, `approval_handler`,
`approval_capability`, `auto_approver`, `cached_tool`, `Check`.

## Sessions & results

`ChatRunner`, `ChatResult`, `StreamEvent`, `load_history`, `save_new_messages`,
`build_deps`, `build_runtime`, `repositories`, `Runtime`, `model_settings`,
`usage_limits`.

## Memory, skills, knowledge, prompts

`attach_memory`, `memory_digest`, `Memory`, `Skill`, `SkillRegistry`,
`load_skill_file`, `parse_front_matter`, `KnowledgeBase`, `chunk_text`,
`Prompt`, `PromptRegistry`, `Compactor`, `summarize_older`,
`transcript`, `truncating_processor`.

## Human-in-the-loop

`Clarification`, `clarification_tool`, `ModerationPolicy`, `ModerationResult`,
`moderation_middleware`, `moderation_hooks`, `check_output`.

## Planning, graphs, teams

`Planner`, `Plan`, `PlanStep`, `StateGraph`, `END`, `GraphError`, `Supervisor`,
`spawn_tool`, `team_tools`.

## Extensions, specs & runs

`ExtensionManifest`, `PanelSpec`, `EXTENSIONS`, `PANELS`, `ACTIONS`,
`register_manifest`, `register_panel`, `register_action`, `run_action`,
`discover_manifests`; `SPECS`, `SpecKind`, `SpecModel`, `SpecRegistry`,
`SpecStore`, `RepositorySpecStore`, `register_spec`, `register_codegen`,
`render_spec`, `AgentSpec`, `TeamDefinitionSpec`, `WorkflowSpec`, `EvalSpec`,
`WorkflowSpecNode`; `RunEvent`, `RunRecorder`, `recorder_for`, `InMemoryRecorder`,
`RepositoryRunRecorder`, `CompositeRecorder`; `Checkpoint`, `CheckpointManager`,
`CheckpointStore`, `MemoryCheckpointStore`, `FileCheckpointStore`,
`RepositoryCheckpointStore`; `ComputerManager`, `LoopbackComputer`,
`PlaywrightComputer`, `attach_computer`; `LoopbackRealtime`, `PydanticAIRealtime`,
`RealtimeManager`; graders `ExactMatchGrader`, `ContainsGrader`, `SchemaGrader`,
`TraceGrader`, `LLMJudgeGrader`, `register_grader`; `CatalogManager`,
`LocalCatalog`, `SkillsCatalog`, `HttpCatalog`, `CatalogItem`,
`register_catalog_source`.

## Contracts & drivers

Every subsystem's contract lives in `agentkit.contracts` (runtime-checkable
Protocols): `CacheContract`, `PromptStore`, `EmbedderContract`, `MemoryStore`,
`RecallStrategy`, `Chunker`, `Retriever`, `Reranker`, `FileSystem`, `QueueDriver`,
`SchedulerDriver`, `Durability`, `Dialect`, `Tracer`, `PriceProvider`,
`RateLimiterContract`, `AuthStrategy`, `Vault`, `Scanner`, `DocumentLoader`,
`Speech`/`Transcriber`/`Synthesizer`, `Extractor`/`LearningStrategy`/
`LearningSink`, `Topology`, `ContextStrategy`, `TaskStore`, `PlanningStrategy`,
`AgentMiddleware`, `GraphExecutor`, `CodeExecutor`, `Reporter`, `Channel`,
`NotificationChannel`, `Spec`, `CheckpointStore`, `RunRecorder`, `RunStore`,
`Computer`, `RealtimeSession`, `Dataset`, `Grader`, `Catalog`.

The registry and the typed identifiers:

| Name | What it is |
| --- | --- |
| `DriverKind` | the `StrEnum` of every subsystem kind |
| `Manager` | base class resolving a settings-selected driver per kind |
| `register_driver`, `register`, `resolve`, `unregister` | the global driver registry |
| `CacheDriver`, `EmbeddingsDriver`, `CommsDriver`, … | per-subsystem driver `StrEnum`s (`agentkit.support.kinds`), incl. `CheckpointDriver`, `ComputerDriver`, `RealtimeDriver`, `CatalogDriver`, `DatasetDriver`, `EvalGraderDriver` |

`App.manager(kind)`, `App.extend(kind, name, factory)` and `App.drivers()` expose
the layer, and each subsystem has a convenience accessor (`app.cache`,
`app.tasks`, `app.graph_executor`, `app.code_executor`, `app.eval_reporter`,
`app.comms`, `app.vault`, …).

## Capability helpers

`attach_tasks`, `attach_code_executor`, `subagent_tool`, `assert_trajectory`,
`CommsContext` (on `Deps.comms`).

## Models, routing, cost

`Model`, `Query`, `DB`, `ModelRouter`, `Route`, `Pricing`, `ModelPrice`,
`estimate_cost`, `usage_cost`, `default_pricing`, `set_default_pricing`,
`Budget`.

## Sandbox & multimodal

`Sandbox`, `SandboxError`, `CommandResult`, `image`, `audio`, `document`,
`content`, `text`, `transcribe`, `synthesize`.

## Events & middleware

`Dispatcher`, `Event`, `Pipeline`, `Middleware`, `run_pipeline`, `emit`.

## Facades

`Facade`, `Memory`, `Schedule`, `DB`, `Events`, `Log`, `Feedback`.

## Config & soul

`AgentSettings`, `get_settings`, `build_model`, `load_soul`, `ensure_soul`,
`soul_path`, `compose_instructions`, `SOUL_FILENAME`, `DEFAULT_SOUL`.

## Guardrails & errors

`scan_injection`, `is_suspicious`, `wrap_untrusted`, `redact`, `check_egress`,
`is_loopback`, `warn_if_exposed`, and the error taxonomy:
`AgentKitError`, `ConfigurationError`, `InvalidInput`, `NotFound`, `Conflict`,
`PermissionDenied`, `RateLimited`, `DependencyMissing`, `UpstreamError`,
`ContentBlocked`, `BudgetExceeded`.

## Evaluations

`EvalSuite`, `Case`, `CaseResult`, `Report`, `TextReporter`, `JsonReporter`,
`PydanticReporter`, `capture_turns`, `load_captured`, `assert_trajectory`.

## Observability & ops

`get_logger`, `setup_logging`, `setup_observability`, `setup_logfire`,
`start_phoenix`, `health_routes`, `db_check`, `install_signal_handlers`,
`scheduler`, `durability`, `workspace`.

## Web UI

`build_webui_app`, `serve_webui`, `webui_service`, `request_context`.

## Submodules

Everything is also importable from its module, e.g.
`agentkit.foundation`, `agentkit.contracts`, `agentkit.support`,
`agentkit.skills`, `agentkit.knowledge`,
`agentkit.compaction`, `agentkit.evals`, `agentkit.planning`, `agentkit.graph`,
`agentkit.teams`, `agentkit.prompts`, `agentkit.limits`, `agentkit.moderation`,
`agentkit.multimodal`, `agentkit.audio`, `agentkit.sandbox`, `agentkit.pricing`,
`agentkit.routing`, `agentkit.hitl`, `agentkit.cache`, `agentkit.tasks`,
`agentkit.executors`, `agentkit.comms`, `agentkit.learning`.
