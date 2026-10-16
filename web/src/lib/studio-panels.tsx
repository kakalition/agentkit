import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ListItem } from "@/components/list-item"
import { ErrorAlert } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { api } from "@/lib/api"

/** The Studio "App" panel: inspect the live internal app (agents, comms, teams). */
export function AppInspector() {
  const app = useQuery({ queryKey: ["studio", "app"], queryFn: api.studioApp })
  if (app.isLoading) return <p className="text-muted-foreground text-sm">Loading…</p>
  if (app.error) return <ErrorAlert error={app.error} />
  const data = app.data
  if (!data) return null
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Primary agent</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{data.agent?.name ?? data.name}</Badge>
            {data.model ? (
              <span className="text-muted-foreground font-mono text-xs">{data.model}</span>
            ) : null}
            {data.posture ? <Badge variant="outline">{data.posture}</Badge> : null}
          </div>
          {data.agent?.description ? (
            <p className="text-muted-foreground">{data.agent.description}</p>
          ) : null}
          <div>
            <div className="text-muted-foreground text-xs uppercase">
              Tools ({data.agent?.tools.length ?? 0})
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {(data.agent?.tools ?? []).map((tool) => (
                <Badge key={tool} variant="outline" className="font-mono text-[10px]">
                  {tool}
                </Badge>
              ))}
              {data.agent?.tools.length ? null : (
                <span className="text-muted-foreground text-xs">none</span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Comms &amp; runtime</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {(["comms", "speaker", "graph"] as const).map((kind) => (
              <div key={kind} className="flex items-center justify-between">
                <span className="text-muted-foreground">{kind}</span>
                <span className="font-mono text-xs">{data[kind]?.driver ?? "—"}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Agents ({data.agents.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {data.agents.length ? (
              data.agents.map((agent) => (
                <div key={agent.name} className="flex items-center justify-between">
                  <span>{agent.name}</span>
                  <span className="flex flex-wrap gap-1">
                    {agent.capabilities.map((cap) => (
                      <Badge key={cap} variant="outline" className="text-[10px]">
                        {cap}
                      </Badge>
                    ))}
                    {agent.remote ? <Badge variant="secondary">remote</Badge> : null}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">No peer agents registered.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Teams ({data.teams.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {data.teams.length ? (
              data.teams.map((team) => (
                <div key={team.name} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span>{team.name}</span>
                    <Badge variant="secondary" className="text-[10px]">
                      {team.kind}
                    </Badge>
                  </div>
                  <div className="text-muted-foreground font-mono text-xs">
                    {team.roster.join(", ") || "(no roster)"}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">No live teams registered.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Specs &amp; extensions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {data.specs_kinds.map((kind) => (
              <div key={kind} className="flex items-center justify-between">
                <span className="text-muted-foreground">{kind}</span>
                <span className="font-mono text-xs">
                  {(data.specs[kind] ?? []).join(", ") || "—"}
                </span>
              </div>
            ))}
            {data.extensions.length ? (
              data.extensions.map((extension) => (
                <div key={String(extension.name)} className="flex items-center justify-between">
                  <span>{String(extension.name)}</span>
                  <span className="font-mono text-xs">{String(extension.version ?? "")}</span>
                </div>
              ))
            ) : (
              <p className="text-muted-foreground text-xs">No extensions loaded.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/** The Studio "Traces" panel: browse recorded runs, their events, and checkpoints. */
export function TracesView() {
  const [selected, setSelected] = useState<string | null>(null)
  const runs = useQuery({ queryKey: ["studio", "runs"], queryFn: () => api.studioRuns(50) })
  const events = useQuery({
    queryKey: ["studio", "run", selected],
    queryFn: () => api.studioRun(selected as string),
    enabled: selected !== null,
  })
  const checkpoints = useQuery({
    queryKey: ["studio", "checkpoints", selected],
    queryFn: () => api.checkpoints(selected as string),
    enabled: selected !== null,
  })
  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Runs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {runs.data?.runs.length ? (
            runs.data.runs.map((run) => (
              <ListItem
                key={run.run_id}
                active={selected === run.run_id}
                onSelect={() => setSelected(run.run_id)}
              >
                <span className="truncate font-mono text-xs">{run.run_id}</span>
                <Badge variant="secondary" className="text-[10px]">
                  {run.events}
                </Badge>
              </ListItem>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">No traces yet. Run a chat or team.</p>
          )}
        </CardContent>
      </Card>
      <div className="min-w-0 space-y-4">
        <ErrorAlert error={runs.error ?? events.error ?? checkpoints.error} />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Events</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {events.data?.events.length ? (
              events.data.events.map((event) => (
                <div key={event.seq} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                  <Badge
                    variant={event.kind === "error" ? "destructive" : "secondary"}
                    className="text-[10px]"
                  >
                    {event.kind}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <div className="text-muted-foreground font-mono text-[10px]">
                      #{event.seq}
                      {event.tool ? ` tool=${event.tool}` : ""}
                    </div>
                    {event.text ? (
                      <div className="whitespace-pre-wrap break-words">{event.text}</div>
                    ) : null}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">
                {selected
                  ? "No events recorded for this run."
                  : "Select a run to inspect its trace."}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Checkpoints ({checkpoints.data?.checkpoints.length ?? 0})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {checkpoints.data?.checkpoints.length ? (
              checkpoints.data.checkpoints.map((checkpoint) => (
                <Collapsible
                  key={String(checkpoint.seq)}
                  className="rounded-md border p-2 text-sm"
                >
                  <CollapsibleTrigger className="flex w-full cursor-pointer items-center gap-1 text-left">
                    <span className="text-muted-foreground font-mono text-xs">
                      #{String(checkpoint.seq)}
                    </span>{" "}
                    {String(checkpoint.label ?? "")}
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <pre className="mt-2 overflow-x-auto text-xs">
                      {JSON.stringify(checkpoint.state, null, 2)}
                    </pre>
                  </CollapsibleContent>
                </Collapsible>
              ))
            ) : (
              <p className="text-muted-foreground text-sm">
                No checkpoints (enable <code>CHECKPOINTS_ENABLED</code> to record run state).
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
