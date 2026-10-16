import { useQuery } from "@tanstack/react-query"

import { ErrorAlert, Loading, Page } from "@/components/page"
import { TableShell } from "@/components/table-shell"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"

function toolName(name: string): string {
  const slug = name.replace(/[^a-zA-Z0-9]/g, "_").replace(/^_+|_+$/g, "")
  return `team_${slug || "agent"}`
}

export default function Teams() {
  const teams = useQuery({ queryKey: ["teams"], queryFn: api.teams })

  return (
    <Page
      title="Teams"
      description="Registered multi-agent rosters and the tool that runs each from Chat."
    >
      <ErrorAlert error={teams.error} />

      <Card>
        <CardHeader>
          <CardTitle>Registered teams ({teams.data?.teams.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {teams.isLoading ? (
            <Loading />
          ) : (
            <TableShell>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead>Members</TableHead>
                    <TableHead>Run tool</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {teams.data?.teams.map((team) => (
                    <TableRow key={team.name}>
                      <TableCell className="font-medium">{team.name}</TableCell>
                      <TableCell>
                        <Badge variant="secondary">{team.kind}</Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {team.roster.length ? team.roster.join(", ") : "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{toolName(team.name)}</TableCell>
                    </TableRow>
                  ))}
                  {teams.data?.teams.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-muted-foreground text-center">
                        No teams registered.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableShell>
          )}
          <p className="text-muted-foreground text-sm">
            A team is runnable from Chat only when its <code>team_&lt;name&gt;</code> tool is
            registered on the agent. If a team has no matching tool above, its roster is not
            exposed to Chat.
          </p>
        </CardContent>
      </Card>
    </Page>
  )
}
