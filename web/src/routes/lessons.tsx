import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, X } from "lucide-react"
import { toast } from "sonner"

import { ErrorAlert, Page } from "@/components/page"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"

export default function Lessons() {
  const queryClient = useQueryClient()
  const proposed = useQuery({
    queryKey: ["lessons", "proposed"],
    queryFn: () => api.lessons("proposed"),
  })
  const active = useQuery({
    queryKey: ["lessons", "active"],
    queryFn: () => api.lessons("active"),
  })

  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) =>
      approve ? api.approveLesson(id) : api.rejectLesson(id),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["lessons"] })
      toast.success(variables.approve ? "Lesson approved" : "Lesson rejected")
    },
    onError: (error) => toast.error((error as Error).message),
  })

  return (
    <Page
      title="Lesson review"
      description="Approve the lessons the agent learned, or reject the ones it should forget."
    >
      <ErrorAlert error={proposed.error ?? active.error} />

      <Card>
        <CardHeader>
          <CardTitle>Proposed ({proposed.data?.lessons.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {proposed.data?.lessons.length ? (
            proposed.data.lessons.map((lesson) => (
              <div
                key={lesson.id}
                className="flex items-start justify-between gap-4 rounded-md border p-3"
              >
                <div className="space-y-1">
                  <p className="text-sm">{lesson.content}</p>
                  <span className="text-muted-foreground text-xs">#{lesson.id}</span>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: lesson.id, approve: true })}
                  >
                    <Check className="size-4" /> Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ id: lesson.id, approve: false })}
                  >
                    <X className="size-4" /> Reject
                  </Button>
                </div>
              </div>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">No lessons awaiting review.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>Active</CardTitle>
          <Badge variant="secondary">{active.data?.lessons.length ?? 0}</Badge>
        </CardHeader>
        <CardContent className="space-y-2">
          {active.data?.lessons.length ? (
            active.data.lessons.map((lesson) => (
              <p key={lesson.id} className="text-sm">
                <span className="text-muted-foreground mr-2">#{lesson.id}</span>
                {lesson.content}
              </p>
            ))
          ) : (
            <p className="text-muted-foreground text-sm">No active lessons yet.</p>
          )}
        </CardContent>
      </Card>
    </Page>
  )
}
