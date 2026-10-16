import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Code2, Play, Plus, Save, Trash2 } from "lucide-react"
import { useState } from "react"

import { ErrorAlert } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { defaultFor, SchemaForm, type JSONSchema } from "@/lib/schema-form"

/** The generic spec panel: list + schema-driven editor + run/code actions. */
export function SpecPanel({ kind, schema }: { kind: string; schema: JSONSchema }) {
  const queryClient = useQueryClient()
  const list = useQuery({
    queryKey: ["studio", "spec", kind],
    queryFn: () => api.studioSpecKind(kind),
  })
  const [draft, setDraft] = useState<Record<string, unknown>>(
    () => defaultFor(schema) as Record<string, unknown>,
  )
  const [selected, setSelected] = useState<string | null>(null)
  const [code, setCode] = useState<string | null>(null)
  const [result, setResult] = useState<unknown>(null)
  const [prompt, setPrompt] = useState("")
  const [target, setTarget] = useState("python")

  const refresh = () => queryClient.invalidateQueries({queryKey: ["studio", "spec", kind]})

  const save = useMutation({
    mutationFn: () => api.saveStudioSpec(kind, draft),
    onSuccess: () => {
      setSelected(String(draft.name ?? ""))
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (name: string) => api.deleteStudioSpec(kind, name),
    onSuccess: () => {
      setSelected(null)
      setCode(null)
      setResult(null)
      setDraft(defaultFor(schema) as Record<string, unknown>)
      refresh()
    },
  })
  const showCode = useMutation({
    mutationFn: () => api.studioSpecCode(kind, selected as string, target),
    onSuccess: (data) => setCode(data.code),
  })
  const run = useMutation({
    mutationFn: () => api.runStudioSpec(kind, selected as string, prompt),
    onSuccess: (data) => setResult(data.result),
  })

  const load = (name: string) => {
    const record = list.data?.specs.find((entry) => entry.name === name)
    if (!record) return
    setSelected(name)
    setDraft(record.spec)
    setCode(null)
    setResult(null)
  }

  const error = list.error ?? save.error ?? remove.error ?? showCode.error ?? run.error

  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm">{kind}</CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setSelected(null)
              setDraft(defaultFor(schema) as Record<string, unknown>)
              setCode(null)
              setResult(null)
            }}
          >
            <Plus className="size-4" /> New
          </Button>
        </CardHeader>
        <CardContent className="space-y-1">
          {list.data?.specs.length ? (
            list.data.specs.map((record) => (
              <button
                key={record.name}
                onClick={() => load(record.name)}
                className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent ${
                  selected === record.name ? "bg-accent" : ""
                }`}
              >
                <span className="truncate">{record.name}</span>
                <Badge variant="secondary" className="text-[10px]">
                  v{record.version}
                </Badge>
              </button>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">No {kind} definitions yet.</p>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <ErrorAlert error={error} />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Definition</CardTitle>
          </CardHeader>
          <CardContent>
            <SchemaForm schema={schema} value={draft} onChange={(next) => setDraft(next as Record<string, unknown>)} />
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => save.mutate()} disabled={!draft.name || save.isPending}>
            <Save className="size-4" /> {selected ? "Update" : "Create"}
          </Button>
          {selected ? (
            <>
              <Button
                variant="ghost"
                onClick={() => remove.mutate(selected)}
                disabled={remove.isPending}
              >
                <Trash2 className="size-4" /> Delete
              </Button>
              <select
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                value={target}
                onChange={(event) => setTarget(event.target.value)}
              >
                <option value="python">python</option>
                <option value="yaml">yaml</option>
                <option value="json">json</option>
              </select>
              <Button
                variant="outline"
                onClick={() => showCode.mutate()}
                disabled={showCode.isPending}
              >
                <Code2 className="size-4" /> Code
              </Button>
            </>
          ) : null}
        </div>

        {selected ? (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Run</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Textarea rows={2} value={prompt} onChange={(event) => setPrompt(event.target.value)} />
              <Button onClick={() => run.mutate()} disabled={run.isPending}>
                <Play className="size-4" /> {run.isPending ? "Running…" : `Run ${kind}`}
              </Button>
            </CardContent>
          </Card>
        ) : null}

        {code ? (
          <pre className="overflow-x-auto rounded-lg border p-3 text-xs">{code}</pre>
        ) : null}
        {result !== null ? (
          <pre className="overflow-x-auto rounded-lg border p-3 text-xs">
            {JSON.stringify(result, null, 2)}
          </pre>
        ) : null}
      </div>
    </div>
  )
}
