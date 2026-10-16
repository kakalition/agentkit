import { useMutation, useQuery } from "@tanstack/react-query"
import { useState, type ComponentType } from "react"
import { toast } from "sonner"

import { ListItem } from "@/components/list-item"
import { ErrorAlert } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { api, type StudioPanel } from "@/lib/api"
import { CatalogBrowser } from "@/lib/catalog-browser"
import type { JSONSchema } from "@/lib/schema-form"
import { SpecPanel } from "@/lib/spec-panel"
import { TracesView } from "@/lib/studio-panels"

/** Rich, hand-built panels keyed by panel id (fall back to the generic renderer). */
const RICH_PANELS: Record<string, ComponentType> = {
  traces: TracesView,
  catalog: CatalogBrowser,
}

export function PanelHost() {
  const panels = useQuery({ queryKey: ["studio", "panels"], queryFn: api.studioPanels })
  const specs = useQuery({ queryKey: ["studio", "specs"], queryFn: api.studioSpecs })
  const [active, setActive] = useState<string | null>(null)

  const list = panels.data?.panels ?? []
  const current = list.find((panel) => panel.id === active) ?? list[0]

  if (panels.isLoading) return <p className="text-muted-foreground text-sm">Loading panels…</p>
  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Panels</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {list.map((panel) => (
            <ListItem
              key={panel.id}
              active={current?.id === panel.id}
              onSelect={() => setActive(panel.id)}
            >
              <span>{panel.title}</span>
              {panel.spec_kind ? (
                <Badge variant="secondary" className="text-[10px]">
                  {panel.spec_kind}
                </Badge>
              ) : null}
            </ListItem>
          ))}
        </CardContent>
      </Card>

      <div className="min-w-0 space-y-4">
        <ErrorAlert error={panels.error ?? specs.error} />
        {current ? (
          <PanelBody panel={current} schemas={(specs.data?.specs ?? {}) as Record<string, JSONSchema>} />
        ) : null}
      </div>
    </div>
  )
}

function PanelBody({
  panel,
  schemas,
}: {
  panel: StudioPanel
  schemas: Record<string, JSONSchema>
}) {
  const Rich = RICH_PANELS[panel.id]
  if (Rich) return <Rich />
  if (panel.spec_kind && schemas[panel.spec_kind]) {
    return <SpecPanel kind={panel.spec_kind} schema={schemas[panel.spec_kind]} />
  }
  return <ActionPanel panel={panel} />
}

/** Fallback panel: named server-side actions invoked with a JSON body. */
function ActionPanel({ panel }: { panel: StudioPanel }) {
  const [body, setBody] = useState<Record<string, unknown>>({})
  const [text, setText] = useState("{}")
  const action = useMutation({
    mutationFn: (actionId: string) => api.studioAction(actionId, body),
    onSuccess: () => toast.success("Action complete"),
    onError: (error) => toast.error((error as Error).message),
  })
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{panel.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-muted-foreground text-sm">
          {panel.description || "This panel has no spec kind; use its actions."}
        </p>
        {panel.actions.length ? (
          <>
            <Textarea
              rows={4}
              className="font-mono text-xs"
              value={text}
              onChange={(event) => {
                setText(event.target.value)
                try {
                  setBody(JSON.parse(event.target.value || "{}"))
                } catch {
                  /* keep typing */
                }
              }}
            />
            <div className="flex flex-wrap gap-2">
              {panel.actions.map((actionId) => (
                <Button
                  key={actionId}
                  size="sm"
                  variant="outline"
                  onClick={() => action.mutate(actionId)}
                  disabled={action.isPending}
                >
                  {actionId}
                </Button>
              ))}
            </div>
            <ErrorAlert error={action.error} />
            {action.data ? (
              <pre className="overflow-x-auto rounded-lg border p-3 text-xs">
                {JSON.stringify(action.data.result, null, 2)}
              </pre>
            ) : null}
          </>
        ) : (
          <p className="text-muted-foreground text-sm">No actions declared.</p>
        )}
      </CardContent>
    </Card>
  )
}
