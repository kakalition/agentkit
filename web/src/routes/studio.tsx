import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Code2, Play, Plus, Save, Trash2, Zap } from "lucide-react"
import { useMemo, useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import type { TeamDefinition, TeamMember, TeamRun } from "@/lib/api"
import { PanelHost } from "@/lib/panel-host"
import { AppInspector, TracesView } from "@/lib/studio-panels"

const EMPTY: TeamDefinition = {
  name: "",
  kind: "groupchat",
  members: [{ name: "a", description: "", capabilities: [] }],
  speaker: "round_robin",
  moderator: null,
  manual_order: [],
  max_turns: 12,
  max_rounds: 8,
  instructions: null,
}

const PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
]

function FlowGraph({ turns }: { turns: { speaker: string; text: string }[] }) {
  const speakers = useMemo(() => {
    const seen: string[] = []
    for (const turn of turns) if (!seen.includes(turn.speaker)) seen.push(turn.speaker)
    return seen
  }, [turns])

  const edges = useMemo(() => {
    const counts = new Map<string, number>()
    for (let i = 1; i < turns.length; i += 1) {
      const key = `${turns[i - 1].speaker}\u0000${turns[i].speaker}`
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return [...counts.entries()].map(([key, count]) => {
      const [from, to] = key.split("\u0000")
      return { from, to, count }
    })
  }, [turns])

  const W = 520
  const H = 340
  const cx = W / 2
  const cy = H / 2
  const radius = Math.max(70, Math.min(W, H) / 2 - 70)
  const n = speakers.length
  const NODE_R = 24

  const pos = (name: string) => {
    const i = speakers.indexOf(name)
    if (n <= 1) return { x: cx, y: cy }
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) }
  }
  const color = (name: string) => PALETTE[speakers.indexOf(name) % PALETTE.length] ?? PALETTE[0]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      <defs>
        <marker
          id="flow-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--muted-foreground)" />
        </marker>
      </defs>
      {edges.map((edge) => {
        const a = pos(edge.from)
        const b = pos(edge.to)
        if (edge.from === edge.to) {
          return (
            <g key={`${edge.from}->${edge.to}`}>
              <circle
                cx={a.x}
                cy={a.y - NODE_R - 12}
                r={11}
                fill="none"
                stroke="var(--muted-foreground)"
                markerEnd="url(#flow-arrow)"
              />
              {edge.count > 1 ? (
                <text
                  x={a.x}
                  y={a.y - NODE_R - 28}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[10px]"
                >
                  {edge.count}
                </text>
              ) : null}
            </g>
          )
        }
        const dx = b.x - a.x
        const dy = b.y - a.y
        const len = Math.hypot(dx, dy) || 1
        const ux = dx / len
        const uy = dy / len
        const sx = a.x + ux * NODE_R
        const sy = a.y + uy * NODE_R
        const ex = b.x - ux * NODE_R
        const ey = b.y - uy * NODE_R
        const qx = (sx + ex) / 2 - uy * 16
        const qy = (sy + ey) / 2 + ux * 16
        return (
          <g key={`${edge.from}->${edge.to}`}>
            <path
              d={`M ${sx} ${sy} Q ${qx} ${qy} ${ex} ${ey}`}
              fill="none"
              stroke="var(--muted-foreground)"
              markerEnd="url(#flow-arrow)"
            />
            {edge.count > 1 ? (
              <text x={qx} y={qy} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                {edge.count}
              </text>
            ) : null}
          </g>
        )
      })}
      {speakers.map((name) => {
        const p = pos(name)
        return (
          <g key={name}>
            <circle cx={p.x} cy={p.y} r={NODE_R} fill={color(name)} opacity={0.85} />
            <text
              x={p.x}
              y={p.y + 4}
              textAnchor="middle"
              className="fill-background text-[11px] font-medium"
            >
              {name.length > 9 ? `${name.slice(0, 8)}…` : name}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function ResultView({ run }: { run: TeamRun }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="secondary">{run.kind}</Badge>
        <span className="text-muted-foreground">
          {run.transcript.length} messages · {run.rounds} rounds
        </span>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Message flow</CardTitle>
        </CardHeader>
        <CardContent>
          <FlowGraph turns={run.transcript} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Transcript</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {run.transcript.map((turn, index) => (
            <div key={index} className="rounded-md border p-2 text-sm">
              <span className="text-muted-foreground mr-2 font-mono text-xs">{turn.speaker}</span>
              <span className="whitespace-pre-wrap">{turn.text}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      {run.ledger ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Ledger</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <div className="text-muted-foreground text-xs uppercase">Plan</div>
              <ul className="list-disc pl-5">
                {run.ledger.plan.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Facts</div>
              <ul className="list-disc pl-5">
                {run.ledger.facts.map((fact, index) => (
                  <li key={index}>{fact}</li>
                ))}
              </ul>
            </div>
            <div>
              <div className="text-muted-foreground text-xs uppercase">Tasks</div>
              <ul className="space-y-1">
                {run.ledger.tasks.map((task) => (
                  <li key={task.id} className="flex items-center gap-2">
                    <Badge variant={task.status === "done" ? "secondary" : "outline"}>
                      {task.status}
                    </Badge>
                    <span>
                      #{task.id} {task.description}
                      {task.owner ? ` (${task.owner})` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Output</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto text-xs whitespace-pre-wrap">{run.output}</pre>
        </CardContent>
      </Card>
    </div>
  )
}

export default function Studio() {
  const queryClient = useQueryClient()
  const teams = useQuery({ queryKey: ["studio", "teams"], queryFn: api.studioTeams })
  const [draft, setDraft] = useState<TeamDefinition>(EMPTY)
  const [selected, setSelected] = useState<string | null>(null)
  const [json, setJson] = useState("")
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [code, setCode] = useState<string | null>(null)
  const [prompt, setPrompt] = useState("Describe the task for the team.")
  const [run, setRun] = useState<TeamRun | null>(null)

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["studio", "teams"] })

  const save = useMutation({
    mutationFn: () => api.saveStudioTeam(sanitize(draft)),
    onSuccess: () => {
      setSelected(draft.name)
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (name: string) => api.deleteStudioTeam(name),
    onSuccess: () => {
      setSelected(null)
      setDraft(EMPTY)
      refresh()
    },
  })
  const activate = useMutation({
    mutationFn: (name: string) => api.activateStudioTeam(name),
    onSuccess: refresh,
  })
  const showCode = useMutation({
    mutationFn: (name: string) => api.studioTeamCode(name),
    onSuccess: (data) => setCode(data.code),
  })
  const runTeam = useMutation({
    mutationFn: (name: string) => api.runStudioTeam(name, prompt),
    onSuccess: setRun,
  })

  const patch = (values: Partial<TeamDefinition>) => setDraft((current) => ({ ...current, ...values }))
  const patchMember = (index: number, values: Partial<TeamMember>) =>
    setDraft((current) => ({
      ...current,
      members: current.members.map((member, i) => (i === index ? { ...member, ...values } : member)),
    }))
  const addMember = () =>
    setDraft((current) => ({
      ...current,
      members: [...current.members, { name: `member${current.members.length + 1}`, description: "", capabilities: [] }],
    }))
  const removeMember = (index: number) =>
    setDraft((current) => ({ ...current, members: current.members.filter((_, i) => i !== index) }))

  const load = (name: string) => {
    const team = teams.data?.teams.find((entry) => entry.name === name)
    if (!team) return
    setSelected(name)
    setDraft({
      name: team.name,
      kind: team.kind,
      members: team.members,
      speaker: team.speaker,
      moderator: team.moderator,
      manual_order: team.manual_order,
      max_turns: team.max_turns,
      max_rounds: team.max_rounds,
      instructions: team.instructions,
    })
    setCode(null)
    setRun(null)
    setJsonError(null)
  }

  const error = teams.error ?? save.error ?? remove.error ?? activate.error ?? runTeam.error

  return (
    <Page title="Studio" description="Build, run, and export declarative multi-agent teams.">
      <ErrorAlert error={error} />

      <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm">Teams</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSelected(null)
                setDraft(EMPTY)
                setCode(null)
                setRun(null)
              }}
            >
              <Plus className="size-4" /> New
            </Button>
          </CardHeader>
          <CardContent className="space-y-1">
            {teams.data?.teams.length ? (
              teams.data.teams.map((team) => (
                <button
                  key={team.name}
                  onClick={() => load(team.name)}
                  className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent ${
                    selected === team.name ? "bg-accent" : ""
                  }`}
                >
                  <span>{team.name}</span>
                  <span className="flex items-center gap-1">
                    {team.registered ? <Zap className="size-3 text-amber-500" /> : null}
                    <Badge variant="secondary" className="text-[10px]">
                      {team.kind}
                    </Badge>
                  </span>
                </button>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">No saved teams yet.</p>
            )}
          </CardContent>
        </Card>

        <Tabs defaultValue="builder">
          <TabsList>
            <TabsTrigger value="builder">Builder</TabsTrigger>
            <TabsTrigger value="json">JSON</TabsTrigger>
            <TabsTrigger value="code">Python</TabsTrigger>
            <TabsTrigger value="playground">Playground</TabsTrigger>
            <TabsTrigger value="app">App</TabsTrigger>
            <TabsTrigger value="traces">Traces</TabsTrigger>
            <TabsTrigger value="panels">Panels</TabsTrigger>
          </TabsList>

          <TabsContent value="builder" className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Definition</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor="team-name">Name</Label>
                    <Input
                      id="team-name"
                      value={draft.name}
                      onChange={(event) => patch({ name: event.target.value })}
                      placeholder="squad"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="team-kind">Kind</Label>
                    <select
                      id="team-kind"
                      className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                      value={draft.kind}
                      onChange={(event) => patch({ kind: event.target.value })}
                    >
                      {(teams.data?.kinds ?? ["groupchat", "supervisor", "managed"]).map((kind) => (
                        <option key={kind} value={kind}>
                          {kind}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="team-speaker">Speaker</Label>
                    <select
                      id="team-speaker"
                      className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                      value={draft.speaker}
                      onChange={(event) => patch({ speaker: event.target.value })}
                    >
                      {(
                        teams.data?.speakers ?? ["round_robin", "moderator", "all", "selector", "manual"]
                      ).map((speaker) => (
                        <option key={speaker} value={speaker}>
                          {speaker}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="team-moderator">Moderator</Label>
                    <select
                      id="team-moderator"
                      className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                      value={draft.moderator ?? ""}
                      onChange={(event) => patch({ moderator: event.target.value || null })}
                    >
                      <option value="">(first member)</option>
                      {draft.members.map((member) => (
                        <option key={member.name} value={member.name}>
                          {member.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="team-turns">Max turns</Label>
                    <Input
                      id="team-turns"
                      type="number"
                      value={draft.max_turns}
                      onChange={(event) => patch({ max_turns: Number(event.target.value) })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="team-rounds">Max rounds</Label>
                    <Input
                      id="team-rounds"
                      type="number"
                      value={draft.max_rounds}
                      onChange={(event) => patch({ max_rounds: Number(event.target.value) })}
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="team-instructions">Instructions</Label>
                  <Textarea
                    id="team-instructions"
                    rows={2}
                    value={draft.instructions ?? ""}
                    onChange={(event) => patch({ instructions: event.target.value || null })}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <CardTitle className="text-sm">Members</CardTitle>
                <Button size="sm" variant="outline" onClick={addMember}>
                  <Plus className="size-4" /> Add member
                </Button>
              </CardHeader>
              <CardContent className="space-y-3">
                {draft.members.map((member, index) => (
                  <div key={index} className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]">
                    <Input
                      value={member.name}
                      onChange={(event) => patchMember(index, { name: event.target.value })}
                      placeholder="name"
                    />
                    <Input
                      value={member.description}
                      onChange={(event) => patchMember(index, { description: event.target.value })}
                      placeholder="description"
                    />
                    <Button variant="ghost" size="icon" onClick={() => removeMember(index)}>
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
              </CardContent>
            </Card>

            <div className="flex flex-wrap gap-2">
              <Button onClick={() => save.mutate()} disabled={!draft.name || save.isPending}>
                <Save className="size-4" /> {selected ? "Update" : "Create"}
              </Button>
              {selected ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => activate.mutate(selected)}
                    disabled={activate.isPending}
                  >
                    <Zap className="size-4" /> Activate
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => remove.mutate(selected)}
                    disabled={remove.isPending}
                  >
                    <Trash2 className="size-4" /> Delete
                  </Button>
                </>
              ) : null}
            </div>
          </TabsContent>

          <TabsContent value="json" className="space-y-3">
            <p className="text-muted-foreground text-sm">
              Edit the definition JSON and apply it to the builder, or export the current draft.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setJson(JSON.stringify(draft, null, 2))}>
                Export current
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(json) as TeamDefinition
                    setDraft(parsed)
                    setJsonError(null)
                  } catch (err) {
                    setJsonError(err instanceof Error ? err.message : "invalid JSON")
                  }
                }}
              >
                Apply JSON
              </Button>
            </div>
            {jsonError ? <p className="text-destructive text-sm">{jsonError}</p> : null}
            <Textarea
              rows={18}
              className="font-mono text-xs"
              value={json}
              onChange={(event) => setJson(event.target.value)}
              placeholder='{ "name": "squad", "kind": "groupchat", "members": [] }'
            />
          </TabsContent>

          <TabsContent value="code" className="space-y-3">
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => selected && showCode.mutate(selected)}
                disabled={!selected || showCode.isPending}
              >
                <Code2 className="size-4" /> Generate Python
              </Button>
            </div>
            {selected ? null : (
              <p className="text-muted-foreground text-sm">Save and select a team to export it.</p>
            )}
            {code ? (
              <pre className="overflow-x-auto rounded-lg border p-3 text-xs">{code}</pre>
            ) : null}
          </TabsContent>

          <TabsContent value="playground" className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Run</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Textarea rows={2} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
                <Button
                  onClick={() => selected && runTeam.mutate(selected)}
                  disabled={!selected || runTeam.isPending || !prompt.trim()}
                >
                  <Play className="size-4" /> {runTeam.isPending ? "Running…" : "Run team"}
                </Button>
                {selected ? null : (
                  <p className="text-muted-foreground text-sm">
                    Save a team (members resolve from the agent registry in code; unregistered
                    members reply with a placeholder).
                  </p>
                )}
              </CardContent>
            </Card>
            {run ? <ResultView run={run} /> : null}
          </TabsContent>

          <TabsContent value="app" className="space-y-4">
            <AppInspector />
          </TabsContent>

          <TabsContent value="traces" className="space-y-4">
            <TracesView />
          </TabsContent>

          <TabsContent value="panels" className="space-y-4">
            <PanelHost />
          </TabsContent>
        </Tabs>
      </div>
    </Page>
  )
}

function sanitize(definition: TeamDefinition): TeamDefinition {
  const names = definition.members.map((member) => member.name)
  return {
    ...definition,
    moderator: definition.moderator && names.includes(definition.moderator) ? definition.moderator : null,
    manual_order: definition.manual_order.filter((name) => names.includes(name)),
  }
}
