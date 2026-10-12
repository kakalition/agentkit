# Notifications

A **notification** is a message your agent sends over one or more channels — the
notification bell for an agent. Define the message once and deliver it anywhere.

```python
from agentkit import Notification

class ReminderDue(Notification):
    channels = ("conversation",)

    def __init__(self, text: str) -> None:
        self.message = text

    def to_conversation(self) -> str:
        return f"⏰ Reminder: {self.message}"
```

Send it:

```python
app.notify(ReminderDue("stretch"), conversation_id="cli:1")
```

`app.notify(...)` returns the list of `SentNotification`s (channel + detail).

## Built-in channels

| Channel | What it does |
| --- | --- |
| `log` | writes the message to the structured log |
| `conversation` | appends an assistant message to the chat history (visible in the web UI and the owner's next turn) |
| `telegram` | logs by default; plug in real delivery (below) |

Choose channels per-send or on the notification:

```python
app.notify(ReminderDue("stretch"), to=["log", "conversation"], conversation_id="cli:1")
```

## Custom channels

Register a sender once; then any notification can target it:

```python
app.notifier.channel("telegram", lambda text, conversation_id=None: bot.send(chat_id, text))
app.notifier.channel("slack", send_slack)

app.notify(ReminderDue("stretch"), to="slack")
```

A sender receives the notification (or its text) and returns an optional detail
string.

## Notifications vs. events

| Use | For |
| --- | --- |
| **Notifications** | user-facing messages delivered to a person/channel |
| [Events](/guide/events) | internal lifecycle signals other code observes |

They compose well: a durable task (or an event listener) can raise a notification.

See the Elle example: `app/notifications.py` defines `ReminderDue`, and the
durable delivery task sends it back into the conversation.
