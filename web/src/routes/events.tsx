import { Play, Square } from "lucide-react"
import { useRef, useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"

type Tick = { at: string; snapshot: Record<string, unknown> }

export default function Events() {
  const [running, setRunning] = useState(false)
  const [ticks, setTicks] = useState<Tick[]>([])
  const [error, setError] = useState<Error | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const start = async () => {
    const controller = new AbortController()
    abortRef.current = controller
    setRunning(true)
    setError(null)
    try {
      await api.events(
        (snapshot) =>
          setTicks((current) =>
            [{ at: new Date().toLocaleTimeString(), snapshot }, ...current].slice(0, 50),
          ),
        controller.signal,
      )
    } catch (err) {
      if (!controller.signal.aborted) setError(err as Error)
    } finally {
      setRunning(false)
      abortRef.current = null
    }
  }

  const stop = () => {
    abortRef.current?.abort()
    setRunning(false)
  }

  return (
    <Page
      title="Events"
      description="Live lifecycle snapshot stream (GET /api/events, polled every 5s)."
    >
      <ErrorAlert error={error} />
      <div className="flex gap-2">
        <Button onClick={() => void start()} disabled={running}>
          <Play className="size-4" /> {running ? "Streaming…" : "Start stream"}
        </Button>
        <Button variant="outline" onClick={stop} disabled={!running}>
          <Square className="size-4" /> Stop
        </Button>
        <Button variant="ghost" onClick={() => setTicks([])} disabled={!ticks.length}>
          Clear
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Snapshots ({ticks.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {ticks.length ? (
            ticks.map((tick, index) => (
              <div key={index} className="flex items-start gap-2 rounded-md border p-2 text-sm">
                <Badge variant="secondary" className="text-[10px]">
                  {tick.at}
                </Badge>
                <pre className="min-w-0 flex-1 overflow-x-auto text-xs">
                  {JSON.stringify(tick.snapshot)}
                </pre>
              </div>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">
              {running ? "Waiting for the first tick…" : "Start the stream to see live snapshots."}
            </p>
          )}
        </CardContent>
      </Card>
    </Page>
  )
}
