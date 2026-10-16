import { useQuery } from "@tanstack/react-query"

import { ErrorAlert, Loading, Page } from "@/components/page"
import { TableShell } from "@/components/table-shell"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

export default function Audit() {
  const audit = useQuery({ queryKey: ["audit"], queryFn: api.audit })
  const verify = useQuery({ queryKey: ["audit", "verify"], queryFn: api.verifyAudit })

  return (
    <Page title="Audit" description="Append-only, hash-chained log of material actions.">
      <ErrorAlert error={audit.error ?? verify.error} />

      <Alert variant={verify.data?.ok === false ? "destructive" : "default"}>
        <AlertTitle>Hash chain {verify.data?.ok ? "verified" : "not verified"}</AlertTitle>
        <AlertDescription>
          {verify.data?.ok
            ? "Every entry links to the previous one; the log is intact."
            : "The chain does not verify — entries may have been modified."}
        </AlertDescription>
      </Alert>

      {audit.isLoading ? (
        <Loading />
      ) : (
        <TableShell>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Seq</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Target</TableHead>
                <TableHead>Actor</TableHead>
                <TableHead>Detail</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {audit.data?.entries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>{entry.seq}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{entry.action}</Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs" title={entry.target || undefined}>
                    {entry.target || "—"}
                  </TableCell>
                  <TableCell className="text-sm">{entry.actor || "—"}</TableCell>
                  <TableCell className="max-w-xs truncate font-mono text-xs">
                    {JSON.stringify(entry.detail)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">{entry.created_at}</TableCell>
                </TableRow>
              ))}
              {audit.data?.entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground text-center">
                    No audit entries.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </TableShell>
      )}
    </Page>
  )
}
