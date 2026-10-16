import { useQuery } from "@tanstack/react-query"

import { ErrorAlert, Loading, Page } from "@/components/page"
import { TableShell } from "@/components/table-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

function render(value: unknown) {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

export default function Config() {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config })
  const entries = Object.entries(config.data?.config ?? {})

  return (
    <Page title="Config" description="Resolved settings — secrets are masked on read.">
      <ErrorAlert error={config.error} />
      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
        </CardHeader>
        <CardContent>
          {config.isLoading ? (
            <Loading />
          ) : (
            <TableShell>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Key</TableHead>
                    <TableHead>Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map(([key, value]) => (
                    <TableRow key={key}>
                      <TableCell className="font-mono text-xs">{key}</TableCell>
                      <TableCell className="font-mono text-xs">{render(value)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableShell>
          )}
        </CardContent>
      </Card>
    </Page>
  )
}
