# Eval Datasets

An **eval dataset** is a named collection of cases you can run graders against.
Datasets live in the `eval_datasets` table (the `repository` driver) or in process
(the `memory` driver), selected by `dataset_driver`.

## Importing cases

`load_dataset_file` parses CSV, JSON, or JSONL into case dicts:

```python
from agentkit import load_dataset_file

cases = load_dataset_file("cases.csv")   # [{"input": "2+2", "expected": "4"}, …]
```

## Storing and reading them

```python
store = agent.app.manager("dataset").driver()
await store.put("math", cases, source="cases.csv")
await store.cases("math")      # the case list
await store.list()             # all datasets
await store.remove("math")
```

Datasets are owner-scoped, so each tenant sees only their own. Any backend can
implement the `DatasetStore` protocol and register via
`app.extend("dataset", name, factory)`.

## Online scoring

Every run already records `run_events` (for the Studio trace viewer). Those live
traces can be graded with any registered grader — opt in with
`online_scoring_enabled` and choose the grader with `online_scoring_grader`
(default `trace`). With it enabled, **each turn is scored automatically** after its
trace is recorded:

```python
result = await app.online_scorer.score(repos, run_id)   # or score on demand
# {"run_id": …, "passed": True, "score": 1.0, "reason": "", "record_id": 7}
```

The score is written as an `eval_runs` row (dataset `online:<run_id>`), so it shows
up alongside offline runs. A trace can also be scored on demand:

```bash
agentkit evals:score <run_id> --grader=trace
```

or via `POST /api/studio/runs/{run_id}/score`.

Datasets pair with graders and recorded runs (see `agentkit.evals`), so a suite
can be replayed against a new model or prompt and compared over time.
