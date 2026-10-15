# Human-in-the-Loop

## Introduction

Real agents sometimes need a person: to approve a risky action, or to answer a
question before proceeding. agentkit supports both — approvals for tools, and
clarification for the conversation.

## Approvals

Mark a tool as risky and enable approvals on the agent:

```python
agent = (
    Agent.make("desk")
    .instructions("…")
    .approvals()
    .tool(send_email, requires_approval=True)
    .output(str)
    .build()
)
```

When the model calls `send_email`, the run **defers**: nothing happens until a
human decides. The app fires an `approval.asked` event:

```python
app.on("approval.asked", lambda event: print(event.requests))
# event.requests = [{"tool_call_id": "...", "tool_name": "send_email"}]
```

### Deciding

Provide an approval callback to the run, or through the app's surface
(web UI, A2A, or Telegram broker). The callback receives the pending requests and
returns a `{tool_call_id: bool}` mapping:

```python
async def approve(requests):
    return {request.tool_call_id: ask_the_human(request) for request in requests}

result = await app.run("email the team", approve=approve)
```

### Resuming

A deferred run can be resumed later — after an out-of-band decision — with the
results:

```python
result = await app.resume(deferred_tool_results, conversation_id="cli:default")
```

`app.resume(...)` continues the same conversation, so the model picks up where it
paused. This is the pause/resume primitive: a turn can span minutes or days.

## Clarification

Sometimes the agent needs information that only the user has. Add the `ask_user`
tool with `.clarify()` and supply a handler:

```python
agent = Agent.make("desk").instructions("…").clarify().output(str).build()
app.agent(agent).clarify(lambda question, options: ask_the_user(question))
```

The model can now call `ask_user`:

```python
ask_user(question="Which city?", options=["Lisbon", "London"])
```

- **With a handler** — the tool returns the human's answer and the turn continues.
- **Without a handler** — the tool returns guidance telling the model to ask the
  question directly in its reply, so the turn still completes cleanly.

```python
from agentkit import Clarification

clarification = Clarification(question="Which city?", options=["Lisbon"])
```

## A Telegram-like flow

```python
def handler(question, options):
    return broker.ask_sync(chat_id, question, options)

app.clarify(handler)

app.on("approval.asked", lambda event: broker.request(chat_id, event.requests))
app.on("turn.end", lambda event: broker.reply(chat_id, event.output))
```

## Design notes

- **Nothing runs without consent.** A deferred tool has not executed; refusing is
  safe.
- **State is durable.** Deferrals and resumes are built on PydanticAI's
  `deferred_tool_results` and the persisted message history, so a restart does not
  lose a pending approval.
- **Clarification is not a failure.** When no human is reachable, the agent asks in
  its reply rather than erroring.

Continue to [Planning & Graphs →](/guide/planning)
