# Testing

## Introduction

agentkit is designed to be as easy to test as it is to run: no network, no clock,
and no import-time side effects.

## Test dependencies, not the agent

Most logic lives in tools and services, which are plain functions and objects.
Test those directly with a stub `RunContext`:

```python
from agentkit.deps import Deps

class FakeCtx:
    def __init__(self, repos):
        self.deps = Deps(settings=settings, repos=repos)

async def test_add_note(repos):
    result = await add_note(FakeCtx(repos), "buy milk")
    assert result == "saved: buy milk"
```

## A runtime fixture

Build a runtime against a temp directory so nothing leaks between tests:

```python
import pytest
from agentkit import build_runtime
from agentkit.runtime import repositories

@pytest.fixture
def runtime(tmp_path):
    settings = AgentSettings(owner_id="test", agent_home=tmp_path)
    return build_runtime(settings)

@pytest.fixture
def repos(runtime):
    async with repositories(runtime) as opened:
        yield opened
```

Force offline behaviour with the `hash` embedding backend:

```bash
MEMORY_EMBEDDING_BACKEND=hash
```

## FunctionModel: no network, no cost

Swap the model for a `FunctionModel` so a turn is deterministic and instant:

```python
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

def test_app_run(runtime):
    app = App(name="test", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.agent(Agent.make("test").instructions("x").output(str))
    app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")]))
    app.boot()

    result = asyncio.run(app.run("hi"))
    assert result.output == "ok"
```

To exercise **tools**, inspect the messages for the tool call and return a result:

```python
def model_fn(messages, info):
    if any(isinstance(p, ToolReturnPart) for m in messages for p in getattr(m, "parts", [])):
        return ModelResponse(parts=[TextPart("done")])
    return ModelResponse(parts=[ToolCallPart("lookup", {"q": "x"})])
```

## Testing the app without booting the world

`App(discover=False)` skips provider discovery. Booting a test app is safe: the
lifecycle is explicit and has no network side effects.

```python
app = App(name="test", settings=settings, discover=False)
app.boot()
```

## Testing scheduled tasks

Tasks are plain callables — call them directly:

```python
from notes.services import digest

def test_digest(repos):
    digest(period="week")   # runs inline
    assert ...
```

## Testing facades

Facades resolve the current app. Scope one explicitly:

```python
from agentkit import Memory, using

def test_memory(runtime):
    app = App(name="test", settings=runtime.settings, discover=False)
    app._runtime = runtime
    app.boot()
    with using(app):
        asyncio.run(Memory.remember("hi"))
```

## Running the suite

```bash
pytest
pytest --cov=agentkit
ruff check src tests
mypy src/agentkit
```

::: tip Keep tests fast
With `FunctionModel`, the `hash` embedder, and a temp `AGENT_HOME`, a full test
suite runs in seconds and never touches the network.
:::

Continue to the [Reference →](/reference/configuration)
