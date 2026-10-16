import { useMutation } from "@tanstack/react-query"
import { Download, Trash2 } from "lucide-react"
import { useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"

export default function Data() {
  const [confirmForget, setConfirmForget] = useState(false)

  const exportData = useMutation({ mutationFn: () => api.exportData() })
  const forget = useMutation({ mutationFn: (confirm: boolean) => api.forgetData(confirm) })

  const download = async () => {
    const data = await exportData.mutateAsync()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = "agentkit-export.json"
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Page
      title="Data"
      description="Export your owner data, or (explicitly) erase it."
    >
      <ErrorAlert error={exportData.error ?? forget.error} />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Export</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-muted-foreground text-sm">
            Download everything stored for this owner as JSON (safe, read-only).
          </p>
          <Button onClick={() => void download()} disabled={exportData.isPending}>
            <Download className="size-4" /> {exportData.isPending ? "Exporting…" : "Export JSON"}
          </Button>
          {exportData.data ? (
            <ul className="text-muted-foreground text-xs">
              {Object.entries(exportData.data).map(([key, value]) => (
                <li key={key} className="flex justify-between">
                  <span>{key}</span>
                  <span className="font-mono">
                    {Array.isArray(value) ? value.length : typeof value === "object" ? "…" : String(value)}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Forget</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Alert variant="destructive">
            <AlertTitle>Destructive</AlertTitle>
            <AlertDescription>
              Forget erases the owner's stored data. It is disabled unless
              <code className="mx-1">DATA_FORGET_ENABLED=true</code>, and you must confirm.
            </AlertDescription>
          </Alert>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 rounded border"
              checked={confirmForget}
              onChange={(event) => setConfirmForget(event.target.checked)}
            />
            I understand this erases my data
          </label>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => forget.mutate(false)}
              disabled={forget.isPending}
            >
              Dry run
            </Button>
            <Button
              variant="destructive"
              onClick={() => forget.mutate(true)}
              disabled={forget.isPending || !confirmForget}
            >
              <Trash2 className="size-4" /> Forget
            </Button>
          </div>
          {forget.data ? (
            <pre className="overflow-x-auto rounded-lg border p-3 text-xs">
              {JSON.stringify(forget.data, null, 2)}
            </pre>
          ) : null}
        </CardContent>
      </Card>
    </Page>
  )
}
