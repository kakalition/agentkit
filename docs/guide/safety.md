# Safety & Moderation

## Introduction

agentkit treats safety as a set of first-class surfaces rather than an
afterthought: tool approvals, policy, prompt-injection scanning, PII redaction,
moderation, secret redaction, egress checks, and a tamper-evident audit log.

## Prompt-injection scanning

Text that enters from tools, MCP resources, or remote agents is untrusted. Scan it
and, when needed, wrap it so the model treats it as data:

```python
from agentkit.guardrails import is_suspicious, scan_injection, wrap_untrusted

signals = scan_injection(tool_result)          # ["ignore previous instructions", …]
if signals:
    tool_result = wrap_untrusted(tool_result, label="web")
```

The `guardrails_hooks()` capability does this for **every tool result** and emits a
`guardrails.injection` event:

```python
from agentkit.foundation.middleware import guardrails_hooks

agent = Agent.make("x").capability(guardrails_hooks()).build()
app.on("guardrails.injection", lambda event: alert(event.tool, event.signals))
```

## PII detection and redaction

```python
from agentkit.guardrails import redact_pii, scan_pii

scan_pii("email ada@example.com")        # ["email"]
redact_pii("call +1 415-555-0142")       # "call [redacted:phone]"
```

Detects emails, phone numbers, SSNs, credit-card numbers, and IBANs.

## Moderation

`ModerationPolicy` combines banned terms, regexes, and PII handling. The middleware
screens each turn's input (and can redact in place); the hooks scan model output.

```python
from agentkit import ModerationPolicy
from agentkit.moderation import moderation_middleware, moderation_hooks

policy = ModerationPolicy(
    banned=["how to make explosives"],
    patterns=[r"\bssn\b"],
    redact_pii=True,
)
app.middleware(moderation_middleware(policy))
agent.capability(moderation_hooks(policy))
```

A blocked input or output raises `ContentBlocked`:

```python
from agentkit.errors import ContentBlocked

try:
    await app.run("…", conversation_id="cli:1")
except ContentBlocked as exc:
    print(exc.detail)      # {"reasons": [...]}
```

## Tool policy and approvals

`ToolPolicy` expresses a model's RBAC once:

```python
from agentkit import ToolPolicy

policy = ToolPolicy(allow={"search", "read_file"})   # deny everything else
agent = Agent.make("safe").instructions("…").policy(policy).build()
```

Risky tools are approved by a human — see [Human-in-the-Loop](/guide/hitl):

```python
agent.tool(send_email, requires_approval=True).approvals()
```

## Secret and amount redaction

Logs are redacted automatically via `agentkit.logging.redact`:

```python
from agentkit.guardrails import redact

redact("api_key=sk-abc123 balance $1,250.00")
```

## Egress (SSRF) checks

Before fetching a URL in a tool, verify it is safe:

```python
from agentkit.guardrails import check_egress

if not check_egress(url, allow_hosts={"api.stripe.com"}):
    raise PermissionDenied("blocked by egress policy")
```

Non-`http(s)` schemes, and private/loopback addresses (unless explicitly allowed),
are rejected.

## The audit log

Record sensitive actions in a **hash-chained** log that can be verified:

```python
async with app.repositories() as repos:
    await repos.audit.append("email.sent", target="email:42", actor="owner")
    assert await repos.audit.verify()
```

Tampering with any entry breaks `verify()`.

## Server exposure

When binding servers beyond loopback, agentkit warns:

```python
from agentkit.guardrails import warn_if_exposed

warn_if_exposed("0.0.0.0", "webui")   # prints a warning to stderr
```

::: danger Do not run untrusted code on the host
The workspace feature is a *workspace*, not an OS sandbox. For untrusted code, run
the agent inside a container or VM.
:::

Continue to [Observability →](/guide/observability)
