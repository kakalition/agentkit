# Model Routing & Cost

Different turns deserve different models: a cheap model for a quick answer, a
capable one for hard reasoning, with a fallback if the first fails. agentkit routes
per turn and records the cost of every call.

## Routing with a resolver

Set a resolver on the app. It receives the [`Turn`](/reference/api) (with `text`,
`conversation_id`, `approve`) and returns a model.

```python
app.model_resolver(lambda turn: "openai:gpt-5-mini" if len(turn.text) < 500 else "openai:gpt-5")
```

## The `ModelRouter`

`ModelRouter` expresses routing declaratively. It is callable, so it can be
installed directly.

```python
from agentkit import ModelRouter

router = (
    ModelRouter()
    .route("openai:gpt-5-mini", when=lambda ctx: ctx is not None and len(ctx.text) < 500)
    .route("openai:gpt-5")
    .otherwise("openai:gpt-4o-mini")
    .with_fallbacks("openai:gpt-4o")
)

app.model_resolver(router)
```

- `.route(model, when=…)` — use `model` when `when(context)` is true (omit `when`
  to match anything).
- `.otherwise(model)` — the model used when no route matches.
- `.with_fallbacks(*models)` — fallbacks tried in order when the selected model
  fails (via PydanticAI's `FallbackModel`).

`router.select(context)` / `router(context)` return the chosen model.

## Cost accounting

Every turn records token usage and an estimated cost. The estimate prefers
PydanticAI's own `RunUsage.cost`, then falls back to
[`genai_prices`](https://github.com/pydantic/genai-prices):

```python
from agentkit import estimate_cost

estimate_cost("openai:gpt-4o-mini", input_tokens=1200, output_tokens=400)  # → 0.00069
```

For accurate billing, or for a model not in the price database, register an
override:

```python
from agentkit import default_pricing

default_pricing().set("openai:gpt-5-mini", input=0.00025, output=0.002)
```

### Reading usage

```python
with app.repositories() as repos:
    totals = repos.usage.totals()
    # {"requests": …, "input_tokens": …, "output_tokens": …,
    #  "total_tokens": …, "cost_usd": …}

    repos.usage.list(limit=50)                       # per-turn rows
    repos.usage.totals(since=yesterday)              # a window
```

Each `ChatResult.usage` also carries the per-turn totals.

## Putting it together

```python
router = (
    ModelRouter()
    .route("openai:gpt-5-mini", when=lambda t: t is not None and len(t.text) < 500)
    .route("openai:gpt-5")
    .with_fallbacks("openai:gpt-4o")
)
app.model_resolver(router).budget(Budget(max_cost=5.0, window_seconds=86_400))
```

Now cheap turns stay cheap, hard turns get a capable model, failures fall back, and
a daily spend ceiling is enforced. See [Budgets & Limits](/guide/budgets).

::: tip Cost is a first-class metric
Because cost is recorded per turn, the operator UI can chart spend by model,
conversation, and day — no extra instrumentation.
:::

Continue to [Multimodal & Voice →](/guide/multimodal)
