import { useQuery } from "@tanstack/react-query"
import { Activity, BarChart3, CalendarClock, MessagesSquare, Workflow } from "lucide-react"

import { ErrorAlert, Page } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"

function StatCard({
  title,
  value,
  icon: Icon,
}: {
  title: string
  value: string | number
  icon: typeof Activity
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="text-muted-foreground size-4" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="truncate font-medium">{value}</span>
    </div>
  )
}

export default function Overview() {
  const info = useQuery({ queryKey: ["info"], queryFn: api.info })
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000 })
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.conversations })
  const schedules = useQuery({ queryKey: ["schedules"], queryFn: api.schedules })
  const workflows = useQuery({ queryKey: ["workflows"], queryFn: () => api.workflows() })
  const usage = useQuery({ queryKey: ["usage"], queryFn: api.usage })

  const enabledSchedules = schedules.data?.jobs.filter((job) => job.enabled).length ?? 0
  const activeWorkflows =
    workflows.data?.workflows.filter((wf) =>
      ["ENQUEUED", "PENDING", "DELAYED"].includes(wf.status ?? ""),
    ).length ?? 0

  return (
    <Page title="Overview" description="A snapshot of the hosting agent.">
      <ErrorAlert error={info.error ?? health.error} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Conversations"
          value={conversations.data?.conversations.length ?? "—"}
          icon={MessagesSquare}
        />
        <StatCard title="Schedules (on)" value={enabledSchedules} icon={CalendarClock} />
        <StatCard title="Workflows (active)" value={activeWorkflows} icon={Workflow} />
        <StatCard
          title="Tokens (total)"
          value={usage.data?.totals.total_tokens ?? "—"}
          icon={BarChart3}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Agent</CardTitle>
          </CardHeader>
          <CardContent className="divide-y">
            <Row label="Name" value={info.data?.name ?? "—"} />
            <Row label="Version" value={info.data?.version ?? "—"} />
            <Row label="Model" value={info.data?.model_name ?? "—"} />
            <Row label="Home" value={info.data?.home ?? "—"} />
            <Row label="Web UI" value={info.data?.webui.url ?? "—"} />
            <Row label="Chat" value={info.data?.chat_enabled ? "enabled" : "unavailable"} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle>Health</CardTitle>
            <Badge variant={health.data?.ok ? "default" : "destructive"}>
              {health.isLoading ? "checking" : health.data?.ok ? "healthy" : "degraded"}
            </Badge>
          </CardHeader>
          <CardContent className="divide-y">
            {health.data
              ? Object.entries(health.data.checks).map(([name, ok]) => (
                  <Row key={name} label={name} value={ok ? "ok" : "failing"} />
                ))
              : null}
            <Separator />
            <Row label="Telegram" value={info.data?.channels.telegram ? "configured" : "off"} />
            <Row
              label="A2A"
              value={info.data ? `${info.data.channels.a2a.host}:${info.data.channels.a2a.port}` : "—"}
            />
            <Row
              label="MCP"
              value={info.data ? `${info.data.channels.mcp.host}:${info.data.channels.mcp.port}` : "—"}
            />
          </CardContent>
        </Card>
      </div>
    </Page>
  )
}
