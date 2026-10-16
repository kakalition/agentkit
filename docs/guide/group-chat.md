# Group Chat & Teams

## Introduction

agentkit runs multi-agent conversations two ways: a **group chat** (a speaker
strategy picks who talks next over a shared transcript) and a **manager-led team**
with a shared ledger. Both are ordinary subsystems — a contract, a `Manager`,
drivers selected by settings, and conformance tests.

## Speaker strategies

A `SpeakerStrategy` answers "who speaks next?" given the roster and transcript.
Selected with `speaker_driver`:

| Driver | Behavior |
| --- | --- |
| `round_robin` | rotate one speaker per turn (default) |
| `moderator` | always ask a designated moderator |
| `all` | ask everyone; collect replies |
| `selector` | ask the model to pick the next speaker |
| `manual` | follow an explicit order |

```bash
SPEAKER_DRIVER=selector
```

## The group-chat runner

```python
from agentkit import GroupChatRunner, RoundRobinSpeaker

runner = GroupChatRunner(
    {"researcher": researcher, "writer": writer},
    speaker=RoundRobinSpeaker(),
    max_turns=6,
)
result = await runner.run("draft the announcement")
print(result.output)         # the last reply
for turn in result.transcript:
    print(turn["speaker"], turn["text"])
```

Roster members may be local agents, `AgentHandle`s, or async callables
`(prompt) -> reply`. The loop ends on the max-turns cap, a `terminator` callback,
consensus, or an empty selection. Each reply emits an `agent.message` event.

`GroupChatTopology` (see [Agent Communication](/guide/agent-communication))
delegates to the runner via `topology.run(task)`.

## Manager-led teams (ledger)

A `ManagedTeam` keeps a `TeamLedger` of facts, a plan, and a task list across
rounds, and replans when a member stalls.

```python
from agentkit import ManagedTeam, register_team

team = ManagedTeam(
    {"planner": planner, "coder": coder, "reviewer": reviewer},
    manager=lambda ledger, stalled: ["reframe the task", "assign a reviewer"],
    max_rounds=8,
)
result = await team.run("ship the feature")
print(result.ledger.render())
```

## Named team presets

Register a roster once and reuse it from any agent:

```python
from agentkit import register_team
from agentkit import Agent

register_team("squad", {"researcher": researcher, "writer": writer}, kind="groupchat")

agent = Agent.make("lead").team("squad").output(str)
```

`Agent.team("squad")` attaches a namespaced `team_squad(prompt)` tool. The kinds
are `groupchat`, `supervisor`, and `managed`. `agentkit inspect` lists the
registered teams.
