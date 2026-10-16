import { useQuery } from "@tanstack/react-query"
import { Bar, BarChart, CartesianGrid, ReferenceLine, XAxis } from "recharts"

import { ErrorAlert, Loading, Page } from "@/components/page"
import { TableShell } from "@/components/table-shell"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

const chartConfig = {
  total_tokens: { label: "Tokens", color: "var(--chart-1)" },
} satisfies ChartConfig

const contextChartConfig = {
  context_tokens: { label: "Context", color: "var(--chart-2)" },
} satisfies ChartConfig

export default function Usage() {
  const usage = useQuery({ queryKey: ["usage"], queryFn: api.usage })
  const totals = usage.data?.totals
  const recent = [...(usage.data?.recent ?? [])].reverse()
  const data = recent.map((row) => ({
    label: row.created_at.slice(5, 16),
    total_tokens: row.total_tokens,
  }))
  const contextData = recent.map((row) => ({
    label: row.created_at.slice(5, 16),
    context_tokens: row.context_tokens,
  }))
  const contextWindow = recent.find((row) => row.context_window)?.context_window ?? null

  return (
    <Page title="Usage" description="Token accounting per turn (counts only).">
      <ErrorAlert error={usage.error} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[
          ["Requests", totals?.requests],
          ["Input tokens", totals?.input_tokens],
          ["Output tokens", totals?.output_tokens],
          ["Total tokens", totals?.total_tokens],
          ["Cache read tokens", totals?.cache_read_tokens],
          ["Context tokens", totals?.context_tokens],
        ].map(([label, value]) => (
          <Card key={label as string}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">{label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{value ?? "—"}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Tokens over time</CardTitle>
        </CardHeader>
        <CardContent>
          {data.length ? (
            <ChartContainer config={chartConfig} className="h-64 w-full">
              <BarChart data={data}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="total_tokens" fill="var(--color-total_tokens)" radius={4} />
              </BarChart>
            </ChartContainer>
          ) : (
            <p className="text-muted-foreground text-sm">No usage recorded yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Context window</CardTitle>
        </CardHeader>
        <CardContent>
          {contextData.length ? (
            <ChartContainer config={contextChartConfig} className="h-64 w-full">
              <BarChart data={contextData}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={8} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="context_tokens" fill="var(--color-context_tokens)" radius={4} />
                {contextWindow ? (
                  <ReferenceLine
                    y={contextWindow}
                    stroke="var(--muted-foreground)"
                    strokeDasharray="4 4"
                    label="context window"
                  />
                ) : null}
              </BarChart>
            </ChartContainer>
          ) : (
            <p className="text-muted-foreground text-sm">No context telemetry recorded yet.</p>
          )}
        </CardContent>
      </Card>

      {usage.isLoading ? (
        <Loading />
      ) : (
        <TableShell>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Conversation</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Context</TableHead>
                <TableHead>Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usage.data?.recent.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="text-muted-foreground text-sm">{row.created_at}</TableCell>
                  <TableCell>{row.kind}</TableCell>
                  <TableCell className="font-mono text-xs" title={row.conversation_id ?? undefined}>
                    {row.conversation_id ?? "—"}
                  </TableCell>
                  <TableCell className="text-sm">{row.model}</TableCell>
                  <TableCell>
                    {row.context_tokens}
                    {row.context_window ? ` / ${row.context_window}` : ""}
                  </TableCell>
                  <TableCell>{row.total_tokens}</TableCell>
                </TableRow>
              ))}
              {usage.data?.recent.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-muted-foreground text-center">
                    No usage recorded yet.
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
