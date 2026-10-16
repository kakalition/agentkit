import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorAlert, Loading, Page } from "@/components/page"
import { TableShell } from "@/components/table-shell"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"

const empty = {
  name: "",
  kind: "cron" as "cron" | "once",
  task: "",
  schedule: "",
  at: "",
  args: "{}",
}

export default function Scheduler() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(empty)

  const schedules = useQuery({ queryKey: ["schedules"], queryFn: api.schedules })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["schedules"] })

  const create = useMutation({
    mutationFn: () =>
      api.createSchedule({
        name: form.name,
        kind: form.kind,
        task: form.task,
        schedule: form.kind === "cron" ? form.schedule : undefined,
        at: form.kind === "once" ? form.at : undefined,
        args: form.args ? (JSON.parse(form.args) as Record<string, unknown>) : {},
      }),
    onSuccess: () => {
      setOpen(false)
      setForm(empty)
      void invalidate()
      toast.success("Schedule created")
    },
    onError: (error) => toast.error((error as Error).message),
  })
  const toggle = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.patchSchedule(name, { enabled }),
    onSuccess: () => void invalidate(),
    onError: (error) => toast.error((error as Error).message),
  })
  const remove = useMutation({
    mutationFn: (name: string) => api.deleteSchedule(name),
    onSuccess: () => {
      void invalidate()
      toast.success("Schedule deleted")
    },
    onError: (error) => toast.error((error as Error).message),
  })

  return (
    <Page
      title="Scheduler"
      description="Durable cron and one-off jobs (executed by the agent's worker)."
      actions={
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus />
              New schedule
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create schedule</DialogTitle>
              <DialogDescription>Register a cron or one-off job for a task.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </div>
              <div className="grid gap-2">
                <Label>Task</Label>
                <Select
                  value={form.task}
                  onValueChange={(value) => setForm({ ...form, task: value })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="choose a task" />
                  </SelectTrigger>
                  <SelectContent>
                    {schedules.data?.tasks.map((task) => (
                      <SelectItem key={task} value={task}>
                        {task}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label>Kind</Label>
                <Select
                  value={form.kind}
                  onValueChange={(value) => setForm({ ...form, kind: value as "cron" | "once" })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cron">cron</SelectItem>
                    <SelectItem value="once">one-off</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {form.kind === "cron" ? (
                <div className="grid gap-2">
                  <Label htmlFor="cron">Cron expression</Label>
                  <Input
                    id="cron"
                    placeholder="0 8 * * 1"
                    value={form.schedule}
                    onChange={(event) => setForm({ ...form, schedule: event.target.value })}
                  />
                </div>
              ) : (
                <div className="grid gap-2">
                  <Label htmlFor="at">Run at (ISO)</Label>
                  <Input
                    id="at"
                    placeholder="2026-11-01T09:00"
                    value={form.at}
                    onChange={(event) => setForm({ ...form, at: event.target.value })}
                  />
                </div>
              )}
              <div className="grid gap-2">
                <Label htmlFor="args">Args (JSON)</Label>
                <Textarea
                  id="args"
                  value={form.args}
                  onChange={(event) => setForm({ ...form, args: event.target.value })}
                />
              </div>
            </div>
            {create.error ? (
              <p className="text-destructive text-sm">{(create.error as Error).message}</p>
            ) : null}
            <DialogFooter>
              <Button
                onClick={() => create.mutate()}
                disabled={!form.name || !form.task || create.isPending}
              >
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      }
    >
      <ErrorAlert error={schedules.error} />
      {schedules.isLoading ? (
        <Loading />
      ) : (
        <TableShell>
          <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Schedule</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Runs</TableHead>
              <TableHead>Last run</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {schedules.data?.jobs.map((job) => (
              <TableRow key={job.name}>
                <TableCell className="font-medium">{job.name}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{job.kind}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">{job.schedule}</TableCell>
                <TableCell>{job.task}</TableCell>
                <TableCell>{job.run_count}</TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {job.last_run ?? "—"}
                </TableCell>
                <TableCell>
                  <Switch
                    checked={job.enabled}
                    onCheckedChange={(checked) =>
                      toggle.mutate({ name: job.name, enabled: checked })
                    }
                  />
                </TableCell>
                <TableCell>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label={`Delete ${job.name}`}>
                        <Trash2 />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete {job.name}?</AlertDialogTitle>
                        <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => remove.mutate(job.name)}>
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </TableCell>
              </TableRow>
            ))}
            {schedules.data?.jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-muted-foreground text-center">
                  No scheduled jobs.
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
