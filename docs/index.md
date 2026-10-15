---
layout: home
title: agentkit
description: Build, run, and ship durable AI agents in Python.
---

<section class="ak-hero">
  <FeralGradient />
  <div class="ak-hero-inner">
    <div class="ak-hero-copy">
      <p class="ak-eyebrow">Python · PydanticAI · DBOS</p>
      <h1 class="ak-hero-title">
        Build, run, and ship
        <span class="ak-grad">durable AI agents</span>.
      </h1>
      <p class="ak-hero-tag">
        A batteries-included framework with a Laravel-style developer experience —
        application container, providers, a fluent agent builder, memory, skills,
        RAG, streaming, and production-grade safety. One process, one mental model.
      </p>
      <p class="ak-hero-actions">
        <a class="ak-btn ak-btn-brand" href="/guide/getting-started">Get Started →</a>
        <a class="ak-btn" href="/guide/philosophy">Why agentkit?</a>
        <a class="ak-btn" href="https://github.com/kakalition/agentkit" target="_blank" rel="noreferrer">GitHub</a>
      </p>
      <p class="ak-hero-note">MIT licensed · Runs locally · No hosted account required</p>
    </div>
    <div class="ak-hero-visual">
      <HeroOrb />
    </div>
  </div>
</section>

<section class="ak-section">
  <p class="ak-eyebrow">Everything included</p>
  <h2 class="ak-section-title">One framework, every primitive</h2>
  <p class="ak-section-lede">Stop wiring a dozen libraries together. agentkit gives your agent persistence, memory, retrieval, scheduling, streaming, safety, and an operator UI — behind one coherent, expressive API.</p>
  <StatStrip />
  <BentoGrid />
</section>

<section class="ak-section ak-split">
  <div class="ak-split-copy">
    <p class="ak-eyebrow">Zero to running</p>
    <h2 class="ak-section-title">Scaffold, serve, and inspect</h2>
    <p>
      The CLI is part of the framework: generate providers, tools, channels and
      models; run every channel plus the web UI in one process; drop into a REPL
      against the live app.
    </p>
    <ul class="ak-checks">
      <li><code>agentkit serve</code> — channels, scheduler and web UI</li>
      <li><code>agentkit tinker</code> — a REPL with history and tools</li>
      <li><code>agentkit inspect</code> — agents, tools, channels, config</li>
      <li><code>agentkit make:provider notes</code> — scaffold boilerplate</li>
    </ul>
  </div>
  <Terminal />
</section>

<section class="ak-section">
  <p class="ak-eyebrow">A taste of agentkit</p>
  <h2 class="ak-section-title">Persona, tools, memory and skills — in one chain</h2>
  <p class="ak-section-lede">Declarative, readable, and as easy to test as it is to read.</p>
</section>

```python
from agentkit import Agent, App, AgentSettings

agent = (
    Agent.make("nudge")
    .persona()                              # reads <AGENT_HOME>/SOUL.md
    .instructions("Be warm, concise, and useful.")
    .memory()                               # remember / recall / forget tools
    .skills()                               # discover SKILL.md folders
    .knowledge(path="./docs")               # RAG over your documents
    .output(str)
    .build()
)

app = App(name="nudge", settings=AgentSettings(owner_id="me"))
app.agent(agent).boot()

print(asyncio.run(app.run("remind me to stretch at 5pm")).output)
```

<Marquee />

<section class="ak-section">
  <p class="ak-eyebrow">Familiar by design</p>
  <h2 class="ak-section-title">A concept map for Laravel developers</h2>
</section>

| Laravel | agentkit |
| --- | --- |
| Service container | `App` — `bind`, `singleton`, `make` |
| Service provider | `Provider` — `register`, `boot` |
| Facade | `Memory`, `Schedule`, `DB`, `Events`, `Log`, `Feedback` |
| Artisan | `agentkit` CLI — `make:*`, `serve`, `tinker`, `inspect` |
| Events & listeners | `app.on("turn.end", ...)` |
| Middleware | `app.middleware(...)` over the turn |
| `config/*.php` | `config/<name>.py` + `Section` |
| Eloquent model | `Model` — `where`, `create`, `update`, `paginate` |
| `php artisan serve` | `agentkit serve` |

<section class="ak-cta">
  <h2>Ready to build?</h2>
  <p>Install agentkit and have a durable agent running in minutes.</p>
  <p class="ak-cta-actions">
    <a class="ak-btn ak-btn-brand" href="/guide/getting-started">Get Started →</a>
    <a class="ak-btn" href="/guide/philosophy">Read the philosophy</a>
  </p>
</section>
