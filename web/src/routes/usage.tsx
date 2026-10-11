import { useQuery } from "@tanstack/react-query"
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts"

import { ErrorAlert, Page } from "@/components/page"
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

export default function Usage() {
  const usage = useQuery({ queryKey: ["usage"], queryFn: api.usage })
  const totals = usage.data?.totals
  const data = [...(usage.data?.recent ?? [])]
    .reverse()
    .map((row) => ({ label: row.created_at.slice(5, 16), total_tokens: row.total_tokens }))

  return (
    <Page title="Usage" description="Token accounting per turn (counts only).">
      <ErrorAlert error={usage.error} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Requests", totals?.requests],
          ["Input tokens", totals?.input_tokens],
          ["Output tokens", totals?.output_tokens],
          ["Total tokens", totals?.total_tokens],
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

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Conversation</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {usage.data?.recent.map((row) => (
              <TableRow key={row.id}>
                <TableCell className="text-muted-foreground text-sm">{row.created_at}</TableCell>
                <TableCell>{row.kind}</TableCell>
                <TableCell className="font-mono text-xs">{row.conversation_id ?? "—"}</TableCell>
                <TableCell className="text-sm">{row.model}</TableCell>
                <TableCell>{row.total_tokens}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Page>
  )
}
