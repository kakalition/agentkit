# Evaluations

## Introduction

You would not ship a web app without tests. Agents deserve the same: suites of
inputs with expected outcomes, run in CI. agentkit's evaluations are executed by
[`pydantic_evals`](https://ai.pydantic.dev/evals/), Pydantic's evaluation framework.

## A suite

```python
from agentkit.evals import Case, EvalSuite

suite = EvalSuite(
    [
        Case("adds", input="what is 2+2?", expect="4"),
        Case("uses the calendar tool", input="book a slot", calls="create_event"),
        Case("stays in persona", input="hi", not_contains=["As an AI language model"]),
    ],
    name="smoke",
)

report = await suite.run(app)
report.raise_for_failures()
```

## Assertions

A `Case` supports several checks, all optional:

| Field | Asserts |
| --- | --- |
| `expect` | the output equals this string |
| `contains` | the output contains these substrings |
| `not_contains` | the output contains none of these substrings |
| `regex` | the output matches a regular expression |
| `calls` | these tools were called |
| `not_calls` | these tools were **not** called |
| `check` | a custom `fn(result) -> bool \| str` |

```python
Case(
    "refund flow",
    input="I want a refund",
    contains="refund",
    calls=["lookup_order", "issue_refund"],
    check=lambda result: result.usage["total_tokens"] < 5000,
)
```

A `check` returning `False` fails; returning a string fails with that message.

## Reports

```python
report.passed            # bool
report.passed_count
report.failed_count
report.summary()         # "smoke: 2/3 passed\n  ✗ ..."
report.render()          # the rich pydantic_evals table
report.raise_for_failures()
```

The underlying `pydantic_evals.EvaluationReport` is available as
`report.pydantic_report` for advanced reporting, and `suite.to_dataset()` yields the
equivalent `pydantic_evals.Dataset`.

## Loading from files

Suites are data, so they can live in YAML or JSON:

```yaml
# evals/smoke.yaml
name: smoke
cases:
  - name: adds
    input: what is 2+2?
    expect: "4"
  - name: uses the calendar tool
    input: book a slot
    calls: create_event
```

```python
suite = EvalSuite.from_file("evals/smoke.yaml")
report = await suite.run(app)
```

## Running in CI

```bash
agentkit eval evals/smoke.yaml --bootstrap bootstrap:app
```

The command boots the app, runs the suite, prints the summary, and exits non-zero
on any failure.

## Deterministic evaluation

Use a PydanticAI `FunctionModel` to make evals fast, free, and offline:

```python
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart

app._model = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("4")]))
report = await EvalSuite([Case("adds", input="2+2?", expect="4")]).run(app)
```

::: tip Evaluate behaviour, not wording
Prefer `calls`/`contains` over exact `expect` where a model may phrase things
differently; reserve `expect` for deterministic or JSON outputs.
:::

Continue to [Testing →](/guide/testing)

## Reporters & trajectory assertions

Reports render through a **reporter** driver (`EVALS_REPORTER_DRIVER`): `text`
(default), `json` (machine-readable), or `pydantic` (the rich table).

```python
report = await suite.run(app)
print(app.eval_reporter.render(report))
```

Assert a run's tool-call trajectory directly:

```python
from agentkit.evals import assert_trajectory

assert_trajectory(result, calls=["search"], forbid=["delete"], order=["search", "publish"])
```

See [Contracts & Drivers](/guide/drivers).
