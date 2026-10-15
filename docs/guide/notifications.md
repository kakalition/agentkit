# Notifications

## Introduction

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

## Drivers

### What a notification channel is, in plain English

A **notification** is the *content* — the message itself ("Your reminder is
due"). A **channel** is the *pipe* that delivers it. Think of a school
notice: the announcement is written once, then it goes out over the loudspeaker,
onto the noticeboard, and into an email — same words, different pipes. You write
the message once and let each channel decide how to deliver it.

agentkit has **two** driver kinds here, and they are easy to confuse:

- **`notification_channel`** — how a notification is *rendered and sent* when you
  call `app.notify(...)`. The built-ins are `log` (write it to the structured
  log), `conversation` (append it to the chat history so it shows in the web UI),
  and `telegram`.
- **`channel`** — the *chat transport* itself: the gateway the agent uses to talk
  to a person (Telegram, Slack, email, Discord). This is the pipe, not the
  message.

In short: a notification channel turns your message into something, and a chat
channel is where conversation messages travel.

::: tip One message, many destinations
A notification declares its own `channels`, and `app.notify(..., to=[...])` can
override them per send. The same notification object can be logged *and* written
into the conversation *and* pushed to Slack from a single call.
:::

### A runnable example

```python
from agentkit import App, Notification

app = App()   # reads NOTIFICATION_CHANNEL_DRIVER / CHANNEL_DRIVER from env / .env

class ReminderDue(Notification):
    channels = ("log",)                 # fallback channels for this notification

    def __init__(self, text: str) -> None:
        self.message = text

    def to_log(self) -> str:            # how it renders on the log channel
        return f"Reminder: {self.message}"

    def to_conversation(self) -> str:   # how it renders in the chat history
        return f"Reminder: {self.message}"

# 1. Default behavior: NOTIFICATION_CHANNEL_DRIVER=log -> structured log only.
sent = app.notify(ReminderDue("stretch"))
print(sent)   # -> [SentNotification(channel='log', ...)]

# 2. Send the same notification to more channels for this call only.
app.notify(ReminderDue("stretch"), to=["log", "conversation"], conversation_id="cli:1")

# 3. Switch the default driver by setting an env var and rebuilding the app:
#    NOTIFICATION_CHANNEL_DRIVER=conversation  (default channel = chat history)
#    CHANNEL_DRIVER=slack                      (chat transport for conversations)
```

### Built-in drivers

**Notification channels** (`NOTIFICATION_CHANNEL_DRIVER`):

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `log` (default) | Writes the notification to the structured log; delivers nothing externally. | Local development, or when you only want a durable trace of what was sent. |
| `conversation` | Appends the notification as an assistant message into the chat history, so it appears in the web UI and in the owner's next turn. Requires a `conversation_id`. | To surface a message inside a conversation the person is already reading. |
| `telegram` | Delivers through a Telegram sender you plug in with `app.notifier.channel("telegram", sender)`; logs instead when no sender is configured. | To push notifications to Telegram. |

**Chat transports** (`CHANNEL_DRIVER`):

| Driver | What it does | When to pick it |
| --- | --- | --- |
| `log` (default) | Logs every outbound message and delivers nothing. | The safe default: run the agent locally without sending anything. |
| `telegram` | The real Telegram gateway (needs a bot token). | To chat with the agent over Telegram. |
| `slack` | The Slack gateway (Socket Mode; needs the `slack` extra). | To chat with the agent in Slack. |
| `email` | The email gateway. | To send and receive over email. |
| `discord` | The Discord gateway (needs the `discord` extra). | To chat with the agent in Discord. |

### How to select a driver

```bash
NOTIFICATION_CHANNEL_DRIVER=log   # log | conversation | telegram
CHANNEL_DRIVER=log                # log | telegram | slack | email | discord
```

Selection follows the standard precedence: an explicit name passed in code
(`app.manager(kind).driver("telegram")`), then the setting, then the default
(`log` for both). `agentkit inspect` prints the resolved values.

### Override it just for your app

`app.extend(...)` registers a driver scoped to this application only:

```python
app.extend(DriverKind.NOTIFICATION_CHANNEL, "pagerduty", factory)
app.extend(DriverKind.CHANNEL, "matrix", factory)
```

Then select it with `NOTIFICATION_CHANNEL_DRIVER=pagerduty` or
`CHANNEL_DRIVER=matrix`.

### Ship a reusable driver

Register it globally so any app can use it:

```python
from agentkit import DriverKind, register_driver

@register_driver(DriverKind.NOTIFICATION_CHANNEL, "pagerduty")
def _pagerduty(app):
    return PagerDutyNotificationChannel(app.notifier)
```

A notification-channel driver implements `send(notification, *, conversation_id=None)`
and returns an optional detail string. See [Contracts & Drivers](/guide/drivers).

### Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `app.notify(...)` returned nothing and no message arrived | The default `log` channel only writes to the structured log; it never delivers externally. |
| A `conversation` notification is missing from history | No `conversation_id` was passed, so the channel returns an empty detail. |
| Warning `no notifier channel 'x'; skipping` | That channel name was never registered — add it with `app.notifier.channel("x", sender)`. |
| `NOTIFICATION_CHANNEL_DRIVER=telegram` still only logs | No real Telegram sender was plugged in via `app.notifier.channel("telegram", sender)`. |
