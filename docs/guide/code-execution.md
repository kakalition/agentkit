# Code Execution

## Who this page is for

No AI or Python-internals background is assumed. We explain what "letting an agent
run code" means, why it is powerful, and why it is dangerous enough that agentkit
puts a human approval in front of it.

## What "code execution" means here

A normal agent can call the **tools** you give it — small, specific functions like
`add_note` or `search_web`. Sometimes a task is easier to *compute* than to
*describe*: "what's the 40th Fibonacci number?", "parse this CSV and total the
sales column", "rename these files". Instead of you writing forty tools, you let
the model **write a short program** and run it.

That is code execution: the agent produces code, the framework runs it, and the
agent reads the output.

```text
you:   "Total the sales column in sales.csv"
model: run_code("import csv; ...  print(total)")   ->  asks your approval
you:   approve
tool:  runs the snippet, returns "12450"
model: "The total is 12,450."
```

## Why it needs a safety gate

Running code is powerful precisely because it can do *anything* the machine can:
read files, make network calls, delete things. A model that has just read a
malicious web page could be tricked into writing harmful code — this is called a
**prompt injection**, and it is a real, common attack.

agentkit's answer is two layers:

1. **Approval gate.** The `run_code` tool is registered with
   `requires_approval=True`. The very first thing that happens is a request for a
   human "yes". Nothing runs until it is approved. (See
   [Human-in-the-Loop](/guide/hitl).)
2. **Isolation.** *Where* the code runs is a choice you make. The default runs it
   on your machine; stronger drivers run it in a disposable container with no
   access to your files or network.

::: warning Assume the code is hostile
Treat any code the model writes as if a stranger wrote it and asked you to run it.
Keep the approval gate on, and prefer a containerized driver for anything
untrusted.
:::

## Quickstart

```python
from agentkit import Agent

agent = (
    Agent.make("analyst")
    .instructions(
        "Use run_code for arithmetic, parsing, and data work. Keep snippets short."
    )
    .code_execution()        # <-- adds the approval-gated run_code tool
    .output(str)
    .build()
)
```

`.code_execution()` is the same as calling `attach_code_executor(agent)` directly:

```python
from agentkit.executors import attach_code_executor

attach_code_executor(agent)
```

::: tip Off by default
`.full()` does **not** include code execution unless you ask for it: use
`.full(code=True)`. Executing code is a high-trust capability, so it is opt-in.
:::

## The tool

One tool is registered:

```text
run_code(code, language="python", timeout=10) -> {"stdout": ..., "stderr": ..., "exit_code": ...}
```

- `code` — the snippet to run.
- `language` — currently only `python` for the local driver.
- `timeout` — seconds before the run is killed (default 10).

The tool returns the program's **stdout**, **stderr**, and **exit code**, which
the model then uses to answer you. If the snippet errors, the model sees the error
and can fix it and try again.

## Where it runs (drivers)

`CODE_EXECUTOR_DRIVER` selects the executor. Like every other part of agentkit,
this is a swappable [driver](/guide/drivers).

| Driver | Where the code runs | Good for | Needs |
| --- | --- | --- | --- |
| `local` (default) | a subprocess of the current Python interpreter | your own machine, quick utility code | nothing |
| `docker` | inside a fresh container | running untrusted code safely | the `docker` extra + a running Docker daemon |
| `jupyter` | a Jupyter kernel | notebook-style, stateful exploration | the `jupyter` extra |
| `e2b` | a hosted cloud sandbox | zero local setup, strong isolation | the `e2b` extra + an API key |

```bash
CODE_EXECUTOR_DRIVER=local      # default
# CODE_EXECUTOR_DRIVER=docker
```

Heavy drivers are **import-guarded**: selecting one without its extra raises a
`ConfigurationError` that tells you exactly what to install, rather than crashing
at import time.

::: danger The `local` driver is not a sandbox
`local` runs in a child process of your Python interpreter. A child process still
has the same files and network as your program. It is a *convenience*, not a
security boundary. For anything you would not run yourself, use `docker`/`e2b`.
:::

## A complete example

```python
from agentkit import Agent, App, DriverKind
from agentkit.executors import LocalSubprocessExecutor
import asyncio

app = App("coder")

# Choose an executor explicitly (or set CODE_EXECUTOR_DRIVER=<name>):
executor = LocalSubprocessExecutor(default_timeout=5)

async def demo():
    result = await executor.run("print(sum(range(10)))")
    print(result.stdout.strip())   # 45
    print(result.ok)               # True

asyncio.run(demo())
```

## Adding your own executor

An executor only needs one method, `async run(code, *, language, timeout, ...)`,
returning an object with `stdout`, `stderr`, `exit_code`, and `ok`:

```python
from agentkit import DriverKind

app.extend(DriverKind.CODEEXEC, "myrunner", lambda app: MyExecutor())
```

Then select it with `CODE_EXECUTOR_DRIVER=myrunner`. See
[Contracts & Drivers](/guide/drivers) for the full pattern.

## Security checklist

- [ ] Keep the approval gate on (do not bypass it for untrusted input).
- [ ] Prefer `docker`/`e2b` over `local` for anything you did not write.
- [ ] Keep `timeout` small so runaway loops cannot hang the agent.
- [ ] Do not expose secrets as environment variables inside the sandbox.
- [ ] Audit runs — every `run_code` call emits an event and is logged.

## Testing

```python
async def test_runs_and_prints():
    from agentkit.executors import LocalSubprocessExecutor

    result = await LocalSubprocessExecutor().run("print(2 + 2)")
    assert result.ok and "4" in result.stdout


def test_tool_requires_approval():
    from agentkit import Agent

    agent = Agent.make("c").instructions("x").code_execution().output(str).build()
    assert agent._function_toolset.tools["run_code"].requires_approval is True
```

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `ConfigurationError` naming an extra | the chosen driver's package is not installed |
| The snippet times out | increase `timeout`, or the code has an infinite loop |
| `unsupported language` | the `local` driver only runs Python |
| Output is empty but `exit_code` is non-zero | the program wrote to stderr — read `stderr` |
