import { useQuery } from "@tanstack/react-query"
import { Download } from "lucide-react"

import { ErrorAlert, Page } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

function humanSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function Artifacts() {
  const artifacts = useQuery({ queryKey: ["artifacts"], queryFn: api.artifacts })

  return (
    <Page title="Artifacts" description="Files the agent produced (charts, PDFs, exports).">
      <ErrorAlert error={artifacts.error} />
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Path</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Modified</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {artifacts.data?.artifacts.map((artifact) => (
              <TableRow key={artifact.path}>
                <TableCell className="font-mono text-xs">{artifact.path}</TableCell>
                <TableCell>{humanSize(artifact.size)}</TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {artifact.modified_at}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm" asChild>
                    <a href={api.artifactUrl(artifact.path)} download>
                      <Download />
                      Download
                    </a>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {artifacts.data?.artifacts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground text-center">
                  No artifacts.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
    </Page>
  )
}
