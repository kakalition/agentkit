import {
  ArrowRight,
  Blocks,
  Brain,
  Check,
  Layers,
  Network,
  ShieldCheck,
  Zap,
} from "lucide-react"
import { Link } from "react-router"

import { Markdown } from "@/components/markdown"
import { Terminal } from "@/components/terminal"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"

const FEATURES = [
  {
    icon: Blocks,
    title: "Declarative agents",
    body: "Compose persona, tools, memory, and skills in one readable chain.",
  },
  {
    icon: Layers,
    title: "An application",
    body: "Container, providers, facades, config sections, and a CLI — not a script.",
  },
  {
    icon: Zap,
    title: "Streaming",
    body: "Token-by-token output to any channel, with usage recorded per turn.",
  },
  {
    icon: Brain,
    title: "Memory & RAG",
    body: "Durable facts plus an embedding-indexed knowledge base out of the box.",
  },
  {
    icon: ShieldCheck,
    title: "Safety",
    body: "Approvals, clarification, moderation, PII scanning, and a hash-chained audit log.",
  },
  {
    icon: Network,
    title: "MCP & A2A",
    body: "Consume MCP toolsets and speak the A2A agent-to-agent protocol.",
  },
]

const STATS = [
  { value: "155", label: "public exports" },
  { value: "279", label: "tests passing" },
  { value: "83%", label: "coverage" },
  { value: "40+", label: "docs pages" },
]

const CHECKS = [
  { code: "agentkit serve", label: "channels, scheduler and web UI" },
  { code: "agentkit tinker", label: "a REPL with history and tools" },
  { code: "agentkit inspect", label: "agents, tools, channels, config" },
  { code: "agentkit make:provider notes", label: "scaffold boilerplate" },
]

const CONCEPTS = [
  ["Service container", "App — bind, singleton, make"],
  ["Service provider", "Provider — register, boot"],
  ["Facade", "Memory, Schedule, DB, Events, Log, Feedback"],
  ["Artisan", "agentkit CLI — make:*, serve, tinker, inspect"],
  ["Events & listeners", 'app.on("turn.end", ...)'],
  ["Middleware", "app.middleware(...) over the turn"],
  ["config/*.php", "config/<name>.py + Section"],
  ["Eloquent model", "Model — where, create, update, paginate"],
  ["php artisan serve", "agentkit serve"],
]

const EXAMPLE = `\`\`\`python
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
\`\`\``

function SectionHeading({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string
  title: string
  lede?: string
}) {
  return (
    <div className="max-w-2xl">
      <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">
        {eyebrow}
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h2>
      {lede ? <p className="mt-4 text-lg text-muted-foreground">{lede}</p> : null}
    </div>
  )
}

export function Landing() {
  return (
    <div>
      <section className="relative overflow-hidden border-b">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_60%_at_50%_0%,var(--muted),transparent)]" />
        <div className="relative mx-auto w-full max-w-[88rem] px-4 py-20 sm:px-6 sm:py-28">
          <div className="mx-auto max-w-4xl text-center">
            <Badge variant="outline" className="font-mono text-xs">
              Python · PydanticAI · DBOS
            </Badge>
            <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
              Build, run, and ship durable AI agents.
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
              A batteries-included framework with a Laravel-style developer experience —
              application container, providers, a fluent agent builder, memory, skills,
              RAG, streaming, and production-grade safety. One process, one mental model.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Button asChild size="lg" className="w-full sm:w-auto">
                <Link to="/guide/getting-started">
                  Get started
                  <ArrowRight data-icon="inline-end" />
                </Link>
              </Button>
              <Button asChild variant="outline" size="lg" className="w-full sm:w-auto">
                <Link to="/guide/philosophy">Why agentkit?</Link>
              </Button>
            </div>
            <p className="mt-5 text-sm text-muted-foreground">
              MIT licensed · Runs locally · No hosted account required
            </p>
          </div>
          <div className="mx-auto mt-14 max-w-2xl">
            <Terminal />
          </div>
        </div>
      </section>

      <section className="border-b">
        <div className="mx-auto w-full max-w-[88rem] px-4 py-20 sm:px-6">
          <SectionHeading
            eyebrow="Everything included"
            title="One framework, every primitive"
            lede="Stop wiring a dozen libraries together. agentkit gives your agent persistence, memory, retrieval, scheduling, streaming, safety, and an operator UI — behind one coherent, expressive API."
          />

          <div className="mt-12 grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => {
              const Icon = feature.icon
              return (
                <div key={feature.title} className="bg-background p-6">
                  <Icon className="size-5 text-foreground" />
                  <h3 className="mt-4 font-medium">{feature.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{feature.body}</p>
                </div>
              )
            })}
          </div>

          <div className="mt-12 grid grid-cols-2 gap-8 sm:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.label}>
                <div className="text-3xl font-semibold tracking-tight">{stat.value}</div>
                <div className="mt-1 text-sm text-muted-foreground">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b">
        <div className="mx-auto grid w-full max-w-[88rem] gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:items-center">
          <div>
            <SectionHeading
              eyebrow="Zero to running"
              title="Scaffold, serve, and inspect"
              lede="The CLI is part of the framework: generate providers, tools, channels and models; run every channel plus the web UI in one process; drop into a REPL against the live app."
            />
            <ul className="mt-8 flex flex-col gap-3">
              {CHECKS.map((check) => (
                <li key={check.code} className="flex items-center gap-3 text-sm">
                  <Check className="size-4 shrink-0 text-muted-foreground" />
                  <code className="rounded-md border bg-muted px-1.5 py-0.5 font-mono text-[13px]">
                    {check.code}
                  </code>
                  <span className="text-muted-foreground">{check.label}</span>
                </li>
              ))}
            </ul>
          </div>
          <Terminal />
        </div>
      </section>

      <section className="border-b">
        <div className="mx-auto w-full max-w-5xl px-4 py-20 sm:px-6">
          <SectionHeading
            eyebrow="A taste of agentkit"
            title="Persona, tools, memory and skills — in one chain"
            lede="Declarative, readable, and as easy to test as it is to read."
          />
          <div className="mt-8">
            <Markdown source={EXAMPLE} />
          </div>
        </div>
      </section>

      <section className="border-b">
        <div className="mx-auto w-full max-w-5xl px-4 py-20 sm:px-6">
          <SectionHeading
            eyebrow="Familiar by design"
            title="A concept map for Laravel developers"
          />
          <div className="mt-8 overflow-hidden rounded-xl border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-left">
                  <th className="px-4 py-2.5 font-medium text-muted-foreground">Laravel</th>
                  <th className="px-4 py-2.5 font-medium text-muted-foreground">agentkit</th>
                </tr>
              </thead>
              <tbody>
                {CONCEPTS.map(([laravel, agentkit]) => (
                  <tr key={laravel} className="border-b last:border-0">
                    <td className="px-4 py-2.5 text-muted-foreground">{laravel}</td>
                    <td className="px-4 py-2.5">
                      <code className="font-mono text-[13px]">{agentkit}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto w-full max-w-[88rem] px-4 py-24 text-center sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
            Ready to build?
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-lg text-muted-foreground">
            Install agentkit and have a durable agent running in minutes.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg" className="w-full sm:w-auto">
              <Link to="/guide/getting-started">
                Get started
                <ArrowRight data-icon="inline-end" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="w-full sm:w-auto">
              <Link to="/guide/philosophy">Read the philosophy</Link>
            </Button>
          </div>
        </div>
      </section>
    </div>
  )
}
