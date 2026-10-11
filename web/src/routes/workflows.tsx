import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MoreHorizontal } from "lucide-react"
import { useState } from "react"

import { ErrorAlert, Page } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import type { Workflow } from "@/lib/api"

function statusVariant(status: string | null) {
  if (status === "SUCCESS") return "default"
  if (status === "ERROR" || status === "MAX_RECOVERY_ATTEMPTS_EXCEEDED") return "destructive"
  return "secondary"
}

function WorkflowTable({
  workflows,
  onSelect,
  onAction,
}: {
  workflows: Workflow[]
  onSelect: (id: string) => void
  onAction: (action: "cancel" | "resume", id: string) => void
}) {
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Id</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Queue</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {workflows.map((workflow) => (
            <TableRow key={workflow.id}>
              <TableCell className="font-mono text-xs" onClick={() => onSelect(workflow.id)}>
                {workflow.id.slice(0, 16)}
              </TableCell>
              <TableCell>{workflow.name ?? "—"}</TableCell>
              <TableCell>
                <Badge variant={statusVariant(workflow.status)}>{workflow.status ?? "—"}</Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">{workflow.queue ?? "—"}</TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onSelect(workflow.id)}>Details</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onAction("cancel", workflow.id)}>
                      Cancel
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onAction("resume", workflow.id)}>
                      Resume
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
          {workflows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-muted-foreground text-center">
                No workflows.
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
      </Table>
    </div>
  )
}

export default function Workflows() {
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string | null>(null)
  const list = useQuery({ queryKey: ["workflows"], queryFn: () => api.workflows() })
  const failed = useQuery({ queryKey: ["workflows", "failed"], queryFn: api.failedWorkflows })
  const detail = useQuery({
    queryKey: ["workflow", selected],
    queryFn: () => api.workflow(selected as string),
    enabled: selected !== null,
  })
  const action = useMutation({
    mutationFn: async ({ kind, id }: { kind: "cancel" | "resume"; id: string }) => {
      if (kind === "cancel") await api.cancelWorkflow(id)
      else await api.resumeWorkflow(id)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workflows"] }),
  })

  const onAction = (kind: "cancel" | "resume", id: string) => action.mutate({ kind, id })

  return (
    <Page title="Workflows" description="Durable execution (DBOS), read via a standalone client.">
      <ErrorAlert error={list.error ?? failed.error} />
      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="failed">Failed</TabsTrigger>
        </TabsList>
        <TabsContent value="all" className="mt-4">
          {list.data?.error ? (
            <p className="text-muted-foreground text-sm">{list.data.error}</p>
          ) : null}
          <WorkflowTable
            workflows={list.data?.workflows ?? []}
            onSelect={setSelected}
            onAction={onAction}
          />
        </TabsContent>
        <TabsContent value="failed" className="mt-4">
          <WorkflowTable
            workflows={failed.data?.workflows ?? []}
            onSelect={setSelected}
            onAction={onAction}
          />
        </TabsContent>
      </Tabs>

      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="w-full sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Workflow {selected?.slice(0, 16)}</SheetTitle>
          </SheetHeader>
          <ScrollArea className="mt-4 h-[70vh] pr-2">
            <pre className="overflow-x-auto text-xs whitespace-pre-wrap">
              {JSON.stringify(detail.data ?? {}, null, 2)}
            </pre>
          </ScrollArea>
        </SheetContent>
      </Sheet>
    </Page>
  )
}
