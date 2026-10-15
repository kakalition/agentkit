# Budgets & Limits

## Introduction

Unattended agents need guardrails on spend. agentkit enforces token, cost, and
request budgets by checking recorded usage **before each turn**.

## Defining a budget

```python
from agentkit import Budget

app.budget(
    Budget(
        max_tokens=1_000_000,
        max_cost=5.0,             # USD
        max_requests=10_000,
        window_seconds=86_400,    # rolling 24h window
        per_conversation=False,   # True → scope to each conversation
    )
)
```

A `None` field is unbounded.

## What happens when a budget is hit

The next turn raises `BudgetExceeded` before it runs:

```python
from agentkit.errors import BudgetExceeded

try:
    result = await app.run("hello", conversation_id="cli:1")
except BudgetExceeded as exc:
    print(exc.detail["reasons"])   # ["cost 5.01 >= 5.0"]
```

`app.stream(...)` is checked the same way.

## Checking manually

```python
from agentkit.limits import check_budget

async with app.repositories() as repos:
    totals = check_budget(repos, Budget(max_cost=5.0, window_seconds=86_400))
```

`check_budget` returns the totals it evaluated, so you can log headroom.

## Rate limits

`Budget` covers cumulative limits. For per-`UsageLimits`-style caps on a single
run, configure the settings that `usage_limits(...)` derives:

```bash
# per-run model request / token ceilings
USAGE_MAX_REQUESTS=
USAGE_MAX_TOKENS=
```

These bound one turn; `Budget` bounds the aggregate.

## Where usage comes from

Budgets read `UsageRepo`, which records every turn's tokens and estimated cost
(see [Model Routing & Cost](/guide/routing#cost-accounting)). Because cost is
recorded per turn and per conversation, budgets can be global or scoped.

## A production setup

```python
app = (
    App(name="nudge", settings=settings)
    .budget(Budget(max_cost=25.0, window_seconds=30 * 86_400, per_conversation=True))
)
```

Each conversation gets its own $25 monthly ceiling; the operator UI's Usage tab
charts spend against it.

::: tip Alert before you block
Subscribe to `turn.end` and warn when usage crosses 80% of a budget, so a limit is
a safety net, not a surprise.
:::

Continue to [Prompt Registry →](/guide/prompts)
