import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

export default function A2A() {
  const [selected, setSelected] = useState<string | null>(null)
  const tasks = useQuery({ queryKey: ["a2a"], queryFn: api.a2a })
  const detail = useQuery({
    queryKey: ["a2a", selected],
    queryFn: () => api.a2aTask(selected as string),
    enabled: selected !== null,
  })

  return (
    <Page title="A2A tasks" description="Durable inbound agent-to-agent tasks.">
      <ErrorAlert error={tasks.error} />
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Id</TableHead>
              <TableHead>Context</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tasks.data?.tasks.map((task) => (
              <TableRow
                key={task.id}
                className="cursor-pointer"
                onClick={() => setSelected(task.id)}
              >
                <TableCell className="font-mono text-xs">{task.id}</TableCell>
                <TableCell className="font-mono text-xs">{task.context_id ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{task.state}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">{task.updated_at}</TableCell>
              </TableRow>
            ))}
            {tasks.data?.tasks.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground text-center">
                  No A2A tasks.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Task {selected}</SheetTitle>
          </SheetHeader>
          <ScrollArea className="mt-4 h-[70vh] pr-2">
            <pre className="overflow-x-auto text-xs whitespace-pre-wrap">
              {JSON.stringify(detail.data?.payload ?? {}, null, 2)}
            </pre>
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </Page>
  )
}
