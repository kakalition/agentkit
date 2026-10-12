# Context Compaction

Long conversations eventually exceed the model's context window. Naively
summarising everything older, or dropping it, loses facts the model still needs.
agentkit ships a **tiered, rolling** compactor that shrinks aggressively while
keeping enough context to continue coherently.

## The problem

Two failure modes dominate simple approaches:

- **Summarise-all**: every turn re-summarises the whole history — expensive, and
  summaries erode as they are re-compressed.
- **Truncate**: the oldest turns vanish, taking decisions and identifiers with
  them.

## The `Compactor`

```python
from agentkit import Compactor

app.history_processor(Compactor(max_tokens=8000, keep_recent=0.45))
# shorthand:
app.compact(max_tokens=8000)
```

It sorts the history into three tiers:

1. **Pinned** — short user messages carrying a durable fact, constraint, or
   identifier, kept **verbatim**.
2. **Verbatim recent** — the newest messages, up to a share of the token budget,
   so the conversation still reads naturally.
3. **Folded** — everything else, extracted into a structured summary and then
   dropped.

## Structured, rolling memory

The folded summary is not a free-form blob. It has fixed sections, rendered back
in priority order until the summary budget is spent — so under pressure the model
keeps the objective and facts, and loses only the chatter:

```
Objective          what the user is working toward
Facts              names, ids, paths, numbers
Constraints        "always…", "never…", preferences
Decisions          what was agreed
Tool results       outcomes worth not recomputing
Open threads       unanswered questions
Recent history     a brief timeline
```

Only **newly dropped** messages are folded in each turn and merged (deduped), so
compaction stays cheap and the summary does not drift.

## Heuristic vs. model-based

By default the compactor uses a fast offline **heuristic** extractor. Pass a model
for higher-quality extraction:

```python
app.history_processor(Compactor(max_tokens=8000, model=my_model))
```

Or inject your own summariser (sync or async):

```python
def summarise(previous_summary: str, transcript: str) -> dict[str, list[str]]:
    return {"decisions": extract_decisions(transcript)}

app.history_processor(Compactor(summarize=summarise, max_tokens=8000))
```

## Tuning

| Option | Default | Meaning |
| --- | --- | --- |
| `max_tokens` | `8000` | compact once the estimated total exceeds this |
| `keep_recent` | `0.45` | share of the budget kept verbatim |
| `pinned_token_ratio` | `0.2` | share reserved for pinned messages |
| `summary_token_ratio` | `0.25` | share reserved for the structured summary |
| `section_cap` | `24` | maximum items retained per section |

Token estimation uses `tiktoken` when available, falling back to a ~4-chars/token
estimate.

## Simpler alternatives

If you want something blunt:

```python
from agentkit.compaction import summarize_older, truncating_processor

app.history_processor(summarize_older(keep_recent=8, threshold=24))
app.history_processor(truncating_processor(max_messages=20))
```

## Introspection

```python
compactor = Compactor(max_tokens=8000)
app.history_processor(compactor)

# after a few turns:
print(compactor.summary)     # the current structured memory
compactor.reset()            # forget the rolling summary
```

Continue to [Streaming →](/guide/streaming)
